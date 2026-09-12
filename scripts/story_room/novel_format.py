#!/usr/bin/env python3
"""Render a world-first MV storyboard into a readable chapter script.

The CEO reviews prose, not JSON. This module turns a validated story dict into:

  * 分鏡圖   - the shot table (鏡次/秒數/鏡別/運鏡/光線/錨點/生成單元/畫面)
  * 正文     - 章回小說體 prose, one paragraph per shot, zero dialogue
  * 音樂同步 - which shots cover which song section
  * 製作註記 - engine, resolution, assembly and publishing policy

Narrative DNA fused from the CEO's reference channels: the world is the
protagonist, chapters serialize one impossible place, and the emotion is
nostalgia for somewhere that never existed.

Usage:
  python -m story_room.novel_format --topic 昭和101年空中都市 --variant 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXPERIMENT_ROOT = (
    Path(__file__).resolve().parents[2]
    / "Auto_Drama" / "output" / "sandbox" / "story_room" / "p3_experiment"
)

FRAMING_PROSE: dict[str, str] = {
    "wide establishing": "先給一個全景",
    "wide": "鏡頭拉遠",
    "medium": "鏡頭停在一個可以久看的位置",
    "close detail": "鏡頭湊近，近到只看見一件東西",
    "wide climax": "最後是一個很大的遠景",
}

CAMERA_PROSE: dict[str, str] = {
    "slow push-in": "它只是緩緩向前，慢得像怕驚動什麼",
    "static wide": "它完全不動，把整個空間交給光",
    "slow pan left": "它極慢地往左移，像在數著窗子",
    "crane up": "它往上抬，屋頂之後還有屋頂",
    "slow pull-out": "它緩緩退開，把這座城還給更大的天",
    "tracking flow": "它貼著路面前進，像有人正走過這條街",
}

LIGHT_PROSE: dict[str, str] = {
    "cold ambient": "光是很淡的冷色，像天亮之前那一段",
    "practical warm": "亮著的只有幾盞燈，暖得不太真實",
    "backlit rim": "光從後面來，把邊緣燒成金色",
    "low-key contrast": "暗處比亮處多，影子拉得很長",
    "soft diffuse": "光被霧磨平了，沒有影子",
    "hero light": "光落在中央，其餘的地方安靜地退後",
}

CLOSING_LINES: tuple[str, ...] = (
    "{anchor}一直在畫面裡，像這座城的座標。",
    "畫面裡沒有人，只有{anchor}和它的影子。",
    "{anchor}又出現了。你已經開始認得它。",
    "你注意到{anchor}還是同一個樣子，別的地方卻不太一樣了。",
    "沒有人解釋這裡為什麼是這樣，{anchor}也不需要解釋。",
)


def _shot_number(shot: dict, position: int) -> int:
    return int(shot.get("shot_number") or shot.get("no") or position)


def _shot_list(story: dict) -> list[dict]:
    return list(story.get("shots") or [])


def _prose_paragraph(shot: dict, index: int, total: int, world: dict) -> str:
    """One readable paragraph for one shot, with no dialogue."""
    landmark = shot.get("visual_anchor") or (world.get("landmarks") or ["那座地標"])[0]
    intent = (shot.get("desc") or "").strip("。 ")
    framing = FRAMING_PROSE.get(shot.get("shot_type", ""), "鏡頭停下來")
    camera = CAMERA_PROSE.get(shot.get("camera", ""), "它移動得很慢")
    light = LIGHT_PROSE.get(shot.get("lighting", ""), "光很安靜")

    if index == 1:
        opening = f"{landmark}最先出現。{framing}，{camera}。{light}。"
    elif index == total:
        opening = f"到最後，{framing}，{camera}。{light}。"
    else:
        opening = f"{framing}，{camera}。{light}。"

    body = f"{intent}。" if intent else ""
    closing = CLOSING_LINES[(index - 1) % len(CLOSING_LINES)].format(anchor=landmark)
    return f"{opening}{body}{closing}"


def _board_table(story: dict) -> list[str]:
    """Markdown table of the storyboard."""
    world = story.get("world_bible") or {}
    rows = [
        "| 鏡 | 秒數 | 鏡別 | 運鏡 | 光線 | 視覺錨點 | 生成單元 | 畫面內容 |",
        "|---:|---:|---|---|---|---|---:|---|",
    ]
    for position, shot in enumerate(_shot_list(story), 1):
        plan = shot.get("generation_plan") or {}
        anchor = shot.get("visual_anchor") or (world.get("landmarks") or ["—"])[0]
        rows.append(
            f"| {_shot_number(shot, position)} "
            f"| {float(shot.get('duration_sec', 0.0)):.1f} "
            f"| {shot.get('shot_type', '—')} "
            f"| {shot.get('camera', '—')} "
            f"| {shot.get('lighting', '—')} "
            f"| {anchor} "
            f"| {int(plan.get('unit_count', 1))}×{float(plan.get('unit_duration_sec', 0.0)):.1f}s "
            f"| {(shot.get('desc') or '').strip()} |"
        )
    return rows


def _music_sync(story: dict) -> list[str]:
    """Map song sections onto shot numbers using the three-act structure."""
    shots = _shot_list(story)
    acts = list(story.get("acts") or [])
    if not shots:
        return ["（無鏡頭）"]
    if not acts:
        acts = [
            {"title": "歌曲前段", "synopsis": "建立世界與懸念"},
            {"title": "主體推進段", "synopsis": "推進與反轉"},
            {"title": "最高潮與尾聲", "synopsis": "收束與餘韻"},
        ]
    per_act = max(1, len(shots) // len(acts))
    rows = ["| 歌曲段落 | 覆盖鏡次 | 秒數 | 情緒任務 |", "|---|---|---:|---|"]
    cursor = 0
    for index, act in enumerate(acts):
        remaining_acts = len(acts) - index - 1
        count = per_act if remaining_acts else len(shots) - cursor
        count = max(1, min(count, len(shots) - cursor))
        chunk = shots[cursor:cursor + count]
        if not chunk:
            break
        numbers = [_shot_number(s, cursor + i + 1) for i, s in enumerate(chunk)]
        span = sum(float(s.get("duration_sec", 0.0)) for s in chunk)
        span_label = f"{numbers[0]}–{numbers[-1]}" if len(numbers) > 1 else str(numbers[0])
        rows.append(
            f"| {act.get('title', '段落')} | 鏡 {span_label} | {span:.1f} "
            f"| {act.get('synopsis', '')} |"
        )
        cursor += count
    return rows


def render_novel(story: dict, prose: list[str] | None = None) -> str:
    """Render the storyboard as a chapter script the CEO can read.

    `prose` optionally supplies LLM-expanded body paragraphs (one per shot).
    The storyboard table, music map and production notes always come from the
    validated story dict, so an LLM can never alter the production contract.
    """
    world = story.get("world_bible") or {}
    shots = _shot_list(story)
    total_sec = sum(float(s.get("duration_sec", 0.0)) for s in shots)
    production = story.get("production_mode", "music_world_mv")

    lines: list[str] = []
    lines.append(f"《{story.get('title', '未命名')}》")
    lines.append("")
    lines.append(f"章次：{story.get('chapter_title', '第一章')}")
    lines.append(
        f"世界：{world.get('era', '—')}｜{world.get('architecture', '—')}"
    )
    lines.append(
        f"色調：{world.get('palette', '—')}｜天候：{world.get('weather', '—')}"
    )
    lines.append(
        f"固定錨點：{'、'.join(world.get('landmarks') or []) or '—'}"
    )
    lines.append(
        f"規格：{len(shots)} 鏡 · {total_sec:.1f} 秒 · 480p · 9:16 · 20fps · 零對白"
    )
    lines.append("")
    lines.append("【卷首語】")
    lines.append(f"  {story.get('epigraph', '')}")
    lines.append("")
    lines.append("【世界】")
    lines.append(f"  {story.get('logline', '')}")
    if story.get("series_note"):
        lines.append(f"  {story['series_note']}")
    lines.append(f"  拍攝方式：{world.get('visual_grammar', '—')}")
    lines.append(f"  鏡頭與運動：{world.get('lens', '—')}；{world.get('motion', '—')}")
    lines.append(f"  連戲規則：{world.get('continuity_rule', '—')}")
    lines.append(f"  禁用清單：{'、'.join(world.get('exclusions') or [])}")
    lines.append("")
    lines.append("【世界史】")
    lines.append(f"  {world.get('chronicle', '—')}")
    lines.append("")
    lines.append("【分鏡圖】")
    lines.extend(_board_table(story))
    lines.append("")
    lines.append("【正文】")
    for position, shot in enumerate(shots, 1):
        expanded = None
        if prose and position - 1 < len(prose):
            candidate = (prose[position - 1] or "").strip()
            expanded = candidate or None
        paragraph = expanded or _prose_paragraph(shot, position, len(shots), world)
        lines.append(f"  {position}. {paragraph}")
        lines.append("")
    lines.append("【音樂同步】")
    lines.extend(_music_sync(story))
    lines.append("")
    lines.append("【製作註記】")
    policy = story.get("music_sync_policy") or {}
    lines.append("  引擎：本地 Wan 2.1（ComfyUI）· 無 API 成本；對白劇才用 Seedance 2.5")
    lines.append("  音樂主軌：CEO 審批母帶為唯一主軌，生成音訊一律丟棄")
    lines.append("  對白：禁止（本模式為音樂驅動、零對白）")
    figure_mode = world.get("figures", "none")
    if figure_mode == "unnamed":
        lines.append(
            "  人物政策：只允許無名遠景剪影，臉部永不入鏡、不得跨鏡延續身份"
        )
    else:
        lines.append("  人物政策：完全無人")
    lines.append(f"  剪輯：依歌曲段落與節拍對齊（{policy.get('method', '—')}）")
    if (story.get("publishing") or {}).get("asmr_twin"):
        lines.append("  延伸上架：同一次渲染可另出無音樂 ASMR 版（一次成本、兩次上架）")
    lines.append(f"  模式：{production}")
    return "\n".join(lines)


def load_variant(topic: str, variant: int) -> dict:
    path = EXPERIMENT_ROOT / topic / f"v{variant}.json"
    if not path.is_file():
        raise SystemExit(f"[FATAL] variant artifact not found: {path}")
    return (json.loads(path.read_text(encoding="utf-8")).get("story") or {})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--variant", type=int, required=True)
    parser.add_argument("--out", help="write to this file instead of stdout")
    args = parser.parse_args()

    text = render_novel(load_variant(args.topic, args.variant))
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
