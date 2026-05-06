#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common/ui_audit_logger.py
v15.11 P3#13 UI 操作審計日誌 — 寫入 assets/data/audit_log.db

功能：
  1. 記錄每次 CEO 觸發的關鍵 UI 操作（publish、Phase 4、pipeline 啟動）
  2. SQLite 儲存，欄位：timestamp、action、channel、operator、params_json、result、duration_sec
  3. 執行緒安全（每次呼叫建立獨立連線，短連線模式）
  4. 非阻塞設計：任何寫入錯誤只列印警告，不影響主流程
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class UIAuditLogger:
    """
    輕量 UI 操作審計日誌器。

    使用範例：
        logger = UIAuditLogger()
        t0 = time.time()
        # ... 執行操作 ...
        logger.log(
            action="publish_final_exports",
            channel="lofi",
            result="success",
            duration_sec=time.time() - t0,
            params={"mode": "auto"},
        )
    """

    _DDL = """
        CREATE TABLE IF NOT EXISTS ui_audit_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     REAL    NOT NULL,
            action        TEXT    NOT NULL,
            channel       TEXT    DEFAULT '',
            operator      TEXT    DEFAULT 'CEO',
            params_json   TEXT    DEFAULT '{}',
            result        TEXT    DEFAULT '',
            duration_sec  REAL    DEFAULT 0.0
        );
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON ui_audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON ui_audit_log(action);
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            from scripts.common.env_manager import config
            db_path = Path(config.workspace_root) / "assets" / "data" / "audit_log.db"
        self._db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.executescript(self._DDL)
                conn.commit()
        except Exception as e:
            print(f"[UIAuditLogger] ⚠️ DB 初始化失敗（將靜默跳過）: {e}")

    def log(
        self,
        action: str,
        *,
        channel: str = "",
        operator: str = "CEO",
        result: str = "",
        duration_sec: float = 0.0,
        params: Optional[dict] = None,
    ) -> None:
        """
        寫入一條審計記錄（非阻塞，任何錯誤只印警告）。

        Args:
            action:       操作名稱，例如 "publish_final_exports"
            channel:      頻道（lofi / light_music）
            operator:     操作者（預設 "CEO"）
            result:       結果摘要（"success" / "failed:…"）
            duration_sec: 操作耗時（秒）
            params:       附加參數字典（會序列化為 JSON）
        """
        try:
            params_json = json.dumps(params or {}, ensure_ascii=False)
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT INTO ui_audit_log "
                    "(timestamp, action, channel, operator, params_json, result, duration_sec) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (time.time(), action, channel, operator,
                     params_json, result, duration_sec),
                )
                conn.commit()
        except Exception as e:
            print(f"[UIAuditLogger] ⚠️ 寫入審計記錄失敗: {e}")

    def recent(self, limit: int = 20) -> list[dict]:
        """查詢最近 N 筆審計記錄（供 Streamlit 儀表板顯示）"""
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                rows = conn.execute(
                    "SELECT timestamp, action, channel, result, duration_sec "
                    "FROM ui_audit_log ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                {"timestamp": r[0], "action": r[1],
                 "channel": r[2], "result": r[3], "duration_sec": r[4]}
                for r in rows
            ]
        except Exception:
            return []


# 全域單例（Streamlit session 共用）
_audit_logger: Optional[UIAuditLogger] = None


def get_audit_logger() -> UIAuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = UIAuditLogger()
    return _audit_logger
