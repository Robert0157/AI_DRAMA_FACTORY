"""Offline worker delivery guards; no model inference or external services."""
import json
import shutil
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.pipeline import mac_wan_worker as worker
from scripts.pipeline.dispatch_to_mac import build_job


def test_model_frames_cover_target_without_padding():
    assert worker.to_wan_frames(5, 20) == 101
    for frames in range(1, 601):
        actual = worker.to_wan_frames(frames / 20, 20)
        assert actual >= frames
        assert (actual - 1) % 4 == 0


@pytest.mark.parametrize("duration,fps", [(0, 20), (-1, 20), (5, 0), (float("nan"), 20)])
def test_invalid_frame_requests_rejected(duration, fps):
    with pytest.raises(ValueError):
        worker.to_wan_frames(duration, fps)


def test_dispatch_compiles_distinct_seeds_and_exact_frames():
    story = {"title": "fixture", "shots": [{"no": 1, "duration_sec": 30, "prompt": "world",
             "generation_plan": {"unit_count": 6, "unit_duration_sec": 5}}]}
    job = build_job(story, None, {})
    units = job["shots"][0]["units"]
    assert len({unit["seed"] for unit in units}) == 6
    assert job["target_frames"] == 600
    assert all(unit["prompt"] == "world" for unit in units)


@pytest.mark.parametrize("case", ["missing", "changed", "short", "no_audio"])
def test_master_rejected_before_generation(tmp_path, monkeypatch, case):
    master = tmp_path / "master.wav"
    master.write_bytes(b"approved fixture")
    music = {"master_track": str(master), "sha256": worker.file_sha256(master)}
    if case == "missing":
        master.unlink()
    if case == "changed":
        master.write_bytes(b"changed fixture")
    monkeypatch.setattr(worker, "probe_video", lambda path: {
        "streams": [] if case == "no_audio" else [{"codec_type": "audio"}],
        "format": {"duration": "1" if case == "short" else "30"}})
    with pytest.raises(ValueError):
        worker.validate_master_track(music, 10)


def test_failed_qc_never_enters_done(tmp_path, monkeypatch):
    service = worker.RenderWorker(tmp_path, "http://unused", tmp_path / "work")
    job = tmp_path / "processing" / "fixture.json"
    job.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(service, "render", lambda *args: {"pass": False, "findings": ["QC failed"]})
    status = service.run_job(job, 1)
    assert status["pass"] is False
    assert (tmp_path / "failed" / "fixture" / "status.json").is_file()
    assert not (tmp_path / "done" / "fixture").exists()


def test_missing_master_blocks_before_comfy(tmp_path, monkeypatch):
    service = worker.RenderWorker(tmp_path, "http://unused", tmp_path / "work")
    job = tmp_path / "processing" / "fixture.json"
    job.write_text(json.dumps({"production": {}, "shots": [{"shot_number": 1, "duration_sec": 5}]}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(service.comfy, "precondition", lambda *args: calls.append(args))
    assert service.run_job(job, 1)["pass"] is False
    assert calls == []


@pytest.mark.parametrize("field,value", [("nb_frames", 99), ("codec_name", "hevc"),
                                        ("width", 720), ("avg_frame_rate", "24/1")])
def test_delivery_rejects_video_mismatch(monkeypatch, field, value):
    video = {"codec_type": "video", "codec_name": "h264", "width": 480, "height": 848,
             "avg_frame_rate": "20/1", "nb_frames": "100"}
    video[field] = value
    monkeypatch.setattr(worker, "probe_video", lambda path: {"streams": [video], "format": {}})
    with pytest.raises(ValueError):
        worker.verify_delivery(Path("fixture.mp4"), 480, 848, 20, 100)


@pytest.mark.parametrize("audio", [None, {"codec_type": "audio", "codec_name": "mp3", "sample_rate": "48000"},
                                  {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100"},
                                  {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "duration": "4"}])
def test_delivery_rejects_audio_mismatch(monkeypatch, audio):
    video = {"codec_type": "video", "codec_name": "h264", "width": 480, "height": 848,
             "avg_frame_rate": "20/1", "nb_frames": "100"}
    monkeypatch.setattr(worker, "probe_video", lambda path: {"streams": [video] + ([audio] if audio else [])})
    with pytest.raises(ValueError):
        worker.verify_delivery(Path("fixture.mp4"), 480, 848, 20, 100)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_ffmpeg_normalize_concat_mux_and_full_decode(tmp_path):
    """Exercise real media tools with synthetic fixtures, never production assets."""
    raw = tmp_path / "raw.mp4"
    unit = tmp_path / "unit.mp4"
    silent = tmp_path / "silent.mp4"
    master = tmp_path / "master.wav"
    final = tmp_path / "final.mp4"
    worker.run_tool([worker._tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                     "testsrc2=size=64x64:rate=20", "-frames:v", "21", "-c:v", "libx264", str(raw)], "fixture video")
    worker.run_tool([worker._tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                     "sine=frequency=440:sample_rate=48000:duration=2", str(master)], "fixture audio")
    worker.normalize_unit(raw, unit, 20, 20)
    worker.concat_clips([unit, unit], silent)
    music = {"master_track": str(master), "sha256": worker.file_sha256(master)}
    assert worker.validate_master_track(music, 2) == master
    worker.mux_master_track(silent, master, final)
    info = worker.verify_delivery(final, 64, 64, 20, 40)
    assert float(info["format"]["duration"]) == pytest.approx(2, abs=0.05)


def test_worker_lock_excludes_second_owner_and_releases(tmp_path):
    with worker.exclusive_worker(tmp_path):
        with pytest.raises(OSError):
            with worker.exclusive_worker(tmp_path):
                pytest.fail("second owner acquired a held lock")
    with worker.exclusive_worker(tmp_path):
        assert (tmp_path / ".worker.lock").is_file()


def _mock_comfy_client(tmp_path):
    client = worker.ComfyClient("http://unused")
    client.task_path = tmp_path / "task.json"
    client._post = Mock(return_value={"prompt_id": "fixture-task"})
    client._get = Mock(return_value={"fixture-task": {"outputs": {"11": {"videos": [{"filename": "test.mp4"}]}}}})
    return client


def _generation_inputs():
    return dict(prompt="fixture", negative_prompt="", width=64, height=64, frames=21,
                fps=20, steps=20, cfg=6, seed=1, filename_prefix="test", timeout_sec=1)


def test_restart_reuses_persisted_provider_task(tmp_path):
    first = _mock_comfy_client(tmp_path)
    result = first.generate(**_generation_inputs())
    second = _mock_comfy_client(tmp_path)
    assert second.generate(**_generation_inputs()) == result
    second._post.assert_not_called()


def test_submission_unknown_does_not_resubmit(tmp_path):
    client = _mock_comfy_client(tmp_path)
    client._post.side_effect = TimeoutError("response lost")
    with pytest.raises(TimeoutError):
        client.generate(**_generation_inputs())
    with pytest.raises(RuntimeError, match="outcome unknown"):
        client.generate(**_generation_inputs())
    assert client._post.call_count == 1


def test_changed_generation_inputs_do_not_reuse_task(tmp_path):
    client = _mock_comfy_client(tmp_path)
    client.generate(**_generation_inputs())
    changed = {**_generation_inputs(), "seed": 2}
    with pytest.raises(ValueError, match="different generation inputs"):
        client.generate(**changed)
    assert client._post.call_count == 1


def test_recovery_conflict_preserves_both_jobs(tmp_path):
    for bucket in ("inbox", "processing"):
        directory = tmp_path / bucket
        directory.mkdir()
        (directory / "fixture.json").write_text(bucket, encoding="utf-8")
    with pytest.raises(RuntimeError, match="recovery conflict"):
        worker.RenderWorker(tmp_path, "http://unused", tmp_path / "work")
    for bucket in ("inbox", "processing"):
        assert (tmp_path / bucket / "fixture.json").read_text(encoding="utf-8") == bucket