# -*- coding: utf-8 -*-
"""
Path resolution helpers (CEO rule: pathlib everywhere, NO hardcoded drives).

Layout:
  Auto_Drama/                      <- this project (fully self-contained)
    output/episodes/{series}/{episode_id}   <- episodic routing (default)
    logs/
    data/                          <- local sqlite state
"""
from __future__ import annotations

from pathlib import Path

from .config import Settings, load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_WORKSPACE = PROJECT_ROOT.parent          # F:\AI_DRAMA_FACTORY (read-only)
LOCALMINIDRAMA_DIR = ORIGINAL_WORKSPACE / "LocalMiniDrama-main"  # referenced in place


class Paths:
    """Central path registry resolved once per process."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.root = PROJECT_ROOT

        out_root_raw = self.settings.get("output.root", "./output")
        out_root = Path(out_root_raw)
        if not out_root.is_absolute():
            out_root = self.root / out_root
        self.output_root = out_root
        self.logs_dir = self.root / "logs"
        self.data_dir = self.root / "data"
        self.config_dir = self.root / "config"

    def ensure_dirs(self) -> None:
        """Create standard directories if missing (idempotent)."""
        for d in (self.output_root, self.logs_dir, self.data_dir):
            d.mkdir(parents=True, exist_ok=True)

    def episode_dir(self, series: str, episode_id: str) -> Path:
        """Dynamic episodic routing: output/episodes/{series}/{episode_id}."""
        layout = self.settings.get("output.layout", "episodes/{series}/{episode_id}")
        rel = layout.format(series=series, episode_id=episode_id)
        p = self.output_root / rel
        p.mkdir(parents=True, exist_ok=True)
        return p

    def job_db_path(self) -> Path:
        """Local pipeline state database (thread-safe usage in state.py)."""
        return self.data_dir / "jobs.db"

    def log_path(self) -> Path:
        return self.logs_dir / "auto_drama.log"
