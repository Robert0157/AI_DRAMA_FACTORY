"""Shot mapping: beats -> music_drama.v2-compatible storyboard draft.

Enforces the Seedance window (4-30s per shot) and zero dialogue. Output is a
scaffold draft: unknown fields are "TODO(CEO)" placeholders. No API calls.
"""
from __future__ import annotations

import math

from .beats import BeatSheet

# Shot craft cycles: rotate through these to avoid uniform "equal-length MV" feel.
SHOT_TYPES: tuple[str, ...] = (
    "wide establishing",
    "medium",
    "wide",
    "close detail",
    "medium",
    "wide climax",
)
CAMERAS: tuple[str, ...] = (
    "slow push-in",
    "static wide",
    "slow pan left",
    "crane up",
    "slow pull-out",
    "tracking flow",
)
LIGHTING: tuple[str, ...] = (
    "cold ambient",
    "practical warm",
    "backlit rim",
    "low-key contrast",
    "soft diffuse",
    "hero light",
)


def split_durations(target_sec: float, n_shots: int) -> list[float]:
    """Even split inside the 4-30s window; the last shot absorbs rounding.

    Raises ValueError when the request cannot fit (too many shots / too short).
    """
    if target_sec < 4.0:
        raise ValueError(f"target too short for one shot: {target_sec}s")
    n = max(int(n_shots), int(math.ceil(target_sec / 30.0)))
    base = round(target_sec / n, 1)
    if base < 4.0:
        # Too many shots for the duration: shrink the count to the legal maximum.
        n = max(1, int(math.floor(target_sec / 4.0)))
        base = round(target_sec / n, 1)
    durs = [base] * (n - 1)
    last = round(target_sec - base * (n - 1), 1)
    if last > 30.0:  # rare rounding overflow; rebalance into the window
        last = 30.0
        durs[0] = round(target_sec - 30.0 - base * (n - 2), 1)
    durs.append(last)
    return durs


def _beat_for_shot(sheet: BeatSheet, i: int, n: int) -> int:
    """Monotonic beat index for shot i of n (start/end beats always included)."""
    if n <= 1:
        return 0
    return round(i * (len(sheet.beats) - 1) / (n - 1))


def map_to_shots(
    sheet: BeatSheet,
    n_shots: int = 6,
    characters: tuple[str, ...] = ("lead",),
) -> list[dict]:
    """Map beats onto contiguous shots with legal durations."""
    durs = split_durations(sheet.target_sec, n_shots)
    spans = sheet.act_spans
    shots: list[dict] = []
    t = 0.0
    for i, dur in enumerate(durs):
        start, end = round(t, 1), round(t + dur, 1)
        beat = sheet.beats[_beat_for_shot(sheet, i, len(durs))]
        act = next((a for a in sheet.acts if a.index == beat.act), sheet.acts[0])
        shots.append(
            {
                "shot_number": i + 1,
                "scene_id": act.index,
                "start_sec": start,
                "end_sec": end,
                "duration_sec": dur,
                "music_section": act.title,
                "audio_cue": beat.cue or "TODO: 對齊歌詞/能量段",
                "title": beat.name,
                "action": beat.intent,
                "shot_type": SHOT_TYPES[i % len(SHOT_TYPES)],
                "camera": CAMERAS[i % len(CAMERAS)],
                "lighting": LIGHTING[i % len(LIGHTING)],
                "characters": list(characters),
                # CN universal prompt scaffold with a character-reference slot.
                "universal_segment_text": (
                    f"{sheet.topic}題材，第{i + 1}鏡（{beat.name}）：{beat.intent}。"
                    f"鏡別：{SHOT_TYPES[i % len(SHOT_TYPES)]}；運鏡：{CAMERAS[i % len(CAMERAS)]}。"
                    f"【角色參考：REF_IMG_01】TODO(CEO): 風格前綴與細節描述"
                ),
            }
        )
        t = end
    # Guard: act spans are informational only; shots stay globally contiguous.
    _ = spans
    return shots


def build_draft(
    sheet: BeatSheet,
    world: str = "lofi",
    episode_id: str = "epXX",
    series: str = "mv",
    resolution: str = "480p",
    aspect_ratio: str = "9:16",
    n_shots: int = 6,
    characters: tuple[str, ...] = ("lead",),
    title: str | None = None,
) -> dict:
    """Assemble a music_drama.v2-shaped scaffold draft (text only)."""
    if world not in ("lofi", "light_music"):
        raise ValueError(f"world must be lofi|light_music, got {world!r}")
    shots = map_to_shots(sheet, n_shots=n_shots, characters=characters)
    spans = sheet.act_spans
    return {
        "schema_version": "music_drama.v2",
        "world": world,
        "series": series,
        "draft_status": "story_room.scaffold (no generation; fill TODOs, then CEO review)",
        "episode": {
            "episode_id": episode_id,
            "title": title or sheet.topic,
            "language": "zh",
            "zero_dialogue": True,
        },
        "audio": {
            # Placeholder: fill with a CEO-approved beat (file + sha256) later.
            "file": "TODO(CEO): assets/audio/ceo_approved_beats/<family>/<track>.mp3",
            "sha256": "0" * 64,
            "duration_sec": round(sheet.target_sec, 1),
            "segment": {"start_sec": 0.0, "end_sec": round(sheet.target_sec, 1)},
            "has_vocals": True,
        },
        "audio_policy": {
            "mode": "music_master",
            "seedance_audio": "discard",
            "ambient_gain_db": -27.0,
            "target_lufs": -14.0,
        },
        "plan": {
            "logline": sheet.logline,
            "hook": sheet.hook,
            "theme": sheet.theme,
            "three_acts": [
                {"act": a.index, "title": a.title, "synopsis": a.synopsis,
                 "span_sec": [spans[a.index - 1][0], spans[a.index - 1][1]]}
                for a in sheet.acts
            ],
            "segments": [
                {"name": a.title, "start_sec": spans[a.index - 1][0],
                 "end_sec": spans[a.index - 1][1], "intent": a.synopsis}
                for a in sheet.acts
            ],
        },
        "visual_style": {
            "genres": ["TODO(CEO): 類型/參考風格"],
            "palette": "TODO(CEO): 色彩推進（開場/主體/高潮/尾聲）",
            "style_prefix": "TODO(CEO): 風格前綴（注入每顆鏡頭）",
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        },
        "cast": [
            {
                "key": characters[0],
                "name": "（待定）主角",
                "role": "main",
                "appearance": "TODO(CEO): 外觀設計",
                "description": "TODO(CEO): 角色功能與情感核心",
                "portrait_prompt": "TODO(CEO): 單人定裝照 prompt（3:4 半身）",
            }
        ],
        "scenes": [
            {
                "scene_id": a.index,
                "location": f"TODO(CEO): {a.title} 主場景",
                "time": "TODO(CEO)",
                "atmosphere": a.synopsis,
                "summary": a.synopsis,
            }
            for a in sheet.acts
        ],
        "shots": shots,
    }
