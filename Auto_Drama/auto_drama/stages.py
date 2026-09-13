# -*- coding: utf-8 -*-
"""
Stage runners (Stage 1..4) driven by a pluggable Provider.

Providers:
  - MockProvider   (auto_drama/mock_provider.py) pure-python, offline demo
  - LiveProvider   (auto_drama/mock_provider.py) wraps real drivers

Each runner:
  - updates JobStore stage progress
  - writes artifacts into ctx.episode_dir (episodic routing)
  - raises StageError loudly on failure (ZERO SILENT FAILURES)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .emotion_arc import EmotionMap, build_emotion_arc, plan_music_jobs
from .logging_util import get_logger
from .schemas import EpisodeDraft, StoryboardShot
from .state import RunContext

log = get_logger()


class StageError(RuntimeError):
    """Raised when a pipeline stage fails (must not be swallowed)."""


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# =====================================================================
# Stage 1 — 劇本擴寫與分鏡拆解 (AI 編劇)
# =====================================================================
def run_stage1_script(ctx: RunContext, provider: Any, book_title: str,
                      source_text: str, emotion_map: EmotionMap) -> List[EpisodeDraft]:
    """Chapter text -> vernacular 3-act -> storyboard JSON per episode."""
    ctx.store.update_stage(ctx.job_id, "script", "running")
    try:
        drafts = provider.expand_script(source_text=source_text, title=book_title)
        if not drafts:
            raise StageError("Stage 1: provider returned no episode drafts")

        storyboard_out = []
        for draft in drafts:
            # Persist raw storyboard JSON (source of truth for later stages).
            shot_dicts = [s.to_dict() for s in draft.shots]
            sb_path = ctx.episode_dir / f"{draft.episode_id}_storyboard.json"
            _write_json(sb_path, {"episode_id": draft.episode_id, "title": draft.title,
                                  "shots": shot_dicts})
            storyboard_out.append({"episode_id": draft.episode_id, "path": str(sb_path),
                                   "shots": len(shot_dicts),
                                   "duration_sec": draft.total_duration()})
            log.info("[Stage1] episode %s -> %d shots (%.1fs)", draft.episode_id,
                     len(draft.shots), draft.total_duration())

        # Emotion arc plan (saved alongside; drives Stage 4 music).
        for draft in drafts:
            arc_path = ctx.episode_dir / f"{draft.episode_id}_emotion_arc.json"
            _write_json(arc_path, [s.to_dict() for s in build_emotion_arc(emotion_map, draft)])

        ctx.storyboard_json_path = ctx.episode_dir / f"{drafts[0].episode_id}_storyboard.json"
        ctx.emotion_arc_path = ctx.episode_dir / f"{drafts[0].episode_id}_emotion_arc.json"
        ctx.manifest["stage1"] = {"episodes": storyboard_out}
        ctx.store.update_stage(ctx.job_id, "script", "completed")
        return drafts
    except Exception as exc:
        ctx.store.update_stage(ctx.job_id, "script", "failed", str(exc))
        raise StageError(f"Stage 1 failed: {exc}") from exc


# =====================================================================
# Stage 2 — 角色建立與影像生成 (AI 視覺)
# =====================================================================
def run_stage2_visual(ctx: RunContext, provider: Any,
                      drafts: List[EpisodeDraft]) -> Dict[str, Any]:
    """Character/scene libraries + per-shot visual media generation."""
    ctx.store.update_stage(ctx.job_id, "visual", "running")
    try:
        results = []
        for draft in drafts:
            chars = provider.create_characters_and_scenes(draft)
            media = []
            for shot in draft.shots:
                shot_media = provider.generate_shot_visual(draft, shot, ctx.episode_dir)
                media.append({"shot": shot.shot_number, "media": [str(p) for p in shot_media]})
            results.append({"episode_id": draft.episode_id, "characters": chars, "media": media})
        ctx.manifest["stage2"] = results
        ctx.store.update_stage(ctx.job_id, "visual", "completed")
        return results
    except Exception as exc:
        ctx.store.update_stage(ctx.job_id, "visual", "failed", str(exc))
        raise StageError(f"Stage 2 failed: {exc}") from exc


# =====================================================================
# Stage 3 — 配音與對嘴 (AI 音頻與 Lip-Sync)
# =====================================================================
def run_stage3_audio_lipsync(ctx: RunContext, provider: Any,
                             drafts: List[EpisodeDraft]) -> Dict[str, Any]:
    """Dialogue TTS + lip-sync video per shot (Seedance/Kling audio-driven)."""
    ctx.store.update_stage(ctx.job_id, "audio_lipsync", "running")
    try:
        results = []
        for draft in drafts:
            lip = []
            for shot in draft.shots:
                if shot.dialogue:
                    out = provider.generate_lipsync_shot(draft, shot, ctx.episode_dir)
                    lip.append({"shot": shot.shot_number, "output": str(out)})
            results.append({"episode_id": draft.episode_id, "lipsync_shots": lip})
        ctx.manifest["stage3"] = results
        ctx.store.update_stage(ctx.job_id, "audio_lipsync", "completed")
        return results
    except Exception as exc:
        ctx.store.update_stage(ctx.job_id, "audio_lipsync", "failed", str(exc))
        raise StageError(f"Stage 3 failed: {exc}") from exc


# =====================================================================
# Stage 4 — 自動剪輯與配樂 (AI 後製)
# =====================================================================
def run_stage4_post(ctx: RunContext, provider: Any,
                    drafts: List[EpisodeDraft], emotion_map: EmotionMap) -> Dict[str, Any]:
    """concat + emotion BGM + subtitles -> final per-episode mp4."""
    ctx.store.update_stage(ctx.job_id, "post", "running")
    try:
        results = []
        for draft in drafts:
            # Music plan from emotion arc (Stage 1 data -> Suno prompt mapping).
            music_plan = plan_music_jobs(emotion_map, draft)
            bgm_path = provider.compose_emotion_bgm(draft, music_plan, ctx.episode_dir)
            final_video = provider.merge_episode(draft, bgm_path, ctx.episode_dir)
            results.append({"episode_id": draft.episode_id,
                            "bgm": str(bgm_path), "final_video": str(final_video)})
            log.info("[Stage4] episode %s -> final %s", draft.episode_id, final_video.name)

        ctx.manifest["stage4"] = results
        if results:
            ctx.final_video_path = Path(results[0]["final_video"])
        _write_json(ctx.episode_dir / "manifest.json", ctx.manifest)
        ctx.store.set_artifacts(ctx.job_id, ctx.manifest)
        ctx.store.update_stage(ctx.job_id, "post", "completed")
        return results
    except Exception as exc:
        ctx.store.update_stage(ctx.job_id, "post", "failed", str(exc))
        raise StageError(f"Stage 4 failed: {exc}") from exc
