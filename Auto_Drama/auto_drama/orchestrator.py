# -*- coding: utf-8 -*-
"""
Pipeline orchestrator: single entry that runs Stage 1..4 for a book chapter.

Human input (CLI): a chapter text file + optional series/title.
Everything downstream is automatic; humans may optionally review at the two
checkpoints (character lock, final episode) via Telegram control.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from .config import Settings, load_settings
from .emotion_arc import EmotionMap
from .logging_util import get_logger, setup_logging
from .mock_provider import LiveProvider, MockProvider
from .paths import Paths
from .state import JobStore, RunContext
from .stages import run_stage1_script, run_stage2_visual, run_stage3_audio_lipsync, run_stage4_post

log = get_logger()


def _load_emotion_map(paths: Paths) -> EmotionMap:
    return EmotionMap(paths.config_dir / "emotion_map.yaml")


def _make_provider(settings: Settings, mode: str):
    """Instantiate Mock or Live provider based on mode."""
    if mode == "mock":
        return MockProvider()
    if mode != "live":
        raise ValueError(f"unknown mode: {mode} (use mock|live)")

    from .lmd_client import LocalMiniDramaClient
    from .llm_client import DeepSeekClient
    from .suno_client import SunoClient, SunoError

    lmd = LocalMiniDramaClient(
        base_url=settings.get("lmd.base_url", "http://127.0.0.1:5679"),
        api_prefix=settings.get("lmd.api_prefix", "/api/v1"),
        timeout_sec=int(settings.get("lmd.timeout_sec", 60)),
    )
    llm = DeepSeekClient(api_key=os.environ.get("DEEPSEEK_API_KEY", ""))
    # Suno is optional for Stage-1-only runs; surface the reason later if used.
    suno = None
    try:
        suno_backend = os.environ.get("SUNO_BACKEND", "official")
        suno = SunoClient(backend=suno_backend,
                          api_key=os.environ.get("SUNO_API_KEY", ""))
    except SunoError as exc:
        log.warning("Suno client not ready (Stage 4 will be unavailable): %s", exc)
    return LiveProvider(lmd=lmd, llm=llm, suno=suno)


def run_book_pipeline(
    source_text: str,
    book_title: str = "",
    series: str = "yuewei",
    mode: str = "mock",
    settings: Optional[Settings] = None,
    paths: Optional[Paths] = None,
) -> Dict:
    """
    Execute the full pipeline for one book chapter text.
    Returns a summary dict including job_id and produced artifacts.
    """
    settings = settings or load_settings()
    paths = paths or Paths(settings)
    paths.ensure_dirs()
    setup_logging(paths.log_path())
    emotion_map = _load_emotion_map(paths)

    store = JobStore(paths.job_db_path())
    job_id = store.create_job(series=series, book_title=book_title or "untitled")
    # Episode dir: output/episodes/{series}/{job_id} (dynamic episodic routing).
    episode_dir = paths.episode_dir(series, job_id)
    ctx = RunContext(job_id=job_id, series=series, episode_dir=episode_dir,
                     store=store, mode=mode, book_title=book_title)

    log.info("job=%s mode=%s series=%s dir=%s", job_id, mode, series, episode_dir)
    provider = _make_provider(settings, mode)

    # ---- Stage 1 ----
    drafts: List = []
    if settings.get("stages.script", True):
        drafts = run_stage1_script(ctx, provider, book_title, source_text, emotion_map)

    # Later stages need drafts; if script disabled and none exist, nothing to do.
    if not drafts:
        log.warning("No episode drafts produced; stopping pipeline.")
        return {"job_id": job_id, "status": "no_drafts"}

    # ---- Stage 2 ----
    if settings.get("stages.visual", True):
        run_stage2_visual(ctx, provider, drafts)

    # ---- Stage 3 ----
    if settings.get("stages.audio_lipsync", True):
        run_stage3_audio_lipsync(ctx, provider, drafts)

    # ---- Stage 4 ----
    if settings.get("stages.post", True):
        run_stage4_post(ctx, provider, drafts, emotion_map)

    job = store.get_job(job_id)
    log.info("job=%s final status=%s", job_id, (job or {}).get("status"))
    return {
        "job_id": job_id,
        "series": series,
        "status": (job or {}).get("status"),
        "episode_dir": str(episode_dir),
        "manifest": ctx.manifest,
    }
