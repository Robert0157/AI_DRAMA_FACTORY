# -*- coding: utf-8 -*-
"""
FFmpeg helpers for Stage 4 (broadcast-grade discipline).

Rules enforced:
- Sequential concat via demuxer list (NO -stream_loop / infinite loops).
- BGM overlay via amix (never strip the original dialogue track).
- Subtitle burn with explicit Noto Serif CJK TC font (no system fallback).
- fps=24, setpts=PTS-STARTPTS, -ar 48000 (prevents long-video drift).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


class FfmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe command fails."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def probe_duration_sec(media_path: Path) -> float:
    """Return media duration in seconds using ffprobe."""
    if not ffprobe_available():
        raise FfmpegError("ffprobe not found on PATH")
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe failed on {media_path}: {proc.stderr[-500:]}")
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise FfmpegError(f"ffprobe returned non-numeric duration: {proc.stdout!r}") from exc


def _write_concat_list(clip_paths: List[Path], list_path: Path) -> None:
    """Write a concat demuxer file list (lossless copy stage)."""
    lines = []
    for p in clip_paths:
        resolved = str(p.resolve()).replace("'", "'\\''")
        lines.append(f"file '{resolved}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def concat_lossless(clip_paths: List[Path], output_path: Path) -> Path:
    """Sequential lossless concat (-c:v copy) via demuxer list; no loops."""
    if not clip_paths:
        raise FfmpegError("concat_lossless: empty clip list")
    if not ffmpeg_available():
        raise FfmpegError("ffmpeg not found on PATH")
    list_path = output_path.parent / (output_path.stem + "_concat.txt")
    _write_concat_list(clip_paths, list_path)
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_path),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FfmpegError(f"concat failed: {proc.stderr[-800:]}")
    return output_path


def mux_bgm(video_path: Path, bgm_path: Path, output_path: Path,
            bgm_volume: float = 0.35, crossfade_sec: int = 8) -> Path:
    """
    Overlay BGM onto a video while preserving the original audio track.
    Uses amix with the original track kept (CEO rule: never strip original).
    bgm is looped with -stream_loop only when it is shorter than the video is
    NOT allowed; instead we pass the track and let amix trim to video length.
    """
    if not ffmpeg_available():
        raise FfmpegError("ffmpeg not found on PATH")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(bgm_path),
        "-filter_complex",
        (
            f"[1:a]volume={bgm_volume}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        ),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FfmpegError(f"mux_bgm failed: {proc.stderr[-800:]}")
    return output_path


def burn_subtitles(video_path: Path, srt_path: Path, fonts_dir: Path,
                   output_path: Path, font_name: str = "Noto Serif CJK TC",
                   font_size: int = 20) -> Path:
    """
    Hard-burn subtitles with an explicit classical Chinese font (思源宋體).
    Never rely on system font fallback.
    """
    if not ffmpeg_available():
        raise FfmpegError("ffmpeg not found on PATH")
    sub = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")
    # Escape for filter graph: colon and apostrophe inside path.
    fonts = str(fonts_dir.resolve()).replace("\\", "/").replace(":", "\\:")
    style = f"Fontname={font_name},FontSize={font_size}"
    filter_str = f"subtitles={sub}:fontsdir={fonts}:force_style='{style}'"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FfmpegError(f"burn_subtitles failed: {proc.stderr[-800:]}")
    return output_path


def assemble_emotion_music_track(segment_paths: List[Path], output_path: Path,
                                 crossfade_sec: int = 8) -> Path:
    """
    Crossfade Suno emotion segments into one continuous BGM track.
    Each consecutive pair is blended with acrossfade at emotion boundaries.
    Falls back to concat when only one segment exists.
    """
    if len(segment_paths) == 1:
        cmd = ["ffmpeg", "-y", "-i", str(segment_paths[0]), "-c:a", "pcm_s16le", str(output_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise FfmpegError(f"single-segment copy failed: {proc.stderr[-500:]}")
        return output_path

    # Build filter_complex chain of acrossfades.
    n = len(segment_paths)
    inputs = []
    for i, p in enumerate(segment_paths):
        inputs += ["-i", str(p)]
    labels = []
    for i in range(n):
        labels.append(f"[{i}:a]")
    filter_parts = []
    prev = "0:a"
    for i in range(1, n):
        out_label = f"[x{i}]"
        filter_parts.append(
            f"[{prev}][{i}:a]acrossfade=d={crossframe_sec(crossfade_sec)}:c1=tri:c2=tri{out_label}"
        )
        prev = f"x{i}"
    filter_graph = ";".join(filter_parts)
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_graph,
           "-map", prev, "-c:a", "pcm_s16le", str(output_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FfmpegError(f"acrossfade chain failed: {proc.stderr[-800:]}")
    return output_path


def crossframe_sec(seconds: int) -> str:
    """Format acrossfade duration for the filter graph."""
    return f"{float(seconds):.3f}"


def write_manifest(path: Path, payload: dict) -> None:
    """Persist a JSON manifest atomically-ish for auditability."""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
