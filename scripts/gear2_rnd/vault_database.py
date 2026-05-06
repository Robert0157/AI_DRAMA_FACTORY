#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【v12.15 終極完整版】音樂資產保鮮庫 - VaultDatabase
✅ 支援多頻道隔離 (root_id, channel)
✅ 支援資產保鮮協議 (derivation_count, is_archived)
✅ 結構完整，防止 ImportError
"""

import sqlite3
import json
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

# 添加專案根目錄到 Python 路徑
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import EnvConfig

config = EnvConfig()

class VaultDatabase:
    """【Protocol L】音樂資產保鮮庫 - SQLite 資料庫管理器"""
    
    def __init__(self, db_path=None):
        """初始化資料庫連接並確保 Schema 最新

        Args:
            db_path: 資料庫文件路徑，默認為 rs_music_vault.db
        """
        if db_path is None:
            self.db_path = config.music_db_path
        else:
            self.db_path = Path(db_path)

        # 確保父目錄存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 【v15.3 修復】以 threading.local() 儲存每執行緒連線，
        # 避免 Streamlit 多執行緒渲染時觸發
        # "SQLite objects created in a thread can only be used in that same thread"
        self._local = threading.local()

        # 初始化資料庫結構（Schema 建立只需一次）
        self._initialize_database()

    # ── 執行緒安全連線 ─────────────────────────────────────────────
    @property
    def conn(self) -> sqlite3.Connection:
        """為當前執行緒回傳（或建立）獨立的 SQLite 連線。"""
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self.db_path), timeout=30)
            c.row_factory = sqlite3.Row
            self._local.conn = c
        return c

    def _initialize_database(self):
        """初始化全量資料表與索引"""
        cursor = self.conn.cursor()
        
        # ========== 防護機制：WAL 模式 ==========
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous = FULL;")
        
        # v15.10 P2#5: 只在首次建立 schema 時印 log，避免每次實例化污染 pipeline log
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audio_assets'")
        _first_init = cursor.fetchone() is None
        if _first_init:
            print(f"🛠️  正在初始化【v12.15 終極大一統】地基: {self.db_path}")
        
        # ========== 建立核心資料表 ==========
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audio_assets (
                track_id TEXT PRIMARY KEY NOT NULL,
                root_id TEXT,
                channel TEXT DEFAULT 'lofi',      -- 【v12.11 物理隔離】頻道標籤
                is_original BOOLEAN DEFAULT 1,
                original_path TEXT NOT NULL,
                mood TEXT,
                genre TEXT,
                bpm INTEGER,
                derivation_count INTEGER DEFAULT 0,
                is_derivative BOOLEAN DEFAULT 0,
                is_archived BOOLEAN DEFAULT 0,
                archived_at TIMESTAMP,
                status TEXT DEFAULT 'ready',
                theme_name TEXT,
                audio_prompt TEXT,
                video_prompt TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ========== 建立所有必要的索引 ==========
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_track_id ON audio_assets(track_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_root_id ON audio_assets(root_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_channel ON audio_assets(channel)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON audio_assets(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_derivation_count ON audio_assets(derivation_count)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mood ON audio_assets(mood)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_genre ON audio_assets(genre)")
        
        # ========== 建立衍生記錄表 ==========
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS derivation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id TEXT NOT NULL,
                derivation_type TEXT NOT NULL,
                parameters JSON,
                output_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES audio_assets(track_id)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_derivation_track_id ON derivation_log(track_id)
        """)
        
        self.conn.commit()
        if _first_init:
            print("✅ v12.15 全量資料庫地基建立成功！")

    # ============= 資料插入方法 =============
    
    def add_track(
        self,
        track_id: str,
        original_path: str,
        root_id: str = None,
        channel: str = 'lofi',
        mood: str = None,
        genre: str = None,
        bpm: int = None,
        **kwargs
    ) -> bool:
        """新增音軌記錄
        
        Args:
            track_id: 唯一音檔識別碼
            original_path: 母帶檔案路徑
            root_id: 根母帶 ID (可選，默認為 track_id)
            channel: 頻道標籤 (可選，默認 'lofi')
            mood: 情緒標籤 (可選)
            genre: 音樂類型 (可選)
            bpm: 節拍 (可選)
            
        Returns:
            True 如果成功，False 如果已存在
        """
        cursor = self.conn.cursor()
        try:
            # 若未指定 root_id，預設為自身 track_id
            if root_id is None:
                root_id = track_id
            
            cursor.execute("""
                INSERT INTO audio_assets (track_id, original_path, root_id, channel, mood, genre, bpm)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (track_id, original_path, root_id, channel, mood, genre, bpm))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def track_exists(self, track_id: str) -> bool:
        """檢查音檔是否存在"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM audio_assets WHERE track_id = ?", (track_id,))
        return cursor.fetchone() is not None

    def update_track_channel_path(self, track_id: str, channel: str, original_path: str) -> bool:
        """檔案歸位後同步頻道與路徑（Protocol L 物理隔離）。"""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE audio_assets
                SET channel = ?, original_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE track_id = ?
                """,
                (channel, original_path, track_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception:
            return False

    def record_derivation(
        self,
        track_id: str,
        derivation_type: str,
        output_path: str,
        parameters: Dict = None
    ) -> bool:
        """記錄衍生提取操作"""
        cursor = self.conn.cursor()
        
        try:
            params_json = json.dumps(parameters) if parameters else None
            cursor.execute("""
                INSERT INTO derivation_log (track_id, derivation_type, output_path, parameters)
                VALUES (?, ?, ?, ?)
            """, (track_id, derivation_type, output_path, params_json))
            
            # 更新衍生計數
            cursor.execute("""
                UPDATE audio_assets SET derivation_count = derivation_count + 1
                WHERE track_id = ?
            """, (track_id,))
            
            self.conn.commit()
            return True
        except Exception:
            return False

    def get_statistics(self) -> Dict:
        """取得保鮮庫統計信息"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) as total FROM audio_assets WHERE is_archived = 0")
            total_tracks = cursor.fetchone()['total'] or 0
            
            cursor.execute("SELECT SUM(derivation_count) as total FROM audio_assets")
            row = cursor.fetchone()
            total_derivations = row['total'] if row and row['total'] else 0
            
            avg_derivations = total_derivations / total_tracks if total_tracks > 0 else 0
            
            return {
                "database_path": str(self.db_path),
                "total_tracks": total_tracks,
                "total_derivations": total_derivations,
                "avg_derivations": avg_derivations,
                "database_size_mb": self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0,
                "mood_distribution": {},
                "genre_distribution": {}
            }
        except Exception as e:
            return {"error": str(e)}

    def get_most_used_tracks(self, limit: int = 5) -> List[Dict]:
        """取得最常使用的音檔"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT track_id, derivation_count 
                FROM audio_assets 
                WHERE is_archived = 0 
                ORDER BY derivation_count DESC 
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []

    def get_all_tracks(self) -> List[Dict]:
        """取得所有活躍音檔"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM audio_assets WHERE is_archived = 0
            """)
            
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []

    def close(self):
        """關閉當前執行緒的資料庫連線。"""
        c = getattr(self._local, "conn", None)
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
            self._local.conn = None

    def __del__(self):
        """解構函式"""
        try:
            self.close()
        except Exception:
            pass

        