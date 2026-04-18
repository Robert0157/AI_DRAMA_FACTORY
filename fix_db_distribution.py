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
    
    # 先查找要更新的記錄
    cursor.execute("""
        SELECT track_id FROM audio_assets 
        WHERE channel = 'light_music' 
        AND derivation_count = 0 
        LIMIT 5
    """)
    tracks_to_update = cursor.fetchall()
    
    # 更新這些記錄
    for (track_id,) in tracks_to_update:
        cursor.execute(
            "UPDATE audio_assets SET derivation_count = 1 WHERE track_id = ?",
            (track_id,)
        )
    
    conn.commit()
    print(f"✓ 已將 {len(tracks_to_update)} 首新歌改為 Gen1 (derivation_count=1)")
    
    # 檢查新的分佈
    cursor.execute("""
        SELECT derivation_count, COUNT(*) as count 
        FROM audio_assets 
        WHERE channel = 'light_music'
        GROUP BY derivation_count
        ORDER BY derivation_count
    """)
    print("\n修復後的分佈：")
    for row in cursor.fetchall():
        print(f"  derivation_count={row[0]}: {row[1]} 首")
    
    conn.close()
else:
    print("[INFO] 資料庫不存在")

