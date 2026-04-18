#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【CTO v9.5 庫存清洗腳本】migrate_v95_vault.py
=======================================================

目的：執行庫存大清洗，使整個系統符合 v9.5 的 derivation_count <= 2 鐵律

流程：
1. 強制備份 rs_music_vault.db → rs_music_vault_backup_v9.db
2. 掃描資料庫，標記所有 derivation_count >= 3 的記錄為待歸檔
3. 掃描 vault_ready_for_mix/，移動所有待歸檔檔案到 ceo_archived_beats/
4. 生成清洗報告
"""

import os
import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
#  路徑定義
# ─────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

DATA_DIR = config.workspace_root / "assets" / "data"
VAULT_DB = DATA_DIR / "rs_music_vault.db"
VAULT_BACKUP = DATA_DIR / "rs_music_vault_backup_v9.db"
VAULT_READY = config.workspace_root / "assets" / "audio" / "vault_ready_for_mix"
ARCHIVED_BEATS = config.workspace_root / "assets" / "audio" / "ceo_archived_beats"
LEARNING_LOG = config.workspace_root / "project_learning.md"

# ─────────────────────────────────────────────
#  日誌與報告用函式
# ─────────────────────────────────────────────
def print_header():
    """清洗腳本標題"""
    print("\n" + "=" * 80)
    print("【CTO v9.5 庫存清洗 Migration 腳本】")
    print("=" * 80)

def log_migration(msg: str):
    """列印與記錄訊息"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[MIGRATE_V95][{timestamp}] {msg}"
    print(log_msg)

def log_to_learning(msg: str):
    """寫入 project_learning.md"""
    try:
        with open(LEARNING_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n【v9.5 庫存清洗】{msg}")
    except Exception as e:
        print(f"⚠️  無法寫入日誌: {e}")

# ─────────────────────────────────────────────
#  Step 1: 備份資料庫
# ─────────────────────────────────────────────
def backup_database():
    """強制備份資料庫"""
    log_migration("【Step 1】強制備份資料庫檔案...")
    
    if not VAULT_DB.exists():
        log_migration("❌ 找不到資料庫: " + str(VAULT_DB))
        return False
    
    try:
        shutil.copy2(VAULT_DB, VAULT_BACKUP)
        backup_size = VAULT_BACKUP.stat().st_size / (1024 ** 2)
        log_migration(f"✅ 備份完成: {VAULT_BACKUP.name} ({backup_size:.1f} MB)")
        return True
    except Exception as e:
        log_migration(f"❌ 備份失敗: {e}")
        return False

# ─────────────────────────────────────────────
#  Step 2: 掃描與標記過度衍生文件
# ─────────────────────────────────────────────
def mark_retired_tracks():
    """掃描資料庫，將 derivation_count >= 3 的記錄標記為待歸檔"""
    log_migration("【Step 2】掃描資料庫，查詢待歸檔文件...")
    
    try:
        conn = sqlite3.connect(VAULT_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 查詢所有 derivation_count >= 3 的記錄 (正確表名: audio_assets)
        cursor.execute("""
            SELECT track_id, derivation_count
            FROM audio_assets 
            WHERE derivation_count >= 3
        """)
        
        retired_tracks = cursor.fetchall()
        
        if not retired_tracks:
            log_migration(f"✅ 統計: 無需清洗 (derivation_count < 3 的記錄已滿足要求)")
            conn.close()
            return []
        
        log_migration(f"⚠️  發現 {len(retired_tracks)} 個過度衍生記錄，準備歸檔...")
        
        retired_ids = []
        for row in retired_tracks:
            track_id = row["track_id"]
            deriv_count = row["derivation_count"]
            
            # 記錄此 track_id 為待封存狀態（檔案稍後移動）
            retired_ids.append(track_id)
            log_migration(f"  📌 待歸檔: {track_id} (deriv_count={deriv_count})")
        
        conn.close()
        
        log_migration(f"✅ 資料庫掃描完成: 共 {len(retired_ids)} 個記錄待歸檔")
        return retired_ids
        
    except sqlite3.Error as e:
        log_migration(f"❌ 資料庫操作失敗: {e}")
        return []

# ─────────────────────────────────────────────
#  Step 3: 掃描與移動過度衍生文件
# ─────────────────────────────────────────────
def archive_retired_files(retired_ids: list):
    """掃描 vault_ready_for_mix/，移動待歸檔檔案到冷凍庫"""
    log_migration("【Step 3】掃描並移動待歸檔文件到冷凍庫...")
    
    if not retired_ids:
        log_migration("ℹ️  無待歸檔記錄，跳過檔案移動")
        return 0
    
    # 確保冷凍庫目錄存在
    ARCHIVED_BEATS.mkdir(parents=True, exist_ok=True)
    
    if not VAULT_READY.exists():
        log_migration(f"⚠️  Vault 目錄不存在: {VAULT_READY}")
        return 0
    
    moved_count = 0
    
    try:
        # 掃描 vault_ready_for_mix/ 中的所有 WAV 檔案
        for wav_file in VAULT_READY.glob("*.wav"):
            filename = wav_file.name
            
            # 檢查是否屬於待歸檔記錄
            # 根據檔名推測 track_id（假設檔名包含 track_id 或其衍生）
            for retired_id in retired_ids:
                if retired_id in filename:
                    try:
                        dest_path = ARCHIVED_BEATS / filename
                        shutil.move(str(wav_file), str(dest_path))
                        moved_count += 1
                        log_migration(f"  🗂️  移動: {filename} → ceo_archived_beats/")
                    except Exception as e:
                        log_migration(f"  ❌ 移動失敗 {filename}: {e}")
                    break
    
    except Exception as e:
        log_migration(f"❌ 檔案掃描失敗: {e}")
    
    log_migration(f"✅ 檔案移動完成: 共 {moved_count} 個檔案移至冷凍庫")
    return moved_count

# ─────────────────────────────────────────────
#  Step 4: 生成清洗報告
# ─────────────────────────────────────────────
def generate_cleanup_report():
    """生成清洗統計報告"""
    log_migration("【Step 4】生成清洗統計報告...")
    
    try:
        conn = sqlite3.connect(VAULT_DB)
        cursor = conn.cursor()
        
        # 統計各分類 (正確表名: audio_assets)
        cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE derivation_count = 0")
        count_new = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE derivation_count = 1")
        count_gen1 = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE derivation_count = 2")
        count_gen2 = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE derivation_count >= 3")
        count_retired = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE derivation_count <= 2")
        count_active = cursor.fetchone()[0]
        
        conn.close()
        
        # 打印報告
        report = f"""
【清洗統計報告】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 新歌 (deriv_count=0)：{count_new} 個
✅ 一代衍生 (deriv_count=1)：{count_gen1} 個
✅ 二代衍生 (deriv_count=2)：{count_gen2} 個
🗑️  待歸檔 (deriv_count>=3)：{count_retired} 個
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 金庫有效記錄：{count_active} 個
📊 金庫總計 (含待歸檔)：{count_active + count_retired} 個

【新比例確認】
🎯 新歌佔比：{count_new / max(count_active, 1) * 100:.1f}% (目標 >= 50%)
🎯 一代佔比：{count_gen1 / max(count_active, 1) * 100:.1f}% (目標 = 25%)
🎯 二代佔比：{count_gen2 / max(count_active, 1) * 100:.1f}% (目標 = 25%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        log_migration(report)
        log_to_learning(report)
        
        return {
            "new": count_new,
            "gen1": count_gen1,
            "gen2": count_gen2,
            "retired": count_retired,
            "active": count_active
        }
        
    except Exception as e:
        log_migration(f"❌ 報告生成失敗: {e}")
        return None

# ─────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────
def main():
    """執行完整的清洗流程"""
    print_header()
    
    # Step 1: 備份
    if not backup_database():
        log_migration("❌ 備份失敗，中止清洗")
        sys.exit(1)
    
    # Step 2: 掃描與標記
    retired_ids = mark_retired_tracks()
    
    # Step 3: 移動檔案
    moved_count = archive_retired_files(retired_ids)
    
    # Step 4: 生成報告
    report = generate_cleanup_report()
    
    # 最終結果
    print("\n" + "=" * 80)
    log_migration("✅ 【v9.5 庫存清洗完成】")
    print("=" * 80)
    log_migration(f"備份檔案：{VAULT_BACKUP}")
    log_migration(f"已移檔案：{moved_count} 個")
    log_migration("📝 詳細日誌已記錄至 project_learning.md")
    print("=" * 80)

if __name__ == "__main__":
    main()
