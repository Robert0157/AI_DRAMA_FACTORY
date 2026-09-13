# -*- coding: utf-8 -*-
"""Data models shared across pipeline stages (dataclasses, JSON-safe)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BookSource:
    """Human-supplied input: a specific chapter/section of a book."""
    file_path: str
    title: str = ""
    chapter_label: str = ""       # e.g. 《閱微草堂筆記》卷九·某則


@dataclass
class StoryboardShot:
    """One shot inside a storyboard JSON (Stage-1 output)."""
    shot_number: int
    title: str = ""
    shot_type: str = "medium"     # extreme_long/long/medium/close_up/extreme_close_up
    angle: str = ""
    movement: str = ""
    time: str = ""
    location: str = ""
    action: str = ""
    dialogue: str = ""
    atmosphere: str = ""
    emotion: str = "suspense"     # canonical tag from emotion_map
    emotion_intensity: int = 1    # -1..3
    duration: float = 5.0
    bgm_prompt: str = ""          # LLM-provided music hint
    sound_effect: str = ""
    characters: List[int] = field(default_factory=list)
    image_prompt: str = ""
    video_prompt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EpisodeDraft:
    """One episode: title + ordered shots (parsed from LLM storyboard JSON)."""
    episode_id: str
    title: str
    shots: List[StoryboardShot] = field(default_factory=list)

    def total_duration(self) -> float:
        return round(sum(s.duration for s in self.shots), 2)


@dataclass
class EmotionSegment:
    """Consecutive shots sharing one dominant emotion -> one music segment."""
    emotion: str
    start_shot: int
    end_shot: int
    duration_sec: float
    max_intensity: int
    bgm_hints: List[str] = field(default_factory=list)
    suno_prompt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MusicSegment:
    """A generated music clip backing one EmotionSegment."""
    segment_index: int
    emotion: str
    suno_prompt: str
    duration_sec: float
    suno_music_id: str = ""
    local_path: str = ""
    chain_from_prev: bool = False   # True when built via Suno extend for continuity

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FinalProduct:
    """Stage-4 output for one episode."""
    episode_id: str
    video_path: str = ""            # concat + amix finished mp4
    bgm_path: str = ""              # assembled emotion music track (wav)
    subtitle_path: str = ""         # burned-subtitle srt if produced
    duration_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
