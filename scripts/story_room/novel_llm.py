#!/usr/bin/env python3
"""LLM prose expansion for world-first MV chapters (DeepSeek).

Why this exists: the deterministic renderer produces structurally correct but
templated prose. The CEO's reference channels carry real world-history depth, and
only a language model can write that. This module rewrites the BODY paragraphs
only - the storyboard table, music map and production contract stay derived from
the validated story dict, so expansion can never break the pipeline.

Caching: expanded prose is stored next to the variant artifact as
`<topic>/v<N>.prose.txt`, so re-exporting does not pay for the API again.

Usage:
  python -m story_room.novel_llm --topic 湖光微火 --variant 1
  python -m story_room.novel_llm --topic 湖光微火 --variant 1 --force
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from .llm_text import available, deepseek_chat

EXPERIMENT_ROOT = (
    Path(__file__).resolve().parents[2]
    / "Auto_Drama" / "output" / "sandbox" / "story_room" / "p3_experiment"
)

SYSTEM = """你是華語文學作家，專寫「世界即主角」的沉浸式章回散文。

鐵律（違反即視為失敗）：
1. 全篇零對白、零人名、零第一人稱敘事者。
2. 世界本身是主角；若出現人物，只能是無名的、不被命名、不延續身份。
3. 段落數量與順序必須完全對應給定的鏡頭，不可合併、不可新增、不可刪減。
4. 每一段都要自然織入一個世界史的細節，但嚴禁用條列、禁用「世界史寫著」這類後設語句。
5. 句子要具體、有質地（材質、光線、聲音、溫度），不要形容詞堆疊，不要空泛抒情。
6. 只輸出正文段落，不要標題、不要編號、不要任何說明或前言。
輸出格式：每一段獨立成段，段落之間以單一空行分隔。"""


def _prose_path(topic: str, variant: int) -> Path:
    return EXPERIMENT_ROOT / topic / f"v{variant}.prose.txt"


def build_user_prompt(story: dict) -> str:
    """Assemble the world bible + storyboard the writer must respect."""
    world = story.get("world_bible") or {}
    shots = story.get("shots") or []
    lines = [
        f"作品題名：{story.get('title', '')}",
        f"章次：{story.get('chapter_title', '')}",
        f"卷首語：{story.get('epigraph', '')}",
        "",
        "【世界史】",
        str(world.get("chronicle", "")),
        "",
        "【世界的固定設定】",
        f"年代：{world.get('era', '')}",
        f"建築：{world.get('architecture', '')}",
        f"色調：{world.get('palette', '')}",
        f"天候：{world.get('weather', '')}",
        f"固定錨點（每一章都要重現）：{'、'.join(world.get('landmarks') or [])}",
        f"視覺語法：{world.get('visual_grammar', '')}",
        f"連戲規則：{world.get('continuity_rule', '')}",
        "",
        "【分鏡（依序，段落數必須等於鏡頭數）】",
    ]
    for position, shot in enumerate(shots, 1):
        cast = shot.get("cast", "none")
        cast_note = {
            "beauty": "畫面主體是一位美麗的無名女子（臉可以入鏡，但不可具名）",
            "surreal": "畫面主體是一個超現實的無名形體（臉被遮住或不可辨識）",
            "none": "畫面完全沒有人",
        }.get(cast, "畫面完全沒有人")
        lines.append(
            f"鏡 {position}｜{shot.get('shot_type', '')}／{shot.get('camera', '')}／"
            f"{shot.get('lighting', '')}｜視覺錨點：{shot.get('visual_anchor', '')}"
            f"｜{cast_note}｜內容：{(shot.get('desc') or '').strip()}"
        )
    lines += [
        "",
        f"請寫 {len(shots)} 段，每段 90 到 150 字，總長不超過 900 字。",
        "段落之間以單一空行分隔，只輸出這 "
        f"{len(shots)} 段，不要任何其他文字。",
    ]
    return "\n".join(lines)


def split_paragraphs(text: str, expected: int) -> list[str]:
    """Split the model output into exactly `expected` non-empty paragraphs."""
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    cleaned: list[str] = []
    for block in blocks:
        # Drop a leading "1." / "第一段" style marker if the model added one.
        cleaned.append(re.sub(r"^\s*(?:\d+[.、)]|第[一二三四五六七八九十]+段[:：]?)\s*", "", block))
    if len(cleaned) != expected:
        raise RuntimeError(
            f"writer returned {len(cleaned)} paragraphs, expected {expected}"
        )
    return cleaned


def expand_prose(story: dict, force: bool = False, model: str | None = None) -> list[str]:
    """Return expanded body paragraphs, using the on-disk cache when present."""
    topic = str(story.get("topic") or "")
    variant = int(story.get("variant") or 1)
    expected = len(story.get("shots") or [])
    if expected == 0:
        raise RuntimeError("story has no shots to expand")

    cache = _prose_path(topic, variant)
    if cache.is_file() and not force:
        cached = [
            block.strip()
            for block in re.split(r"\n\s*\n", cache.read_text(encoding="utf-8"))
            if block.strip()
        ]
        if len(cached) == expected:
            return cached

    if not available():
        raise RuntimeError(
            "DEEPSEEK_API_KEY not configured; cannot expand prose (ZERO SILENT FAILURES)"
        )
    raw = deepseek_chat(SYSTEM, build_user_prompt(story), model=model, temperature=1.1)
    paragraphs = split_paragraphs(raw, expected)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("\n\n".join(paragraphs), encoding="utf-8")
    return paragraphs


def main() -> int:
    from .novel_format import load_variant, render_novel

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--variant", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()

    story = load_variant(args.topic, args.variant)
    prose = expand_prose(story, force=args.force)
    text = render_novel(story, prose=prose)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"WROTE {target}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
