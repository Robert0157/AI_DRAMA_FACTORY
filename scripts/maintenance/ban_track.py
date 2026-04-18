#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ban_track.py — 單曲基因級下架工具
==================================

【功能】
根據關鍵字查找音軌，執行「基因級下架」：
- 將匹配的軌道標記為已封存（is_archived = 1）
- 同時將其所有衍生製品（同一 root_id）也標記為已封存
- 確保「連根拔除」，不留痕跡

【使用】
python ban_track.py "Vast Stillness"
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.gear2_rnd.vault_database import VaultDatabase


def ban_track_by_keyword(keyword: str) -> None:
    """
    【基因級下架】根據關鍵字查找並下架音軌及其所有衍生物。
    
    參數:
        keyword: 歌曲名稱或關鍵字（用於模糊搜尋）
    """
    try:
        vault = VaultDatabase()
        
        # 步驟 1: 查詢所有未封存的軌道
        print(f"\n[BAN] 開始搜尋: 【{keyword}】")
        print("-" * 80)
        
        # 直接查詢 SQL
        try:
            import sqlite3
            db_path = config.music_db_path
            
            if not db_path.exists():
                print(f"❌ 資料庫不存在: {db_path}")
                print(f"   (請確認已執行過產線至少一次以建立資料庫)")
                return
            
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 搜尋名稱包含關鍵字的所有軌道
            query = """
                SELECT id, name, root_id, is_archived 
                FROM audio_assets 
                WHERE name LIKE ? AND is_archived = 0
                ORDER BY root_id
            """
            cursor.execute(query, (f"%{keyword}%",))
            matching_tracks = [dict(row) for row in cursor.fetchall()]
            
            if not matching_tracks:
                print(f"⚠️  未找到匹配的軌道")
                print(f"   (搜尋關鍵字: {keyword})")
                conn.close()
                return
            
            # 步驟 2: 收集所有相關的 root_id
            root_ids_to_ban = set()
            for track in matching_tracks:
                root_ids_to_ban.add(track['root_id'])
                print(f"  ✓ 找到: {track['name']} (ID: {track['id']}, ROOT: {track['root_id']})")
            
            print(f"\n[BAN] 準備下架: {len(root_ids_to_ban)} 個基因家族")
            
            # 步驟 3: 將所有相關軌道標記為已封存
            total_banned = 0
            for root_id in root_ids_to_ban:
                update_query = """
                    UPDATE audio_assets 
                    SET is_archived = 1 
                    WHERE root_id = ? AND is_archived = 0
                """
                cursor.execute(update_query, (root_id,))
                total_banned += cursor.rowcount
                
                # 查詢該基因家族的所有成員
                select_query = """
                    SELECT name FROM audio_assets 
                    WHERE root_id = ? AND is_archived = 1
                """
                cursor.execute(select_query, (root_id,))
                archived_members = [row[0] for row in cursor.fetchall()]
                print(f"  ✓ 基因 {root_id} 已下架 ({len(archived_members)} 個成員)")
            
            conn.commit()
            conn.close()
            
            print(f"\n✅ 基因級下架完成！")
            print(f"   共下架: {total_banned} 個軌道")
            print(f"   已斷絕: {len(root_ids_to_ban)} 個基因血脈")
            print("-" * 80)
            
        except sqlite3.Error as e:
            print(f"❌ 資料庫查詢失敗: {e}")
            return
        except Exception as e:
            print(f"❌ 資料庫操作異常: {e}")
            return
        
    except Exception as e:
        print(f"❌ 下架程序異常: {e}")
        sys.exit(1)


def main():
    """主程式入口"""
    if len(sys.argv) < 2:
        print("使用方法: python ban_track.py <關鍵字>")
        print("範例: python ban_track.py \"Vast Stillness\"")
        sys.exit(1)
    
    keyword = sys.argv[1]
    ban_track_by_keyword(keyword)


if __name__ == "__main__":
    main()
