"""CEO console: mirror review-ready artifacts into the workspace CEO/ folder.

CEO 2026-09-12 directive: every artifact a human (CEO) must read or review
lives under <WORKSPACE_ROOT>/CEO/ with a generated README.md index. This tool
only COPIES review payloads - pipeline originals (Y: share) stay authoritative.

Subfolders:
  01_劇本鑄造/<series>/   forge progress summary, iteration_log.md, 劇本小說版.md (novel; no JSON)
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
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, "") and str(ROOT) not in sys.path:  # direct run: enable scripts.* imports
    sys.path.insert(0, str(ROOT))


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
    """Copy the forge run's review payload and write a progress summary.

    CEO 2026-09-12 reminder: the review folder carries NO machine JSON. The
    script is mirrored as a human-readable novel (劇本小說版.md); the
    LocalMiniDrama storyboard JSON stays pipeline-side (Y: share).
    """
    src = _share_root() / "Auto_Drama" / "output" / "script_forge" / series
    dst = _ceo_root() / "01_劇本鑄造" / series
    if not src.is_dir():
        return {"forge": "missing", "path": str(src)}
    dst.mkdir(parents=True, exist_ok=True)
    for stale in dst.glob("*.json"):  # purge leftovers from the old JSON-mirror era
        stale.unlink()
    log = src / "iteration_log.md"
    if log.is_file():
        shutil.copy2(log, dst / "iteration_log.md")
    meta: dict = {}
    if (src / "run_meta.json").is_file():
        meta = json.loads((src / "run_meta.json").read_text(encoding="utf-8"))
    iters = sorted(src.glob("iter_*.json"))
    last: dict = json.loads(iters[-1].read_text(encoding="utf-8")) if iters else {}
    final = last.get("final") or {}
    novel_line = "- 劇本小說版：`劇本小說版.md`（人類小說體供審核）"
    novel_state = "skipped"
    try:
        from scripts.story_room import script_novel  # lazy: keeps this tool dependency-free
        if (src / "best_package.json").is_file():
            md, stats = script_novel.render_run(src, series)
            (dst / "劇本小說版.md").write_text(md, encoding="utf-8")
            novel_state = "synced"
            total = stats.get("episodes", 0)
            done = stats.get("llm", 0) + stats.get("stale", 0)  # stale still counts as novelized
            if total and done >= total:
                novel_line = f"- 劇本小說版：`劇本小說版.md`（人類小說體；{done}/{total} 集全部已小說化）"
            else:
                novel_line = (
                    f"- 劇本小說版：`劇本小說版.md`（人類小說體；"
                    f"{done}/{total} 集已小說化，其餘為大綱體）"
                )
    except Exception as exc:  # noqa: BLE001 - ZERO SILENT FAILURES: surface the reason
        print(f"[warn] novel render failed: {exc}", file=sys.stderr, flush=True)
        novel_state = f"failed: {exc}"
    gate_line = "- 閘門：迭代 ≥15 ∧ 總分 ≥8.8 ∧ 單域 ≥8.0 ∧ 零 error → `lock_ready.json`（CP-D 入場證）"
    if (src / "lock_ready.json").is_file():
        gate_line = "- **✅ 已達好萊塢門檻（lock_ready 已核發；CP-D 入場證就緒）**"
    champion_lines: list[str] = []
    bm_path = src / "best_meta.json"
    if bm_path.is_file():
        try:
            bm = json.loads(bm_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            bm = {}
        c_score = bm.get("score")
        if c_score is not None:
            c_iter = bm.get("iteration", "—")
            c_domains = bm.get("domains") or {}
            c_min = min(c_domains.values()) if c_domains else None
            line = (f"- 王者（★）第 {c_iter} 迭代：μ **{c_score}**；八域 "
                    f"{json.dumps(c_domains, ensure_ascii=False)}")
            if c_min is not None:
                line += f"（最低域 {c_min}）"
            c_errors = sum(1 for f in (bm.get("findings") or []) if f.get("level") == "error")
            line += "；errors 0 ✓" if c_errors == 0 else f"；errors {c_errors}"
            champion_lines.append(line)
            try:
                need = round(8.8 - float(c_score), 2)
            except (TypeError, ValueError):
                need = None
            if need is not None:
                parts = [f"μ 還需 +{need}" if need > 0 else "μ 已達標 ✓"]
                if c_min is not None:
                    need_min = round(8.0 - float(c_min), 2)
                    parts.append(f"最低域還需 +{need_min}" if need_min > 0 else "最低域已達標 ✓")
                champion_lines.append("- 距閘門：" + "；".join(parts))
    lines = [
        f"# 劇本鑄造進度 — {series}",
        "",
        f"- 狀態：**{meta.get('status', '?')}**",
        f"- 迭代次數：{meta.get('iterations', 0)}（CEO 下限 {meta.get('min_iters', 15)}；上限 {meta.get('max_iters', '?')}）",
        *champion_lines,
        f"- 最新一輪（#{meta.get('iterations', 0)}）：淨分 {final.get('final_total', '—')}（懲罰後稽核值；王者以 μ 比較）",
        novel_line,
        gate_line,
        "- 完整迭代表：`iteration_log.md`（★＝王者、⚠＝評審異常輪）",
        "- 審核格式：劇本一律小說體（人類閱讀）；LocalMiniDrama 分鏡 JSON 為產線機器格式，不上桌",
        f"- 最後同步：{_now()}",
        "",
    ]
    (dst / "進度摘要.md").write_text("\n".join(lines), encoding="utf-8")
    return {"forge": "synced", "iterations": meta.get("iterations"),
            "status": meta.get("status"), "novel": novel_state}


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
        "命名規則：`CEO/00_命名規則.md`（v1，權威）——新增／改名一律遵循。",
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
