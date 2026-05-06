#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
首尾 Loop 接縫檢查（音訊優先）
================================
比對成片「開頭」與「結尾」同一長度音訊窗，評估 YouTube Shorts / 循環播放時
首尾相接是否大致連貫（非感知模型，僅能量形狀相似度）。

長片（預設 > skip_if_longer_than_sec）不自動做全檔首尾比對（音樂長帶通常刻意有起承轉合，
首尾本來就不該相同）；仍可用 CLI 強制檢查。

環境變數：
  AI_DRAMA_LOOP_SEAM_STRICT=1  — multi_scene 管線在檢查失敗時視為失敗（預設僅警告）
"""

from __future__ import annotations

import argparse
import math
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@dataclass
class LoopSeamReport:
    ok: bool
    skipped: bool
    reason: str
    mae: Optional[float]
    threshold: float
    window_sec: float
    duration_sec: Optional[float]
    has_audio: bool

    def exit_code(self) -> int:
        if self.skipped:
            return 0
        return 0 if self.ok else 1


def _which_or_name(name: str) -> str:
    from shutil import which

    w = which(name)
    return w if w else name


def _ffprobe_duration_sec(path: Path, ffprobe: str) -> Optional[float]:
    try:
        out = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if out.returncode != 0:
            return None
        return float(out.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, OSError):
        return None


def _ffprobe_has_audio(path: Path, ffprobe: str) -> bool:
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        return False


def _extract_pcm_mono(path: Path, *, start_sec: float, duration_sec: float, ffmpeg: str) -> Optional[bytes]:
    """s16le mono 48kHz PCM."""
    if duration_sec <= 0 or start_sec < 0:
        return None
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_sec:.6f}",
        "-i",
        str(path),
        "-t",
        f"{duration_sec:.6f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-f",
        "s16le",
        "-",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        if out.returncode != 0:
            return None
        return out.stdout
    except (subprocess.TimeoutExpired, OSError):
        return None


def _pcm_to_norm_f32(data: bytes):
    """Return list of float32 -1..1 (numpy-free)."""
    n = len(data) // 2
    if n == 0:
        return []
    fmt = "<" + "h" * n
    samples = struct.unpack(fmt, data[: n * 2])
    return [s / 32768.0 for s in samples]


def _rms_normalize(samples: list[float]) -> list[float]:
    if not samples:
        return samples
    mean = sum(samples) / len(samples)
    centered = [x - mean for x in samples]
    acc = sum(x * x for x in centered)
    rms = math.sqrt(acc / len(centered)) if centered else 0.0
    if rms < 1e-8:
        return centered
    inv = 1.0 / rms
    return [x * inv for x in centered]


def _mae(a: list[float], b: list[float]) -> float:
    m = min(len(a), len(b))
    if m == 0:
        return 1.0
    return sum(abs(a[i] - b[i]) for i in range(m)) / m


def check_loop_seam_media(
    media_path: Path,
    *,
    window_sec: float = 0.45,
    mae_threshold: float = 0.20,
    skip_if_longer_than_sec: float = 600.0,
    ffmpeg: Optional[str] = None,
    ffprobe: Optional[str] = None,
) -> LoopSeamReport:
    """
    比對音訊開頭與結尾窗（RMS 正規化後 MAE）。數值越小越「像」。

    skip_if_longer_than_sec:
        超過此時長的檔案不自動檢查（長片預設跳過）；設為 None 或 <=0 表示永不因此跳過。
    """
    ffmpeg = ffmpeg or _which_or_name("ffmpeg")
    ffprobe = ffprobe or _which_or_name("ffprobe")
    path = Path(media_path)
    if not path.is_file():
        return LoopSeamReport(
            ok=False,
            skipped=False,
            reason="file_missing",
            mae=None,
            threshold=mae_threshold,
            window_sec=window_sec,
            duration_sec=None,
            has_audio=False,
        )

    dur = _ffprobe_duration_sec(path, ffprobe)
    has_audio = _ffprobe_has_audio(path, ffprobe)

    skip_long = skip_if_longer_than_sec is not None and skip_if_longer_than_sec > 0
    if skip_long and dur is not None and dur > skip_if_longer_than_sec:
        return LoopSeamReport(
            ok=True,
            skipped=True,
            reason=f"longform_skip(dur={dur:.1f}s > {skip_if_longer_than_sec}s)",
            mae=None,
            threshold=mae_threshold,
            window_sec=window_sec,
            duration_sec=dur,
            has_audio=has_audio,
        )

    if dur is not None and dur < window_sec * 2 + 0.05:
        return LoopSeamReport(
            ok=False,
            skipped=False,
            reason="too_short_for_window",
            mae=None,
            threshold=mae_threshold,
            window_sec=window_sec,
            duration_sec=dur,
            has_audio=has_audio,
        )

    if not has_audio:
        return LoopSeamReport(
            ok=True,
            skipped=True,
            reason="no_audio_stream",
            mae=None,
            threshold=mae_threshold,
            window_sec=window_sec,
            duration_sec=dur,
            has_audio=False,
        )

    head_raw = _extract_pcm_mono(path, start_sec=0.0, duration_sec=window_sec, ffmpeg=ffmpeg)
    tail_start = max(0.0, (dur or 0.0) - window_sec) if dur is not None else 0.0
    tail_raw = _extract_pcm_mono(path, start_sec=tail_start, duration_sec=window_sec, ffmpeg=ffmpeg)

    if not head_raw or not tail_raw:
        return LoopSeamReport(
            ok=False,
            skipped=False,
            reason="pcm_extract_failed",
            mae=None,
            threshold=mae_threshold,
            window_sec=window_sec,
            duration_sec=dur,
            has_audio=True,
        )

    ha = _rms_normalize(_pcm_to_norm_f32(head_raw))
    tb = _rms_normalize(_pcm_to_norm_f32(tail_raw))
    mae = _mae(ha, tb)
    ok = mae <= mae_threshold
    reason = "ok" if ok else "mae_above_threshold"
    return LoopSeamReport(
        ok=ok,
        skipped=False,
        reason=reason,
        mae=mae,
        threshold=mae_threshold,
        window_sec=window_sec,
        duration_sec=dur,
        has_audio=True,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="首尾音訊 loop 接縫檢查（MAE / RMS 正規化）")
    parser.add_argument("media", type=Path, help="影片或音訊檔")
    parser.add_argument("--window", type=float, default=0.45, help="首尾取樣窗（秒）")
    parser.add_argument("--threshold", type=float, default=0.20, help="MAE 通過門檻（越小越嚴）")
    parser.add_argument(
        "--skip-longer-than",
        type=float,
        default=None,
        metavar="SEC",
        help="超過此秒數則跳過檢查（管線預設 600；CLI 未指定則一律檢查不分長短）",
    )
    args = parser.parse_args(argv)

    rep = check_loop_seam_media(
        args.media,
        window_sec=args.window,
        mae_threshold=args.threshold,
        skip_if_longer_than_sec=args.skip_longer_than,
    )
    if rep.skipped:
        print(f"SKIP: {rep.reason} duration={rep.duration_sec}")
        return 0
    if rep.mae is not None:
        print(f"MAE={rep.mae:.5f} threshold={rep.threshold} window={rep.window_sec}s ok={rep.ok} ({rep.reason})")
    else:
        print(f"FAIL: {rep.reason}")
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
