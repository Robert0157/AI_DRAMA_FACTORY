#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
依長片 MP4 選對應 Tracklist_*.txt（與縫合輸出時間軸一致）。
獨立小模組，供 UI backend / cheatsheet 共用，避免循環或大包匯入失敗。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional


def is_real_tracklist(path: Path) -> bool:
    return "placeholder" not in path.name.lower()


def _pick_tracklist_by_mp4_stem(real: List[Path], mp4_stem: str) -> Optional[Path]:
    """
    依 MP4 檔名尾碼 _YYYYMMDD_HHMMSS 配對 Tracklist_YYYYMMDD_HHMM.txt。
    例如母帶 …_20260502_151011 對應 Tracklist_20260502_1510.txt（151011 以前綴對齊）。
    """
    m = re.search(r"_(\d{8})_(\d{4,6})$", mp4_stem)
    if not m:
        return None
    ymd, run_time = m.group(1), m.group(2)
    hits: List[Path] = []
    for p in real:
        tm = re.match(r"Tracklist_(\d{8})_(\d+)\.txt$", p.name, re.I)
        if not tm:
            continue
        if tm.group(1) != ymd:
            continue
        tl_t = tm.group(2)
        if run_time.startswith(tl_t):
            hits.append(p)
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    return max(hits, key=lambda p: p.stat().st_mtime)


def pick_tracklist_txt_for_mp4(export_dir: Path, media_path: Path) -> Optional[Path]:
    """
    選與本次「1hr 母帶」同一次縫合 run 的 Tracklist_YYYYMMDD_HHMM.txt。

    `media_path` 可為最終 **MP4** 或 **WAV**（檔名皆為 *1HrMix_* 時間戳），以 stem 對齊 Tracklist。

    策略（依序）：
    1) 檔名時間戳與母帶 stem 一致（與 lofi_assembler 寫入之 Tracklist_{同 run}.txt 對齊）。
    2) 非 placeholder 之 Tracklist，取「修改時間不晚於母帶（容許時鐘誤差）」且最晚寫入者。
    3) 若皆晚於母帶，則取修改時間最接近的一份。
    """
    real = [p for p in export_dir.glob("Tracklist_*.txt") if is_real_tracklist(p)]
    if not real:
        return None
    by_stem = _pick_tracklist_by_mp4_stem(real, media_path.stem)
    if by_stem is not None:
        return by_stem
    mp4_mt = media_path.stat().st_mtime
    slack = 300.0
    before_or_near = [p for p in real if p.stat().st_mtime <= mp4_mt + slack]
    if before_or_near:
        return max(before_or_near, key=lambda p: p.stat().st_mtime)
    return min(real, key=lambda p: abs(p.stat().st_mtime - mp4_mt))


# 向後相容別名
pick_tracklist_txt_for_mix_master = pick_tracklist_txt_for_mp4
