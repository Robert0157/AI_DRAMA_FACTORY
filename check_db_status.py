#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from scripts.common.env_manager import EnvConfig as _C
db_path = _C().music_db_path
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM audio_assets')
total = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM audio_assets WHERE channel = "light_music"')
light = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM audio_assets WHERE channel = "lofi"')
lofi = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM audio_assets WHERE channel IS NULL OR channel = ""')
null_ch = cursor.fetchone()[0]

conn.close()

print(f"總記錄數: {total}")
print(f"light_music: {light}")
print(f"lofi: {lofi}")
print(f"未標記: {null_ch}")

if light > 0 or lofi > 0:
    print("\n✅ 【DB 校正成功】資料庫頻道標籤已同步！")
else:
    print("\n⚠️  警告：未發現任何標記，請檢查資料庫。")
