from __future__ import annotations

from scripts.story_room.mv_strategy import (
    apply_music_world_strategy,
    validate_music_world_story,
)
from scripts.story_room.world_library import (
    all_worlds,
    draft_from_seed,
    mutate,
    novelty,
)


def _seed_story(topic: str) -> dict:
    """Minimal drama-shaped story for the world-first transform."""
    return {
        "topic": topic,
        "variant": 1,
        "beats": [{"index": 1, "act": 1, "name": "世界建立", "intent": "建立世界"}],
        "acts": [
            {"act": 1, "title": "第一幕", "synopsis": "建立主角所處的世界與日常，環境主導"}
        ],
        "shots": [
            {
                "no": 1,
                "title": "鏡1",
                "desc": "建立主角所處的世界與日常，環境主導",
                "duration_sec": 20.0,
            }
        ],
    }


def test_non_builtin_topic_passes_the_contract() -> None:
    """A world that is not a built-in seed must still satisfy validation."""
    story = apply_music_world_strategy(_seed_story("某個尚未收錄的世界"), "某個尚未收錄的世界", 1)
    result = validate_music_world_story(story)
    assert result["pass"], result["findings"]
    assert (story["world_bible"].get("chronicle") or "").strip()


def test_world_first_intent_removes_the_protagonist() -> None:
    story = apply_music_world_strategy(_seed_story("測試世界"), "測試世界", 1)
    assert "主角" not in story["shots"][0]["desc"]
    assert "主角" not in story["acts"][0]["synopsis"]


def test_library_contains_the_harvested_worlds() -> None:
    library = all_worlds()
    for name in ("深夜霓虹列車", "未來日常", "上古中國穿越", "聖誕美術館之夜"):
        assert name in library


def test_novelty_flags_a_near_duplicate() -> None:
    library = all_worlds()
    twin = mutate(library["深夜霓虹列車"], "time_of_day", "night")
    assert novelty(twin, library) < 0.34


def test_intake_matches_the_night_train_seed() -> None:
    draft = draft_from_seed("AI Music Video - Neon Train at 3AM (Late Night LoFi)", "lofi")
    assert draft["template"]["figures"] == "unnamed"
    assert "霓虹" in draft["template"]["palette"]


def test_mutation_changes_only_the_target_axis() -> None:
    library = all_worlds()
    base = library["未來日常"]
    derived = mutate(base, "season", "冬")
    assert derived["palette"] == base["palette"]
    assert "落雪" in derived["weather"]
    assert derived["derived_from"] == {"axis": "season", "value": "冬"}


def test_unenriched_intake_draft_is_blocked_from_production() -> None:
    """A world that still says 待補 must fail the production contract."""
    story = apply_music_world_strategy(_seed_story("某個尚未收錄的世界"), "某個尚未收錄的世界", 1)
    story["world_bible"]["palette"] = "待補：三色主調"
    result = validate_music_world_story(story)
    assert not result["pass"]
    assert any("待補" in finding for finding in result["findings"])
