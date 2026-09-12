"""Offline checks for the weekly reference-intake planner (no network access)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reference_intake import stock_search as ss  # noqa: E402


def test_query_config_loads():
    config = ss.load_query_config()
    assert config["worlds"] and config["generic"]


def test_rotation_is_deterministic():
    config = ss.load_query_config()
    first = ss.build_query_plan(config, week=36)
    second = ss.build_query_plan(config, week=36)
    assert first == second and first


def test_rotation_moves_to_next_world_next_week():
    config = ss.load_query_config()
    week36 = {label for label, _ in ss.build_query_plan(config, week=36)}
    week37 = {label for label, _ in ss.build_query_plan(config, week=37)}
    assert week36 != week37


def test_orientation_mapping():
    assert ss.map_orientation("pexels", "portrait") == "portrait"
    assert ss.map_orientation("pixabay", "portrait") == "vertical"
    assert ss.map_orientation("unsplash", "landscape") == "landscape"


def test_unknown_world_is_rejected():
    config = ss.load_query_config()
    try:
        ss.build_query_plan(config, week=1, world="不存在的世界")
    except SystemExit:
        return
    raise AssertionError("unknown world must raise SystemExit")


def test_week_plan_covers_both_channels():
    config = ss.load_query_config()
    labels = [label for label, _ in ss.build_query_plan(config, week=40)]
    lofi_labels = {label for label in labels if label.startswith("lofi.")}
    lm_labels = {label for label in labels if label.startswith("light_music.")}
    assert len(lofi_labels) == 1, f"expected exactly one lofi type per week, got {lofi_labels}"
    assert len(lm_labels) == 1, f"expected exactly one light_music type per week, got {lm_labels}"


def test_type_restriction_returns_single_label():
    config = ss.load_query_config()
    plan = ss.build_query_plan(config, week=40, type_label="lofi.dream_objects")
    assert plan
    assert {label for label, _ in plan} == {"lofi.dream_objects"}


def test_unknown_type_is_rejected():
    config = ss.load_query_config()
    try:
        ss.build_query_plan(config, week=40, type_label="lofi.nope")
    except SystemExit:
        return
    raise AssertionError("unknown type label must raise SystemExit")
