# -*- coding: utf-8 -*-
"""Unit tests for scripts/gear2_rnd/loop_seam_checker.py (mocked FFmpeg)."""

import struct
from pathlib import Path
from unittest import mock

from scripts.gear2_rnd.loop_seam_checker import (
    _mae,
    _rms_normalize,
    check_loop_seam_media,
)


def test_rms_normalize_and_mae_identical():
    samples = [0.1, -0.1, 0.05, -0.05]
    a = _rms_normalize(samples)
    b = _rms_normalize(list(samples))
    assert _mae(a, b) < 1e-9


def test_mae_different():
    a = _rms_normalize([1.0, 0.0, -1.0, 0.0])
    b = _rms_normalize([0.0, 1.0, 0.0, -1.0])
    assert _mae(a, b) > 0.1


def _s16le_sine(freq_hz: float, sr: int, n: int) -> bytes:
    import math

    out = bytearray()
    for i in range(n):
        v = int(32767 * 0.5 * math.sin(2 * math.pi * freq_hz * i / sr))
        out.extend(struct.pack("<h", max(-32768, min(32767, v))))
    return bytes(out)


@mock.patch("scripts.gear2_rnd.loop_seam_checker._extract_pcm_mono")
@mock.patch("scripts.gear2_rnd.loop_seam_checker._ffprobe_has_audio")
@mock.patch("scripts.gear2_rnd.loop_seam_checker._ffprobe_duration_sec")
def test_check_pass_identical_tail_head(mock_dur, mock_audio, mock_pcm, tmp_path):
    sr = 48000
    window = 0.45
    n = int(sr * window)
    pcm = _s16le_sine(440.0, sr, n)
    mock_dur.return_value = 120.0
    mock_audio.return_value = True
    mock_pcm.side_effect = [pcm, pcm]

    p = tmp_path / "x.mp4"
    p.write_bytes(b"dummy")

    rep = check_loop_seam_media(p, window_sec=window, mae_threshold=0.25)
    assert not rep.skipped
    assert rep.ok
    assert rep.mae is not None
    assert rep.mae < 0.01


@mock.patch("scripts.gear2_rnd.loop_seam_checker._extract_pcm_mono")
@mock.patch("scripts.gear2_rnd.loop_seam_checker._ffprobe_has_audio")
@mock.patch("scripts.gear2_rnd.loop_seam_checker._ffprobe_duration_sec")
def test_check_fail_different_signals(mock_dur, mock_audio, mock_pcm, tmp_path):
    sr = 48000
    window = 0.45
    n = int(sr * window)
    mock_dur.return_value = 90.0
    mock_audio.return_value = True
    mock_pcm.side_effect = [_s16le_sine(200.0, sr, n), _s16le_sine(3000.0, sr, n)]

    p = tmp_path / "y.mp4"
    p.write_bytes(b"dummy")

    rep = check_loop_seam_media(p, window_sec=window, mae_threshold=0.15)
    assert not rep.skipped
    assert not rep.ok
    assert rep.reason == "mae_above_threshold"


@mock.patch("scripts.gear2_rnd.loop_seam_checker._ffprobe_duration_sec")
def test_longform_skip(mock_dur, tmp_path):
    mock_dur.return_value = 3600.0
    p = tmp_path / "long.mp4"
    p.write_bytes(b"x")
    rep = check_loop_seam_media(p, skip_if_longer_than_sec=600.0)
    assert rep.skipped
    assert "longform_skip" in rep.reason


def test_missing_file():
    rep = check_loop_seam_media(Path("/nonexistent/path/file.mp4"))
    assert not rep.ok
    assert rep.reason == "file_missing"
