#!/usr/bin/env python3
"""B-line script novel renderer: pipeline JSON -> human novel format for CEO review.

CEO 2026-09-12 reminder: review copies of the script MUST be presented as a
human novel (prose). The LocalMiniDrama storyboard JSON is the machine format
of the pipeline only and must never be the CEO-facing deliverable.

Two quality tiers:
  * deterministic - assembles cover/synopsis/cast/world/arcs/episodes from the
    validated package fields (always available, $0)
  * LLM novelized - one DeepSeek call per episode turns the outline (and any
    written teleplay excerpt) into novel prose; results are cached under
    <run>/novel/ep_NN.md keyed by a source hash, so re-exports are free. A
    source change never downgrades the doc to outline fallback: the previous
    novelized text is kept until the next --llm run realigns it.

Usage:
  python scripts/story_room/script_novel.py --series-id timegate-56 --llm
  python scripts/story_room/script_novel.py --series-id timegate-56   # cache-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, "") and str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The writer prompt enforces: prose only, no shot language, keep all dialogue.
_NOVEL_SYS = (
    "你是華語小說家，負責把短劇的劇本與分集大綱改寫成小說體正文。\n"
    "規則：\n"
    "1. 第三人稱、現代中文小說文體；只輸出正文段落，不要標題、不要編號、不要任何說明。\n"
    "2. 嚴禁出現製作術語與鏡頭指令（COLD OPEN、機位、秒數、長鏡、480p、分鏡、轉場等）。\n"
    "3. 保留輸入劇本節錄中的全部台詞與關鍵事件；可理順語序、補寫場景與人物心理。\n"
    "4. 不得新增或刪除劇情事實，不得自創角色姓名。\n"
    "5. 有劇本節錄時 300–600 字；僅有大綱時 200–350 字。"
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _cn_number(n: int) -> str:
    """Chinese numeral for 1..99 (chapters read better as 第一集 than 第1集)."""
    digits = "零一二三四五六七八九"
    if n <= 0:
        return str(n)
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n - 10] if n > 10 else "")
    tens, ones = divmod(n, 10)
    return digits[tens] + "十" + (digits[ones] if ones else "")


def _ep_excerpt(package: dict, ep: int) -> str:
    """Teleplay excerpt for an episode (pilot dict), empty when not written yet."""
    pilot = package.get("pilot") or {}
    entry = pilot.get(f"ep{ep}")
    if isinstance(entry, dict):
        text = entry.get("script_excerpt")
        if text:
            return str(text).strip()
    return ""


def _src_hash(package: dict, row: dict, excerpt: str) -> str:
    """Cache key: episode fields + excerpt text (changes invalidate the cache)."""
    h = hashlib.sha256()
    h.update(json.dumps(
        [row.get("title"), row.get("summary"), row.get("hook"), row.get("cliffhanger")],
        ensure_ascii=False,
    ).encode("utf-8"))
    h.update(excerpt.encode("utf-8"))
    return h.hexdigest()[:12]


def _fallback_passage(package: dict, row: dict) -> str:
    """Deterministic outline-to-prose weave used when no LLM text exists yet."""
    summary = str(row.get("summary") or "").strip("。 ")
    hook = str(row.get("hook") or "").strip("。 ")
    cliff = str(row.get("cliffhanger") or "").strip("。 ")
    parts: list[str] = []
    if summary:
        parts.append(f"{summary}。")
    if hook:
        parts.append(f"真正把觀眾推向下一集的，是那個懸念——{hook}。")
    if cliff:
        parts.append(f"這一集收在：{cliff}。")
    return "".join(parts) or f"第{row.get('ep')}集《{row.get('title', '')}》。"


def novelize_episode(package: dict, row: dict, excerpt: str = "",
                     model: str | None = None, timeout: float = 200.0) -> str:
    """One LLM call: teleplay/outline -> novel prose for a single episode."""
    from scripts.story_room import llm_text

    bible = package.get("bible") or {}
    cast = "、".join(
        str(p.get("name")) for p in (bible.get("protagonists") or [])
        if isinstance(p, dict) and p.get("name")
    )[:120]
    rules = ((bible.get("canon") or {}).get("rules") or [])
    world = "；".join(str(r) for r in rules[:3])[:220]

    lines = [
        f"【劇集】第{row.get('ep')}集《{row.get('title', '')}》（弧{row.get('arc', '?')}）",
        f"【大綱】{row.get('summary', '')}",
        f"【鉤子】{row.get('hook', '')}",
        f"【收束】{row.get('cliffhanger', '')}",
    ]
    if cast:
        lines.append(f"【主要人物】{cast}")
    if world:
        lines.append(f"【世界觀要點】{world}")
    if excerpt:
        lines += ["【劇本節錄（實拍版；請改寫為小說體，保留全部台詞與事件）】", excerpt[:6000]]
        lines.append("請輸出本集小說體正文（300–600 字），去除所有鏡頭與製作指令。")
    else:
        lines.append("請依大綱撰寫本集小說體正文（200–350 字）：有場景、動作與情緒，收在鉤子上；寫成故事，不是摘要。")
    reply = llm_text.deepseek_chat(_NOVEL_SYS, "\n".join(lines),
                                   model=model, max_tokens=1600,
                                   temperature=0.8, timeout=timeout)
    text = reply.strip()
    head = text.splitlines()
    if head and head[0].lstrip().startswith("#"):
        text = "\n".join(head[1:]).strip()
    return text


def _cache_path(cache_dir: Path, ep: int) -> Path:
    return cache_dir / f"ep_{ep:02d}.md"


def _read_cache_body(path: Path | None) -> tuple[str, str]:
    """Return (header, body) of a novel cache file; ("", "") when unreadable."""
    if not path or not path.is_file():
        return "", ""
    text = path.read_text(encoding="utf-8")
    first, _, body = text.partition("\n")
    if not first.startswith("<!-- src:"):
        return "", ""
    return first, body.strip()


def build_novel(package: dict, *, series_id: str, meta: dict | None = None,
                cache_dir: Path | None = None, llm: bool = False,
                model: str | None = None, workers: int = 6,
                force: bool = False) -> tuple[str, dict]:
    """Render the package into novel markdown; returns (markdown, stats)."""
    outline = package.get("episode_outline") or []
    rows = sorted((r for r in outline if isinstance(r, dict)), key=lambda r: int(r.get("ep") or 0))
    novel_dir = Path(cache_dir) if cache_dir else None
    if novel_dir:
        novel_dir.mkdir(parents=True, exist_ok=True)

    passages: dict[int, tuple[str, str]] = {}   # ep -> (text, source)
    pending: list[dict] = []
    for row in rows:
        ep = int(row.get("ep") or 0)
        if not ep:
            continue
        excerpt = _ep_excerpt(package, ep)
        src_hash = _src_hash(package, row, excerpt)
        cache = _cache_path(novel_dir, ep) if novel_dir else None
        header, body = _read_cache_body(cache) if (cache and not force) else ("", "")
        if body:
            if src_hash in header:
                passages[ep] = (body, "llm")
                continue
            if not llm:
                # Source changed but regeneration is off: keep the last
                # novelized text instead of downgrading to the outline
                # fallback; a later --llm run realigns stale episodes.
                passages[ep] = (body, "stale")
                continue
        pending.append({"ep": ep, "row": row, "excerpt": excerpt, "hash": src_hash})

    if llm and pending:
        from scripts.story_room import llm_text
        if not llm_text.available():
            raise SystemExit("[FATAL] DeepSeek key missing; cannot novelize")

        def _task(item: dict) -> tuple[dict, str]:
            return item, novelize_episode(package, item["row"], item["excerpt"], model=model)

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(_task, item): item for item in pending}
            for fut in as_completed(futures):
                item = futures[fut]
                try:
                    _item, text = fut.result()
                    if novel_dir and text:
                        _cache_path(novel_dir, item["ep"]).write_text(
                            f"<!-- src:{item['hash']} | model:{model or 'default'} | {_now()} -->\n\n{text}",
                            encoding="utf-8",
                        )
                    if text:
                        passages[item["ep"]] = (text, "llm")
                        print(f"[novel] ep{item['ep']:02d} novelized ({len(text)} chars)", flush=True)
                    else:
                        passages[item["ep"]] = (_fallback_passage(package, item["row"]), "fallback")
                except Exception as exc:  # noqa: BLE001 - degrade this ep, keep the doc
                    print(f"[warn] novel ep{item['ep']} failed: {str(exc)[:140]}",
                          file=sys.stderr, flush=True)
                    _h, stale_body = _read_cache_body(
                        _cache_path(novel_dir, item["ep"]) if novel_dir else None)
                    if stale_body:
                        passages[item["ep"]] = (stale_body, "stale")
                    else:
                        passages[item["ep"]] = (_fallback_passage(package, item["row"]), "fallback")

    for item in pending:
        if item["ep"] not in passages:
            passages[item["ep"]] = (_fallback_passage(package, item["row"]), "fallback")

    md = _assemble(package, series_id=series_id, meta=meta or {}, rows=rows, passages=passages)
    stats = {
        "episodes": len(rows),
        "llm": sum(1 for v in passages.values() if v[1] == "llm"),
        "stale": sum(1 for v in passages.values() if v[1] == "stale"),
        "fallback": sum(1 for v in passages.values() if v[1] == "fallback"),
    }
    return md, stats


def _assemble(package: dict, *, series_id: str, meta: dict, rows: list[dict],
              passages: dict[int, tuple[str, str]]) -> str:
    """Compose the full novel markdown document (README-style, human first)."""
    title = str(package.get("title") or series_id)
    focus = ""
    if meta.get("best_score") is not None:
        focus = f"｜王者 μ{meta.get('best_score')}"
        if meta.get("best_iteration"):
            focus += f"（第 {meta['best_iteration']} 迭代）"

    lines = [
        f"# 《{title}》劇本小說版 — {series_id}",
        "",
        f"> 供 CEO 審核（人類小說體）｜產出：{_now()}{focus}",
        "> 本文件由王者企劃包自動轉譯；機器格式（分鏡 JSON）僅存於產線，不在此呈現。",
        "",
        "## 故事梗概",
        "",
        str(package.get("logline") or "（待補）"),
        "",
    ]
    theme = package.get("theme")
    genre = package.get("genre")
    fmt = package.get("target_format")
    if theme:
        lines += [f"**主題**：{theme}", ""]
    if isinstance(genre, dict):
        lines += [f"**類型**：{genre.get('mix', '')}｜入口：{genre.get('access', '')}｜調性：{genre.get('tone', '')}", ""]
    if isinstance(fmt, dict):
        lines += [f"**規格**：{fmt.get('episodes', 56)} 集 × {fmt.get('episode_sec', 175)} 秒"
                  f"（{fmt.get('shots_per_ep', '6')}×30s 長鏡；{fmt.get('resolution', '480p')}）", ""]

    bible = package.get("bible") or {}
    lines += ["## 人物介紹", ""]
    for p in (bible.get("protagonists") or []):
        if not isinstance(p, dict):
            continue
        lines.append(f"### {p.get('name', '')}")
        if p.get("role"):
            lines.append(f"**定位**：{p['role']}")
        if p.get("arc"):
            lines.append(str(p["arc"]))
        if p.get("access_method"):
            lines.append(f"**進入方式**：{p['access_method']}")
        lines.append("")
    for a in (bible.get("antagonists") or []):
        if not isinstance(a, dict):
            continue
        lines.append(f"### {a.get('name', '')}")
        if a.get("role"):
            lines.append(f"**定位**：{a['role']}")
        if a.get("arc"):
            lines.append(str(a["arc"]))
        lines.append("")

    lines += ["## 世界與神話", ""]
    rules = bible.get("world_rules") or []
    if rules:
        lines.append("### 世界規則")
        lines += [f"- {r}" for r in rules]
        lines.append("")
    myth = bible.get("mythology") or {}
    if myth.get("east"):
        lines.append("### 東方神話")
        lines += [f"- {m}" for m in myth["east"]]
        lines.append("")
    if myth.get("west"):
        lines.append("### 西方神話")
        lines += [f"- {m}" for m in myth["west"]]
        lines.append("")

    lines += ["## 分弧導讀", ""]
    for arc in (package.get("arcs") or []):
        if not isinstance(arc, dict):
            continue
        arc_raw = arc.get("arc")
        try:
            arc_label = f"第{_cn_number(int(arc_raw))}弧"  # numeric arc number
        except (TypeError, ValueError):
            arc_label = str(arc_raw or "弧")  # packages may carry prose labels
        lines.append(f"### {arc_label}（Episodes {arc.get('episodes', '')}）")
        if arc.get("summary"):
            lines.append(str(arc["summary"]))
        if arc.get("climax"):
            lines.append(f"**高潮**：{arc['climax']}")
        extras = []
        if arc.get("lm_special"):
            extras.append(f"light_music 特輯：{arc['lm_special']}")
        if arc.get("lf_special"):
            extras.append(f"lofi 特輯：{arc['lf_special']}")
        if extras:
            lines.append("**一劇三用**：" + "；".join(extras))
        lines.append("")

    lines += ["## 分集速覽", "", "| 集 | 標題 | 一句話 |", "|---:|---|---|"]
    for row in rows:
        lines.append(f"| {row.get('ep')} | {row.get('title', '')} | {row.get('summary', '')} |")
    lines.append("")

    lines += ["## 全劇故事（小說體）", ""]
    for row in rows:
        ep = int(row.get("ep") or 0)
        text, _source = passages.get(ep) or (_fallback_passage(package, row), "fallback")
        lines.append(f"### 第{_cn_number(ep)}集《{row.get('title', '')}》")
        lines.append("")
        lines.append(text)
        lines.append("")

    foreshadows = [f for f in (package.get("foreshadows") or []) if isinstance(f, dict)]
    if foreshadows:
        lines += ["## 伏筆總表", ""]
        for f in foreshadows:
            lines.append(f"- {f.get('setup', '')} → {f.get('payoff', '')}")
        lines.append("")

    lines += ["---", "", f"> {series_id}｜《{title}》劇本小說版｜自動產出（script_novel.py）", ""]
    return "\n".join(lines)


def render_run(run_dir: Path | str, series_id: str, *, llm: bool = False,
               model: str | None = None, workers: int = 6,
               force: bool = False) -> tuple[str, dict]:
    """Render the run's champion package (best_package.json) into novel markdown."""
    run_dir = Path(run_dir)
    pkg_path = run_dir / "best_package.json"
    if not pkg_path.is_file():
        raise FileNotFoundError(f"best_package.json not found under {run_dir}")
    package = json.loads(pkg_path.read_text(encoding="utf-8"))
    meta_path = run_dir / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    return build_novel(package, series_id=series_id, meta=meta, cache_dir=run_dir / "novel",
                       llm=llm, model=model, workers=workers, force=force)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--package", help="package JSON path (default: <run>/best_package.json)")
    parser.add_argument("--out", help="output markdown path (default: <run>/劇本小說版.md)")
    parser.add_argument("--llm", action="store_true",
                        help="novelize missing episodes via DeepSeek (cached per episode)")
    parser.add_argument("--force", action="store_true", help="ignore caches and regenerate")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--model")
    args = parser.parse_args(argv)

    from scripts.story_room.script_forge import out_root

    run_dir = out_root() / args.series_id
    pkg_path = Path(args.package) if args.package else run_dir / "best_package.json"
    if not pkg_path.is_file():
        raise SystemExit(f"[FATAL] package not found: {pkg_path}")
    package = json.loads(pkg_path.read_text(encoding="utf-8"))
    meta_path = run_dir / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}

    md, stats = build_novel(package, series_id=args.series_id, meta=meta,
                            cache_dir=run_dir / "novel", llm=args.llm,
                            model=args.model, workers=args.workers, force=args.force)
    out = Path(args.out) if args.out else run_dir / "劇本小說版.md"
    out.write_text(md, encoding="utf-8")
    print(json.dumps({"out": str(out), **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
