#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single source builder for YouTube sheet content/output."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.common.tracklist_pick import pick_tracklist_txt_for_mp4

# YouTube 上架文案唯一檔名規則
YOUTUBE_SHEET_GLOB = "youtube_sheet_*.txt"


def glob_youtube_sheet_paths(export_dir: Path) -> List[Path]:
    """所有 YouTube 上架文案（僅新檔名），依修改時間排序。"""
    paths = list(export_dir.glob(YOUTUBE_SHEET_GLOB))
    # 去重（極少數同名大小寫問題）
    uniq = {p.resolve(): p for p in paths}.values()
    return sorted(uniq, key=lambda p: p.stat().st_mtime)


def _extract_tracklist_lines_only(raw: str) -> str:
    """
    從 lofi_assembler 寫入的 Tracklist 檔抽出「MM:SS - 曲名」區塊，
    外層加上與 Youtube_sample 一致的 60 字元分隔線。
    """
    lines = raw.replace("\r\n", "\n").strip().split("\n")
    sep60 = "=" * 60

    # 找 assembler 格式：兩條 60 '=' 之間為時間軸正文
    idxs = [i for i, ln in enumerate(lines) if ln.strip() == sep60]
    if len(idxs) >= 2:
        body = lines[idxs[0] + 1 : idxs[1]]
        stamp_lines = [ln for ln in body if re.match(r"^\d{2}:\d{2}\s+-\s+", ln.strip())]
        if stamp_lines:
            return sep60 + "\n" + "\n".join(stamp_lines) + "\n" + sep60

    # 後備：任意符合時間軸列
    stamp_lines = [ln.strip() for ln in lines if re.match(r"^\d{2}:\d{2}\s+-\s+", ln.strip())]
    if stamp_lines:
        return sep60 + "\n" + "\n".join(stamp_lines) + "\n" + sep60

    return raw.strip()


def _load_tracklist_content(export_dir: Path) -> tuple[str, Optional[Path], Optional[Path], bool]:
    """
    Returns:
        (內嵌於 cheatsheet 的 tracklist 區塊, tracklist 來源檔, 配對的 1hr WAV, used_fallback_message)

    與發行／SEO 一致：依「當次要上架的那一輸出」選 Tracklist — 優先最新 MP4 stem，
    無 MP4 則用最新 1hr WAV stem，再以 pick_tracklist_txt_for_mp4 與 Tracklist_{同 run}.txt 對齊
    （來源：lofi_assembler 以母帶 stem 寫入之檔名）。
    """
    mp4s = sorted(export_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    wavs = sorted(
        list(export_dir.glob("R&S_Echoes_*_1HrMix_*.wav"))
        + list(export_dir.glob("R&S_Echoes_1HrMix_*.wav")),
        key=lambda p: p.stat().st_mtime,
    )
    media: Optional[Path] = mp4s[-1] if mp4s else (wavs[-1] if wavs else None)
    if media is None:
        msg = (
            "(尚未找到縫合母帶產生的 Tracklist_*.txt — 請先執行「縫合長軌」，"
            "或確認 export 目錄內非僅有 placeholder 版 Tracklist)"
        )
        return msg, None, None, True

    tl_path = pick_tracklist_txt_for_mp4(export_dir, media)
    paired_master_wav = None
    for w in wavs:
        if w.stem == media.stem:
            paired_master_wav = w
            break
    if paired_master_wav is None and wavs:
        paired_master_wav = wavs[-1]

    if tl_path is None or not tl_path.is_file():
        msg = (
            "(找不到與當前母帶對齊之 Tracklist_*.txt — 請確認縫合已寫入 Tracklist_{同 run}.txt)"
        )
        return msg, None, paired_master_wav, True

    raw = tl_path.read_text(encoding="utf-8")
    extracted = _extract_tracklist_lines_only(raw)
    looks_ok = "=" * 60 in extracted and re.search(r"\d{2}:\d{2}\s+-", extracted)
    if not looks_ok:
        return (
            "(無法從 Tracklist 解析時間軸 — 請確認為 lofi_assembler 產出之正式 Tracklist，並重新縫合)",
            tl_path,
            paired_master_wav,
            True,
        )
    return extracted, tl_path, paired_master_wav, False


def _load_metadata(export_dir: Path, channel: str) -> tuple[Dict[str, Any], Optional[Path]]:
    meta_path = export_dir / f"metadata_distrokid_{channel}.json"
    if not meta_path.exists():
        fallback = sorted(export_dir.glob("metadata_distrokid*.json"), key=lambda p: p.stat().st_mtime)
        meta_path = fallback[-1] if fallback else None
    if not meta_path or not meta_path.exists():
        return {}, None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")), meta_path
    except Exception:
        return {}, meta_path


def build_youtube_cheatsheet_content(
    *,
    channel: str,
    tracklist_content: str,
    metadata: Dict[str, Any],
    now: Optional[dt.datetime] = None,
) -> str:
    now = now or dt.datetime.now()
    channel_lower = channel.lower()
    album_title = metadata.get("album_title", "R&S Echoes - 1 Hour Mix")

    if channel_lower == "light_music":
        yt_title_suffix = "1 Hour Ambient Nature Mix 🌿 Relaxing Soundscape for Focus & Sleep"
        brand_story = """Welcome to R&S Echoes Nature. 🌿✨

We created this channel as your digital sanctuary—a quiet corner of the internet to help you reconnect with nature, tune out the noise, and find your inner peace.

Whether you're pulling a late-night coding session, studying for finals, or simply looking to wind down and breathe, our curated natural soundscapes and immersive visual echoes are here to keep you company.

Grab your headphones, take a deep breath, and let the calming sounds of nature wash over you.  🌧️🌲"""
        production_footer = """━━━━━━━━━━━━━━━━━━━━
⚙️ Production: Visuals (Midjourney/Kling/Veo) & Audio (Suno). Uniquely master-processed, mixed with high-fidelity ambient sounds, and seamlessly looped.

© Copyright: All curated ambient mixes and visual loops are protected by copyright and officially distributed to streaming platforms (Spotify/Apple). Unauthorized reproduction, re-uploading, or sampling is strictly prohibited. Thank you for respecting our craft! 🙏🍃
━━━━━━━━━━━━━━━━━━━━"""
    else:
        yt_title_suffix = "1 Hour Lofi Mix 🎵 Relaxing Beats for Study & Work"
        brand_story = """Welcome to R&S Echoes 🌿✨

R&S Echoes 專注於打造沉浸式的 Lo-Fi、Ambient 與 Cinematic 音樂體驗。
我們為遠程工作者、學生與創意工作者提供靈感與專注的伴奏。

每一首曲都經過精心製作，確保：
✅ 錄音室純淨音質（無黑膠噪聲、無磁帶嘶聲、無背景雜音）
✅ -16 LUFS YouTube 標準音量"""
        production_footer = """━━━━━━━━━━━━━━━━━━━━
⚙️ Production: Visuals (Midjourney/Kling/Veo) & Audio (Suno). Studio-mastered Lo-Fi mix (-16 LUFS), seamlessly looped.

© Copyright: All curated mixes and visual loops are protected by copyright and officially distributed to streaming platforms (Spotify/Apple). Unauthorized reproduction, re-uploading, or sampling is strictly prohibited. Thank you for respecting our craft! 🙏
━━━━━━━━━━━━━━━━━━━━"""

    title_one_line = f"{album_title} | {yt_title_suffix}"
    desc_opener = f"🎵 {album_title} - {yt_title_suffix}"

    today = now.strftime("%Y-%m-%d")
    # 版型對齊 assets/final_exports/.../Youtube_sample.txt
    return f"""======================================================
🎬 R&S Echoes - YouTube 上架企劃文案
======================================================
專輯：{album_title}
生成時間：{today}
版本：Official Release (v10 - No Draft)

======================================================
【📺 YouTube 長片標題】
======================================================

{title_one_line}

======================================================
【📝 YouTube 長片描述文案】
======================================================

{desc_opener}

Perfect for:
✨ Studying & Focus
🎧 Relaxation & Meditation
😴 Sleep & Background Music
🎮 Gaming & Streaming

---

【⏱️ TRACKLIST】
{tracklist_content}

---

【🎨 R&S Echoes Brand Name Story】

{brand_story}

{production_footer}
---
======================================================
"""


def generate_youtube_cheatsheet_file(
    export_dir: Path,
    channel: str,
    *,
    now: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    now = now or dt.datetime.now()
    channel_lower = channel.lower()
    export_dir.mkdir(parents=True, exist_ok=True)

    tracklist_content, tracklist_path, paired_master_wav, used_fallback = _load_tracklist_content(export_dir)
    metadata, metadata_path = _load_metadata(export_dir, channel_lower)
    content = build_youtube_cheatsheet_content(
        channel=channel_lower,
        tracklist_content=tracklist_content,
        metadata=metadata,
        now=now,
    )

    ts = now.strftime("%Y%m%d_%H%M%S")
    out_path = export_dir / f"youtube_sheet_{ts}.txt"
    out_path.write_text(content, encoding="utf-8")
    return {
        "output_path": out_path,
        "tracklist_path": tracklist_path,
        "paired_master_wav": paired_master_wav,
        "metadata_path": metadata_path,
        "used_default_tracklist": tracklist_path is None or used_fallback,
        "used_default_metadata": metadata_path is None,
    }
