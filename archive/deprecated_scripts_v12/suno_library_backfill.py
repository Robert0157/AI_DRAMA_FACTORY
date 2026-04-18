#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


def _fetch_library() -> list[dict]:
    req = urllib.request.Request("http://localhost:3000/api/get", method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return []


def _safe_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad else c for c in name)
    return out.strip().replace(" ", "_")


def _append_project_learning(message: str) -> None:
    learning_path = Path(config.workspace_root) / "project_learning.md"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"\n\n## [{stamp}] suno_library_backfill.py Fatal\n"
        f"- Error: {message}\n"
        "- Action: Pipeline halted with sys.exit(1).\n"
    )
    existing = learning_path.read_text(encoding="utf-8") if learning_path.exists() else ""
    learning_path.write_text(existing + entry, encoding="utf-8")


def _run_mastering_pipeline(timeout_sec: int) -> None:
    script = Path(config.workspace_root) / "scripts" / "gear1_prod" / "audio_mastering_engine.py"
    if not script.exists():
        raise FileNotFoundError(f"audio_mastering_engine.py not found: {script}")

    cmd = [sys.executable, str(script)]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if result.returncode != 0:
        stderr_tail = (result.stderr or "")[-2000:]
        stdout_tail = (result.stdout or "")[-2000:]
        raise RuntimeError(
            "audio_mastering_engine failed"
            f"\nreturncode={result.returncode}"
            f"\nSTDOUT tail:\n{stdout_tail}"
            f"\nSTDERR tail:\n{stderr_tail}"
        )

    print("[PIPELINE] audio_mastering_engine.py completed.")
    out_tail = (result.stdout or "")[-2000:]
    if out_tail:
        print("[PIPELINE] mastering tail:")
        print(out_tail)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill raw_tracks from Suno account library and trigger mastering+Telegram QA")
    parser.add_argument("--target-new", type=int, default=10)
    parser.add_argument("--mastering-timeout-sec", type=int, default=3600)
    args = parser.parse_args()

    raw_tracks = Path(config.workspace_root) / "assets" / "audio" / "raw_tracks"
    raw_tracks.mkdir(parents=True, exist_ok=True)

    before = len([p for p in raw_tracks.iterdir() if p.is_file()])
    print(f"[RAW] before_count={before}")

    items = _fetch_library()
    print(f"[LIB] fetched_items={len(items)}")

    # 優先選 complete/streaming 且有 audio_url 的曲目
    candidates = []
    for t in items:
        status = str(t.get("status", "")).lower()
        audio_url = t.get("audio_url") or t.get("stream_audio_url")
        if status in {"complete", "streaming"} and audio_url:
            candidates.append(t)

    # 以 created_at 由新到舊排序（若存在）
    candidates.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)

    added = 0
    for t in candidates:
        if added >= args.target_new:
            break

        track_id = str(t.get("id", "unknown"))
        title = _safe_name(str(t.get("title", "untitled")))
        audio_url = t.get("audio_url") or t.get("stream_audio_url")
        ext = ".mp3"

        dst = raw_tracks / f"{title}_{track_id[:8]}{ext}"
        if dst.exists():
            continue

        try:
            urllib.request.urlretrieve(audio_url, str(dst))  # noqa: S310
            added += 1
            print(f"  [OK] {dst.name}")
        except Exception as e:  # noqa: BLE001
            print(f"  [WARN] download failed: {track_id} -> {e}")

    after = len([p for p in raw_tracks.iterdir() if p.is_file()])
    print(f"[RAW] added={added}, after_count={after}")

    if added < args.target_new:
        _append_project_learning(
            f"Backfill downloaded {added} tracks, below target {args.target_new}."
        )
        print("[FATAL] backfill below target; halted.")
        sys.exit(1)

    # 嚴格遵循生命週期：下載到 raw_tracks 後，立即進入母帶與 Telegram QA。
    try:
        _run_mastering_pipeline(timeout_sec=args.mastering_timeout_sec)
    except Exception as e:  # noqa: BLE001
        _append_project_learning(str(e))
        print(f"[FATAL] mastering pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
