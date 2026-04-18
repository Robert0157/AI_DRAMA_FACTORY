#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音樂優先策略編排器 (v8.4)

功能：
1. 讀取音樂檔案（mp3/wav 等）
2. 使用 librosa 進行節拍偵測 (beat_track, onset_detect)
3. 輸出標準格式的 beats.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import librosa
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


def _find_music_file(job_id: str, audio_filename: str = None) -> Path:
    """查找 zaouli_test_XXX 目錄下的指定或優先 mp3 檔案。"""
    audio_dir = Path(config.workspace_root) / "assets" / "audio" / job_id
    if not audio_dir.exists():
        raise FileNotFoundError(f"Audio directory not found: {audio_dir}")
    
    # 若指定檔名，優先使用
    if audio_filename:
        specified_path = audio_dir / audio_filename
        if specified_path.exists():
            print(f"[ORCHESTRATOR] using specified audio: {audio_filename}")
            return specified_path
        else:
            raise FileNotFoundError(f"Specified audio not found: {specified_path}")
    
    # 優先查找特定名稱的檔案
    preferred_names = ["music_epic.mp3", "african_tribal_001.mp3", "This is not just music..mp3"]
    for pref in preferred_names:
        pref_path = audio_dir / pref
        if pref_path.exists():
            print(f"[ORCHESTRATOR] found preferred audio: {pref}")
            return pref_path
    
    # 回退：查找第一個 mp3
    mp3_files = list(audio_dir.glob("*.mp3"))
    if mp3_files:
        selected = mp3_files[0]
        print(f"[ORCHESTRATOR] auto-selected audio: {selected.name}")
        return selected
    
    # 查找 wav
    wav_files = list(audio_dir.glob("*.wav"))
    if wav_files:
        selected = wav_files[0]
        print(f"[ORCHESTRATOR] auto-selected audio: {selected.name}")
        return selected
    
    raise FileNotFoundError(f"No audio files found in: {audio_dir}")


def extract_beats(music_path: Path) -> dict:
    """
    使用 librosa 進行節拍偵測。
    
    返回：
    {
        "bpm": float,
        "beat_times": [float, ...],  # 重拍時間（秒）
        "onset_times": [float, ...]   # 小節起點時間（秒）
    }
    """
    print(f"[ORCHESTRATOR] loading audio: {music_path.name}")
    
    # 載入音樂
    y, sr = librosa.load(str(music_path), sr=None)
    duration = librosa.get_duration(y=y, sr=sr)
    print(f"[ORCHESTRATOR] audio loaded: {duration:.2f}s @ {sr}Hz")
    
    # 節拍偵測
    print("[ORCHESTRATOR] detecting beats...")
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
    print(f"[ORCHESTRATOR] detected BPM: {tempo:.1f}")
    print(f"[ORCHESTRATOR] detected beats: {len(beats)}")
    
    # 小節起點偵測
    print("[ORCHESTRATOR] detecting onsets...")
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units='time')
    print(f"[ORCHESTRATOR] detected onsets: {len(onsets)}")
    
    return {
        "bpm": float(tempo),
        "beat_times": beats.tolist(),
        "onset_times": onsets.tolist(),
        "duration_sec": float(duration),
    }


def extract_beats_only(job_id: str, audio_filename: str = None) -> None:
    """
    主入口：抓出節拍並寫入 beats.json。
    """
    music_path = _find_music_file(job_id, audio_filename)
    beats_data = extract_beats(music_path)
    
    # 寫入 beats.json
    output_dir = Path(config.workspace_root) / "assets" / "scripts" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "beats.json"
    
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(beats_data, fh, indent=2, ensure_ascii=False)
    
    print(f"[ORCHESTRATOR] beats.json written: {output_path}")
    print(f"[ORCHESTRATOR] summary: {beats_data['bpm']:.1f} BPM, {len(beats_data['beat_times'])} beats")
    
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="音樂優先策略編排器")
    parser.add_argument("--job-id", required=True, help="工作批次 ID (例: zaouli_test_002)")
    parser.add_argument("--audio-file", default=None, help="指定音訊檔名 (例: This is not just music..mp3)")
    args = parser.parse_args()
    
    try:
        extract_beats_only(args.job_id, args.audio_file)
    except Exception as exc:  # noqa: BLE001
        print(f"[ORCHESTRATOR][ERROR] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
