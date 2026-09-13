"""Unit tests for the mir_v1 music timeline planner (offline, no audio IO).

Covers the CEO-frozen semantics (2026-09-13):
  D1  unique (source, in, out) triples -> zero replays by construction
  D2  1.6 s global shot floor; 4.5 s absolute cap incl. the tail merge
  plus determinism, frame budget, JSON round-trip and validator behaviour.
"""
import pytest

from scripts.pipeline.music_timeline import (
    MusicAnalysis,
    SourceSpec,
    TimelinePlan,
    load_plan,
    plan_from_analysis,
    save_plan,
    validate_plan,
)


def _analysis(**overrides) -> MusicAnalysis:
    """Synthetic landmarks: dense beats/onsets and a simple energy curve."""
    base = {
        "sha256": "ab" * 32,
        "duration_sec": 60.0,
        "bpm": 120.0,
        "beats": [round(i * 0.5, 3) for i in range(1, 120)],
        "onsets": [round(i * 0.25 + 0.1, 3) for i in range(1, 240)],
        "rms_times": [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        "rms": [0.1, 0.5, 0.9, 0.3, 0.7, 0.2, 0.6],
        "peak_t": 20.0,
        "calm_t": 0.0,
    }
    base.update(overrides)
    return MusicAnalysis(**base)


def _sources(count: int = 4, duration: float = 60.0) -> list[SourceSpec]:
    return [SourceSpec(path=f"unit{i}.mp4", duration_sec=duration) for i in range(count)]


def test_shot_lengths_respect_floor_and_cap():
    plan = plan_from_analysis(_analysis(), 30.0, _sources(), seed=1)
    assert validate_plan(plan) == []
    for shot in plan.shots:
        length = shot.end_sec - shot.start_sec
        assert 1.6 - 1e-6 <= length <= 4.5 + 1e-6


def test_frames_sum_matches_timeline_exactly():
    plan = plan_from_analysis(_analysis(), 47.3, _sources(), seed=2)
    assert sum(shot.frames for shot in plan.shots) == round(47.3 * 20)


def test_boundaries_cover_zero_to_duration():
    plan = plan_from_analysis(_analysis(), 30.0, _sources(), seed=3)
    assert plan.boundaries[0] == 0.0
    assert abs(plan.boundaries[-1] - 30.0) < 0.01
    assert all(a < b for a, b in zip(plan.boundaries, plan.boundaries[1:]))


def test_deterministic_with_seed():
    first = plan_from_analysis(_analysis(), 30.0, _sources(), seed=5)
    second = plan_from_analysis(_analysis(), 30.0, _sources(), seed=5)
    assert first.boundaries == second.boundaries
    assert [s.source for s in first.shots] == [s.source for s in second.shots]


def test_adjacent_sources_differ():
    plan = plan_from_analysis(_analysis(), 40.0, _sources(), seed=4)
    sources = [shot.source for shot in plan.shots]
    assert all(a != b for a, b in zip(sources, sources[1:]))


def test_unique_triples_zero_replays():
    plan = plan_from_analysis(_analysis(), 40.0, _sources(), seed=6)
    triples = [(s.source, s.in_offset_sec, s.out_offset_sec) for s in plan.shots]
    assert len(set(triples)) == len(triples)


def test_validator_flags_short_shot():
    plan = plan_from_analysis(_analysis(), 30.0, _sources(), seed=7)
    data = plan.to_json_dict()
    data["shots"][0] = {**data["shots"][0], "end_sec": data["shots"][0]["start_sec"] + 0.5,
                        "frames": 10}
    broken = TimelinePlan.from_json_dict(data)
    errors = validate_plan(broken)
    assert any("shorter than" in error for error in errors)


def test_json_roundtrip(tmp_path):
    plan = plan_from_analysis(_analysis(), 25.0, _sources(), seed=8)
    target = tmp_path / "plan.json"
    save_plan(plan, target)
    loaded = load_plan(target)
    assert loaded.shots == plan.shots
    assert loaded.boundaries == plan.boundaries
    assert loaded.source_use_count == plan.source_use_count


def test_source_pool_too_small_raises():
    with pytest.raises(RuntimeError, match="too small"):
        plan_from_analysis(_analysis(), 100.0, _sources(count=2, duration=10.0), seed=9)
