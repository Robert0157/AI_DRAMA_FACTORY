#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本驗證與備份腳本
"""
import hashlib
from pathlib import Path
from datetime import datetime
import shutil

print('=' * 70)
print('📋 lofi_assembler.py 版本驗證與備份系統')
print('=' * 70)

current_file = Path(r'scripts\gear1_prod\lofi_assembler.py')
patched_file = Path(r'scripts\gear1_prod\lofi_assembler_v2_cto_patched.py')

# 1. 計算 MD5
print('\n🔍 計算檔案 MD5...')
with open(current_file, 'rb') as f:
    current_hash = hashlib.md5(f.read()).hexdigest()

with open(patched_file, 'rb') as f:
    patched_hash = hashlib.md5(f.read()).hexdigest()

print(f'   當前版本 MD5: {current_hash[:16]}...')
print(f'   修復版本 MD5: {patched_hash[:16]}...')

# 2. 版本判定
if current_hash == patched_hash:
    status = '✅ 最新修復版本'
    is_latest = True
else:
    status = '❌ 舊版本'
    is_latest = False

print(f'\n{status}')

# 3. 核心特徵檢查
print('\n🔍 核心特徵檢查:')
with open(current_file, 'r', encoding='utf-8') as f:
    content = f.read()
    has_channel = '--channel' in content
    has_light_music = 'light_music' in content
    has_patch_mark = '【修復' in content

print(f'   --channel 參數: {"✅" if has_channel else "❌"}')
print(f'   light_music 支持: {"✅" if has_light_music else "❌"}')
print(f'   4層修復標記: {"✅" if has_patch_mark else "❌"}')

# 4. 備份舊版本
print('\n💾 執行備份...')

if is_latest:
    # 最新版本：備份已有的 .bak 檔案
    backups = list(Path(r'scripts\gear1_prod').glob('lofi_assembler.py.bak*'))
    if backups:
        print(f'   發現 {len(backups)} 個舊備份：')
        for b in backups:
            print(f'      - {b.name}')
        
        # 清理舊備份（保留最新的 3 個）
        backups_sorted = sorted(backups, key=lambda x: x.stat().st_mtime, reverse=True)
        if len(backups_sorted) > 3:
            print(f'\n   清理多餘備份（保留最新 3 個）...')
            for old_backup in backups_sorted[3:]:
                old_backup.unlink()
                print(f'      ✅ 已刪除: {old_backup.name}')
else:
    # 舊版本：立即備份
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = current_file.with_name(f'lofi_assembler.py.bak_OLD_{ts}')
    shutil.copy2(current_file, backup_path)
    print(f'   ✅ 已備份舊版本: {backup_path.name}')
    
    # 提示更新
    print(f'\n⚠️  建議立即更新到最新修復版本！')
    print(f'   執行命令：')
    print(f'   Remove-Item scripts\\gear1_prod\\lofi_assembler.py')
    print(f'   Copy-Item scripts\\gear1_prod\\lofi_assembler_v2_cto_patched.py scripts\\gear1_prod\\lofi_assembler.py')

print('\n' + '=' * 70)
print('✅ 驗證完成')
print('=' * 70)
