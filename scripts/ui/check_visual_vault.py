#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""視覺金庫素材數量快速檢查"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.gear2_rnd.visual_vault_db import VisualVaultDB

db = VisualVaultDB()
cur = db.conn.cursor()

cur.execute("""
    SELECT channel,
           COUNT(*) as total,
           SUM(CASE WHEN is_archived=0 THEN 1 ELSE 0 END) as active,
           SUM(CASE WHEN is_archived=0 AND derivation_count=0 THEN 1 ELSE 0 END) as dc0,
           SUM(CASE WHEN is_archived=0 AND derivation_count=1 THEN 1 ELSE 0 END) as dc1,
           SUM(CASE WHEN is_archived=0 AND derivation_count=2 THEN 1 ELSE 0 END) as dc2,
           SUM(CASE WHEN is_archived=0 AND derivation_count>=3 THEN 1 ELSE 0 END) as dc3plus,
           SUM(CASE WHEN is_archived=1 THEN 1 ELSE 0 END) as archived
    FROM video_assets
    GROUP BY channel
    ORDER BY channel
""")
rows = cur.fetchall()

print("=" * 50)
print("  視覺金庫戰情報表（重置後）")
print("=" * 50)
for r in rows:
    ch = r["channel"]
    print(f"\n  頻道: {ch.upper()}")
    print(f"  {'─'*40}")
    print(f"  DB 總記錄:          {r['total']}")
    print(f"  有效（非封存）:     {r['active']}")
    print(f"  ├─ 全新  (dc=0):   {r['dc0']}")
    print(f"  ├─ 一代  (dc=1):   {r['dc1']}")
    print(f"  ├─ 二代  (dc=2):   {r['dc2']}")
    print(f"  └─ 三代+ (dc>=3):  {r['dc3plus']}")
    print(f"  封存:               {r['archived']}")

# 物理檔案驗證
cur.execute("SELECT file_path, channel, derivation_count FROM video_assets WHERE is_archived=0")
all_active = cur.fetchall()
exist   = [r for r in all_active if Path(r["file_path"]).exists()]
missing = [r for r in all_active if not Path(r["file_path"]).exists()]

print("\n" + "=" * 50)
print("  物理檔案驗證")
print("=" * 50)
print(f"  DB 有效記錄: {len(all_active)}")
print(f"  實際存在:    {len(exist)}")
print(f"  檔案遺失:    {len(missing)}")
if missing:
    print("\n  遺失清單（最多顯示10筆）：")
    for m in missing[:10]:
        print(f"    ⚠  [{m['channel']}] dc={m['derivation_count']}  {m['file_path']}")

db.close()
print("\n  ✅ 檢查完成")
