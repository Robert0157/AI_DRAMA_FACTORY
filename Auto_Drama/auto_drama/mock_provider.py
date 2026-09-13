# -*- coding: utf-8 -*-
"""
Providers used by stage runners.

MockProvider — fully offline end-to-end demo. Produces placeholder artifacts
(no network, no API keys, no ffmpeg). Written as *.mock marker files so no
one mistakes them for real media.

LiveProvider — wraps real drivers:
  Stage1: DeepSeekClient (classical-Chinese -> vernacular -> storyboard JSON)
  Stage2/3: LocalMiniDrama REST API + Seedance/Kling via backend
  Stage4: SunoClient + ffmpeg helpers
Live Stage 2/3 calls are wired to LocalMiniDrama endpoints; provider surfaces
clear errors when the backend is not reachable.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List

from .json_clean import clean_llm_json
from .logging_util import get_logger
from .schemas import EpisodeDraft, StoryboardShot

log = get_logger()

# Emotion rotation used by the mock so emotion-arc aggregation is exercised.
_MOCK_EMOTION_ROTATION = ["suspense", "sad", "tense", "suspense",
                          "relief", "warm", "tense", "sad", "romance", "joyful"]


# ---------------------------------------------------------------------
# Chapter splitting (mock-level, rule-based)
# ---------------------------------------------------------------------
_CHAPTER_HEAD = re.compile(
    r"^\s*(第[0-9一二三四五六七八九十百千]+[卷章節回]|"
    r"卷[0-9一二三四五六七八九十百千]+|"
    r"[^\s。，]{1,24}(則|篇|記|志))[：:、.．\s]?"
)


def split_chapters(source_text: str, limit: int = 2) -> List[Dict[str, str]]:
    """Rule-based chapter split; falls back to a single '全篇' chunk."""
    lines = source_text.replace("\r\n", "\n").split("\n")
    chapters: List[Dict[str, str]] = []
    cur_title = "全篇"
    cur: List[str] = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("#"):
            continue  # skip comment lines (e.g. sample file headers)
        if s and _CHAPTER_HEAD.match(s):
            if cur and "".join(cur).strip():
                chapters.append({"title": cur_title, "content": "\n".join(cur)})
            cur_title = s[:30]
            cur = []
        else:
            cur.append(ln)
    if cur and "".join(cur).strip():
        chapters.append({"title": cur_title, "content": "\n".join(cur)})
    if not chapters:
        chapters = [{"title": "全篇", "content": source_text}]
    # Keep demo small.
    return chapters[: max(1, min(limit, len(chapters)))]


class MockProvider:
    """Deterministic offline provider for end-to-end validation."""

    def __init__(self) -> None:
        self.mode = "mock"

    # ---- Stage 1 ----
    def expand_script(self, source_text: str, title: str = "") -> List[EpisodeDraft]:
        chapters = split_chapters(source_text, limit=2)
        drafts: List[EpisodeDraft] = []
        for ci, ch in enumerate(chapters, start=1):
            body_lines = [l.strip() for l in ch["content"].splitlines() if l.strip()]
            shots: List[StoryboardShot] = []
            n_shots = min(8, max(3, len(body_lines)))
            for i in range(n_shots):
                emotion = _MOCK_EMOTION_ROTATION[i % len(_MOCK_EMOTION_ROTATION)]
                dialogue = ""
                if body_lines:
                    dialogue = body_lines[i % len(body_lines)][:40]
                shots.append(StoryboardShot(
                    shot_number=i + 1,
                    title=f"鏡頭{i + 1}",
                    shot_type="medium" if i % 2 == 0 else "close_up",
                    time="夜" if emotion in ("suspense", "horror", "tense") else "日",
                    location="古寺" if ci % 2 else "荒郊",
                    action=f"角色於{emotion}氛圍中行動",
                    dialogue=dialogue,
                    atmosphere=f"{emotion}場景氣氛",
                    emotion=emotion,
                    emotion_intensity=(i % 5) - 1,
                    duration=5.0,
                    bgm_prompt=f"情緒提示: {emotion}",
                    image_prompt=f"{emotion} cinematic still, ancient Chinese setting",
                    video_prompt=f"{emotion} cinematic shot, subtle motion, ancient Chinese setting",
                    characters=[1, 2],
                ))
            drafts.append(EpisodeDraft(
                episode_id=f"ep{ci:02d}",
                title=f"{title or '無題'} · {ch['title']}",
                shots=shots,
            ))
        return drafts

    # ---- Stage 2 ----
    def create_characters_and_scenes(self, draft: EpisodeDraft) -> Dict[str, Any]:
        # Placeholder "character library" reference (mock).
        return {"characters": ["書生", "狐仙"], "scenes": [s.location for s in draft.shots]}

    def generate_shot_visual(self, draft: EpisodeDraft, shot: StoryboardShot,
                             out_dir: Path) -> List[Path]:
        markers = []
        for kind in ("image", "video"):
            p = out_dir / f"{draft.episode_id}_sc00_sh{shot.shot_number:03d}_{kind}.mock"
            p.write_text(
                f"MOCK {kind} for shot {shot.shot_number} emotion={shot.emotion}\n"
                f"{shot.image_prompt if kind == 'image' else shot.video_prompt}\n",
                encoding="utf-8",
            )
            markers.append(p)
        return markers

    # ---- Stage 3 ----
    def generate_lipsync_shot(self, draft: EpisodeDraft, shot: StoryboardShot,
                              out_dir: Path) -> Path:
        p = out_dir / f"{draft.episode_id}_sc00_sh{shot.shot_number:03d}_lipsync.mp4.mock"
        p.write_text(f"MOCK lipsync for shot {shot.shot_number}\ndialogue: {shot.dialogue}\n",
                     encoding="utf-8")
        return p

    # ---- Stage 4 ----
    def compose_emotion_bgm(self, draft: EpisodeDraft, music_plan: List[dict],
                            out_dir: Path) -> Path:
        p = out_dir / f"{draft.episode_id}_bgm.wav.mock"
        lines = [f"MOCK BGM segments: {len(music_plan)}"]
        for m in music_plan:
            lines.append(
                f"  seg{m['segment_index']}: emotion={m['emotion']} "
                f"shots {m['start_shot']}-{m['end_shot']} "
                f"dur={m['duration_sec']}s chain={m['chain_from_prev']}"
            )
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def merge_episode(self, draft: EpisodeDraft, bgm_path: Path, out_dir: Path) -> Path:
        p = out_dir / f"{draft.episode_id}_final.mp4.mock"
        lines = [
            "MOCK FINAL EPISODE (placeholder; real concat+amix runs in live mode)",
            f"episode: {draft.episode_id}  shots: {len(draft.shots)}",
            f"bgm: {bgm_path.name}",
        ]
        for s in draft.shots:
            lines.append(f"  {s.shot_number:02d} {s.duration:>4}s emotion={s.emotion}")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p


# ---------------------------------------------------------------------
# Live provider (real drivers; requires backend + API keys)
# ---------------------------------------------------------------------
class LiveProvider:
    """Wraps DeepSeek/Suno/LocalMiniDrama/ffmpeg drivers for live runs."""

    def __init__(self, lmd=None, llm=None, suno=None) -> None:
        self.mode = "live"
        self.lmd = lmd
        self.llm = llm
        self.suno = suno

    # ---- Stage 1 (functional) ----
    def expand_script(self, source_text: str, title: str = "") -> List[EpisodeDraft]:
        """DeepSeek-R1: 古文章節 -> 白話三幕劇 -> 分鏡 JSON."""
        if self.llm is None:
            raise RuntimeError(
                "LiveProvider.expand_script: DEEPSEEK_API_KEY 未設定或 LLM client 不存在"
            )
        system = (
            "你是資深古典文學改編編劇。將給定的中國古典筆記小說章節"
            "擴寫為白話三幕短劇並拆解分鏡。\n"
            "每個分鏡必須輸出 JSON 欄位: shot_number, title, shot_type, angle, movement, "
            "time, location, action, dialogue, atmosphere, emotion, emotion_intensity(-1..3), "
            "duration, bgm_prompt, sound_effect, characters, image_prompt, video_prompt。\n"
            "emotion 只能是以下之一: suspense/sad/tense/horror/joyful/epic/warm/"
            "conflict/relief/romance。bgm_prompt 用一句描述該鏡配樂情緒。\n"
            "只回傳 JSON: {\"episode_title\":..., \"shots\":[...]}，不要 markdown。"
        )
        user = f"書籍: {title or '(未指定)'}\n章節原文如下，請改編並拆解為 6-10 個分鏡：\n\n{source_text[:6000]}"
        raw = self.llm.chat_json(system, user)
        shots_raw = raw.get("shots") if isinstance(raw, dict) else raw
        if not isinstance(shots_raw, list):
            raise RuntimeError("LiveProvider.expand_script: LLM output missing 'shots' array")
        shots = []
        for idx, item in enumerate(shots_raw, start=1):
            emotion = str(item.get("emotion") or "suspense")
            shots.append(StoryboardShot(
                shot_number=int(item.get("shot_number") or idx),
                title=str(item.get("title") or f"鏡頭{idx}"),
                shot_type=str(item.get("shot_type") or "medium"),
                angle=str(item.get("angle") or ""),
                movement=str(item.get("movement") or ""),
                time=str(item.get("time") or ""),
                location=str(item.get("location") or ""),
                action=str(item.get("action") or ""),
                dialogue=str(item.get("dialogue") or ""),
                atmosphere=str(item.get("atmosphere") or ""),
                emotion=emotion,
                emotion_intensity=int(item.get("emotion_intensity") or 1),
                duration=float(item.get("duration") or 5.0),
                bgm_prompt=str(item.get("bgm_prompt") or ""),
                sound_effect=str(item.get("sound_effect") or ""),
                image_prompt=str(item.get("image_prompt") or ""),
                video_prompt=str(item.get("video_prompt") or ""),
            ))
        return [EpisodeDraft(episode_id="ep01",
                             title=str(raw.get("episode_title") or title or "第1集"),
                             shots=shots)]

    # ---- Stage 2/3 (wired to LocalMiniDrama REST; backend must be up) ----
    def create_characters_and_scenes(self, draft: EpisodeDraft) -> Dict[str, Any]:
        # Real flow: POST /generation/characters + scenes; poll tasks.
        # Not auto-executed in v0.1 without a live backend; surface the call path.
        return {"note": "live: POST /generation/characters + /scenes (requires LMD backend)"}

    def generate_shot_visual(self, draft: EpisodeDraft, shot: StoryboardShot,
                             out_dir: Path) -> List[Path]:
        raise NotImplementedError(
            "Live Stage 2 visual generation requires a running LocalMiniDrama "
            "backend (POST /videos/image/{id}); wire via lmd_client."
        )

    def generate_lipsync_shot(self, draft: EpisodeDraft, shot: StoryboardShot,
                              out_dir: Path) -> Path:
        raise NotImplementedError(
            "Live Stage 3 lip-sync requires Seedance 2.0/Kling audio-driven path "
            "in LocalMiniDrama backend; wire via lmd_client."
        )

    def compose_emotion_bgm(self, draft: EpisodeDraft, music_plan: List[dict],
                            out_dir: Path) -> Path:
        raise NotImplementedError(
            "Live Stage 4 BGM requires SUNO_API_KEY and ffmpeg; wire suno_client "
            "generate/extend per music_plan then ffmpeg.assemble_emotion_music_track."
        )

    def merge_episode(self, draft: EpisodeDraft, bgm_path: Path, out_dir: Path) -> Path:
        raise NotImplementedError(
            "Live Stage 4 merge requires ffmpeg concat + amix; wire ffmpeg helpers."
        )
