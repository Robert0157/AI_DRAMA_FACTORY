# -*- coding: utf-8 -*-
"""Tests for the emotion-arc -> Suno prompt mapping."""
from pathlib import Path

from auto_drama.emotion_arc import EmotionMap, build_emotion_arc, build_suno_prompt, plan_music_jobs
from auto_drama.schemas import EpisodeDraft, StoryboardShot

EMOTION_YAML = Path(__file__).resolve().parents[1] / "config" / "emotion_map.yaml"


def _shot(n: int, emotion: str, intensity: int = 1, hint: str = "") -> StoryboardShot:
    return StoryboardShot(shot_number=n, emotion=emotion,
                          emotion_intensity=intensity, bgm_prompt=hint, duration=5.0)


def test_alias_normalization():
    em = EmotionMap(EMOTION_YAML)
    assert em.canonical("懸疑") == "suspense"
    assert em.canonical("悲傷") == "sad"
    assert em.canonical("恐怖") == "horror"
    assert em.canonical("unknown_word") == "suspense"


def test_adjacent_same_emotion_merged():
    em = EmotionMap(EMOTION_YAML)
    draft = EpisodeDraft(
        episode_id="ep01", title="t",
        shots=[_shot(1, "suspense"), _shot(2, "suspense"), _shot(3, "sad"), _shot(4, "sad")],
    )
    arc = build_emotion_arc(em, draft)
    assert len(arc) == 2
    assert arc[0].emotion == "suspense" and arc[0].start_shot == 1 and arc[0].end_shot == 2
    assert arc[0].duration_sec == 10.0
    assert arc[1].emotion == "sad" and arc[1].start_shot == 3 and arc[1].end_shot == 4


def test_alternating_emotions_kept_separate():
    em = EmotionMap(EMOTION_YAML)
    draft = EpisodeDraft(
        episode_id="ep01", title="t",
        shots=[_shot(1, "suspense"), _shot(2, "sad"), _shot(3, "suspense")],
    )
    arc = build_emotion_arc(em, draft)
    assert len(arc) == 3


def test_suno_prompt_is_instrumental_and_contains_emotion():
    em = EmotionMap(EMOTION_YAML)
    prompt = build_suno_prompt(em, "sad", ["夜雨孤燈"], intensity=2)
    assert "NO vocals" in prompt
    assert "sorrowful" in prompt or "melancholic" in prompt
    assert "erhu" in prompt


def test_music_plan_chains_from_previous():
    em = EmotionMap(EMOTION_YAML)
    draft = EpisodeDraft(
        episode_id="ep01", title="t",
        shots=[_shot(1, "suspense"), _shot(2, "suspense"), _shot(3, "sad")],
    )
    plan = plan_music_jobs(em, draft)
    assert plan[0]["chain_from_prev"] is False
    assert plan[1]["chain_from_prev"] is True
    assert plan[0]["duration_sec"] == 10.0
