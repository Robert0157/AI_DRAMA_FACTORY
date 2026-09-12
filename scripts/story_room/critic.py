"""Story Room critic (story_room.v1): rule-based review of a draft scaffold.

Checks story-level invariants that music_drama.validate_draft does NOT cover:
hook presence, three-act coverage, beat density, shot rhythm legality (4-30s),
zero-dialogue compliance and cue placeholders. Deterministic; no API calls.
"""
from __future__ import annotations

from typing import Any

SEEDANCE_MIN_SEC = 4.0
SEEDANCE_MAX_SEC = 30.0


def _check(code: str, level: str, message: str) -> dict:
    return {"code": code, "level": level, "message": message}


def review(draft: dict[str, Any]) -> dict[str, Any]:
    """Run story_room.v1 checks; returns a report dict with counts."""
    checks: list[dict] = []
    plan = draft.get("plan", {})
    episode = draft.get("episode", {})
    shots = draft.get("shots", [])
    target = float(draft.get("audio", {}).get("duration_sec", 0.0))

    # S1 logline / hook / theme presence
    for key in ("logline", "hook", "theme"):
        val = str(plan.get(key, ""))
        if val and not val.startswith("TODO"):
            checks.append(_check(f"S1_{key}", "ok", f"{key} 已填寫"))
        else:
            checks.append(_check(f"S1_{key}", "error", f"{key} 缺失或仍為 TODO"))

    # S2 three acts and contiguous coverage
    acts = plan.get("three_acts", [])
    if len(acts) == 3:
        checks.append(_check("S2_acts", "ok", "三幕齊備"))
        spans = [a.get("span_sec", [0, 0]) for a in acts]
        contiguous = (
            abs(spans[0][0]) < 0.05
            and all(abs(spans[i][1] - spans[i + 1][0]) < 0.1 for i in range(2))
            and (target == 0.0 or abs(spans[2][1] - target) < 0.5)
        )
        checks.append(
            _check("S2_span", "ok" if contiguous else "error",
                   "三幕時間軸連續且覆蓋全曲" if contiguous else "三幕時間軸不連續或未覆蓋全曲")
        )
    else:
        checks.append(_check("S2_acts", "error", f"三幕數量={len(acts)}（需為 3）"))

    # S3 beat density 8-12
    n_beats = len(plan.get("segments", []))  # segments mirror acts; beats live in shots
    # Beats are carried by shots here; use distinct shot titles as beat proxies.
    titles = {s.get("title", "") for s in shots}
    if 8 <= len(titles) <= 14:
        checks.append(_check("S3_beat_density", "ok", f"節拍密度 {len(titles)}（8-14 之間）"))
    else:
        checks.append(_check("S3_beat_density", "warn",
                             f"節拍密度 {len(titles)}（建議 8-12；目前以鏡頭標題計）"))
    _ = n_beats

    # S4 shot legality and rhythm
    if not shots:
        checks.append(_check("S4_shots", "error", "無鏡頭"))
    else:
        illegal = [s["shot_number"] for s in shots
                   if not (SEEDANCE_MIN_SEC - 0.01 <= float(s.get("duration_sec", 0)) <= SEEDANCE_MAX_SEC + 0.01)]
        checks.append(
            _check("S4_duration", "ok" if not illegal else "error",
                   "所有鏡頭時長在 4-30s 內" if not illegal else f"鏡頭超窗：{illegal}")
        )
        ordered = sorted(shots, key=lambda s: s.get("start_sec", 0))
        contiguous = abs(float(ordered[0].get("start_sec", -1))) < 0.05
        for a, b in zip(ordered, ordered[1:]):
            if abs(float(a.get("end_sec", 0)) - float(b.get("start_sec", 0))) > 0.1:
                contiguous = False
                break
        total = float(ordered[-1].get("end_sec", 0))
        total_ok = target == 0.0 or abs(total - target) < 0.5
        checks.append(
            _check("S4_continuity", "ok" if contiguous and total_ok else "error",
                   "鏡頭無縫連續且總長閉合" if contiguous and total_ok
                   else f"鏡頭不連續或總長不符（{total:.1f}s vs {target:.1f}s）")
        )

    # S5 zero dialogue
    zd = episode.get("zero_dialogue") is True
    leaked = [s.get("shot_number") for s in shots if str(s.get("dialogue", "")).strip()]
    checks.append(
        _check("S5_zero_dialogue", "ok" if zd and not leaked else "error",
               "零對白合規" if zd and not leaked else "對白洩漏或 zero_dialogue 未設 True")
    )

    # S6 character references present per shot
    no_char = [s.get("shot_number") for s in shots if not s.get("characters")]
    checks.append(
        _check("S6_characters", "ok" if not no_char else "warn",
               "每鏡皆有角色引用" if not no_char else f"缺少角色引用：{no_char}")
    )

    # S7 cue placeholders
    todo_cues = sum(1 for s in shots if str(s.get("audio_cue", "")).startswith("TODO"))
    checks.append(
        _check("S7_audio_cue", "ok" if todo_cues == 0 else "warn",
               "audio_cue 已對齊" if todo_cues == 0 else f"{todo_cues} 鏡 audio_cue 尚未對齊歌詞/能量段")
    )

    counts = {
        "ok": sum(1 for c in checks if c["level"] == "ok"),
        "warn": sum(1 for c in checks if c["level"] == "warn"),
        "error": sum(1 for c in checks if c["level"] == "error"),
    }
    return {"checks": checks, "counts": counts, "pass": counts["error"] == 0}


def format_report(result: dict[str, Any]) -> str:
    """Human-readable one-screen report for terminal/chat review."""
    lines = ["=== Story Room Critic (story_room.v1) ==="]
    for c in result["checks"]:
        lines.append(f"[{c['level'].upper():5s}] {c['code']}: {c['message']}")
    cnt = result["counts"]
    lines.append(f"RESULT ok={cnt['ok']} warn={cnt['warn']} error={cnt['error']} "
                 f"-> {'PASS' if result['pass'] else 'FAIL'}")
    return "\n".join(lines)
