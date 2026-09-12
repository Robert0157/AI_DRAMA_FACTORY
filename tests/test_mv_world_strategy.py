from __future__ import annotations

from scripts.story_room.agents import run_adversarial
from scripts.story_room.diversity import make_variant_plans
from scripts.story_room.mv_strategy import (
    MV_VALIDATION_TOPICS,
    validate_music_world_story,
)


def test_three_topics_have_five_unique_world_variants() -> None:
    assert len(MV_VALIDATION_TOPICS) == 3
    for topic in MV_VALIDATION_TOPICS:
        plans = make_variant_plans(topic, n=5, seed=42)
        validations = [
            validate_music_world_story(
                run_adversarial(topic, plan, offline=True)["story"]
            )
            for plan in plans
        ]
        assert all(item["pass"] for item in validations)
        assert len({item["world_signature"] for item in validations}) == 5
        assert all(item["wan_shots"] == 6 for item in validations)
        assert all(item["generation_units"] >= 35 for item in validations)