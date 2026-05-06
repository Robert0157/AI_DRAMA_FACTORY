#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""長片上傳（Long_Queue sidecar）固定 tags — 與 CEO 頻道設定對齊。"""

from __future__ import annotations

import re
from typing import Any, Iterable, List


# light_music：21 個固定 tag（YouTube API 使用無 # 字串；與 Studio 習慣可互相轉換）
LIGHT_MUSIC_LONGFORM_TAGS_FIXED: List[str] = [
    "AmbientMusic",
    "NatureSounds",
    "SleepMusic",
    "DeepFocus",
    "Relaxation",
    "RSEchoesNature",
    "4KLandscape",
    "Meditation",
    "HealingFrequency",
    "NoVocals",
    "StudyMusic",
    "FocusMusic",
    "ProductiveVibes",
    "CreativeWork",
    "RemoteWork",
    "MentalHealth",
    "MindfulMusic",
    "AI Music",
    "專注音樂",
    "環境音樂",
    "放鬆心情",
]


def parse_tags_field(tags: Any) -> List[str]:
    """將 metadata 的 tags（字串或列表）拆成單一 tag 列表（去掉 #）。"""
    if tags is None:
        return []
    if isinstance(tags, list):
        raw = [str(t).strip() for t in tags if str(t).strip()]
    elif isinstance(tags, str):
        raw = [t.strip() for t in re.split(r"[#,]", tags) if t.strip()]
    else:
        return []
    out: List[str] = []
    for t in raw:
        t = t.lstrip("#").strip()
        if t:
            out.append(t)
    return out


def merge_longform_tags(channel: str, metadata_tags: Any, *, extras: Iterable[str] | None = None) -> List[str]:
    """
    合併固定 tags 與 metadata／額外 tags：固定項優先、其餘依序去重（不分大小寫）。
    """
    ch = (channel or "").strip().lower()
    base: List[str] = []
    if ch == "light_music":
        base = list(LIGHT_MUSIC_LONGFORM_TAGS_FIXED)

    merged = list(base)
    merged.extend(parse_tags_field(metadata_tags))
    if extras:
        merged.extend(parse_tags_field(list(extras)))

    seen: set[str] = set()
    result: List[str] = []
    for t in merged:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(t)
    return result
