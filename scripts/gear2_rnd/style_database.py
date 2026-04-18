#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SQLite 資料庫管理模塊 - 用於替代 JSON 存儲
提供：去重檢查、資料插入、查詢、導出等功能
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple


class StyleDatabase:
    """SQLite 資料庫管理器"""
    
    def __init__(self, db_path: str = None):
        """初始化資料庫
        
        Args:
            db_path: 資料庫文件路徑，默認為 assets/data/style_vault.db
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "assets" / "data" / "style_vault.db"
        else:
            db_path = Path(db_path)
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化資料庫
        self._initialize_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        獲取資料庫連接 - 含軍規級防護機制
        
        防鎖死機制：
        - timeout=30 參數：強制等待 30 秒以解決 Database Locked
        - 適用場景：齒輪一（讀取端）與齒輪二（寫入端）併發時
                   底層 SQLite 會自動排隊，防止致命衝突
        
        Returns:
            sqlite3.Connection：帶有超時與行工廠的連線物件
        """
        # 防鎖死：timeout=30 強制等待 30 秒，確保並行讀寫時安全排隊
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row  # 允許以字典方式訪問行
        return conn
    
    def _initialize_database(self):
        """
        建立資料庫結構 - 含軍規級防護機制
        
        WAL 模式（Write-Ahead Logging）：
        - 提升併發效能，允許讀取端與寫入端同時運作
        - 在 /Volumes/AI_Workspace 外接硬碟上運作時，性能提升明顯
        
        Fsync 物理寫入防護（PRAGMA synchronous = FULL）：
        - 強迫作業系統繞過 OS Cache，直接物理寫入 APFS 外接硬碟
        - 防範：USB 瞬斷、斷電、磁碟故障導致的靜默資料損毀
        - 代價：寫入速度略降，但資料安全性提升至軍規級
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # ========== 防護機制 1：WAL 模式 ==========
        # 提升併發效能，允許讀取與寫入平行運作
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        # ========== 防護機制 2：強制物理寫入 (Fsync) ==========
        # FULL 模式：確保每次寫入都物理落地，防範硬碟瞬斷損毀
        # 替代方案：NORMAL (折衷)、OFF (快速但不安全)
        cursor.execute("PRAGMA synchronous = FULL;")
        
        # 建立主表 (新增 video_genes 和 audio_genes 欄位用於潘朵拉基因庫)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS style_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT UNIQUE NOT NULL,
                theme_name TEXT NOT NULL,
                audio_prompt TEXT NOT NULL,
                video_prompt TEXT NOT NULL,
                video_genes TEXT DEFAULT '{}',
                audio_genes TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 資料庫遷移：添加基因欄位（如果不存在）
        self._migrate_add_gene_columns(cursor)
        
        # 建立索引以加快查詢
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_id ON style_entries(source_id)
        """)
        
        # 建立處理記錄表（用於追蹤哪些 URL 已處理）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                video_id TEXT NOT NULL,
                status TEXT DEFAULT 'SUCCESS',
                message TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 為 processing_log 建立索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_video_id_log ON processing_log(video_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status_log ON processing_log(status)
        """)
        
        conn.commit()
        conn.close()
    
    def _migrate_add_gene_columns(self, cursor):
        """資料庫遷移：添加基因欄位（潘朵拉升級）"""
        try:
            # 檢查是否已有 video_genes 欄位
            cursor.execute("PRAGMA table_info(style_entries)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'video_genes' not in columns:
                cursor.execute("""
                    ALTER TABLE style_entries 
                    ADD COLUMN video_genes TEXT DEFAULT '{}'
                """)
                print("✅ 已添加 video_genes 欄位")
            
            if 'audio_genes' not in columns:
                cursor.execute("""
                    ALTER TABLE style_entries 
                    ADD COLUMN audio_genes TEXT DEFAULT '{}'
                """)
                print("✅ 已添加 audio_genes 欄位")
        
        except Exception as e:
            print(f"⚠️  遷移過程中出現警告: {e}")
    
    # ============= 查詢方法 =============
    
    def video_id_exists(self, video_id: str) -> bool:
        """檢查 video_id 是否已存在（去重）
        
        Args:
            video_id: YouTube 影片 ID
            
        Returns:
            True 如果已存在，False 否則
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM style_entries WHERE source_id = ?", (video_id,))
        exists = cursor.fetchone() is not None
        
        conn.close()
        return exists
    
    def url_already_processed(self, url: str) -> Tuple[bool, Optional[str]]:
        """檢查 URL 是否已在此次會話中處理過
        
        Args:
            url: YouTube URL
            
        Returns:
            (已處理, video_id 或 None)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT video_id, status FROM processing_log WHERE url = ? ORDER BY processed_at DESC LIMIT 1",
            (url,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row["status"] == "SUCCESS", row["video_id"]
        return False, None
    
    def get_entry(self, video_id: str) -> Optional[Dict]:
        """獲取單個條目
        
        Args:
            video_id: YouTube 影片 ID
            
        Returns:
            條目字典或 None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM style_entries WHERE source_id = ?
        """, (video_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_all_entries(self) -> List[Dict]:
        """獲取所有條目
        
        Returns:
            條目列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM style_entries ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def count_entries(self) -> int:
        """獲取條目總數"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM style_entries")
        count = cursor.fetchone()["count"]
        
        conn.close()
        return count
    
    def search_entries(self, keyword: str) -> List[Dict]:
        """搜尋條目（按 theme_name）
        
        Args:
            keyword: 搜尋關鍵字
            
        Returns:
            匹配的條目列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM style_entries 
            WHERE theme_name LIKE ? OR source_id LIKE ?
            ORDER BY created_at DESC
        """, (f"%{keyword}%", f"%{keyword}%"))
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ============= 插入/更新方法 =============
    
    def insert_entry(self, source_id: str, theme_name: str, audio_prompt: str, video_prompt: str, video_genes: str = '{}', audio_genes: str = '{}') -> bool:
        """插入新條目 (支援潘朵拉基因庫)
        
        Args:
            source_id: YouTube 影片 ID
            theme_name: 主題名稱
            audio_prompt: 音頻分析提示词
            video_prompt: 影片分析提示词
            video_genes: 影片基因 JSON (新增參數，默認空 JSON)
            audio_genes: 音頻基因 JSON (新增參數，默認空 JSON)
            
        Returns:
            成功返回 True
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO style_entries (source_id, theme_name, audio_prompt, video_prompt, video_genes, audio_genes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (source_id, theme_name, audio_prompt, video_prompt, video_genes, audio_genes))
            
            conn.commit()
            conn.close()
            return True
        
        except sqlite3.IntegrityError:
            # source_id 已存在（重複）
            return False
        except Exception as e:
            print(f"插入失敗: {e}")
            return False
    
    def log_processing(self, url: str, video_id: str, status: str = "SUCCESS", message: str = None) -> bool:
        """記錄 URL 處理狀態
        
        Args:
            url: YouTube URL
            video_id: 影片 ID
            status: 處理狀態 (SUCCESS/FAILED)
            message: 錯誤信息
            
        Returns:
            成功返回 True
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO processing_log (url, video_id, status, message)
                VALUES (?, ?, ?, ?)
            """, (url, video_id, status, message))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"記錄失敗: {e}")
            return False
    
    def update_entry(self, video_id: str, theme_name: str = None, audio_prompt: str = None, video_prompt: str = None) -> bool:
        """更新現有條目
        
        Args:
            video_id: YouTube 影片 ID
            theme_name: 新的主題名稱 (可選)
            audio_prompt: 新的音頻提示词 (可選)
            video_prompt: 新的影片提示词 (可選)
            
        Returns:
            成功返回 True
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 構建 UPDATE 語句
            updates = ["updated_at = CURRENT_TIMESTAMP"]
            params = []
            
            if theme_name is not None:
                updates.append("theme_name = ?")
                params.append(theme_name)
            
            if audio_prompt is not None:
                updates.append("audio_prompt = ?")
                params.append(audio_prompt)
            
            if video_prompt is not None:
                updates.append("video_prompt = ?")
                params.append(video_prompt)
            
            params.append(video_id)
            
            sql = f"UPDATE style_entries SET {', '.join(updates)} WHERE source_id = ?"
            cursor.execute(sql, params)
            
            conn.commit()
            conn.close()
            return cursor.rowcount > 0
        
        except Exception as e:
            print(f"更新失敗: {e}")
            return False
    
    # ============= 刪除方法 =============
    
    def delete_entry(self, video_id: str) -> bool:
        """刪除條目
        
        Args:
            video_id: YouTube 影片 ID
            
        Returns:
            成功返回 True
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM style_entries WHERE source_id = ?", (video_id,))
            
            conn.commit()
            conn.close()
            return cursor.rowcount > 0
        
        except Exception as e:
            print(f"刪除失敗: {e}")
            return False
    
    def clear_all(self) -> bool:
        """清空所有條目（危險操作）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM style_entries")
            cursor.execute("DELETE FROM processing_log")
            
            conn.commit()
            conn.close()
            return True
        
        except Exception as e:
            print(f"清空失敗: {e}")
            return False
    
    # ============= 導出方法 =============
    
    def export_to_json(self, output_path: str = None) -> str:
        """將資料庫導出為 JSON 格式
        
        Args:
            output_path: 輸出文件路徑 (可選)
            
        Returns:
            JSON 文件路徑
        """
        if output_path is None:
            output_path = self.db_path.parent / "style_vault.json"
        else:
            output_path = Path(output_path)
        
        try:
            entries = self.get_all_entries()
            
            # 將 timestamp 轉換為字符串
            for entry in entries:
                if isinstance(entry.get("created_at"), str):
                    pass  # 已經是字符串
                if isinstance(entry.get("updated_at"), str):
                    pass
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            
            return str(output_path)
        
        except Exception as e:
            print(f"導出失敗: {e}")
            return None
    
    def get_statistics(self) -> Dict:
        """獲取資料庫統計信息
        
        Returns:
            統計信息字典
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 總條目數
        cursor.execute("SELECT COUNT(*) as count FROM style_entries")
        total_entries = cursor.fetchone()["count"]
        
        # 成功處理數
        cursor.execute("SELECT COUNT(*) as count FROM processing_log WHERE status = 'SUCCESS'")
        success_count = cursor.fetchone()["count"]
        
        # 失敗處理數
        cursor.execute("SELECT COUNT(*) as count FROM processing_log WHERE status = 'FAILED'")
        failed_count = cursor.fetchone()["count"]
        
        # 資料庫大小
        db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        
        conn.close()
        
        return {
            "total_entries": total_entries,
            "success_processed": success_count,
            "failed_processed": failed_count,
            "database_size_bytes": db_size_bytes,
            "database_size_mb": round(db_size_bytes / (1024 * 1024), 2),
            "database_path": str(self.db_path)
        }


if __name__ == "__main__":
    # 測試代碼
    db = StyleDatabase()
    
    print("✅ 資料庫已初始化")
    print(f"資料庫路徑: {db.db_path}")
    
    # 測試插入
    db.insert_entry(
        "test_video_001",
        "Test Theme",
        "Test audio prompt",
        "Test video prompt"
    )
    
    # 測試查詢
    entry = db.get_entry("test_video_001")
    print(f"查詢結果: {entry}")
    
    # 測試統計
    stats = db.get_statistics()
    print(f"統計: {json.dumps(stats, ensure_ascii=False, indent=2)}")
