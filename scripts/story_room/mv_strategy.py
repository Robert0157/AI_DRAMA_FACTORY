"""World-first MV production strategy for Lofi and Light Music channels."""
from __future__ import annotations

import copy
import json
import math
from typing import Any

from .map_shots import CAMERAS, LIGHTING, SHOT_TYPES

# Fused from the CEO's reference channels (Surreal AI / LEFT BEHIND /
# 存在しない街の記憶): the world is the protagonist, episodes are numbered
# chapters of one continuous place, and the emotion is nostalgia for somewhere
# that never existed. Characters never persist across chapters.
NOSTALGIA_EPIGRAPHS: tuple[str, ...] = (
    "有些地方，你從來沒有去過，卻一直想回去。",
    "沒人記得這座城是什麼時候開始浮著的，大家只是照常起床。",
    "如果一個地方從未存在，那懷念它的人算不算它的居民？",
    "海把舊的日本收走了，卻把屋頂留了下來。",
    "模型裡的人不知道自己住在模型裡，所以他們過得很好。",
)

# The dramatic beat sheet is written for character drama. World-first MV has no
# protagonist, so every beat intent is re-worded to describe the PLACE instead.
WORLD_FIRST_BEAT_REWRITES: dict[str, str] = {
    "建立主角所處的世界與日常，環境主導": "建立這座地方的日常與規則，環境主導",
    "異常事件正式進入主角的世界": "異常正式進入這座地方的日常",
    "主角做出選擇，離開原本狀態": "場景離開原本狀態，往更深處推進",
    "主角面對第一個障礙，付出小代價": "環境出現第一個不和諧，代價開始累積",
    "真相或規則揭露，主角的理解被顛覆": "真相或規則揭露，原本的觀看方式被推翻",
    "主角失去關鍵之物，幾乎放棄": "這座地方失去關鍵之物，幾乎放棄",
    "主角以自身代價回應，完成蛻變": "以自身代價回應，完成蛻變",
    "建立世界、主角與懸念": "建立世界與懸念",
}


def world_first_intent(text: str) -> str:
    """Rewrite drama phrasing that assumes a protagonist into place phrasing."""
    if not text:
        return text
    if text in WORLD_FIRST_BEAT_REWRITES:
        return WORLD_FIRST_BEAT_REWRITES[text]
    for drama, place in WORLD_FIRST_BEAT_REWRITES.items():
        if drama in text:
            return text.replace(drama, place)
    return text.replace("主角", "這座地方")


# CEO ruling 2026-09-11 (rev.2): the lofi channel keeps its proven figure
# signature - unnamed faces MAY be visible (no identity continuity) - and the
# figure cast is now 100% beautiful women. The surreal-figure clause stays in the
# table for any future world that declares a surreal share in its cast_mix.
FIGURE_CLAUSES: dict[tuple[str, str], str] = {
    ("none", ""): "no people, no humans, no characters, no dialogue, no text",
    ("unnamed", ""): (
        "unnamed distant silhouettes only, faces never visible, "
        "no identifiable person, no dialogue, no text"
    ),
    ("unnamed_visible", "beauty"): (
        "one beautiful elegant unnamed woman, face may be visible, "
        "cinematic portrait light, no named character, no dialogue, no text, no logo"
    ),
    ("unnamed_visible", "surreal"): (
        "an unnamed surreal figure, face obscured or masked, "
        "no named character, no dialogue, no text"
    ),
}


def cast_plan(world: dict[str, Any], shot_count: int) -> list[str]:
    """Spread the world's cast mix across the shots (surreal slots evenly placed)."""
    mix = world.get("cast_mix") or {}
    if not mix or shot_count <= 0:
        return [""] * max(shot_count, 0)
    beauty = float(mix.get("female_beauty", 1.0))
    surreal = float(mix.get("surreal_figure", 0.0))
    total = beauty + surreal
    if total <= 0:
        return [""] * shot_count
    surreal_count = int(round(shot_count * (surreal / total)))
    plan = ["beauty"] * shot_count
    for slot in range(surreal_count):
        position = int(round((slot + 0.5) * shot_count / surreal_count)) - 1
        plan[max(0, min(shot_count - 1, position))] = "surreal"
    return plan


# CEO ruling 2026-09-11: mass production runs at 480p, one episode per channel
# per week. 720p is cancelled pending explicit per-case approval.
MV_PUBLISH_CADENCE: dict[str, object] = {
    "episodes_per_channel_per_week": 1,
    "resolution": "480p",
    "fps": 20,
    "target_duration_sec": 175,
    "channels": ("lofi", "light_music"),
}

# CEO ruling 2026-09-12: the MV lines may stretch paid engine credits with a
# "base clip + variation" edit - one base may return, but never unchanged.
# This is the explicit, scoped relaxation of the no-loop rule (copilot §2.1a).
BASE_VARIATION_POLICY: dict[str, object] = {
    "enabled": True,
    "max_reuse_per_base": 3,
    "visible_variation_required": True,
    "adjacent_duplicate_forbidden": True,
    "native_coverage_min": 0.60,
    "manifest_field": "variation_plan",
    "approved_by": "CEO 2026-09-12",
}

MV_VALIDATION_TOPICS: tuple[str, ...] = (
    "湖光微火",
    "伸展台之夢",
    "華服荒原",
)

# Worlds harvested from the CEO's reference channels. The validation batch
# rotates; this library persists.
WORLD_SPECS: dict[str, dict[str, Any]] = {
    "昭和101年空中都市": {
        "channel": "lofi",
        "era": "昭和復古與架空101年",
        "architecture": "浮空商店街、木造住宅、路面電車與神木平台",
        "palette": "褪色青綠、鎢絲琥珀、雨後灰藍",
        "weather": "海霧、細雨、低雲",
        "landmarks": ["中央神木", "懸空電車站", "紅色商店街拱門"],
        "figures": "none",
        "chronicle": (
            "昭和一百零一年，海平面上升，淹掉了舊日本列島的低地。人們沒有造新船，"
            "而是把整座山連同神木一起鋸下、抬上浮台——他們說，只要神木還在，戶籍就還在。"
            "此後七十年，這座城一直浮著，商店街照常開門，電車照常誤點。"
            "城裡的人不太談海，只談明天的天氣。"
        ),
    },
    "超現實海岸生態": {
        "channel": "light_music",
        "era": "無時間感的夢境自然史",
        "architecture": "貝殼礁塔、潮汐花園與漂浮鳥巢",
        "palette": "珍珠白、海玻璃綠、珊瑚紅",
        "weather": "薄霧晨光、柔和海風、反射水氣",
        "landmarks": ["母岸巨鳥", "鏡面潮池", "發光貝殼拱門"],
        "figures": "none",
        "chronicle": (
            "這裡沒有歷史，只有潮汐。有人說這片海岸比人類更早學會做夢——"
            "貝殼一層一層長成塔，鳥在海面上築巢，巢比鳥大。"
            "所有東西都在緩慢地變成別的東西，但沒有東西真的死掉。"
        ),
    },
    "雲上懷舊列車城": {
        "channel": "light_music",
        "era": "架空蒸汽年代的日常記憶",
        "architecture": "雲海車站、黃銅列車、玻璃溫室與鐘樓",
        "palette": "天空藍、黃銅金、舊紙米白",
        "weather": "晨霧、雲瀑、夕陽逆光",
        "landmarks": ["中央鐘樓", "雲瀑月台", "玻璃溫室車廂"],
        "figures": "none",
        "chronicle": (
            "蒸汽年代的工程師發現雲是可以鋪軌的。他們在雲海之上蓋了車站，"
            "從此列車不再準時——因為雲會移動。城裡的人靠鐘樓報時，"
            "而鐘樓自己每年慢一天，沒有人想去校正它。"
        ),
    },
    "深夜霓虹列車": {
        "channel": "lofi",
        "era": "凌晨一點到四點之間的城市",
        "architecture": "高架月台、便利店招牌、雨後柏油與車廂內裝",
        "palette": "霓虹洋紅、鈉燈橘、深夜藍",
        "weather": "雨後濕氣、低雲、地面反光",
        "landmarks": ["霓虹月台", "空車廂", "無人剪票口"],
        "figures": "unnamed",
        "chronicle": (
            "這條線只在凌晨一點到四點之間存在。白天它是地圖上一條畫錯的線；"
            "入夜之後，霓虹先亮，列車才來。乘客不多，大多是睡不著、也不想睡的人。"
            "沒有人查票，因為這條線沒有終點站。"
        ),
    },
    "未來日常": {
        "channel": "light_music",
        "era": "二十二世紀的某個星期二",
        "architecture": "層疊住宅塔、空中步道、室內農園與自動窗",
        "palette": "晨光白、霧銀、植物嫩綠",
        "weather": "人工晴空、區塊陣雨、低空薄霧",
        "landmarks": ["早餐桌窗景", "空中步道", "頂樓小花園"],
        "figures": "none",
        "chronicle": (
            "二十二世紀的某個星期二。城市早已解決了所有重大問題，"
            "於是居民開始認真對待小事：澆一盆不會長大的植物，替鄰居留一盞燈。"
            "奇觀不再發生在街上，而是發生在早餐桌上。"
        ),
    },
    "上古中國穿越": {
        "channel": "lofi",
        "era": "西元前二一一年，秦",
        "architecture": "夯土城牆、驛站、傾斜屋瓦與田埂",
        "palette": "土黃、炭黑、火把橙",
        "weather": "風沙、薄暮、遠處炊煙",
        "landmarks": ["夯土城門", "驛站火把", "遠處田埂"],
        "figures": "unnamed",
        "chronicle": (
            "西元前二一一年，秦。一個現代人舉著鏡頭走進這個年份——"
            "他不會說這裡的語言，也沒有人聽得懂他。他只能記錄：泥路、驛站、"
            "傾斜的屋瓦、遠處正在移動的火把。他沒有改變任何事，"
            "只是把兩千年後的疑問帶了進來。"
        ),
    },
    "聖誕美術館之夜": {
        "channel": "light_music",
        "era": "平安夜，閉館之後",
        "architecture": "大理石廊柱、油畫長廊、玻璃天窗與打蠟地板",
        "palette": "暖金、深紅、雪白",
        "weather": "室內暖光、窗外落雪",
        "landmarks": ["玻璃天窗", "長廊盡頭", "磨亮的地板痕跡"],
        "figures": "unnamed",
        "chronicle": (
            "平安夜的美術館不對外開放，但館內的雕像會在整點離開基座。"
            "它們不說話，只是跳舞，跳到天亮再回到原位。"
            "唯一留下的證據，是地板上一圈被磨亮的痕跡。"
        ),
    },
}

VISUAL_TREATMENTS: tuple[dict[str, str], ...] = (
    {
        "id": "miniature_daily_life",
        "name": "微縮日常",
        "grammar": "tilt-shift miniature scale, patient observational camera",
    },
    {
        "id": "memory_archive",
        "name": "記憶檔案",
        "grammar": "archival visual diary, restrained locked shots and slow pans",
    },
    {
        "id": "surreal_metamorphosis",
        "name": "超現實變形",
        "grammar": "gentle impossible transformations, continuous dream logic",
    },
    {
        "id": "slow_travelogue",
        "name": "慢速漫遊",
        "grammar": "forward travelogue movement through connected landmarks",
    },
    {
        "id": "chapter_chronicle",
        "name": "章回編年",
        "grammar": "recurring landmark chronicle, wide establishing compositions",
    },
)


def _world_spec(topic: str) -> dict[str, Any]:
    """Resolve a world: built-in seed -> runtime library -> safe generic fallback."""
    if topic in WORLD_SPECS:
        return copy.deepcopy(WORLD_SPECS[topic])
    try:  # lazy import: world_library reads WORLD_SPECS from this module
        from .world_library import runtime_worlds

        extra = runtime_worlds()
        if topic in extra:
            spec = copy.deepcopy(extra[topic])
            spec.setdefault("channel", "lofi")
            spec.setdefault("figures", "none")
            return spec
    except Exception:  # noqa: BLE001 - a broken sidecar must not kill generation
        pass
    return {
        "channel": "lofi",
        "era": "timeless imagined memory",
        "architecture": f"a coherent environment derived from {topic}",
        "palette": "muted natural color with one warm accent",
        "weather": "soft atmospheric haze",
        "landmarks": [f"{topic} central landmark", "transit threshold", "memory object"],
        "figures": "none",
        "chronicle": (
            f"沒有人記得{topic}是從哪一年開始的。它一直照自己的規則運作，"
            "外來的問題在這裡都得不到答案。"
        ),
    }


def apply_music_world_strategy(story: dict, topic: str, variant: int) -> dict:
    """Attach a deterministic Wan-first production contract to one story."""
    updated = copy.deepcopy(story)
    treatment = VISUAL_TREATMENTS[(variant - 1) % len(VISUAL_TREATMENTS)]
    world = _world_spec(topic)
    world.update({
        "treatment_id": treatment["id"],
        "treatment_name": treatment["name"],
        "visual_grammar": treatment["grammar"],
        "lens": "24mm and 35mm environmental lenses; no facial close-ups",
        "motion": "slow push, pan, crane, or locked atmospheric observation",
        "continuity_rule": "repeat at least one landmark and the same palette in every chapter",
        "exclusions": ["named lead", "facial close-up", "dialogue", "lip sync", "visible text"],
    })

    updated["production_mode"] = "music_world_mv"
    updated["title"] = f"{topic}｜{treatment['name']}"
    updated["logline"] = (
        f"以{world['landmarks'][0]}為反覆視覺錨點，透過{treatment['name']}呈現"
        f"{topic}的環境變化，讓世界本身承載情緒與記憶。"
    )
    updated["theme"] = f"世界即主角：{world['era']} × {treatment['name']}"
    updated["characters"] = []
    updated["world_bible"] = world
    # Strip the protagonist assumption out of the inherited dramatic structure.
    updated["acts"] = [
        {**act, "synopsis": world_first_intent(str(act.get("synopsis", "")))}
        for act in (updated.get("acts") or [])
    ]

    # Serialized-chapter framing, fused from the reference channels.
    chapter_no = int(updated.get("chapter_no") or 1)
    updated["chapter_no"] = chapter_no
    updated["chapter_title"] = f"第{chapter_no}章 · {treatment['name']}"
    updated["epigraph"] = NOSTALGIA_EPIGRAPHS[(variant - 1) % len(NOSTALGIA_EPIGRAPHS)]
    updated["series_note"] = (
        f"{topic}是同一座世界的連續章回：每一章換一種觀看方式，"
        f"{'、'.join(world['landmarks'])}固定重現，角色不出現、也不累積。"
        f"觀眾追的是這個地方，不是某個人。"
    )
    updated["publishing"] = {
        "asmr_twin": True,
        "note": "同一次渲染可另出無音樂 ASMR 版：一次成本、兩次上架",
    }
    updated["music_sync_policy"] = {
        "source": "ceo_approved_master_track",
        "method": "edit_to_sections_and_beats",
        "generated_audio": "discard",
        "dialogue": "forbidden",
    }

    source_shots: list[dict] = list(updated.get("shots", []))
    figure_mode = world.get("figures", "none")
    plan = cast_plan(world, len(source_shots))
    styled_shots: list[dict] = []
    for index, source_shot in enumerate(source_shots, 1):
        shot = dict(source_shot)
        duration = float(shot.get("duration_sec", 0.0))
        unit_count = max(1, math.ceil(duration / 5.0))
        unit_duration = round(duration / unit_count, 3)
        landmark = world["landmarks"][(index - 1) % len(world["landmarks"])]
        # Figures are allowed only in the modes the world declares, and the lofi
        # channel runs a 100% beautiful-women cast (CEO ruling rev.2 2026-09-11).
        cast = plan[index - 1] if plan else ""
        shot_class = "environment" if figure_mode == "none" else "ambient_figure"
        figure_clause = FIGURE_CLAUSES.get(
            (figure_mode, cast), FIGURE_CLAUSES[("unnamed", "")]
        )
        shot.update({
            "cast": cast or "none",
            "characters": [],
            "dialogue": "",
            "shot_class": shot_class,
            "desc": world_first_intent(str(shot.get("desc", ""))),
            # Slow observational grammar borrowed from the reference channels.
            "shot_type": SHOT_TYPES[(index - 1) % len(SHOT_TYPES)],
            "camera": CAMERAS[(index - 1) % len(CAMERAS)],
            "lighting": LIGHTING[(index - 1) % len(LIGHTING)],
            "generation_route": {
                "engine": "wan21_local",
                "provider": "comfyui_wan21",
                "resolution": "480p",
                "reason": "music-world MV environment shot",
            },
            "generation_plan": {
                "unit_count": unit_count,
                "unit_duration_sec": unit_duration,
                "assembly": "sequential_concat",
            },
            "visual_anchor": landmark,
            "prompt": (
                f"{treatment['grammar']}; {world['era']}; {world['architecture']}; "
                f"palette: {world['palette']}; weather: {world['weather']}; "
                f"landmark: {landmark}; {shot.get('desc', '')}; {figure_clause}"
            ),
        })
        styled_shots.append(shot)
    updated["shots"] = styled_shots
    return updated


def validate_music_world_story(story: dict) -> dict[str, Any]:
    """Validate the world-first, local-Wan production contract."""
    findings: list[str] = []
    world = story.get("world_bible") or {}
    required_world = {
        "channel", "era", "architecture", "palette", "weather", "landmarks",
        "treatment_id", "visual_grammar", "continuity_rule", "exclusions",
        "chronicle", "figures",
    }
    missing_world = sorted(required_world.difference(world))
    if story.get("production_mode") != "music_world_mv":
        findings.append("production_mode must be music_world_mv")
    if story.get("characters") != []:
        findings.append("music-world MV must not define recurring characters")
    if missing_world:
        findings.append(f"world_bible missing: {missing_world}")
    # An uninriched intake draft must never reach production.
    if "待補" in json.dumps(world, ensure_ascii=False) or "待補充" in json.dumps(
        world, ensure_ascii=False
    ):
        findings.append("world_bible still contains intake placeholders (待補)")

    shots = story.get("shots") or []
    if not shots:
        findings.append("story has no shots")
    for index, shot in enumerate(shots, 1):
        route = shot.get("generation_route") or {}
        plan = shot.get("generation_plan") or {}
        if shot.get("characters") != [] or shot.get("dialogue"):
            findings.append(f"shot {index} is not explicitly character-free")
        if route.get("engine") != "wan21_local" or route.get("resolution") != "480p":
            findings.append(f"shot {index} is not routed to local Wan 480p")
        unit_duration = float(plan.get("unit_duration_sec", 0.0))
        if not 4.0 <= unit_duration <= 5.0:
            findings.append(f"shot {index} generation unit is outside 4-5 seconds")
        prompt = str(shot.get("prompt", ""))
        shot_class = shot.get("shot_class")
        if shot_class == "environment":
            if "no people" not in prompt:
                findings.append(
                    f"shot {index} environment prompt lacks the no-people constraint"
                )
        elif shot_class == "ambient_figure":
            if "unnamed" not in prompt:
                findings.append(
                    f"shot {index} ambient-figure prompt lacks the unnamed constraint"
                )
            elif not ("faces never visible" in prompt
                      or "face may be visible" in prompt
                      or "face obscured" in prompt):
                findings.append(
                    f"shot {index} ambient-figure prompt lacks a face policy"
                )
        else:
            findings.append(f"shot {index} has an unknown shot_class: {shot_class!r}")

    music_policy = story.get("music_sync_policy") or {}
    if music_policy.get("source") != "ceo_approved_master_track":
        findings.append("CEO-approved master track is not the music source")
    if music_policy.get("generated_audio") != "discard":
        findings.append("generated audio must be discarded")
    return {
        "pass": not findings,
        "findings": findings,
        "world_signature": (
            f"{world.get('treatment_id', 'missing')}|"
            f"{world.get('palette', 'missing')}|{world.get('weather', 'missing')}"
        ),
        "wan_shots": sum(
            1 for shot in shots
            if (shot.get("generation_route") or {}).get("engine") == "wan21_local"
        ),
        "generation_units": sum(
            int((shot.get("generation_plan") or {}).get("unit_count", 0))
            for shot in shots
        ),
    }