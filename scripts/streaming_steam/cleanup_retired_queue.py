#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理 queue/ 內「不在 live_manifest.json」且檔齡超過門檻的 mp4，
安全移入 frozen_broadcast/。可搭配 launchd/cron 定時執行。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _safe_basename(name: str) -> str:
    base = Path(name).name
    if base != name or "/" in name or "\\" in name or not base.strip():
        _die(f"❌ manifest 含非法 file 名稱：{name!r}")
    return base


def _unique_frozen_path(frozen_dir: Path, old_base: str) -> Path:
    stem = Path(old_base).stem
    suf = Path(old_base).suffix or ".mp4"
    dest = frozen_dir / old_base
    if not dest.exists():
        return dest
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return frozen_dir / f"{stem}_retired_{ts}{suf}"


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        _die(f"❌ 找不到 manifest：{path}")
    except json.JSONDecodeError as e:
        _die(f"❌ JSON 解析失敗：{path}\n   {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Move retired queue mp4 (not referenced by manifest) into frozen_broadcast")
    ap.add_argument("--streaming-root", "--steam-root", type=Path, dest="streaming_root", required=True)
    ap.add_argument("--manifest", type=Path, default=None, help="預設：Streaming/config/live_manifest.json")
    ap.add_argument("--min-age-hours", type=float, default=24.0, help="最小檔齡（小時），預設 24")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = args.streaming_root.resolve()
    manifest_path = (args.manifest or (root / "config" / "live_manifest.json")).resolve()
    queue = root / "queue"
    frozen = root / "frozen_broadcast"
    frozen.mkdir(parents=True, exist_ok=True)

    if not queue.is_dir():
        _die(f"❌ 找不到 queue 目錄：{queue}")

    data = load_manifest(manifest_path)
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        _die("❌ manifest.entries 必須為非空陣列")

    keep = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            _die(f"❌ entries[{i}] 必須為物件")
        file_name = e.get("file")
        if not isinstance(file_name, str):
            _die(f"❌ entries[{i}].file 必須為字串")
        keep.add(_safe_basename(file_name))

    now = datetime.now(timezone.utc).timestamp()
    min_age_sec = max(0.0, args.min_age_hours) * 3600.0
    moved = 0
    skipped = 0
    for p in sorted(queue.glob("*.mp4")):
        if p.name in keep:
            skipped += 1
            continue
        age_sec = now - p.stat().st_mtime
        if age_sec < min_age_sec:
            print(f"ℹ️  skip（檔齡不足）: {p.name} age={age_sec/3600:.2f}h")
            skipped += 1
            continue
        dest = _unique_frozen_path(frozen, p.name)
        if args.dry_run:
            print(f"DRY-RUN move: {p} -> {dest}")
        else:
            shutil.move(str(p), str(dest))
            print(f"✅ moved: {p.name} -> {dest.name}")
        moved += 1

    print(f"完成：moved={moved}, skipped={skipped}, dry_run={args.dry_run}")


if __name__ == "__main__":
    main()

