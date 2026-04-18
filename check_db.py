#!/usr/bin/env python3
import sqlite3
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from scripts.common.env_manager import EnvConfig as _C
db_path = _C().music_db_path
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 檢查整體記錄
    cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE channel = 'light_music'")
    count = cursor.fetchone()[0]
    print(f"Light Music 總記錄: {count}")
    
    # 按 derivation_count 分組
    cursor.execute("""
        SELECT derivation_count, COUNT(*) as count 
        FROM audio_assets 
        WHERE channel = 'light_music'
        GROUP BY derivation_count
        ORDER BY derivation_count
    """)
    for row in cursor.fetchall():
        print(f"  derivation_count={row[0]}: {row[1]} 首")
    
    conn.close()
else:
    print("[INFO] 資料庫不存在")


