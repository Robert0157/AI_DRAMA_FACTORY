#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.gear1_prod.kling_api_engine import fatal_log


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, timeout=180, capture_output=True)


def _ffprobe_duration(video_path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        text=True,
        timeout=30,
    ).strip()
    return float(out)


def _build_ref_segment(source: Path, target: Path, start_sec: int, duration_sec: int, vf_filter: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        str(source),
        "-t",
        str(duration_sec),
        "-vf",
        vf_filter,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        str(target),
    ]
    _run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare 12 sequential motion refs with single-subject letterbox")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--source-video", required=True)
    parser.add_argument("--segment-sec", type=int, default=5)
    parser.add_argument("--segments", type=int, default=12)
    args = parser.parse_args()

    workspace = Path(config.workspace_root)
    source_video = Path(args.source_video)
    if not source_video.is_absolute():
        source_video = workspace / source_video

    try:
        if not source_video.exists():
            raise RuntimeError(f"source video not found: {source_video}")

        total_needed = args.segment_sec * args.segments
        src_duration = _ffprobe_duration(source_video)
        if src_duration < total_needed:
            raise RuntimeError(
                f"source video too short: duration={src_duration:.2f}s, required={total_needed}s"
            )

        refs_dir = workspace / "assets" / "video_clips" / args.job_id / "motion_refs"

        # 複雜邏輯說明：先做中央單人裁切，再等比縮放與補黑邊到 960x960，避免上半身檢測失敗。
        vf_filter = (
            "crop=100:300:240:20,"
            "drawbox=x=0:y=0:w=22:h=ih:color=black:t=fill,"
            "drawbox=x=78:y=0:w=22:h=ih:color=black:t=fill,"
            "scale=960:960:force_original_aspect_ratio=decrease,"
            "pad=960:960:(ow-iw)/2:(oh-ih)/2:color=black"
        )

        outputs: list[str] = []
        for idx in range(1, args.segments + 1):
            start_sec = (idx - 1) * args.segment_sec
            ref_path = refs_dir / f"ref_{idx:02d}.mp4"
            _build_ref_segment(source_video, ref_path, start_sec, args.segment_sec, vf_filter)
            outputs.append(str(ref_path))
            print(f"[REF] built ref_{idx:02d}.mp4 start={start_sec}s")

        manifest_path = refs_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "job_id": args.job_id,
                    "source_video": str(source_video),
                    "segments": args.segments,
                    "segment_sec": args.segment_sec,
                    "outputs": outputs,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        print(f"[REF] completed: {refs_dir}")
        print(f"[REF] manifest: {manifest_path}")
    except Exception as exc:  # noqa: BLE001
        fatal_log(exc, label="prepare_motion_refs")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
