# -*- coding: utf-8 -*-
"""
Emotion Arc engine: aggregates per-shot emotions into contiguous music
segments and maps each segment to a Suno-compatible prompt.

Key idea (CEO alignment): the storyboard LLM already emits `emotion`,
`emotion_intensity` and `bgm_prompt` per shot; this module turns those into
a timed BGM plan so sad scenes get sad music, suspense gets suspense music.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml

from .schemas import EmotionSegment, EpisodeDraft, StoryboardShot


class EmotionMap:
    """Loads config/emotion_map.yaml and normalizes emotion tags."""

    def __init__(self, yaml_path: Path) -> None:
        with open(yaml_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        self._canonical: Dict[str, dict] = {
            k: v for k, v in data.items() if isinstance(v, dict) and "tags" in v
        }
        self._aliases: Dict[str, str] = data.get("aliases", {}) or {}

    def canonical(self, raw_emotion: str) -> str:
        """Map any alias/Chinese word to a canonical key; fallback to 'suspense'."""
        key = str(raw_emotion or "").strip()
        if key in self._canonical:
            return key
        key_lower = key.lower()
        if key_lower in self._canonical:
            return key_lower
        if key in self._aliases:
            return self._aliases[key]
        # Fallback chain for common English words not used as keys.
        en_map = {
            "sad": "sad", "sorrow": "sad", "grief": "sad",
            "tense": "tense", "thriller": "tense", "suspenseful": "suspense",
            "horror": "horror", "scary": "horror", "fear": "horror",
            "joy": "joyful", "happy": "joyful", "cheerful": "joyful",
            "epic": "epic", "grand": "epic", "warm": "warm", "tender": "warm",
            "conflict": "conflict", "relief": "relief", "hopeful": "relief",
            "romance": "romance", "romantic": "romance",
        }
        return en_map.get(key_lower, "suspense")

    def entry(self, canonical: str) -> dict:
        return self._canonical.get(canonical, self._canonical["suspense"])

    def keys(self) -> List[str]:
        return list(self._canonical.keys())


def _intensity_boost(canonical: str, intensity: int) -> str:
    """Energy phrasing appended based on emotion_intensity (-1..3)."""
    if intensity >= 3:
        return ", escalating, climactic, peak tension"
    if intensity <= 0:
        return ", subdued, sparse, restrained"
    if intensity == 2:
        return ", building, moderately intense"
    return ""


def build_suno_prompt(emotion_map: EmotionMap, canonical: str,
                      bgm_hints: List[str], intensity: int = 1) -> str:
    """
    Compose a Suno prompt for one emotion segment.
    Always instrumental-first with explicit negative tags (no vocals),
    because dialogue/vocals come from the drama's own audio track.
    """
    e = emotion_map.entry(canonical)
    hints = ", ".join(list(dict.fromkeys([h for h in bgm_hints if h]))[:3])
    parts = [
        "ancient Chinese drama soundtrack (古風影視配樂), instrumental ONLY, NO vocals, NO lyrics, NO singing",
        e["tags"] + _intensity_boost(canonical, intensity),
        f"instruments: {e['instruments']}",
        f"tempo BPM {e['bpm']}",
        f"negative: {e['negative']}",
        "pristine studio sound, high quality, cinematic mix, seamless loop-ready",
    ]
    if hints:
        parts.append(f"scene mood hints: {hints}")
    return ", ".join(parts)


def build_emotion_arc(emotion_map: EmotionMap, draft: EpisodeDraft) -> List[EmotionSegment]:
    """
    Merge consecutive shots with the same canonical emotion into segments.
    A segment becomes a candidate Suno generation (or extend from previous).
    """
    segments: List[EmotionSegment] = []
    current: EmotionSegment | None = None

    for shot in draft.shots:
        canonical = emotion_map.canonical(shot.emotion)
        intensity = int(shot.emotion_intensity or 1)
        dur = max(0.5, float(shot.duration or 5.0))
        hint = (shot.bgm_prompt or "").strip()

        if current is None or current.emotion != canonical:
            if current is not None:
                current.suno_prompt = build_suno_prompt(
                    emotion_map, current.emotion, current.bgm_hints, current.max_intensity
                )
                segments.append(current)
            current = EmotionSegment(
                emotion=canonical,
                start_shot=shot.shot_number,
                end_shot=shot.shot_number,
                duration_sec=round(dur, 2),
                max_intensity=intensity,
                bgm_hints=[hint] if hint else [],
            )
        else:
            current.end_shot = shot.shot_number
            current.duration_sec = round(current.duration_sec + dur, 2)
            current.max_intensity = max(current.max_intensity, intensity)
            if hint and hint not in current.bgm_hints:
                current.bgm_hints.append(hint)

    if current is not None:
        current.suno_prompt = build_suno_prompt(
            emotion_map, current.emotion, current.bgm_hints, current.max_intensity
        )
        segments.append(current)

    return segments


def plan_music_jobs(emotion_map: EmotionMap, draft: EpisodeDraft) -> List[dict]:
    """
    High-level music plan consumed by the Suno driver.
    Each entry: emotion segment + whether it chains via Suno extend from the
    previous segment (true when emotions are adjacent for continuity).
    """
    arc = build_emotion_arc(emotion_map, draft)
    plan = []
    for idx, seg in enumerate(arc):
        plan.append({
            "segment_index": idx,
            "emotion": seg.emotion,
            "suno_prompt": seg.suno_prompt,
            "duration_sec": seg.duration_sec,
            "start_shot": seg.start_shot,
            "end_shot": seg.end_shot,
            "chain_from_prev": idx > 0,   # extend keeps cross-segment musical coherence
        })
    return plan
