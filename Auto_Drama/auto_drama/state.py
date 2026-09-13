# -*- coding: utf-8 -*-
"""
Pipeline run state machine backed by SQLite.

Thread-safety rule (mirrors CEO sqlite rule): connections are created per
thread via threading.local and are NEVER closed manually; lifetime is managed
by the threading.local container.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_local = threading.local()

# Stage order of the pipeline.
STAGE_ORDER = ["script", "visual", "audio_lipsync", "post"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class JobStore:
    """Persistent store for pipeline runs (one row = one job)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    series TEXT NOT NULL,
                    book_title TEXT,
                    source_file TEXT,
                    status TEXT NOT NULL DEFAULT 'queued',
                    stage_progress TEXT NOT NULL DEFAULT '{}',
                    artifact_manifest TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _conn(self) -> sqlite3.Connection:
        """Thread-local connection; never closed manually."""
        conn = getattr(_local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            _local.conn = conn
        return conn

    def create_job(
        self, series: str, book_title: str = "", source_file: str = ""
    ) -> str:
        job_id = uuid.uuid4().hex[:12]
        now = _now_iso()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, series, book_title, source_file, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                (job_id, series, book_title, source_file, now, now),
            )
        return job_id

    def update_stage(self, job_id: str, stage: str, status: str, error: str = "") -> None:
        """Mark one stage done/failed and persist error text if any."""
        row = self.get_job(job_id)
        if row is None:
            return
        progress = json.loads(row["stage_progress"]) if row["stage_progress"] else {}
        progress[stage] = {"status": status, "error": error, "at": _now_iso()}
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET stage_progress = ?, status = ?, error = ?, updated_at = ? WHERE job_id = ?",
                (_json(progress), self._derive_status(progress, status), error, _now_iso(), job_id),
            )

    @staticmethod
    def _derive_status(progress: Dict, last_status: str) -> str:
        """Overall job status derived from stage statuses."""
        if last_status == "failed":
            return "failed"
        values = [p.get("status") for p in progress.values()]
        if not values:
            return "running"
        if all(v == "completed" for v in values):
            return "completed"
        return "running"

    def set_artifacts(self, job_id: str, manifest: Dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET artifact_manifest = ?, updated_at = ? WHERE job_id = ?",
                (_json(manifest), _now_iso(), job_id),
            )

    def get_job(self, job_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_jobs(self, limit: int = 20) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def _json(obj: object) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


@dataclass
class RunContext:
    """In-memory context passed along the pipeline for one job."""

    job_id: str
    series: str
    episode_dir: Path
    store: JobStore
    mode: str = "mock"                      # mock | live
    book_title: str = ""
    source_file: str = ""
    chapters: List[str] = field(default_factory=list)
    storyboard_json_path: Optional[Path] = None
    emotion_arc_path: Optional[Path] = None
    final_video_path: Optional[Path] = None
    manifest: Dict = field(default_factory=dict)
