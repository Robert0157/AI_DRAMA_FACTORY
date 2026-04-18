import sqlite3, sys, os
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

# 動態路徑：遵守架構鐵律，不硬編碼任何絕對路徑
DB_PATH = Path(config.workspace_root) / "assets" / "budget_ledger.db"

def init_and_log_cost(project_tier, visual_cost, audio_cost, total_tokens_cost):
    # 修復：補入缺失的 sqlite3.connect()，並加上 timeout=30 防 DB Locked
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    # CTO 規範：啟動 WAL 模式，大幅提升 APFS 併發寫入效能
    conn.execute('PRAGMA journal_mode=WAL;')
    cursor = conn.cursor()
    
    # 冷啟動防禦：確保資料表存在
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            project_tier TEXT,
            visual_cost REAL,
            audio_cost REAL,
            total_tokens_cost REAL,
            total_cpv REAL
        )
    ''')
    
    total_cpv = float(visual_cost) + float(audio_cost) + float(total_tokens_cost)
    
    # 寫入帳本
    cursor.execute('''
        INSERT INTO ledger (project_tier, visual_cost, audio_cost, total_tokens_cost, total_cpv)
        VALUES (?, ?, ?, ?, ?)
    ''', (project_tier, visual_cost, audio_cost, total_tokens_cost, total_cpv))
    
    conn.commit()
    conn.close()
    print(f"💰 Financial Ledger Updated. Total CPV: ${total_cpv:.4f} USD")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python ledger_manager.py <Tier> <VisualCost> <AudioCost> <TokenCost>")
        sys.exit(1)
    init_and_log_cost(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
	