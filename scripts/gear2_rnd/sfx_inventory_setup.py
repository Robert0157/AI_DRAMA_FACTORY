#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SFX 清單建置工具 - 將現有音檔映射到 CEO 指定的標準名稱
"""

import shutil
from pathlib import Path

# 現有的高品質音檔對應到 CEO 要求的清單
sfx_dir = Path("assets/sfx")
mapping = {
    "ambient.wav": "rain.wav",              # 環境音 → 雨聲
    "nature_ambience.wav": "river.wav",     # 自然環境 → 溪流聲
    "nature_gentle.wav": "wind.wav"         # 輕柔自然 → 微風聲
}

print("\n🔄 重新映射 SFX 檔案為 CEO 要求的清單...")
print("="*70)

success_count = 0

for source, target in mapping.items():
    source_path = sfx_dir / source
    target_path = sfx_dir / target
    
    if not source_path.exists():
        print(f"  ⚠️  未找到源檔案: {source}")
        continue
    
    if target_path.exists():
        print(f"  ⏭️  目標檔案已存在: {target} (跳過)")
        success_count += 1
        continue
    
    try:
        shutil.copy2(source_path, target_path)
        source_size_mb = source_path.stat().st_size / (1024 * 1024)
        print(f"  ✅ {source:25s} → {target:25s} ({source_size_mb:.2f} MB)")
        success_count += 1
    except Exception as e:
        print(f"  ❌ {source} → {target}: {e}")

print("="*70)
print(f"\n✅ 映射完成: {success_count}/{len(mapping)} 個檔案")

# 驗證最終結果
print("\n📊 最終 SFX 目錄結構:")
wav_files = sorted(sfx_dir.glob("*.wav"))
for f in wav_files:
    size_mb = f.stat().st_size / (1024 * 1024)
    print(f"  • {f.name:20s} ({size_mb:8.2f} MB)")

required_files = ['rain.wav', 'river.wav', 'wind.wav', 'birds.wav', 'crickets.wav']
prepared = [f.name for f in wav_files if f.name in required_files]
print(f"\n📌 已準備: {len(prepared)}/5 核心 SFX 檔案")
for fname in required_files:
    status = "✅" if fname in prepared else "⏳"
    print(f"  {status} {fname}")
