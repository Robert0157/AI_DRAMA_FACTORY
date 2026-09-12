#!/usr/bin/env python3
"""Dynamic world-library growth: novelty scoring, batch proposal, seed intake.

The bottleneck for MV diversity is not *finding* topics — it is keeping each new
world coherent, non-duplicated and on-brand. This module therefore does three
things and deliberately avoids web scraping:

  1. list      - show the built-in seeds plus any worlds added at runtime
  2. propose   - rank candidates by novelty and pick the next validation batch
  3. intake    - turn a CEO seed (a video title, a one-line idea) into a DRAFT
                 world spec that can be reviewed and then committed

Sources, in priority order:
  procedural synthesis (combinatorial grammar + LLM chronicle)
  CEO taste intake (what the CEO actually watches)
  derivative mutation (season / decade / weather axes over a proven world)
  performance feedback (official YouTube APIs - never page scraping)

Scraping YouTube/TikTok is forbidden by the project rules and is also the wrong
signal: a title never tells you palette, weather, landmarks or world history.

Usage:
  python -m story_room.world_library list
  python -m story_room.world_library propose --n 3
  python -m story_room.world_library intake --seed "Neon Train at 3AM" --channel lofi
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WORKSPACE = Path(__file__).resolve().parents[2]
LIBRARY_PATH = WORKSPACE / "configs" / "world_library.json"

RECORD_KEYS = ("era", "architecture", "palette", "weather", "landmarks", "figures")

# Keyword -> world-component tables used by the offline intake path. The LLM
# enrichment pass (documented next step) replaces this table when enabled.
KEYWORD_TABLE: tuple[tuple[tuple[str, ...], dict[str, Any]], ...] = (
    (("night", "夜", "neon", "霓虹", "lofi", "late"), {
        "era": "凌晨一點到四點之間的城市",
        "architecture": "高架月台、便利店招牌、雨後柏油與車廂內裝",
        "palette": "霓虹洋紅、鈉燈橘、深夜藍",
        "weather": "雨後濕氣、低雲、地面反光",
        "landmarks": ["霓虹月台", "空車廂", "無人剪票口"],
        "figures": "unnamed",
    }),
    (("train", "列車", "rail", "鐵道", "steam", "蒸汽"), {
        "era": "架空蒸汽年代的日常記憶",
        "architecture": "雲海車站、黃銅列車、玻璃溫室與鐘樓",
        "palette": "天空藍、黃銅金、舊紙米白",
        "weather": "晨霧、雲瀑、夕陽逆光",
        "landmarks": ["中央鐘樓", "雲瀑月台", "玻璃溫室車廂"],
        "figures": "none",
    }),
    (("future", "未來", "tomorrow", "echoes", "city", "都市"), {
        "era": "二十二世紀的某個星期二",
        "architecture": "層疊住宅塔、空中步道、室內農園與自動窗",
        "palette": "晨光白、霧銀、植物嫩綠",
        "weather": "人工晴空、區塊陣雨、低空薄霧",
        "landmarks": ["早餐桌窗景", "空中步道", "頂樓小花園"],
        "figures": "none",
    }),
    (("ancient", "古代", "秦", "漢", "vlog", "time travel", "穿越"), {
        "era": "西元前二一一年，秦",
        "architecture": "夯土城牆、驛站、傾斜屋瓦與田埂",
        "palette": "土黃、炭黑、火把橙",
        "weather": "風沙、薄暮、遠處炊煙",
        "landmarks": ["夯土城門", "驛站火把", "遠處田埂"],
        "figures": "unnamed",
    }),
    (("christmas", "聖誕", "dance", "舞蹈", "gallery", "美術館"), {
        "era": "平安夜，閉館之後",
        "architecture": "大理石廊柱、油畫長廊、玻璃天窗與打蠟地板",
        "palette": "暖金、深紅、雪白",
        "weather": "室內暖光、窗外落雪",
        "landmarks": ["玻璃天窗", "長廊盡頭", "磨亮的地板痕跡"],
        "figures": "unnamed",
    }),
    (("sea", "海", "coast", "海岸", "ocean", "潮"), {
        "era": "無時間感的夢境自然史",
        "architecture": "貝殼礁塔、潮汐花園與漂浮鳥巢",
        "palette": "珍珠白、海玻璃綠、珊瑚紅",
        "weather": "薄霧晨光、柔和海風、反射水氣",
        "landmarks": ["母岸巨鳥", "鏡面潮池", "發光貝殼拱門"],
        "figures": "none",
    }),
)

# Derivative-mutation axes: the cheapest way to multiply one proven world.
MUTATION_AXES: dict[str, dict[str, str]] = {
    "season": {"春": "春霧", "夏": "暑氣與雷雨", "秋": "乾燥落葉", "冬": "落雪與結霜"},
    "time_of_day": {"dawn": "破曉", "noon": "正午強光", "dusk": "暮色", "night": "深夜"},
    "decade_shift": {"-50": "五十年前", "+50": "五十年後"},
}


def builtin_worlds() -> dict[str, Any]:
    """The curated seeds shipped in mv_strategy."""
    if __package__ in (None, ""):  # direct script execution
        from story_room.mv_strategy import WORLD_SPECS  # type: ignore
    else:
        from .mv_strategy import WORLD_SPECS

    return {name: dict(spec) for name, spec in WORLD_SPECS.items()}


def runtime_worlds() -> dict[str, Any]:
    """Worlds added at runtime through intake."""
    if not LIBRARY_PATH.is_file():
        return {}
    try:
        payload = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(payload.get("worlds") or {})


def all_worlds() -> dict[str, Any]:
    """Built-in seeds merged with runtime worlds (runtime wins on a name clash)."""
    merged = builtin_worlds()
    merged.update(runtime_worlds())
    return merged


def _tokens(world: dict[str, Any]) -> set[str]:
    """Flatten a world spec into comparable tokens."""
    parts: list[str] = []
    for key in RECORD_KEYS:
        value = world.get(key)
        if isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    joined = " ".join(parts).lower()
    return {token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", joined) if token}


def novelty(world: dict[str, Any], existing: dict[str, Any]) -> float:
    """1.0 = nothing like it in the library, 0.0 = near-duplicate."""
    candidate = _tokens(world)
    if not candidate:
        return 0.0
    worst = 0.0
    for other in existing.values():
        tokens = _tokens(other)
        if not tokens:
            continue
        overlap = len(candidate & tokens) / len(candidate | tokens)
        worst = max(worst, overlap)
    return round(1.0 - worst, 4)


def propose_batch(n: int = 3, candidates: dict[str, Any] | None = None) -> list[str]:
    """Pick the n most novel candidates, balancing the two channels."""
    library = all_worlds()
    pool = dict(candidates) if candidates else {
        name: spec for name, spec in library.items() if name not in library
    }
    scored = sorted(
        ((name, novelty(spec, library), spec.get("channel", "lofi"))
         for name, spec in (candidates or {}).items()),
        key=lambda item: item[1],
        reverse=True,
    )
    picked: list[str] = []
    channel_count: dict[str, int] = {}
    for name, _score, channel in scored:
        if len(picked) >= n:
            break
        if channel_count.get(channel, 0) >= max(1, n // 2 + 1):
            continue
        picked.append(name)
        channel_count[channel] = channel_count.get(channel, 0) + 1
    for name, _score, _channel in scored:  # backfill if balancing was too strict
        if len(picked) >= n:
            break
        if name not in picked:
            picked.append(name)
    _ = pool
    return picked


def draft_from_seed(seed: str, channel: str = "lofi") -> dict[str, Any]:
    """Turn a CEO seed into a DRAFT world spec (offline, deterministic).

    The LLM enrichment pass is the documented next step; it should rewrite
    `chronicle` and sharpen the component lists before commit.
    """
    lowered = seed.lower()
    matched: dict[str, Any] = {}
    for keywords, components in KEYWORD_TABLE:
        if any(keyword in lowered for keyword in keywords):
            matched = dict(components)
            break
    if not matched:
        matched = {
            "era": f"由「{seed}」推導的年代",
            "architecture": f"以「{seed}」為核心的建築語彙（待補）",
            "palette": "待補：三色主調",
            "weather": "待補：天候與濕度",
            "landmarks": [f"{seed} 的主地標", "第二地標（待補）", "第三地標（待補）"],
            "figures": "none",
        }
    name = re.sub(r"\s+", " ", seed).strip()[:24] or "未命名世界"
    return {
        "name": name,
        "channel": channel,
        "template": matched,
        "chronicle": f"（待 LLM 擴寫）以「{seed}」為起點的世界史。",
        "source": "intake.draft_from_seed",
    }


def mutate(world: dict[str, Any], axis: str, value: str) -> dict[str, Any]:
    """Derive a new world from a proven one by changing a single axis."""
    if axis not in MUTATION_AXES:
        raise ValueError(f"unknown mutation axis: {axis!r}")
    label = MUTATION_AXES[axis].get(value, value)
    derived = json.loads(json.dumps(world, ensure_ascii=False))
    derived["weather"] = f"{label}；{derived.get('weather', '')}".strip("；")
    derived["derived_from"] = {"axis": axis, "value": value}
    return derived


def commit(name: str, spec: dict[str, Any], overwrite: bool = False) -> str:
    """Persist a world into the runtime library, rejecting near-duplicates."""
    library = all_worlds()
    if name in library and not overwrite:
        return f"SKIP {name}: already in library"
    score = novelty(spec, {k: v for k, v in library.items() if k != name})
    if score < 0.25 and not overwrite:
        return f"REJECT {name}: near-duplicate (novelty {score})"
    payload = {"version": 1, "worlds": runtime_worlds()}
    payload["worlds"][name] = spec
    LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return f"COMMIT {name}: novelty {score}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show the whole library")
    p_prop = sub.add_parser("propose", help="rank candidates by novelty")
    p_prop.add_argument("--n", type=int, default=3)
    p_intake = sub.add_parser("intake", help="draft a world from a seed")
    p_intake.add_argument("--seed", required=True)
    p_intake.add_argument("--channel", default="lofi", choices=("lofi", "light_music"))
    p_intake.add_argument("--apply", action="store_true", help="commit the draft")
    args = parser.parse_args()

    if args.command == "list":
        for name, spec in sorted(all_worlds().items()):
            print(f"{name}\t{spec.get('channel')}\tfigures={spec.get('figures')}")
        print(f"TOTAL {len(all_worlds())}")
        return 0

    if args.command == "propose":
        candidates = {
            name: spec for name, spec in runtime_worlds().items()
        }
        if not candidates:
            print("NO_RUNTIME_WORLDS: use intake to add candidates first")
            return 0
        for name in propose_batch(args.n, candidates):
            print(f"PROPOSE {name}")
        return 0

    draft = draft_from_seed(args.seed, args.channel)
    print(json.dumps(draft, ensure_ascii=False, indent=1))
    if args.apply:
        spec = {
            "channel": draft["channel"],
            "figures": draft["template"].get("figures", "none"),
            "chronicle": draft["chronicle"],
            **{k: v for k, v in draft["template"].items() if k != "figures"},
        }
        print(commit(draft["name"], spec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
