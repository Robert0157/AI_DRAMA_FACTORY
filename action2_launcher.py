#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Action 2 啟動器 - 使用新下載的高質量自然音效執行母帶製作
"""
import subprocess
import os
import sys
from pathlib import Path

# 設定環境
os.environ['PATH'] = r"C:\Program Files (x86)\sox-14-4-2;C:\ffmpeg\bin;" + os.environ.get('PATH', '')

print("\n" + "=" * 80)
print("🎵 Action 2: 母帶製作 + Telegram Demo 發送")
print("=" * 80)
print("\n📌 使用新下載的高質量自然音效:")
print("  • birds-on-a-river.wav (河邊鳥鳴)")
print("  • birdsound.wav (鳥聲)")
print("  • flowing-river.wav (河水流動)")
print("  • frog-forest.wav (青蛙雨林)")
print("  • frogs.wav (青蛙鳴聲)")
print("  • rain.wav (雨聲)")
print("  • small-brook-flowing-around-rocks.wav (小溪流)")
print("  • swallows.wav (燕子鳴聲)")
print("\n🔧 執行参數:")
print("  --decay-sec 1.2 (Lo-Fi Reverb 衰減)")
print("  --sfx-volume 0.10 (SFX 音量)")
print("  --clip-threshold-db -3.0 (剪裁阈值)")
print("  --seed 42 (隨機種子)")
print("  --timeout-sec 180 (單首3分鐘超時)")

print("\n" + "=" * 80)
print("⏳ 正在啟動 audio_mastering_engine...")
print("=" * 80)

try:
    cmd = [
        sys.executable,
        "-B",
        "scripts/gear1_prod/audio_mastering_engine.py",
        "--decay-sec", "1.2",
        "--sfx-volume", "0.10",
        "--clip-threshold-db", "-3.0",
        "--seed", "42",
        "--timeout-sec", "180"
    ]
    
    result = subprocess.run(cmd, cwd="f:/AI_DRAMA_FACTORY")
    sys.exit(result.returncode)
    
except Exception as e:
    print(f"\n❌ 啟動失敗: {e}")
    sys.exit(1)
