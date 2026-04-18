#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.gear1_prod.audio_mastering_engine import _export_loudnorm_direct, _extract_demo_60sec
from scripts.gear1_prod.telegram_approval_gate import TelegramApprovalGate

TARGETS = [
    "TimeExpansion_v15_01_8036cc8d.mp3",
    "TimeExpansion_v15_02_d454c18b.mp3",
    "Taipei_Midnight_Expansion_Test_661d6897.mp3",
    "Coastal_Circuit_Loop_db191d33.mp3",
    "Coastal_Circuit_Loop_d8bbf4ec.mp3",
    "Soft_Coffee_Steam_16a88762.mp3",
    "Soft_Coffee_Steam_c33ed473.mp3",
    "_0577c2a1.mp3",
    "_2a607201.mp3",
    "Vast_Stillness_94802326.mp3",
]


def main() -> None:
    workspace = Path(config.workspace_root)
    raw = workspace / "assets" / "audio" / "raw_tracks"
    mastered = workspace / "assets" / "audio" / "mastered_tracks"
    demo_root = mastered / "_demo_60sec"
    demo_root.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"

    queue_path = workspace / "assets" / ".approval_queue.json"
    queue_data = json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.exists() else {"queue": []}
    existing_track_names = {r.get("track_name") for r in queue_data.get("queue", [])}

    gate = TelegramApprovalGate()

    queued_new = 0
    skipped_existing = 0

    for name in TARGETS:
        mp3_path = raw / name
        if not mp3_path.exists():
            print(f"[WARN] missing raw: {name}")
            continue

        stem = mp3_path.stem
        wav_path = mastered / f"{stem}.wav"
        if not wav_path.exists():
            _export_loudnorm_direct(
                ffmpeg_bin=ffmpeg,
                input_mp3=mp3_path,
                output_wav=wav_path,
                track_title=stem,
                track_author="R&S Echoes",
                target_lufs=-16,
                timeout_sec=300,
                dry_run=False,
            )
            print(f"[MASTERED] {wav_path.name}")

        demo_path = demo_root / f"{stem}_demo_60sec.mp3"
        ok = _extract_demo_60sec(wav_path, demo_path, ffmpeg, timeout_sec=120)
        if not ok:
            print(f"[WARN] demo failed: {stem}")
            continue

        if stem in existing_track_names:
            skipped_existing += 1
            print(f"[SKIP] already queued: {stem}")
            continue

        track_id = gate.enqueue_track_for_approval(track_name=stem, demo_path=demo_path)
        asyncio.run(gate.send_demo_to_ceo(track_id))
        queued_new += 1
        print(f"[QUEUED] {stem} -> {track_id}")

    print(f"[SUMMARY] queued_new={queued_new}, skipped_existing={skipped_existing}")


if __name__ == "__main__":
    main()
