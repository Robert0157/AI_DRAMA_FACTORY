"""CEO console: mirror review-ready artifacts into the workspace CEO/ folder.

CEO 2026-09-12 directive: every artifact a human (CEO) must read or review
lives under <WORKSPACE_ROOT>/CEO/ with a generated README.md index. This tool
only COPIES review payloads - pipeline originals (Y: share) stay authoritative.

Subfolders:
  01_劇本鑄造/<series>/   forge progress summary, iteration_log.md, latest iter, lock_ready
  02_素材與CP-D/<week>/    review.html, contact sheets, proposal.md, veo_prompts.txt, intake images
  03_樣片與交付/            sample list (pass / duration / output path)

Usage:
  python scripts/common/ceo_console.py --sync
  python scripts/common/ceo_console.py --sync --forge-series timegate-56 --week 2026-W37
Env overrides (tests):  CEO_CONSOLE_ROOT, CEO_SOURCE_ROOT
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _ceo_root() -> Path:
    """CEO console folder (workspace-root/CEO unless overridden)."""
    return Path(os.environ.get("CEO_CONSOLE_ROOT") or (ROOT / "CEO"))


def _share_root() -> Path:
    """Pipeline share (Y: on the PC, fallback to the workspace copy)."""
    env = os.environ.get("CEO_SOURCE_ROOT")
    if env:
        return Path(env)
    share = Path("Y:/AI_Drama_Factory")
    return share if share.exists() else ROOT


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sync_forge(series: str) -> dict:
    """Copy the forge run's review payload and write a progress summary."""
    src = _share_root() / "Auto_Drama" / "output" / "script_forge" / series
    dst = _ceo_root() / "01_劇本鑄造" / series
    if not src.is_dir():
        return {"forge": "missing", "path": str(src)}
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("iteration_log.md", "run_meta.json", "lock_ready.json", "state_latest.json"):
        p = src / name
        if p.is_file():
            shutil.copy2(p, dst / name)
    iters = sorted(src.glob("iter_*.json"))
    if iters:
        shutil.copy2(iters[-1], dst / iters[-1].name)
    meta: dict = {}
    if (src / "run_meta.json").is_file():
        meta = json.loads((src / "run_meta.json").read_text(encoding="utf-8"))
    last: dict = json.loads(iters[-1].read_text(encoding="utf-8")) if iters else {}
    final = last.get("final") or {}
    lines = [
        f"# 劇本鑄造進度 — {series}",
        "",
        f"- 狀態：**{meta.get('status', '?')}**",
        f"- 迭代次數：{meta.get('iterations', 0)}（CEO 下限 {meta.get('min_iters', 15)}；上限 {meta.get('max_iters', '?')}）",
        f"- 最新總分：{final.get('final_total', '—')}（最低域 {final.get('min_domain', '—')}）",
        f"- 八域：{json.dumps(final.get('domains') or {}, ensure_ascii=False)}",
        "- 閘門：迭代 ≥15 ∧ 總分 ≥8.8 ∧ 單域 ≥8.0 ∧ 零 error → `lock_ready.json`（CP-D 入場證）",
        "- 完整迭代表：`iteration_log.md`（逐迭代八域分數與動作）",
        f"- 最後同步：{_now()}",
        "",
    ]
    (dst / "進度摘要.md").write_text("\n".join(lines), encoding="utf-8")
    return {"forge": "synced", "iterations": meta.get("iterations"), "status": meta.get("status")}


def sync_cp_d(week: str) -> dict:
    """Make the CP-D review pack self-contained inside the CEO folder."""
    share = _share_root()
    src = share / "assets" / "reference_intake" / "cp_d" / week
    inbox = share / "assets" / "reference_intake" / "inbox" / week
    dst = _ceo_root() / "02_素材與CP-D" / week
    if not src.is_dir():
        return {"cp_d": "missing", "path": str(src)}
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("review.html", "proposal.md", "proposal.json", "veo_prompts.txt"):
        p = src / name
        if p.is_file():
            shutil.copy2(p, dst / name)
    for p in src.glob("sheet_*.jpg"):
        shutil.copy2(p, dst / p.name)
    if inbox.is_dir():
        for p in inbox.glob("*.jpg"):
            shutil.copy2(p, dst / p.name)  # keeps review.html images self-contained
        if (inbox / "manifest.json").is_file():
            shutil.copy2(inbox / "manifest.json", dst / "manifest.json")
    return {"cp_d": "synced", "week": week}


def sync_samples() -> dict:
    """Write a compact sample list from the handoff done queue."""
    handoff = _share_root() / "Auto_Drama" / "output" / "handoff" / "done"
    dst = _ceo_root() / "03_樣片與交付"
    dst.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    if handoff.is_dir():
        for d in sorted(handoff.iterdir()):
            st = d / "status.json"
            if st.is_file():
                data = json.loads(st.read_text(encoding="utf-8"))
                rows.append(
                    f"- `{d.name}` → pass={data.get('pass')}｜{data.get('duration_sec')}s"
                    f"｜{data.get('size')}｜{data.get('output')}"
                )
    (dst / "樣片清單.md").write_text(
        "# 樣片清單（handoff/done）\n\n" + ("\n".join(rows) or "（尚無）")
        + f"\n\n> 最後同步：{_now()}\n",
        encoding="utf-8",
    )
    return {"samples": len(rows)}


def write_index() -> Path:
    """Regenerate the CEO/README.md navigation index."""
    root = _ceo_root()
    root.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CEO 控台（自動生成索引）",
        "",
        f"> 最後更新：{_now()}｜由 `scripts/common/ceo_console.py --sync` 產生",
        "",
        "所有提供 CEO 理解／審核的資訊一律放在本資料夾；產線原件為單一真理（不在此改動）。",
        "",
    ]
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        lines.append(f"## {sub.name}")
        for f in sorted(sub.rglob("*")):
            if f.is_file():
                lines.append(f"- `{f.relative_to(root)}`")
        lines.append("")
    (root / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return root / "README.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="mirror artifacts and rebuild the index")
    parser.add_argument("--forge-series", default="timegate-56")
    parser.add_argument("--week", default="2026-W37")
    args = parser.parse_args(argv)
    if not args.sync:
        parser.print_help()
        return 0
    out = {**sync_forge(args.forge_series), **sync_cp_d(args.week), **sync_samples()}
    idx = write_index()
    print(json.dumps(out, ensure_ascii=False))
    print(f"INDEX {idx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
