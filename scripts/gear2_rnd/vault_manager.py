#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
資料庫管理工具
功能：查詢、統計、導出、備份等操作
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# 導入資料庫模塊
sys.path.insert(0, str(Path(__file__).parent))
from style_database import StyleDatabase


class VaultManager:
    """資料庫管理器"""
    
    def __init__(self):
        """初始化管理器"""
        self.db = StyleDatabase()
    
    # ============= 統計函式 =============
    
    def show_statistics(self):
        """顯示資料庫統計信息"""
        stats = self.db.get_statistics()
        
        print("\n" + "="*60)
        print("📊 資料庫統計信息")
        print("="*60)
        print(f"✅ 總條目數: {stats['total_entries']}")
        print(f"✅ 成功處理: {stats['success_processed']} 個")
        print(f"❌ 失敗處理: {stats['failed_processed']} 個")
        print(f"💾 資料庫大小: {stats['database_size_mb']} MB ({stats['database_size_bytes']} 位元組)")
        print(f"📁 資料庫路徑: {stats['database_path']}")
        print("="*60 + "\n")
        
        return stats
    
    # ============= 查詢函式 =============
    
    def list_all_entries(self, limit: Optional[int] = None):
        """列出所有條目
        
        Args:
            limit: 限制數量 (可選)
        """
        entries = self.db.get_all_entries()
        
        if limit:
            entries = entries[:limit]
        
        print("\n" + "="*60)
        print(f"📚 所有條目 (顯示 {len(entries)} 個)")
        print("="*60)
        
        for idx, entry in enumerate(entries, 1):
            print(f"\n【{idx}】 {entry['source_id']}")
            print(f"    主題: {entry['theme_name']}")
            print(f"    建立於: {entry['created_at']}")
            print(f"    更新於: {entry['updated_at']}")
            print(f"    音頻提示: {entry['audio_prompt'][:100]}...")
            print(f"    影片提示: {entry['video_prompt'][:100]}...")
        
        print("\n" + "="*60 + "\n")
    
    def search_entry(self, keyword: str):
        """搜尋條目
        
        Args:
            keyword: 搜尋關鍵字
        """
        results = self.db.search_entries(keyword)
        
        print(f"\n{'='*60}")
        print(f"🔍 搜尋結果: '{keyword}' (找到 {len(results)} 個)")
        print("="*60)
        
        if not results:
            print("未找到相關條目")
        else:
            for idx, entry in enumerate(results, 1):
                print(f"\n【{idx}】 {entry['source_id']}")
                print(f"    主題: {entry['theme_name']}")
                print(f"    建立於: {entry['created_at']}")
        
        print("="*60 + "\n")
        return results
    
    def get_entry_detail(self, video_id: str):
        """獲取單個條目的詳細信息
        
        Args:
            video_id: YouTube 影片 ID
        """
        entry = self.db.get_entry(video_id)
        
        if not entry:
            print(f"\n❌ 找不到條目: {video_id}\n")
            return None
        
        print(f"\n{'='*60}")
        print(f"📄 條目詳情: {video_id}")
        print("="*60)
        print(f"ID: {entry['id']}")
        print(f"來源 ID: {entry['source_id']}")
        print(f"主題: {entry['theme_name']}")
        print(f"建立於: {entry['created_at']}")
        print(f"更新於: {entry['updated_at']}")
        
        print(f"\n【音頻提示】")
        print(f"{entry['audio_prompt']}")
        
        print(f"\n【影片提示】")
        print(f"{entry['video_prompt']}")
        print("="*60 + "\n")
        
        return entry
    
    # ============= 導出函式 =============
    
    def export_to_json(self, output_path: Optional[str] = None):
        """導出資料庫為 JSON
        
        Args:
            output_path: 輸出路徑 (可選)
        """
        result_path = self.db.export_to_json(output_path)
        
        if result_path:
            print(f"\n✅ 已導出為 JSON: {result_path}")
            
            # 顯示檔案大小
            file_size = Path(result_path).stat().st_size
            print(f"   檔案大小: {file_size / 1024:.2f} KB")
        else:
            print(f"\n❌ 導出失敗")
    
    # ============= 刪除函式 =============
    
    def delete_entry_by_id(self, video_id: str, confirm: bool = True):
        """刪除單個條目
        
        Args:
            video_id: YouTube 影片 ID
            confirm: 是否確認
        """
        entry = self.db.get_entry(video_id)
        
        if not entry:
            print(f"\n❌ 找不到條目: {video_id}\n")
            return False
        
        if confirm:
            print(f"\n⚠️  確認刪除? video_id={video_id}")
            user_input = input("輸入 'yes' 確認: ").strip().lower()
            if user_input != "yes":
                print("已取消")
                return False
        
        if self.db.delete_entry(video_id):
            print(f"\n✅ 已刪除: {video_id}")
            return True
        else:
            print(f"\n❌ 刪除失敗: {video_id}")
            return False
    
    # ============= 互動菜單 =============
    
    def interactive_menu(self):
        """互動菜單"""
        while True:
            print("\n" + "="*60)
            print("🏠 資料庫管理工具 - 主菜單")
            print("="*60)
            print("1. 顯示統計信息")
            print("2. 列出所有條目")
            print("3. 搜尋條目")
            print("4. 查看條目詳情")
            print("5. 導出為 JSON")
            print("6. 刪除條目")
            print("7. 清空所有條目 (危險!)")
            print("0. 退出")
            print("="*60)
            
            choice = input("選擇操作 (0-7): ").strip()
            
            if choice == "0":
                print("\n再見！\n")
                break
            elif choice == "1":
                self.show_statistics()
            elif choice == "2":
                limit_input = input("限制數量 (按 Enter 顯示全部): ").strip()
                limit = int(limit_input) if limit_input.isdigit() else None
                self.list_all_entries(limit)
            elif choice == "3":
                keyword = input("輸入搜尋關鍵字: ").strip()
                if keyword:
                    self.search_entry(keyword)
            elif choice == "4":
                video_id = input("輸入 video_id: ").strip()
                if video_id:
                    self.get_entry_detail(video_id)
            elif choice == "5":
                output_path = input("輸入輸出路徑 (按 Enter 使用默認): ").strip()
                output_path = output_path if output_path else None
                self.export_to_json(output_path)
            elif choice == "6":
                video_id = input("輸入要刪除的 video_id: ").strip()
                if video_id:
                    self.delete_entry_by_id(video_id)
            elif choice == "7":
                confirm = input("⚠️  確認清空所有條目？輸入 'yes' 確認: ").strip().lower()
                if confirm == "yes":
                    if self.db.clear_all():
                        print("✅ 已清空所有條目")
                    else:
                        print("❌ 清空失敗")
            else:
                print("❌ 無效選擇")


def main():
    """主程式"""
    
    # 建立管理器
    manager = VaultManager()
    
    # 檢查命令行參數
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "stats":
            manager.show_statistics()
        elif command == "list":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
            manager.list_all_entries(limit)
        elif command == "search":
            keyword = sys.argv[2] if len(sys.argv) > 2 else ""
            if keyword:
                manager.search_entry(keyword)
        elif command == "detail":
            video_id = sys.argv[2] if len(sys.argv) > 2 else ""
            if video_id:
                manager.get_entry_detail(video_id)
        elif command == "export":
            output_path = sys.argv[2] if len(sys.argv) > 2 else None
            manager.export_to_json(output_path)
        elif command == "delete":
            video_id = sys.argv[2] if len(sys.argv) > 2 else ""
            if video_id:
                manager.delete_entry_by_id(video_id, confirm=True)
        else:
            print("未知命令")
    else:
        # 啟動互動菜單
        manager.interactive_menu()


if __name__ == "__main__":
    main()
