#!/usr/bin/env python3
"""Daily reference-intake runner (Mac launchd schedule, CP-D step 1).

2026-09-14 redesign (CEO directive):
  - ONE fixed folder: assets/reference_intake/inbox (no per-ISO-week subfolders).
  - Runs DAILY at 02:00. Before fetching, leftovers older than the review window
    (18 h) that were NOT moved by the CEO to VEO_download/Approved_material are
    deleted: "其餘的素材在第二天就全部刪除".
  - Cross-day duplicates are suppressed by the seen-assets registry
    (reference_intake/_state/seen_assets.json), which stock_search.py maintains.
  - The world-proposal engine is PAUSED (pending redesign around Approved_material).
  - The inbox (and the CEO folders generally) is CEO-mutable: files/folders may be
    uploaded or deleted at any moment. All enumeration/stat/write paths tolerate
    items vanishing mid-run; a deleted inbox is recreated by stock_search.py; the
    purge age uses max(mtime, birthtime, ctime) so freshly uploaded files are kept
    even when their copied timestamps are old.
Usage (Mac):
  /Volumes/AI_Workspace/AI_Drama_Factory/.venv/bin/python3 scripts/reference_intake/daily_intake.py
  ... daily_intake.py --dry-run          # plan print only; no network, no purge
  ... daily_intake.py --force            # bypass the "already fetched today" guard
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
INTAKE_ROOT = Path(
    os.environ.get(
        "REFERENCE_INTAKE_ROOT",
        "/Volumes/AI_Workspace/AI_Drama_Factory/assets/reference_intake/inbox",
    )
)
TELEGRAM_SENDER = WORKSPACE / "scripts" / "telegram" / "telegram_text_send.py"
SEARCH = WORKSPACE / "scripts" / "reference_intake" / "stock_search.py"
ENV_FILES = (
    # Mac convention: per-service secret files live outside the repo (chmod 600).
    Path.home() / "Library/Application Support/AI_Drama_Factory/reference_intake.env",
)
PURGE_MIN_AGE_HOURS = 18  # review window; the next 02:00 run deletes the rest
APPROVED_HINT = "把要用的圖移至 CEO/02_素材與CP-D/VEO_download/Approved_material（PC: F:）"


def load_env_files() -> None:
    """Load KEY=VALUE secrets (stock API keys) that the scheduled job needs."""
    for path in ENV_FILES:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_manifest() -> dict:
    """Current fixed-folder manifest, or an empty dict when absent/corrupt."""
    path = INTAKE_ROOT / "manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def notify(text: str) -> None:
    """Best-effort Telegram notification via the shared Mac sender."""
    if not TELEGRAM_SENDER.is_file():
        print(f"[warn] telegram sender missing: {TELEGRAM_SENDER}", flush=True)
        return
    env = dict(os.environ)
    env.setdefault(
        "TELEGRAM_ENV_FILE",
        str(Path.home() / "Library/Application Support/AI_Drama_Factory/telegram_queue_notify.env"),
    )
    code = subprocess.call([sys.executable, str(TELEGRAM_SENDER), text], env=env)
    if code != 0:
        print(f"[warn] telegram send failed rc={code}", flush=True)


def purge_old_files(dry_run: bool) -> int:
    """Delete leftovers older than the review window (CEO rule: next-day cleanup).

    Tolerates the CEO moving/deleting items concurrently; the age reference is
    max(mtime, birthtime, ctime) so freshly copied files with old timestamps are
    never purged. Empty subfolders left behind are removed afterwards.
    """
    cutoff = time.time() - PURGE_MIN_AGE_HOURS * 3600
    removed = 0
    if not INTAKE_ROOT.is_dir():
        return 0  # CEO deleted the folder; stock_search.py recreates it
    try:
        items = sorted(INTAKE_ROOT.rglob("*"))
    except OSError:
        return 0
    for item in items:
        try:
            if not item.is_file():
                continue
            stat = item.stat()
        except OSError:
            continue  # vanished mid-run (CEO moving files)
        age_ref = max(stat.st_mtime, getattr(stat, "st_birthtime", 0.0), stat.st_ctime)
        if age_ref >= cutoff:
            continue
        if dry_run:
            print(f"[purge] would delete {item.relative_to(INTAKE_ROOT)}", flush=True)
            removed += 1
            continue
        try:
            item.unlink()
        except OSError as exc:
            print(f"[purge] skip {item.name}: {exc}", flush=True)
            continue
        print(f"[purge] deleted {item.relative_to(INTAKE_ROOT)}", flush=True)
        removed += 1
    if not dry_run:
        for folder in sorted(INTAKE_ROOT.rglob("*"), reverse=True):
            try:
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
                    print(f"[purge] removed empty dir {folder.relative_to(INTAKE_ROOT)}", flush=True)
            except OSError:
                continue
    return removed


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def safe_list_images() -> tuple[int, list[str]]:
    """Count current inbox images without crashing when the CEO deletes things."""
    if not INTAKE_ROOT.is_dir():
        return 0, []
    names: list[str] = []
    try:
        for item in INTAKE_ROOT.iterdir():
            if item.is_file() and item.suffix.lower() in IMAGE_EXTS:
                names.append(item.name)
    except OSError:
        pass
    return len(names), names


def summarize(manifest: dict) -> str:
    """Human-readable one-message summary for the CEO (counts live files now)."""
    present, _ = safe_list_images()
    failures = manifest.get("failures") or []
    lines = [f"[素材] 每日搜尋完成；inbox 現有 {present} 張待審"]
    if failures:
        lines.append("失敗查詢：" + "; ".join(failures))
    lines.append("路徑：assets/reference_intake/inbox（Y:）")
    lines.append(f"下一步：{APPROVED_HINT}")
    lines.append("未移出的素材將於明日 02:00 自動清除。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="plan print only; no network, no purge")
    parser.add_argument("--force", action="store_true", help="run even if today's batch exists")
    parser.add_argument("--with-proposal", action="store_true", help="reserved; proposal engine is paused")
    args = parser.parse_args(argv)

    load_env_files()
    removed = purge_old_files(args.dry_run)
    print(f"[intake] purge removed={removed} (dry_run={args.dry_run})", flush=True)

    manifest = load_manifest()
    if manifest.get("run_date") == date.today().isoformat() and not args.force:
        print("[intake] today's batch already fetched; skipping (use --force)", flush=True)
        return 0

    cmd = [sys.executable, str(SEARCH)]
    if args.dry_run:
        cmd.append("--dry-run")
    code = subprocess.call(cmd)
    if code != 0:
        notify(
            "[素材] 每日搜尋失敗：請檢查網路與圖庫 API 狀態"
            "（Pexels 若 403／1010＝Cloudflare 封非瀏覽器 UA、非金鑰失效；"
            "可用 rca_pexels.py 診斷）；詳見 ~/Library/Logs/AI_Drama_Factory/reference_intake.err.log"
        )
        print(f"[intake] stock search failed rc={code}", file=sys.stderr, flush=True)
        return code or 1

    manifest = load_manifest()
    failures = manifest.get("failures") or []
    present, _ = safe_list_images()
    if not args.dry_run and (failures or present):
        notify(summarize(manifest))
        print(f"[intake] notified: inbox={present} failures={len(failures)}", flush=True)
    else:
        print(f"[intake] no-notify (dry_run={args.dry_run}) inbox={present} failures={len(failures)}", flush=True)
    if args.with_proposal:
        print("[intake] proposal engine paused (2026-09-14 redesign); flag reserved", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
