# -*- coding: utf-8 -*-
"""End-to-end mock pipeline test (no network, no API keys)."""
import json
from pathlib import Path

from auto_drama.orchestrator import run_book_pipeline

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_inputs" / "yuewei_sample.txt"


def test_mock_pipeline_end_to_end(tmp_path):
    import auto_drama.config as cfg_mod
    from auto_drama.config import Settings
    from auto_drama.paths import Paths

    # Point outputs into an isolated temp dir for the test.
    settings = Settings({**cfg_mod.load_settings(ROOT).raw, "output": {"root": str(tmp_path / "out")}})
    paths = Paths(settings)

    text = SAMPLE.read_text(encoding="utf-8")
    summary = run_book_pipeline(
        source_text=text,
        book_title="閱微草堂筆記樣本",
        series="yuewei",
        mode="mock",
        settings=settings,
        paths=paths,
    )

    assert summary["status"] == "completed"
    episode_dir = Path(summary["episode_dir"])
    assert episode_dir.exists()

    # Storyboard + emotion arc + final artifacts all produced.
    storyboards = list(episode_dir.glob("*_storyboard.json"))
    assert storyboards, "storyboard JSON missing"
    arcs = list(episode_dir.glob("*_emotion_arc.json"))
    assert arcs, "emotion arc JSON missing"

    sb = json.loads(storyboards[0].read_text(encoding="utf-8"))
    assert sb["shots"] and sb["shots"][0]["emotion"] in (
        "suspense", "sad", "tense", "horror", "joyful", "epic", "warm",
        "conflict", "relief", "romance",
    )

    arc = json.loads(arcs[0].read_text(encoding="utf-8"))
    assert arc and "suno_prompt" in arc[0]

    finals = list(episode_dir.glob("*_final.mp4.mock"))
    assert finals, "final mock episode missing"

    manifest = json.loads((episode_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "stage1" in manifest and "stage4" in manifest
