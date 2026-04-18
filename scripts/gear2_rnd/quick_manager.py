#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🚀 一鍵快速管理工具 (v2.0 - 關鍵字搜尋版)
快速完成: 管理/新增/刪除/更換 關鍵字、開啟批量分析等所有操作！
"""

import json
import sys
import re
from pathlib import Path
from typing import List, Dict
import subprocess
import os

# 路徑配置
WORKSPACE = Path(__file__).parent
INPUT_FILE = WORKSPACE / "video_input.txt"
DATA_DIR = WORKSPACE / "assets" / "data"
DB_PATH = DATA_DIR / "style_vault.db"
SCRIPTS_DIR = WORKSPACE / "assets" / "scripts"

# 設定工作目錄
os.chdir(WORKSPACE)

# 添加路徑
SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(WORKSPACE))

# 確保路徑存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

from style_database import StyleDatabase
from common.atomic_io import atomic_write_text, atomic_write_json


class QuickManager:
    """一鍵快速管理器 (關鍵字搜尋版)"""

    def __init__(self):
        self.db = StyleDatabase()
        self.keywords: List[str] = []
        self.load_keywords()

    def load_keywords(self):
        """讀取關鍵字列表"""
        if INPUT_FILE.exists():
            with open(INPUT_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            # 用正規表達式提取 Keyword="..." 格式
            keyword_pattern = r'Keyword="([^"]+)"'
            self.keywords = re.findall(keyword_pattern, content)

    def save_keywords(self):
        """保存關鍵字列表"""
        text = "".join([f'Keyword="{keyword}"\n' for keyword in self.keywords]) + "end\n"
        atomic_write_text(INPUT_FILE, text)

    def show_menu(self):
        """顯示主菜單"""
        print("\n" + "="*70)
        print("🚀 一鍵快速管理工具 (v3.0 - 強化版)".center(70))
        print("="*70)
        print("\n【操作選單】\n")
        print("  1️⃣  📋 查看關鍵字列表")
        print("  2️⃣  ➕ 新增關鍵字")
        print("  3️⃣  ❌ 刪除關鍵字")
        print("  4️⃣  🔄 更換關鍵字")
        print("  5️⃣  🎬 開始批量分析（YouTube+B站搜尋）")
        print("  6️⃣  📊 查看資料庫統計")
        print("  7️⃣  💾 匯出資料庫為 JSON")
        print("  8️⃣  🧹 清理舊檔案")
        print("  9️⃣  🔧 系統診斷")
        print("  🔟  🗑️  清理快取")
        print("  0️⃣  ❌ 退出程式")
        print("\n" + "="*70)

    def view_keywords(self):
        """查看關鍵字列表"""
        print("\n📋 當前關鍵字列表:")
        print("-" * 70)
        if not self.keywords:
            print("  ⚠️  列表為空")
        else:
            for i, keyword in enumerate(self.keywords, 1):
                print(f"  {i}. Keyword=\"{keyword}\"")
        print("-" * 70)

    def add_keyword(self):
        """新增關鍵字"""
        print("\n➕ 新增關鍵字")
        print("-" * 70)
        keyword = input("  輸入新關鍵字 (或按 Enter 取消): ").strip()

        if not keyword:
            print("  ⏭️  已取消")
            return

        if keyword in self.keywords:
            print("  ⚠️  該關鍵字已存在！")
            return

        self.keywords.append(keyword)
        self.save_keywords()
        print(f"  ✅ 成功新增: \"{keyword}\"")

    def delete_keyword(self):
        """刪除關鍵字"""
        print("\n❌ 刪除關鍵字")
        print("-" * 70)
        self.view_keywords()

        if not self.keywords:
            return

        try:
            idx = int(input("\n  輸入要刪除的編號 (或按 Enter 取消): ")) - 1
            if 0 <= idx < len(self.keywords):
                removed = self.keywords.pop(idx)
                self.save_keywords()
                print(f"  ✅ 已刪除: \"{removed}\"")
            else:
                print("  ❌ 無效編號！")
        except ValueError:
            print("  ⏭️  已取消")

    def replace_keyword(self):
        """更換關鍵字"""
        print("\n🔄 更換關鍵字")
        print("-" * 70)
        self.view_keywords()

        if not self.keywords:
            return

        try:
            idx = int(input("\n  輸入要更換的編號: ")) - 1
            if 0 <= idx < len(self.keywords):
                old_keyword = self.keywords[idx]
                new_keyword = input(f"  輸入新關鍵字 (舊: \"{old_keyword}\"): ").strip()

                if not new_keyword:
                    print("  ⏭️  已取消")
                    return

                self.keywords[idx] = new_keyword
                self.save_keywords()
                print(f"  ✅ 已更換: \"{old_keyword}\" → \"{new_keyword}\"")
            else:
                print("  ❌ 無效編號！")
        except ValueError:
            print("  ⏭️  已取消")

    def start_analysis(self):
        """開始批量分析"""
        print("\n🎬 開始批量分析（YouTube+B站搜尋）")
        print("-" * 70)
        self.view_keywords()

        if not self.keywords:
            print("  ❌ 關鍵字列表為空！請先新增關鍵字")
            return

        print(f"\n  📋 將搜尋 {len(self.keywords)} 個關鍵字")
        print(f"     YouTube: 各 10 個視頻")
        print(f"     B 站: 各 10 個視頻")
        print(f"     預期總 URL 數: ~{len(self.keywords) * 15}-{len(self.keywords) * 20}")

        confirm = input("\n  確認開始分析? (y/n): ").lower()
        if confirm != 'y':
            print("  ⏭️  已取消")
            return

        print("\n  🚀 啟動批量分析工具...")
        print("  ⏳ 這可能需要幾分鐘時間，請耐心等待...\n")
        try:
            result = subprocess.run(
                [sys.executable, "assets/scripts/batch_style_analyzer_sqlite.py"],
                cwd=WORKSPACE,
                capture_output=False
            )
            if result.returncode == 0:
                print("\n  ✅ 分析完成！")
            else:
                print("\n  ⚠️  分析過程中出現錯誤")
        except Exception as e:
            print(f"  ❌ 啟動失敗: {e}")

    def show_stats(self):
        """查看資料庫統計"""
        print("\n📊 資料庫統計")
        print("-" * 70)
        try:
            stats = self.db.get_statistics()
            print(f"  ✅ 總條目數: {stats['total_entries']}")
            print(f"  💾 資料庫大小: {stats['database_size_mb']} MB")
            print(f"  📁 資料庫路徑: {stats['database_path']}")

            # 列出所有條目
            if stats['total_entries'] > 0:
                print("\n  📝 條目列表:")
                entries = self.db.get_all_entries()
                for idx, entry in enumerate(entries, 1):
                    theme = entry.get('theme_name', 'Unknown')
                    print(f"    {idx}. {entry['source_id']} - {theme}")
        except Exception as e:
            print(f"  ❌ 錯誤: {e}")
        print("-" * 70)

    def export_json(self):
        """匯出資料庫為 JSON"""
        print("\n💾 匯出資料庫為 JSON")
        print("-" * 70)
        filename = input("  輸入檔案名稱 (default: style_vault.json): ").strip()
        if not filename:
            filename = "style_vault.json"

        if not filename.endswith('.json'):
            filename += '.json'

        export_path = DATA_DIR / filename

        try:
            entries = self.db.get_all_entries()
            atomic_write_json(export_path, entries, indent=2)
            print(f"  ✅ 已匯出: {export_path}")
        except Exception as e:
            print(f"  ❌ 匯出失敗: {e}")

    def cleanup_files(self):
        """清理舊檔案"""
        print("\n🧹 清理舊檔案")
        print("-" * 70)

        patterns = [
            ("*.mp3", "音頻檔案"),
            ("*.mp4", "影片檔案"),
        ]

        total_freed = 0

        for pattern, desc in patterns:
            files = list(DATA_DIR.glob(pattern))
            if files:
                print(f"\n  找到 {len(files)} 個{desc}:")
                for f in files[:5]:  # 只顯示前5個
                    size_kb = f.stat().st_size / 1024
                    print(f"    - {f.name} ({size_kb:.2f} KB)")
                if len(files) > 5:
                    print(f"    ... 及其他 {len(files) - 5} 個檔案")

                confirm = input(f"\n  刪除這些{desc}? (y/n): ").lower()
                if confirm == 'y':
                    for f in files:
                        try:
                            f.unlink()
                            total_freed += f.stat().st_size / 1024
                        except Exception as e:
                            print(f"    ❌ 刪除失敗: {f.name}")

        if total_freed > 0:
            print(f"\n  ✅ 清理完成，釋放 {total_freed:.2f} KB")
        else:
            print("\n  ℹ️  沒有舊檔案需要清理")

    def diagnose_system(self):
        """系統診斷 - 檢查所有核心組件"""
        print("\n🔧 系統診斷")
        print("="*70)
        
        checks = []
        
        # 檢查 1: 資料庫模塊
        print("  ✓ 檢查 1: 資料庫模塊初始化...", end="")
        try:
            test_db = StyleDatabase()
            print(f" ✅")
            checks.append(("資料庫模塊", True, test_db.db_path))
        except Exception as e:
            print(f" ❌ ({e})")
            checks.append(("資料庫模塊", False, str(e)))
        
        # 檢查 2: 分析工具
        print("  ✓ 檢查 2: 批量分析工具...", end="")
        analyzer_path = SCRIPTS_DIR / "batch_style_analyzer_sqlite.py"
        if analyzer_path.exists():
            print(f" ✅")
            checks.append(("批量分析工具", True, str(analyzer_path)))
        else:
            print(f" ❌ (檔案不存在)")
            checks.append(("批量分析工具", False, "檔案不存在"))
        
        # 檢查 3: video_input.txt
        print("  ✓ 檢查 3: video_input.txt...", end="")
        if INPUT_FILE.exists():
            with open(INPUT_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            keyword_count = len(re.findall(r'Keyword="([^"]+)"', content))
            url_count = len(re.findall(r'URL=', content))
            print(f" ✅")
            checks.append(("video_input.txt", True, f"{keyword_count}個關鍵字, {url_count}個URL"))
        else:
            print(f" ⚠️ (檔案不存在)")
            checks.append(("video_input.txt", False, "檔案不存在"))
        
        # 檢查 4: 資料庫統計
        print("  ✓ 檢查 4: 資料庫條目...", end="")
        try:
            count = self.db.count_entries()
            print(f" ✅")
            checks.append(("資料庫條目", True, f"{count}個"))
        except Exception as e:
            print(f" ❌")
            checks.append(("資料庫條目", False, str(e)))
        
        # 顯示結果
        print("\n" + "="*70)
        print("📊 診斷結果摘要:")
        print("-" * 70)
        passed = 0
        for name, status, info in checks:
            icon = "✅" if status else "❌"
            print(f"  {icon} {name:15} → {info}")
            if status:
                passed += 1
        print("-" * 70)
        print(f"\n  結果: {passed}/{len(checks)} 項通過\n")
        if passed == len(checks):
            print("  💚 系統正常！可以開始分析")
        else:
            print("  ⚠️  發現問題，請檢查相關檔案")

    def clear_cache(self):
        """清理快取 - 強制重新搜尋 URL"""
        print("\n🗑️  清理快取")
        print("-" * 70)
        print("\n  快取檔案:")
        
        cache_files = [
            (WORKSPACE / ".url_pool.json", "URL 池快取"),
            (WORKSPACE / ".video_input_hash", "輸入檔案雜湊"),
        ]
        
        existing_files = []
        total_size = 0
        
        for cache_path, desc in cache_files:
            if cache_path.exists():
                size = cache_path.stat().st_size / 1024
                existing_files.append((cache_path, desc))
                total_size += size
                print(f"    📄 {desc}: {size:.2f} KB")
        
        if not existing_files:
            print("    ℹ️  沒有快取檔案")
            return
        
        print(f"\n  合計: {total_size:.2f} KB")
        confirm = input(f"\n  確認刪除? (y/n): ").lower()
        if confirm == 'y':
            for cache_path, desc in existing_files:
                try:
                    cache_path.unlink()
                    print(f"    ✅ 已刪除: {desc}")
                except Exception as e:
                    print(f"    ❌ 刪除失敗: {desc} ({e})")
            print(f"\n  ✅ 快取清理完成！")
            print(f"  下次執行分析時將重新搜尋關鍵字對應的 URL")
        else:
            print("\n  ⏭️  已取消")

    def run(self):
        """主程式循環"""
        while True:
            self.show_menu()
            choice = input("  請選擇操作 (0-10): ").strip()

            if choice == "1":
                self.view_keywords()
            elif choice == "2":
                self.add_keyword()
            elif choice == "3":
                self.delete_keyword()
            elif choice == "4":
                self.replace_keyword()
            elif choice == "5":
                self.start_analysis()
            elif choice == "6":
                self.show_stats()
            elif choice == "7":
                self.export_json()
            elif choice == "8":
                self.cleanup_files()
            elif choice == "9":
                self.diagnose_system()
            elif choice == "10":
                self.clear_cache()
            elif choice == "0":
                print("\n👋 謝謝使用，再見！\n")
                break
            else:
                print("  ❌ 無效選擇，請重試")

            input("\n  按 Enter 繼續...")


def main():
    """主入口"""
    try:
        manager = QuickManager()
        manager.run()
    except KeyboardInterrupt:
        print("\n\n👋 程式已中止")
    except Exception as e:
        print(f"\n❌ 程式錯誤: {e}")


if __name__ == "__main__":
    main()
