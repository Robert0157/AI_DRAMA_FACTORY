#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【v12.9 緊急搶修】VaultDatabase 強制遷移 (Migration)

功能：
1. 檢測 vault.db 是否缺少 channel 欄位
2. 若缺少，執行 ALTER TABLE 補齊
3. 確保 pipeline_runner.py 啟動時不再報出 no such column 錯誤

執行方法：
    python scripts/gear2_rnd/migrate_db.py
"""

import sys
import sqlite3
from pathlib import Path

# 導入 VaultDatabase 以獲取 db_path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.gear2_rnd.vault_database import VaultDatabase


def check_and_migrate_vault_db():
    """檢測並遷移 vault.db，補齊缺失的欄位"""
    
    print("\n" + "="*80)
    print("【v12.9 VaultDatabase 強制遷移】")
    print("="*80)
    
    # 初始化 VaultDatabase（觸發 _initialize_database）
    vault = VaultDatabase()
    db_path = vault.db_path
    
    print(f"\n📍 資料庫位置: {db_path}")
    
    conn = sqlite3.connect(str(db_path), timeout=30)
    cursor = conn.cursor()
    
    try:
        # 檢查 audio_assets 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audio_assets'")
        if not cursor.fetchone():
            print("❌ audio_assets 表不存在！需要首次建立...")
            conn.close()
            return False
        
        # 檢查表的欄位結構（列出所有欄位）
        cursor.execute("PRAGMA table_info(audio_assets)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        print(f"\n✅ audio_assets 表已存在，包含 {len(column_names)} 個欄位：")
        for col_name in column_names:
            print(f"   - {col_name}")
        
        # 檢查是否缺少 channel 欄位
        if 'channel' not in column_names:
            print("\n⚠️  檢測到缺失欄位: channel")
            print("   正在執行 ALTER TABLE 補齊...")
            
            cursor.execute("""
                ALTER TABLE audio_assets 
                ADD COLUMN channel TEXT DEFAULT 'lofi'
            """)
            conn.commit()
            print("   ✅ channel 欄位已添加（默認值: 'lofi'）")
        else:
            print("\n✅ channel 欄位已存在，無需遷移")
        
        # 檢查是否缺少 root_id 欄位（應該已經存在）
        if 'root_id' not in column_names:
            print("\n⚠️  檢測到缺失欄位: root_id")
            print("   正在執行 ALTER TABLE 補齊...")
            
            cursor.execute("""
                ALTER TABLE audio_assets 
                ADD COLUMN root_id TEXT
            """)
            conn.commit()
            print("   ✅ root_id 欄位已添加")
        else:
            print("✅ root_id 欄位已存在，無需遷移")
        
        # 最終驗証
        cursor.execute("PRAGMA table_info(audio_assets)")
        final_columns = [col[1] for col in cursor.fetchall()]
        
        print("\n✅ 遷移完成。最終欄位清單：")
        for col_name in final_columns:
            print(f"   - {col_name}")
        
        # 打印表的 row count
        cursor.execute("SELECT COUNT(*) FROM audio_assets")
        count = cursor.fetchone()[0]
        print(f"\n📊 audio_assets 表包含 {count} 條記錄")
        
        conn.close()
        print("\n" + "="*80)
        print("🚀 VaultDatabase 遷移完成！pipeline_runner.py 現在可以安全啟動")
        print("="*80 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 遷移過程中出現錯誤: {e}")
        conn.close()
        return False


if __name__ == "__main__":
    success = check_and_migrate_vault_db()
    sys.exit(0 if success else 1)
