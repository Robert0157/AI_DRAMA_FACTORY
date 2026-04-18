#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性修復腳本：將 e2e_smoke 誤封存的 lofi 金庫還原
  ceo_archived_beats/lofi/*.wav  → vault_ready_for_mix/lofi/
  ceo_archived_beats/lofi/*.mp3  → ceo_approved_beats/lofi/
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common.env_manager import config

root = Path(config.workspace_root) / "assets" / "audio"
archived = root / "ceo_archived_beats" / "lofi"
vault    = root / "vault_ready_for_mix"  / "lofi"
ceo      = root / "ceo_approved_beats"   / "lofi"

vault.mkdir(parents=True, exist_ok=True)
ceo.mkdir(parents=True, exist_ok=True)

wav_masters = [f for f in archived.glob("*.wav") if f.is_file()]
raw_mp3s    = [f for f in archived.glob("*.mp3") if f.is_file()]

print(f"封存目錄中：{len(wav_masters)} 個 WAV 母帶 / {len(raw_mp3s)} 個 MP3 原始")
print("開始還原...\n")

moved_vault = moved_ceo = 0
errors = []

for f in wav_masters:
    dst = vault / f.name
    if dst.exists():
        print(f"  [SKIP 已存在] {f.name}")
        continue
    try:
        shutil.move(str(f), str(dst))
        moved_vault += 1
    except Exception as e:
        errors.append(f"{f.name}: {e}")

for f in raw_mp3s:
    dst = ceo / f.name
    if dst.exists():
        print(f"  [SKIP 已存在] {f.name}")
        continue
    try:
        shutil.move(str(f), str(dst))
        moved_ceo += 1
    except Exception as e:
        errors.append(f"{f.name}: {e}")

print()
print("=== 還原結果 ===")
print(f"  WAV → vault_ready_for_mix/lofi/ : {moved_vault} 個")
print(f"  MP3 → ceo_approved_beats/lofi/  : {moved_ceo} 個")
if errors:
    print(f"  ❌ 錯誤 {len(errors)} 個：")
    for e in errors[:10]:
        print(f"     {e}")

print()
print("=== 驗證 ===")
vault_wavs = len(list(vault.glob("*.wav")))
ceo_mp3s   = len(list(ceo.glob("*.mp3")))
archived_left = len([f for f in archived.iterdir() if f.is_file()])
print(f"  vault_ready_for_mix/lofi/ : {vault_wavs} 個 WAV")
print(f"  ceo_approved_beats/lofi/  : {ceo_mp3s} 個 MP3")
print(f"  ceo_archived_beats/lofi/  : {archived_left} 個（剩餘）")

if vault_wavs > 0:
    print("\n✅ lofi 金庫已還原！")
else:
    print("\n⚠️  WAV 還原異常，請手動確認 archived 目錄內容")
