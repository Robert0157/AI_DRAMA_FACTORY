"""Offline checks for the CP-D world-proposal engine (no network, no commits)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reference_intake import world_proposal as wp  # noqa: E402
from scripts.story_room import world_library as wl  # noqa: E402


def _fake_manifest() -> dict:
    return {
        "schema": "reference_intake.v1",
        "items": [
            {"provider": "pexels", "id": 1, "file": "a1.jpg", "label": "lofi_aesthetic", "query": "moody neon night city"},
            {"provider": "pexels", "id": 2, "file": "a2.jpg", "label": "lofi_aesthetic", "query": "moody neon night city"},
            {"provider": "pexels", "id": 3, "file": "a3.jpg", "label": "湖光微火", "query": "lake campfire night"},
        ],
    }


def test_build_candidates_in_degraded_mode():
    manifest = _fake_manifest()
    drafts, warnings = wp.build_candidates(manifest, analyses=[], n=4)
    assert 1 <= len(drafts) <= 4
    for name, spec in drafts.items():
        assert spec["name"] == name
        assert spec.get("channel") in ("lofi", "light_music")
        assert spec.get("palette"), name
        assert spec.get("veo_prompt") and spec.get("veo_target")
        assert "novelty" in spec


def test_existing_world_labels_produce_mutants():
    manifest = _fake_manifest()
    drafts, _ = wp.build_candidates(manifest, analyses=[], n=5)
    mutants = [s for s in drafts.values() if s.get("derived_from")]
    assert mutants, "intake matching an existing world must yield derivative drafts"


def test_write_pack_files(tmp_path):
    manifest = _fake_manifest()
    drafts, warnings = wp.build_candidates(manifest, analyses=[], n=4)
    pack_dir = wp.write_pack(
        tmp_path / "cp_d" / "2026-W99",
        "2026-W99",
        drafts,
        {"generated": "2026-09-12T00:00:00", "week_path": "X", "vision": {"enabled": False}},
        manifest,
        warnings,
    )
    assert (pack_dir / "proposal.json").is_file()
    assert (pack_dir / "proposal.md").is_file()
    assert (pack_dir / "veo_prompts.txt").is_file()
    payload = json.loads((pack_dir / "proposal.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "cp_d.proposal.v1"
    assert payload["drafts"]


def test_engine_never_writes_the_world_library(tmp_path):
    library_before = wl.LIBRARY_PATH.read_text(encoding="utf-8") if wl.LIBRARY_PATH.is_file() else ""
    manifest = _fake_manifest()
    drafts, warnings = wp.build_candidates(manifest, analyses=[], n=3)
    wp.write_pack(tmp_path, "2026-W99", drafts, {"generated": "t", "week_path": "X", "vision": {}}, manifest, warnings)
    library_after = wl.LIBRARY_PATH.read_text(encoding="utf-8") if wl.LIBRARY_PATH.is_file() else ""
    assert library_before == library_after


def test_balanced_pick_alternates_channels():
    rows = [(f"lofi-{i}", 1.0, {"channel": "lofi"}) for i in range(4)]
    rows += [(f"lm-{i}", 1.0, {"channel": "light_music"}) for i in range(3)]
    picked = wp._balanced_pick(rows, 4)
    channels = {spec["channel"] for _n, _s, spec in picked}
    assert len(picked) == 4
    assert channels == {"lofi", "light_music"}, f"both channels must survive the cap: {channels}"


def test_balanced_pick_respects_novelty_floor():
    rows = [("a", 0.10, {"channel": "lofi"}), ("b", 0.90, {"channel": "lofi"})]
    picked = wp._balanced_pick(rows, 4)
    assert [name for name, _score, _spec in picked] == ["b"]


def test_pack_keeps_both_channels_when_capped():
    manifest = {
        "schema": "reference_intake.v1",
        "items": [
            {"provider": "pexels", "id": 11, "file": "l1.jpg", "label": "lofi.dream_objects", "query": "vintage globe"},
            {"provider": "pexels", "id": 12, "file": "l2.jpg", "label": "lofi.mythic_traveler", "query": "desert caravan"},
            {"provider": "pexels", "id": 13, "file": "m1.jpg", "label": "light_music.water_light", "query": "lake ripples"},
            {"provider": "pexels", "id": 14, "file": "m2.jpg", "label": "light_music.zen_dawn", "query": "zen garden"},
        ],
    }
    drafts, _ = wp.build_candidates(manifest, analyses=[], n=4)
    channels = {s.get("channel") for s in drafts.values()}
    assert channels == {"lofi", "light_music"}, f"lofi-only pack regression: {channels}"
