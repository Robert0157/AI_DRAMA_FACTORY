#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚨 【v12.11 深度重建工具】force_reset_db.py
==========================================

功能：若偵測到 root_id 缺失，直接刪除舊的 vault.db 並根據最新 Schema 重建。

使用方法：
    python scripts/gear2_rnd/force_reset_db.py [--check-only]

【v12.11 CTO 指令】：
- 如果 --check-only 標誌被套用，則僅檢查而不進行重建
- 如果偵測到 root_id 列缺失，自動刪除舊 DB 並重新建立
- 新 DB 將基於最新的 VaultDatabase Schema
"""

import os
import sys
import sqlite3
from pathlib import Path
import argparse
import datetime

# 添加專案根目錄到 Python 路徑
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # f:\AI_DRAMA_FACTORY
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.gear2_rnd.vault_database import VaultDatabase
from scripts.common.env_manager import EnvConfig

config = EnvConfig()


def _log(msg: str) -> None:
    """記錄訊息"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def check_root_id_column() -> bool:
    """
    檢查 vault.db 中的 audio_assets 表是否存在 root_id 列。
    
    返回：
        True: root_id 列存在，資料庫結構正常
        False: root_id 列缺失，需要進行深度重建
    """
    db_path = config.music_db_path
    
    if not db_path.exists():
        _log(f"📁 資料庫不存在: {db_path}")
        _log(f"   → 將在深度重建時建立新資料庫")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        cursor = conn.cursor()
        
        # 使用 PRAGMA table_info 檢查列結構
        cursor.execute("PRAGMA table_info(audio_assets)")
        columns = cursor.fetchall()
        conn.close()
        
        column_names = [col[1] for col in columns]
        _log(f"✅ 資料庫結構檢查:")
        _log(f"   表: audio_assets")
        _log(f"   列數: {len(column_names)}")
        _log(f"   列名: {', '.join(column_names)}")
        
        if "root_id" not in column_names:
            _log(f"❌ 偵測到結構缺陷: root_id 列缺失！")
            return False
        
        if "channel" not in column_names:
            _log(f"❌ 偵測到結構缺陷: channel 列缺失！")
            return False
        
        _log(f"✅ 資料庫結構通過驗證，root_id 與 channel 列均存在")
        return True
        
    except sqlite3.OperationalError as e:
        _log(f"⚠️  無法查詢表結構: {e}")
        _log(f"   → 表可能不存在，將進行深度重建")
        return False
    except Exception as e:
        _log(f"❌ 資料庫檢查失敗: {e}")
        return False


def force_reset_database() -> bool:
    """
    【v12.11 深度重建】執行資料庫重建流程：
    1. 備份舊 DB
    2. 刪除舊 DB
    3. 根據最新 Schema 重建
    
    返回：
        True: 重建成功
        False: 重建失敗
    """
    db_path = config.music_db_path
    backup_dir = Path(config.workspace_root) / "assets" / "backup_archive"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    _log(f"\n{'='*60}")
    _log(f"🚨 【v12.11 深度重建】開始資料庫強制重置")
    _log(f"{'='*60}\n")
    
    # 步驟 1：備份舊 DB
    if db_path.exists():
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"rs_music_vault_backup_{timestamp}.db"
            
            _log(f"📦 步驟 1: 備份舊資料庫")
            _log(f"   源: {db_path}")
            _log(f"   目標: {backup_path}")
            
            import shutil
            shutil.copy2(str(db_path), str(backup_path))
            
            _log(f"✅ 備份成功: {backup_path.name}")
            
        except Exception as e:
            _log(f"❌ 備份失敗: {e}")
            _log(f"   (將繼續進行刪除和重建，但舊資料可能遺失)")
    else:
        _log(f"ℹ️  步驟 1: 舊資料庫不存在，跳過備份")
    
    # 步驟 2：刪除舊 DB
    try:
        _log(f"\n🗑️  步驟 2: 刪除舊資料庫")
        if db_path.exists():
            db_path.unlink()
            _log(f"✅ 已刪除: {db_path}")
        else:
            _log(f"ℹ️  舊資料庫不存在，無需刪除")
    except Exception as e:
        _log(f"❌ 刪除失敗: {e}")
        return False
    
    # 步驟 3：根據最新 Schema 重建
    try:
        _log(f"\n🔨 步驟 3: 根據最新 Schema 重建資料庫")
        
        # 初始化 VaultDatabase，它會自動建立新資料庫
        vault = VaultDatabase()
        
        _log(f"✅ 資料庫已重建於: {db_path}")
        
        # 驗證新資料庫的結構
        conn = sqlite3.connect(str(db_path), timeout=5)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(audio_assets)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        conn.close()
        
        _log(f"\n✅ 新資料庫結構驗證:")
        _log(f"   表: audio_assets")
        _log(f"   列: {', '.join(column_names)}")
        
        # 確認關鍵列存在
        required_cols = {"root_id", "channel", "track_id", "derivation_count"}
        missing_cols = required_cols - set(column_names)
        if missing_cols:
            _log(f"❌ 新資料庫仍缺少列: {missing_cols}")
            return False
        
        _log(f"✅ 所有必需列都日已建立")
        return True
        
    except Exception as e:
        _log(f"❌ 重建失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(
        description="【v12.11】VaultDatabase 深度重建工具"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="僅檢查資料庫結構，不執行重建"
    )
    args = parser.parse_args()
    
    _log(f"【v12.11 深度重建工具】force_reset_db.py 啟動")
    _log(f"工作目錄: {config.workspace_root}")
    _log(f"資料庫路徑: {config.music_db_path}\n")
    
    # 檢查 root_id 列是否存在
    has_root_id = check_root_id_column()
    
    _log(f"")
    
    if has_root_id:
        _log(f"✅ 資料庫結構正常，無需重建")
        return 0
    
    if args.check_only:
        _log(f"ℹ️  使用了 --check-only 標誌，不執行重建")
        _log(f"💡 要進行強制重建，請執行: python {__file__}")
        return 1
    
    # 執行深度重建
    _log(f"⚠️  偵測到資料庫結構缺陷，準備進行強制重建...")
    _log(f"")
    
    success = force_reset_database()
    
    _log(f"")
    if success:
        _log(f"{'='*60}")
        _log(f"✅ 【v12.11 深度重建完成】資料庫已成功重置")
        _log(f"   新資料庫已準備就緒，所有列均已初始化")
        _log(f"   下次執行 pipeline_runner.py 時將自動使用新資料庫")
        _log(f"{'='*60}")
        return 0
    else:
        _log(f"{'='*60}")
        _log(f"❌ 【v12.11 深度重建失敗】")
        _log(f"   請檢查日誌並聯絡工程師排查問題")
        _log(f"{'='*60}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
