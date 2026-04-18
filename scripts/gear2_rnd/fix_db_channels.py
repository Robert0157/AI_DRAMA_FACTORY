#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 DB 幽靈校正腳本 (Channel 欄位強制同步)

【CTO 指令】將資料庫與硬碟的頻道認知強制対齐：
1. 包含 -18.0LUFS 的歌曲 → light_music
2. 其餘空白或 NULL → lofi (預設)

執行：python scripts/gear2_rnd/fix_db_channels.py
"""

import sqlite3
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.common.env_manager import EnvConfig as _EnvConfig
_cfg = _EnvConfig()


def fix_channels():
    """
    修復資料庫 channel 欄位，確保與硬碟文件名保持一致。
    """
    db_path = _cfg.music_db_path
    
    if not db_path.exists():
        print(f"❌ 資料庫不存在: {db_path}")
        return False
    
    print(f"🛠️  【CTO 幽靈校正】開始修復資料庫...")
    print(f"   資料庫位置: {db_path.name}")
    print(f"   修復邏輯:")
    print(f"     • -18.0LUFS → light_music")
    print(f"     • 空白 / NULL → lofi (預設)")
    print(f"   " + "="*60)
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # 1. 將包含 -18.0LUFS 的歌曲標記為 light_music
        print(f"\n【步驟 1】掃描並標記 light_music 頻道...")
        cursor.execute("""
            UPDATE audio_assets 
            SET channel = 'light_music' 
            WHERE track_id LIKE '%-18.0LUFS%'
        """)
        updated_light = cursor.rowcount
        print(f"   ✅ 成功校正為 light_music: {updated_light} 筆記錄")
        
        # 2. 將未設置或為空的標記為預設 lofi
        print(f"\n【步驟 2】掃描並預設 lofi 頻道...")
        cursor.execute("""
            UPDATE audio_assets 
            SET channel = 'lofi' 
            WHERE channel IS NULL OR channel = ''
        """)
        updated_lofi = cursor.rowcount
        print(f"   ✅ 成功預設為 lofi: {updated_lofi} 筆記錄")
        
        # 3. 驗證修復結果
        print(f"\n【步驟 3】驗證修復結果...")
        cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE channel = 'light_music'")
        light_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE channel = 'lofi'")
        lofi_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE channel IS NULL OR channel = ''")
        null_count = cursor.fetchone()[0]
        
        print(f"   統計結果:")
        print(f"     • light_music: {light_count} 首")
        print(f"     • lofi: {lofi_count} 首")
        print(f"     • 未標記: {null_count} 首 ⚠️" if null_count > 0 else "     • 未標記: {null_count} 首 ✅")
        
        conn.commit()
        conn.close()
        
        print(f"\n" + "="*60)
        print(f"✅ 【CTO 幽靈校正】完成！資料庫已同步至硬碟狀態")
        print(f"   系統現已準備好進行頻道隔離選曲！")
        print(f"="*60)
        
        return True
        
    except sqlite3.DatabaseError as e:
        print(f"\n❌ 資料庫錯誤: {e}")
        return False
    except Exception as e:
        print(f"\n❌ 未預期的錯誤: {e}")
        return False


if __name__ == "__main__":
    success = fix_channels()
    exit(0 if success else 1)
