#!/usr/bin/env python3
"""快速審計 rs_music_vault.db 頻道分佈，並偵測 track_id LUFS vs channel 不符的記錄。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.gear2_rnd.vault_database import VaultDatabase

db = VaultDatabase()
cur = db.conn.cursor()

cur.execute(
    "SELECT channel, COUNT(*) as n FROM audio_assets WHERE is_archived = 0 GROUP BY channel ORDER BY channel"
)
print("DB channel 分佈（活躍）：")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} 首")

cur.execute(
    "SELECT COUNT(*) FROM audio_assets WHERE channel = 'lofi' AND track_id LIKE '%-18%LUFS%'"
)
bad_lofi = cur.fetchone()[0]

cur.execute(
    "SELECT COUNT(*) FROM audio_assets WHERE channel = 'light_music' AND track_id LIKE '%-16%LUFS%'"
)
bad_light = cur.fetchone()[0]

print()
print("DB 異常記錄（channel 與 track_id LUFS 不符）：")
print(f"  channel=lofi 但 track_id 含 -18LUFS  : {bad_lofi} 筆")
print(f"  channel=light_music 但 track_id 含 -16LUFS : {bad_light} 筆")

if bad_lofi > 0:
    cur.execute(
        "SELECT track_id, channel FROM audio_assets WHERE channel = 'lofi' AND track_id LIKE '%-18%LUFS%' LIMIT 10"
    )
    print("  (前 10 筆):")
    for row in cur.fetchall():
        print(f"    {row[0]} → {row[1]}")

if bad_light > 0:
    cur.execute(
        "SELECT track_id, channel FROM audio_assets WHERE channel = 'light_music' AND track_id LIKE '%-16%LUFS%' LIMIT 10"
    )
    print("  (前 10 筆):")
    for row in cur.fetchall():
        print(f"    {row[0]} → {row[1]}")

if bad_lofi == 0 and bad_light == 0:
    print("  ✅ DB 無異常，channel 與 LUFS 完全一致！")

db.close()
