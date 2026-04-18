#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【一鍵資料庫淨化】scripts/gear2_rnd/cleanup_vault_orphans.py
移除所有指向不存在物理文件的孤立記錄
"""

import sys
from pathlib import Path

# 【CTO 強制執行】確保腳本能找到專案根目錄
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.gear2_rnd.visual_vault_db import VisualVaultDB


def cleanup_all_orphans():
    """一鍵清理全部孤立記錄"""
    print("\n" + "="*70)
    print("【v15.0 資料庫淨化】移除所有孤立記錄 (Orphaned Records)")
    print("="*70)
    
    try:
        vault = VisualVaultDB()
        
        # 執行全頻道清理
        total_removed = vault.cleanup_orphaned_records(channel=None)
        
        if total_removed == 0:
            print("\n✅ 資料庫已清潔，無孤立記錄需要移除")
        else:
            print(f"\n🧹 成功移除 {total_removed} 個幽靈資產記錄")
        
        vault.close()
        print("\n✅ 資料庫淨化程序完成")
        return total_removed
    
    except Exception as e:
        print(f"\n❌ 淨化失敗: {e}")
        return -1


def cleanup_channel_orphans(channel: str):
    """清理指定頻道的孤立記錄"""
    print("\n" + "="*70)
    print(f"【頻道淨化】移除 {channel} 頻道的孤立記錄")
    print("="*70)
    
    try:
        vault = VisualVaultDB()
        
        # 執行頻道級別清理
        removed_count = vault.cleanup_orphaned_records(channel=channel)
        
        if removed_count == 0:
            print(f"\n✅ 頻道 {channel} 已清潔")
        else:
            print(f"\n🧹 頻道 {channel} 移除了 {removed_count} 個記錄")
        
        vault.close()
        return removed_count
    
    except Exception as e:
        print(f"\n❌ 頻道淨化失敗: {e}")
        return -1


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="資料庫孤立記錄清理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例用法：
  # 清理全部孤立記錄
  python cleanup_vault_orphans.py
  
  # 清理特定頻道
  python cleanup_vault_orphans.py --channel lofi
        """
    )
    
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="指定頻道 (例如: lofi, light_music)，不指定則清理全部"
    )
    
    args = parser.parse_args()
    
    if args.channel:
        cleanup_channel_orphans(args.channel)
    else:
        cleanup_all_orphans()
