#!/usr/bin/env python3
"""驗證 VaultDatabase threading.local 跨執行緒修復"""
import sys, threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gear2_rnd.vault_database import VaultDatabase

db = VaultDatabase()
errors = []
results = []

def worker(label):
    try:
        stats = db.get_statistics()
        tracks = db.get_all_tracks()
        results.append(f"{label}: total={stats.get('total_tracks', 'ERR')} tracks={len(tracks)}")
    except Exception as e:
        errors.append(f"{label}: {e}")

threads = [threading.Thread(target=worker, args=(f"T{i}",)) for i in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()

if errors:
    print("FAIL:", errors)
    sys.exit(1)
for r in results:
    print("[OK]", r)
print("=== 跨執行緒 SQLite 修復驗證通過 ===")
