#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.gear1_prod.kling_api_engine import fatal_log


def main() -> None:
    parser = argparse.ArgumentParser(description="Build shots_for_kling with sequential motion refs")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--source-shots", required=True)
    parser.add_argument("--output-shots", required=True)
    args = parser.parse_args()

    workspace = Path(config.workspace_root)
    source_shots = Path(args.source_shots)
    output_shots = Path(args.output_shots)

    if not source_shots.is_absolute():
        source_shots = workspace / source_shots
    if not output_shots.is_absolute():
        output_shots = workspace / output_shots

    try:
        with open(source_shots, "r", encoding="utf-8") as f:
            shots = json.load(f)
        if not isinstance(shots, list) or not shots:
            raise RuntimeError(f"invalid source shots json: {source_shots}")

        refs_dir = workspace / "assets" / "video_clips" / args.job_id / "motion_refs"
        upgraded = []
        for idx, shot in enumerate(shots, start=1):
            item = dict(shot)
            item["reference_video_path"] = (
                Path("assets") / "video_clips" / args.job_id / "motion_refs" / f"ref_{idx:02d}.mp4"
            ).as_posix()
            item["reference_subject"] = "single"
            upgraded.append(item)

        output_shots.parent.mkdir(parents=True, exist_ok=True)
        with open(output_shots, "w", encoding="utf-8") as f:
            json.dump(upgraded, f, ensure_ascii=False, indent=2)

        print(f"[SHOTS] source: {source_shots}")
        print(f"[SHOTS] output: {output_shots}")
        print(f"[SHOTS] refs: {refs_dir}")
        print(f"[SHOTS] total: {len(upgraded)}")
    except Exception as exc:  # noqa: BLE001
        fatal_log(exc, label="build_motion_control_shots")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
