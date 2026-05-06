#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
music_metadata_engine.py
數位唱片企劃引擎 (Music Metadata & Distribution Engine) — v15.9 國際雙語版
Phase 3：llm_client.generate_structured_json（預設 MiniMax / NVIDIA NIM），不依賴 MJ/Kling。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.atomic_io import atomic_write_json, atomic_write_text
from scripts.common.env_manager import config
from scripts.common.llm_client import generate_structured_json


@dataclass
class MetadataRecord:
    album_title: str
    track_list: list[str]
    spotify_subgenre: str
    youtube_seo_description: str
    generated_at: str
    youtube_copyright: str


# 兩頻道共用：album_title = {LLM 創意前綴} + 固定尾段，總長度 ≤ ALBUM_TITLE_MAX_TOTAL
ALBUM_TITLE_MAX_TOTAL = 100

# light_music
LIGHT_MUSIC_ALBUM_TITLE_SUFFIX = (
    "| 🌿 Relaxing Soundscape for Focus & Sleep"
    "#環境音樂 #RSEchoesNature #放鬆心情"
)

# lofi
LOFI_ALBUM_TITLE_SUFFIX = (
    "| 🎧 Chill Lo-fi Beats for Study & Sleep"
    "#lofi #RSEchoesLoFi #讀書音樂"
)

_LIGHT_MUSIC_BRAND_STORY = """【🎨 R&S Echoes Brand Name Story】

Welcome to R&S Echoes Nature. 🌿✨
我們創建這個頻道，是為了打造您的數位避風港——網路上的一個靜謐角落，幫助您重新與自然連接，屏蔽喧囂，找到內心的平靜。無論您是在深夜奮戰、備戰期末考試，還是只想放鬆身心、舒緩呼吸，我們精心挑選的自然音景和沈浸式視覺體驗都將陪伴您左右。戴上耳機，深呼吸，讓大自然的舒緩之聲輕柔地拂過您的身心。 🌧️🌲

We created this channel as your digital sanctuary—a quiet corner of the internet to help you reconnect with nature, tune out the noise, and find your inner peace.

Whether you're pulling a late-night coding session, studying for finals, or simply looking to wind down and breathe, our curated natural soundscapes and immersive visual echoes are here to keep you company.

Grab your headphones, take a deep breath, and let the calming sounds of nature wash over you.  🌧️🌲"""

_LIGHT_MUSIC_COPYRIGHT_BLOCK = """━━━━━━━━━━━━━━━━━━━━
⚙️ Production: Visuals (Midjourney/Kling/Veo) & Audio (Suno). Uniquely master-processed, mixed with high-fidelity ambient sounds, and seamlessly looped.

© Copyright: All curated ambient mixes and visual loops are protected by copyright and officially distributed to streaming platforms (Spotify/Apple). Unauthorized reproduction, re-uploading, or sampling is strictly prohibited. Thank you for respecting our craft! 🙏🍃
━━━━━━━━━━━━━━━━━━━━
#讀書音樂 #白噪音 #深度工作 #冥想放鬆 #雨聲音樂
---
======================================================"""

_LOFI_BRAND_STORY = """-------------------------------------
Welcome to R&S Echoes Lo-fi. ☕🌙

這裡是為深夜讀書、遠端工作與程式打拼準備的 Lo-fi 角落——用柔和的節拍替城市的噪音按下靜音，讓專注回到你的桌面。
無論是考前衝刺、副作用業，或只想在霓虹與咖啡香裡慢下來，我們的 Chillhop 與 Lo-fi 律動都願意陪你熬過每一個時區。

We built this corner for late-night study sessions, remote work, and deep-focus coding—soft drums, warm keys, and tape hiss that turns busy streets into a quiet booth.
Put on your headphones, sip something warm, and let the beat carry you through the midnight shift.

Grab your headphones—let’s lock in. 🎧✨"""

_LOFI_COPYRIGHT_BLOCK = """━━━━━━━━━━━━━━━━━━━━
⚙️ Production: Visuals (Midjourney/Kling/Veo) & Audio (Suno). Mastered for warm low-end, vinyl-style warmth, and seamless long-form listening.

© Copyright: All curated Lo-fi mixes and visual loops are protected by copyright and officially distributed to streaming platforms (Spotify/Apple). Unauthorized reproduction, re-uploading, or sampling is strictly prohibited. Thank you for respecting our craft! 🙏
━━━━━━━━━━━━━━━━━━━━
#lofihiphop #studybeats #chillhop #深夜讀書 #深度工作 #放鬆音樂"""


def _fatal_exit(step: str, reason: str) -> None:
    print(f"\n❌ [FATAL ERROR] {step} 失敗: {reason}")
    sys.exit(1)


def _strip_rs_echoes_vol_prefix(text: str) -> str:
    """與 CEO 偏好一致：album_title / youtube_seo 不重複 R&S Echoes Vol.N: 前綴。"""
    if not text or not text.strip():
        return text
    return re.sub(r"R&S Echoes Vol\.\d+:\s*", "", text).strip()


def _creative_prefix_from_llm(raw: str, suffix: str) -> str:
    """從 LLM 回傳取「僅前綴」；若誤含固定尾段則剥除。"""
    s = _strip_rs_echoes_vol_prefix((raw or "").strip())
    if s.endswith(suffix):
        s = s[: -len(suffix)].rstrip()
    return s.strip()


def compose_suffixed_album_title(
    creative: str,
    suffix: str,
    *,
    channel_label: str,
    log_truncation: bool = True,
) -> str:
    """組合 album_title = 前綴 + suffix，總字數（Unicode）≤ ALBUM_TITLE_MAX_TOTAL。"""
    c = _creative_prefix_from_llm(creative, suffix)
    if not c:
        return ""
    max_c = ALBUM_TITLE_MAX_TOTAL - len(suffix)
    if max_c < 1:
        _fatal_exit("Config", f"{channel_label}：固定尾段長度已達或超過上限，無法保留前綴")
    if len(c) > max_c:
        c = c[:max_c].rstrip()
        if log_truncation:
            print(
                f"[METADATA] ℹ️ {channel_label} 專輯前綴已截斷至 ≤{max_c} 字"
                f"（與尾段合計 ≤{ALBUM_TITLE_MAX_TOTAL} 字）"
            )
    out = c + suffix
    if len(out) > ALBUM_TITLE_MAX_TOTAL:
        _fatal_exit("Internal", f"{channel_label} album_title 長度檢查失敗")
    return out


def compose_light_music_album_title(creative: str, *, log_truncation: bool = True) -> str:
    return compose_suffixed_album_title(
        creative,
        LIGHT_MUSIC_ALBUM_TITLE_SUFFIX,
        channel_label="light_music",
        log_truncation=log_truncation,
    )


def compose_lofi_album_title(creative: str, *, log_truncation: bool = True) -> str:
    return compose_suffixed_album_title(
        creative,
        LOFI_ALBUM_TITLE_SUFFIX,
        channel_label="lofi",
        log_truncation=log_truncation,
    )


def _max_prefix_chars(suffix: str) -> int:
    return ALBUM_TITLE_MAX_TOTAL - len(suffix)


def _album_core_before_hashtags(album_title: str) -> str:
    """去掉第一個 # 之後的 hashtag 區（SEO 首行基底）。"""
    s = (album_title or "").strip()
    if "#" in s:
        s = s.split("#", 1)[0].strip()
    return s


def _light_music_seo_headline(album_core: str) -> str:
    """（相容）舊邏輯：依無 hashtag 之 core 替換第一個「 | 」。新正文請用 headline_full。"""
    core = album_core.replace(" | ", " - 1 Hour Ambient Nature Mix ", 1)
    return f"🎵 {core}"


def _light_music_seo_headline_full(album_title: str) -> str:
    """
    CEO 定稿首行：完整 album_title（含尾端 hashtag）後接
    「 - 1 Hour Ambient Nature Mix 🌿 Relaxing Soundscape for Focus & Sleep」。
    """
    t = (album_title or "").strip()
    return f"🎵 {t} - 1 Hour Ambient Nature Mix 🌿"


def _lofi_seo_headline(album_core: str) -> str:
    """🎵 … - 1 Hour Lo-fi Hip Hop Mix …"""
    core = album_core.replace(" | ", " - 1 Hour Lo-fi Hip Hop Mix ", 1)
    return f"🎵 {core}"


def _format_hourly_tracklist_block(tracks: List[str]) -> str:
    """依約 1 小時均分時間軸，輸出 TRACKLIST 區塊。"""
    sep60 = "=" * 60
    cleaned = [str(t).strip() for t in tracks if str(t).strip()]
    if not cleaned:
        return f"【⏱️ TRACKLIST】\n{sep60}\n(曲目待補)\n{sep60}"
    n = len(cleaned)
    total_sec = 3600
    seg = total_sec // n
    lines_body: List[str] = []
    acc = 0
    for name in cleaned:
        mm, ss = divmod(acc, 60)
        lines_body.append(f"{mm:02d}:{ss:02d} - {name}")
        acc += seg
    body = "\n".join(lines_body)
    return f"【⏱️ TRACKLIST】\n{sep60}\n{body}\n{sep60}"


def _tracklist_block_from_assembler_file(raw_text: str) -> Optional[str]:
    """
    由縫合產物 Tracklist_*.txt 正文組出 description 內之 TRACKLIST 區塊（保留真實時間戳）。
    解析失敗回傳 None，呼叫端應退回均分 1 小時邏輯。
    """
    from scripts.common.youtube_cheatsheet_builder import _extract_tracklist_lines_only

    extracted = _extract_tracklist_lines_only(raw_text)
    sep60 = "=" * 60
    if sep60 not in extracted or not re.search(r"\d{2}:\d{2}\s+-\s+", extracted):
        return None
    return f"【⏱️ TRACKLIST】\n{extracted}"


def compose_light_music_youtube_seo(
    album_title: str,
    track_list: List[str],
    *,
    master_tracklist_file_text: Optional[str] = None,
) -> str:
    """
    youtube_seo_description = 專輯意象首行 + Perfect for + TRACKLIST
    + Brand story + Production／Copyright／Hashtag（CEO 範例）。

    若提供 `master_tracklist_file_text`（縫合寫入之 Tracklist_*.txt 全文），
    TRACKLIST 區塊改為 **母帶真實時間軸**；否則以 track_list 均分 1 小時（僅作後備）。
    """
    headline = _light_music_seo_headline_full(album_title)
    perfect = (
        "Perfect for:\n"
        "✨ Studying & Focus\n"
        "🎧 Relaxation & Meditation\n"
        "😴 Sleep & Background Music\n"
        "🎮 Gaming & Streaming"
    )
    if master_tracklist_file_text and master_tracklist_file_text.strip():
        tl = _tracklist_block_from_assembler_file(master_tracklist_file_text)
    else:
        tl = None
    if not tl:
        tl = _format_hourly_tracklist_block(track_list)
    parts = [
        headline,
        "",
        perfect,
        "",
        "---",
        "",
        tl,
        "",
        "---",
        "",
        _LIGHT_MUSIC_BRAND_STORY,
        "",
        _LIGHT_MUSIC_COPYRIGHT_BLOCK,
    ]
    return "\n".join(parts)


def compose_lofi_youtube_seo(
    album_title: str,
    track_list: List[str],
    *,
    master_tracklist_file_text: Optional[str] = None,
) -> str:
    """與 light_music 同結構；若有縫合 Tracklist 全文則時間軸與母帶一致。"""
    core = _album_core_before_hashtags(album_title)
    headline = _lofi_seo_headline(core)
    perfect = (
        "Perfect for:\n"
        "📚 Study & Homework\n"
        "💻 Coding & Deep Work\n"
        "☕ Café & Late Lounge\n"
        "🌙 Midnight Chill"
    )
    if master_tracklist_file_text and master_tracklist_file_text.strip():
        tl = _tracklist_block_from_assembler_file(master_tracklist_file_text)
    else:
        tl = None
    if not tl:
        tl = _format_hourly_tracklist_block(track_list)
    parts = [
        headline,
        "",
        perfect,
        "",
        "---",
        "",
        tl,
        "",
        _LOFI_BRAND_STORY,
        "",
        _LOFI_COPYRIGHT_BLOCK,
    ]
    return "\n".join(parts)


def _is_too_similar(candidate: str, existing_keys: Set[str], threshold: float = 0.75) -> bool:
    """Return True if candidate is ≥threshold similar to any existing normalised title key."""
    for key in existing_keys:
        if SequenceMatcher(None, candidate, key).ratio() >= threshold:
            return True
    return False


def _get_content_signals_from_vaults(channel: str) -> Dict:
    """
    Query audio + visual vaults and return content_signals dict used to
    constrain the LLM so album_title / track_list reflect ACTUAL content.

    Gracefully returns empty signals if vaults are unavailable (new installs,
    CI runs, etc.) — the rest of the generation still proceeds normally.
    """
    signals: Dict = {"audio_moods": [], "audio_genres": [], "video_scenes": []}

    try:
        from scripts.gear2_rnd.vault_database import VaultDatabase
        _av = VaultDatabase()
        cur = _av.conn.cursor()
        cur.execute(
            "SELECT mood, COUNT(*) c FROM audio_assets "
            "WHERE channel=? AND derivation_count=0 AND mood IS NOT NULL "
            "GROUP BY mood ORDER BY c DESC LIMIT 5",
            (channel,),
        )
        signals["audio_moods"] = [r[0] for r in cur.fetchall()]
        cur.execute(
            "SELECT genre, COUNT(*) c FROM audio_assets "
            "WHERE channel=? AND derivation_count=0 AND genre IS NOT NULL "
            "GROUP BY genre ORDER BY c DESC LIMIT 3",
            (channel,),
        )
        signals["audio_genres"] = [r[0] for r in cur.fetchall()]
        _av.close()
    except Exception:
        pass

    try:
        from scripts.gear2_rnd.visual_vault_db import VisualVaultDB
        _vv = VisualVaultDB()
        cur2 = _vv.conn.cursor()
        cur2.execute(
            "SELECT scene_tags FROM video_assets WHERE channel=? AND is_archived=0",
            (channel,),
        )
        counter: Dict[str, int] = {}
        for (raw_tags,) in cur2.fetchall():
            try:
                tags = json.loads(raw_tags) if isinstance(raw_tags, str) else []
            except Exception:
                tags = []
            for t in tags:
                counter[t] = counter.get(t, 0) + 1
        signals["video_scenes"] = [
            t for t, _ in sorted(counter.items(), key=lambda x: x[1], reverse=True)[:5]
        ]
        _vv.close()
    except Exception:
        pass

    return signals


def _build_content_constraint_block(signals: Dict) -> str:
    """Build LLM constraint paragraph from content_signals; returns '' if no data."""
    lines: List[str] = []
    if signals.get("audio_moods"):
        lines.append(f"- Actual audio mood tags: {', '.join(signals['audio_moods'])}")
    if signals.get("audio_genres"):
        lines.append(f"- Audio genres present: {', '.join(signals['audio_genres'])}")
    if signals.get("video_scenes"):
        scenes = ", ".join(signals["video_scenes"])
        lines.append(f"- Video scene tags used in this production: {scenes}")
        lines.append(
            "- The album_title and track names MUST semantically match these actual scenes."
        )
        lines.append(
            "- Do NOT reference visual elements or instruments NOT listed above."
        )
    if not lines:
        return ""
    return "\n\nCONTENT ACCURACY CONSTRAINTS (mandatory — violation = rejection):\n" + "\n".join(lines)


def _title_registry_path() -> Path:
    return config.workspace_root / "assets" / "data" / "youtube_title_registry.json"


def _load_title_registry() -> Dict[str, Dict[str, str]]:
    p = _title_registry_path()
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _save_title_registry(registry: Dict[str, Dict[str, str]]) -> None:
    p = _title_registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(p, registry, indent=2)


def _normalize_title_key(title: str) -> str:
    t = (title or "").strip().lower()
    # 去掉末尾 Vol. N，避免同標題只靠卷號混淆
    t = re.sub(r"\s+vol\.?\s*\d+\s*$", "", t, flags=re.IGNORECASE)
    # 收斂空白與分隔符
    t = re.sub(r"\s+", " ", t)
    return t


def _extract_album_title_from_sheet(sheet_path: Path) -> str:
    try:
        for line in sheet_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("專輯："):
                return line.replace("專輯：", "", 1).strip()
    except Exception:
        return ""
    return ""


def _collect_existing_title_keys(channel: str) -> Set[str]:
    keys: Set[str] = set()
    ch = channel.lower()

    registry = _load_title_registry()
    for k in (registry.get(ch, {}) or {}).keys():
        nk = _normalize_title_key(k)
        if nk:
            keys.add(nk)

    export_dir = config.workspace_root / "assets" / "final_exports" / ch
    if not export_dir.exists():
        return keys

    for p in export_dir.glob("metadata_distrokid*.json"):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            title = str(obj.get("album_title", "")).strip()
            nk = _normalize_title_key(_strip_rs_echoes_vol_prefix(title))
            if nk:
                keys.add(nk)
        except Exception:
            continue

    for p in export_dir.glob("youtube_sheet_*.txt"):
        nk = _normalize_title_key(_extract_album_title_from_sheet(p))
        if nk:
            keys.add(nk)

    return keys


def _title_style_ok(channel: str, album_title: str) -> bool:
    t = (album_title or "").lower()
    if channel == "light_music":
        cues = (
            "ambient", "nature", "calm", "peace", "serene", "ethereal", "horizon",
            "forest", "rain", "breeze", "dawn", "靜", "自然", "空靈", "雨", "風", "光", "晨", "海",
        )
    else:
        cues = (
            "lofi", "lo-fi", "chill", "beats", "study", "midnight", "jazz", "dream",
            "coffee", "city", "夜", "霧", "雨", "夢", "街", "咖啡", "慢",
        )
    return any(c in t for c in cues)


def _register_title(channel: str, album_title: str) -> None:
    ch = channel.lower()
    title = album_title.strip()
    if not title:
        return
    registry = _load_title_registry()
    if ch not in registry or not isinstance(registry[ch], dict):
        registry[ch] = {}
    registry[ch][title] = datetime.now().isoformat(timespec="seconds")
    _save_title_registry(registry)


def _build_distrokid_sheet_content(record: MetadataRecord, channel: str) -> str:
    """
    DistroKid 上架單（對齊 sample）：
    僅保留標題、主曲風、次曲風三段核心欄位。
    """
    ch = channel.lower()
    primary_genre = (
        "Electronic / Ambient" if ch == "light_music" else "Hip-Hop / Lo-fi"
    )
    return f"""==================================================
【R&S Echoes 雙語發行企劃書 (DistroKid / Spotify)】
生成時間: {record.generated_at}
頻道戰區: {channel.upper()}
==================================================

🎧 [Album Title / 專輯名稱]
{record.album_title}

🏷️ [Primary Genre / 主要曲風]
{primary_genre}

🏷️ [Secondary Genre / 次要曲風 (Spotify)]
{record.spotify_subgenre}
"""


def validate_light_music_metadata_record(
    record: MetadataRecord, expected_tracks: Optional[int] = None
) -> List[str]:
    """
    驗證寫入前 light_music 的 MetadataRecord。
    回傳錯誤訊息清單；空陣列表示通過。
    """
    errs: List[str] = []
    at = (record.album_title or "").strip()
    if not at:
        errs.append("album_title 為空")
    else:
        n = len(at)
        if n > ALBUM_TITLE_MAX_TOTAL:
            errs.append(f"album_title 長度 {n} 超過上限 {ALBUM_TITLE_MAX_TOTAL}")
        if not at.endswith(LIGHT_MUSIC_ALBUM_TITLE_SUFFIX):
            errs.append("album_title 未以 light_music 固定尾段結尾")
    tl = record.track_list
    if not isinstance(tl, list) or not tl:
        errs.append("track_list 為空或格式錯誤")
    else:
        for i, x in enumerate(tl, 1):
            if not str(x).strip():
                errs.append(f"track_list 第 {i} 首曲目名稱為空")
        if expected_tracks is not None and len(tl) != expected_tracks:
            errs.append(
                f"track_list 曲目數 {len(tl)} 與本檔預期 {expected_tracks} 不一致"
            )
    if not (record.spotify_subgenre or "").strip():
        errs.append("spotify_subgenre 為空")
    se = record.youtube_seo_description or ""
    if not se.strip():
        errs.append("youtube_seo_description 為空")
    else:
        for marker in ("【⏱️ TRACKLIST】", "Perfect for:", "🎵 "):
            if marker not in se:
                errs.append(f"youtube_seo_description 缺少預期區塊：{marker!r}")
    if not (record.generated_at or "").strip():
        errs.append("generated_at 為空")
    if not (record.youtube_copyright or "").strip():
        errs.append("youtube_copyright 為空")
    return errs


def print_light_music_human_readable_report(
    record: MetadataRecord,
    *,
    json_path: str,
    distrokid_sheet_path: Optional[str] = None,
    expected_tracks: Optional[int] = None,
    seo_preview_chars: int = 900,
) -> None:
    """
    將 light_music 中繼資料以人類易讀格式印出（含驗證狀態與 SEO 預覽）。
    """
    val_errs = validate_light_music_metadata_record(record, expected_tracks)
    status = "✅ 驗證通過" if not val_errs else "⚠️ 驗證有問題（請見上方錯誤）"

    lines: List[str] = []
    lines.append("")
    lines.append("═" * 76)
    lines.append(f"  light_music 中繼資料 — 人類可讀摘要    {status}")
    lines.append("═" * 76)
    if val_errs:
        lines.append("【驗證錯誤】")
        for e in val_errs:
            lines.append(f"  ‣ {e}")
        lines.append("")
    lines.append(f"【JSON】{json_path}")
    if distrokid_sheet_path:
        lines.append(f"【DistroKid Sheet】{distrokid_sheet_path}")
    lines.append(f"【產出時間】{record.generated_at}")
    lines.append("")
    lines.append(
        f"【專輯標題】共 {len(record.album_title)} 字（上限 {ALBUM_TITLE_MAX_TOTAL}）"
    )
    lines.extend(
        textwrap.wrap(
            record.album_title,
            width=72,
            initial_indent="  ",
            subsequent_indent="  ",
        )
    )
    lines.append("")
    lines.append("【創意前綴】（固定尾段之前）")
    creative = _creative_prefix_from_llm(record.album_title, LIGHT_MUSIC_ALBUM_TITLE_SUFFIX)
    lines.extend(
        textwrap.wrap(
            creative or "（無）",
            width=72,
            initial_indent="  ",
            subsequent_indent="  ",
        )
    )
    lines.append("")
    lines.append(f"【Spotify 子曲風】{record.spotify_subgenre}")
    lines.append("")
    ntr = len(record.track_list)
    exp = f"（預期 {expected_tracks} 首）" if expected_tracks is not None else ""
    lines.append(f"【曲目】共 {ntr} 首{exp}")
    for i, name in enumerate(record.track_list, 1):
        lines.append(f"  {i:2d}. {name}")
    lines.append("")
    lines.append(f"【版權短句】{record.youtube_copyright}")
    lines.append("")
    seo = record.youtube_seo_description or ""
    lines.append(
        f"【YouTube SEO 描述】共 {len(seo)} 字 — 下方為前 {seo_preview_chars} 字預覽"
    )
    lines.append("—" * 76)
    preview = seo[:seo_preview_chars] if len(seo) > seo_preview_chars else seo
    for ln in preview.splitlines():
        lines.append(f"  {ln}")
    if len(seo) > seo_preview_chars:
        lines.append(f"  …（尚有 {len(seo) - seo_preview_chars} 字，完整內容見 JSON）")
    lines.append("—" * 76)
    lines.append("")
    print("\n".join(lines), flush=True)


def _generate_light_music_metadata(
    track_count: int,
    volume: str,
    provider: str,
    content_signals: Optional[Dict] = None,
) -> dict:
    """light_music：LLM 產生前綴 + 固定尾段；總長度 ≤ 100；並產出 track_list / spotify_subgenre。"""
    genre_hint = "Light Music, Cinematic Ambient, Acoustic"
    system_prompt = (
        'You are a top-tier Music Distributor for the record label "R&S Echoes". '
        "Always respond with valid JSON only, no markdown, no extra text."
    )

    max_c = _max_prefix_chars(LIGHT_MUSIC_ALBUM_TITLE_SUFFIX)
    suf_literal = LIGHT_MUSIC_ALBUM_TITLE_SUFFIX
    content_block = _build_content_constraint_block(content_signals or {})
    base_prompt = f"""Generate light_music (ambient / nature) release metadata for an album with exactly {track_count} tracks. Volume context: {volume}.

The FINAL store-facing album title will be EXACTLY: your `album_title` field text IMMEDIATELY concatenated with NO extra spaces as:
`{{album_title}}{suf_literal}`

CONSTRAINTS:
- In JSON, `album_title` must be ONLY the creative bilingual name (e.g. English / 繁體中文), NOT including the fixed suffix above.
- The creative part MUST be at most {max_c} Unicode characters so that the full title is at most {ALBUM_TITLE_MAX_TOTAL} characters total.
- Do NOT use "R&S Echoes Vol.X:" prefix. Match ambient / nature / healing vibe.

Musical Style: {genre_hint}.{content_block}

Output strictly in this JSON format:
{{
  "album_title": "Creative EN / 繁中",
  "track_list": ["Track 1", "Track 2"],
  "spotify_subgenre": "[e.g. ambient]"
}}

The track_list array MUST contain exactly {track_count} non-empty strings."""

    _labels = {"zhipu": "智譜 GLM-4", "gemini": "Gemini 2.5 Flash", "minimax": "MiniMax M2.7 (NVIDIA NIM)"}
    engine_label = _labels.get(provider, provider)
    print(
        f"[METADATA] 正在呼叫 {engine_label} 生成 light_music 企劃 "
        f"(Tracks: {track_count}, Provider: {provider})..."
    )
    if content_signals and any(content_signals.values()):
        print(f"[METADATA] 🎯 Content signals: {content_signals}")

    existing_title_keys = _collect_existing_title_keys("light_music")
    rejected_titles: List[str] = []
    last_reason = "unknown"

    for attempt in range(1, 4):
        rejected_block = (
            "\nRejected full album_title list (must not repeat):\n- "
            + "\n- ".join(rejected_titles)
            if rejected_titles
            else ""
        )
        user_prompt = base_prompt + rejected_block
        try:
            response_json = generate_structured_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                provider=provider,
            )
        except Exception as e:
            _fatal_exit("LLM Generation", str(e))

        raw_creative = str(response_json.get("album_title", "")).strip()
        full_title = compose_light_music_album_title(raw_creative, log_truncation=True)
        if not full_title or not _creative_prefix_from_llm(
            raw_creative, LIGHT_MUSIC_ALBUM_TITLE_SUFFIX
        ):
            last_reason = "album_title 前綴空值"
            rejected_titles.append(raw_creative or "<EMPTY>")
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason}")
            continue

        title_key = _normalize_title_key(full_title)
        if title_key in existing_title_keys:
            last_reason = "album_title 與既有標題重複"
            rejected_titles.append(full_title)
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason} -> {full_title}")
            continue

        if _is_too_similar(title_key, existing_title_keys):
            last_reason = "album_title 與既有標題相似度過高 (>75%)"
            rejected_titles.append(full_title)
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason} -> {full_title}")
            continue

        if not _title_style_ok("light_music", full_title):
            last_reason = "album_title 風格不符合 light_music"
            rejected_titles.append(full_title)
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason} -> {full_title}")
            continue

        tl = response_json.get("track_list")
        if not isinstance(tl, list) or len(tl) != track_count:
            last_reason = f"track_list 須為長度 {track_count} 的陣列"
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason}")
            continue
        cleaned_tl: List[str] = []
        bad = False
        for x in tl:
            if not isinstance(x, str) or not str(x).strip():
                bad = True
                break
            cleaned_tl.append(str(x).strip())
        if bad:
            last_reason = "track_list 含空曲目名"
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason}")
            continue

        sg_raw = response_json.get("spotify_subgenre", "ambient")
        sg = str(sg_raw).strip() if isinstance(sg_raw, str) else "ambient"

        response_json["album_title"] = full_title
        response_json["track_list"] = cleaned_tl
        response_json["spotify_subgenre"] = sg or "ambient"
        response_json["youtube_seo_description"] = ""
        _register_title("light_music", full_title)
        return response_json

    _fatal_exit("LLM Generation", f"light_music 嘗試 3 次仍失敗（最後原因: {last_reason}）")


def _generate_lofi_metadata(
    track_count: int,
    volume: str,
    provider: str,
    content_signals: Optional[Dict] = None,
) -> dict:
    """lofi：LLM 產生前綴 + LOFI_ALBUM_TITLE_SUFFIX；總長度 ≤ ALBUM_TITLE_MAX_TOTAL。"""
    genre_hint = "Lo-fi Hip Hop, Chillhop"
    system_prompt = (
        'You are a top-tier Music Distributor for the record label "R&S Echoes". '
        "Always respond with valid JSON only, no markdown, no extra text."
    )

    max_c = _max_prefix_chars(LOFI_ALBUM_TITLE_SUFFIX)
    suf_literal = LOFI_ALBUM_TITLE_SUFFIX
    content_block = _build_content_constraint_block(content_signals or {})
    base_prompt = f"""Generate lofi / chillhop release metadata for an album with exactly {track_count} tracks. Volume context: {volume}.

The FINAL store-facing album title will be EXACTLY: your `album_title` field text IMMEDIATELY concatenated with NO extra spaces as:
`{{album_title}}{suf_literal}`

CONSTRAINTS:
- In JSON, `album_title` must be ONLY the creative bilingual name (e.g. English / 繁體中文), NOT including the fixed suffix above.
- The creative part MUST be at most {max_c} Unicode characters so that the full title is at most {ALBUM_TITLE_MAX_TOTAL} characters total.
- Do NOT use "R&S Echoes Vol.X:" prefix. Match lo-fi / chillhop / study beats vibe.

Musical Style: {genre_hint}.{content_block}

Output strictly in this JSON format:
{{
  "album_title": "Creative EN / 繁中",
  "track_list": ["Track 1", "Track 2"],
  "spotify_subgenre": "[e.g. lo-fi hip hop]"
}}

The track_list array MUST contain exactly {track_count} non-empty strings."""

    _labels = {"zhipu": "智譜 GLM-4", "gemini": "Gemini 2.5 Flash", "minimax": "MiniMax M2.7 (NVIDIA NIM)"}
    engine_label = _labels.get(provider, provider)
    print(
        f"[METADATA] 正在呼叫 {engine_label} 生成 lofi 企劃 "
        f"(Tracks: {track_count}, Provider: {provider})..."
    )
    if content_signals and any(content_signals.values()):
        print(f"[METADATA] 🎯 Content signals: {content_signals}")

    existing_title_keys = _collect_existing_title_keys("lofi")
    rejected_titles: List[str] = []
    last_reason = "unknown"

    for attempt in range(1, 4):
        rejected_block = (
            "\nRejected full album_title list (must not repeat):\n- "
            + "\n- ".join(rejected_titles)
            if rejected_titles
            else ""
        )
        user_prompt = base_prompt + rejected_block
        try:
            response_json = generate_structured_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                provider=provider,
            )
        except Exception as e:
            _fatal_exit("LLM Generation", str(e))

        raw_creative = str(response_json.get("album_title", "")).strip()
        full_title = compose_lofi_album_title(raw_creative, log_truncation=True)
        if not full_title or not _creative_prefix_from_llm(raw_creative, LOFI_ALBUM_TITLE_SUFFIX):
            last_reason = "album_title 前綴空值"
            rejected_titles.append(raw_creative or "<EMPTY>")
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason}")
            continue

        title_key = _normalize_title_key(full_title)
        if title_key in existing_title_keys:
            last_reason = "album_title 與既有標題重複"
            rejected_titles.append(full_title)
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason} -> {full_title}")
            continue

        if _is_too_similar(title_key, existing_title_keys):
            last_reason = "album_title 與既有標題相似度過高 (>75%)"
            rejected_titles.append(full_title)
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason} -> {full_title}")
            continue

        if not _title_style_ok("lofi", full_title):
            last_reason = "album_title 風格不符合 lofi"
            rejected_titles.append(full_title)
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason} -> {full_title}")
            continue

        tl = response_json.get("track_list")
        if not isinstance(tl, list) or len(tl) != track_count:
            last_reason = f"track_list 須為長度 {track_count} 的陣列"
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason}")
            continue
        cleaned_tl: List[str] = []
        bad = False
        for x in tl:
            if not isinstance(x, str) or not str(x).strip():
                bad = True
                break
            cleaned_tl.append(str(x).strip())
        if bad:
            last_reason = "track_list 含空曲目名"
            print(f"[METADATA] ⚠️ 第 {attempt}/3 次重試：{last_reason}")
            continue

        sg_raw = response_json.get("spotify_subgenre", "lo-fi hip hop")
        sg = str(sg_raw).strip() if isinstance(sg_raw, str) else "lo-fi hip hop"

        response_json["album_title"] = full_title
        response_json["track_list"] = cleaned_tl
        response_json["spotify_subgenre"] = sg or "lo-fi hip hop"
        response_json["youtube_seo_description"] = ""
        _register_title("lofi", full_title)
        return response_json

    _fatal_exit("LLM Generation", f"lofi 嘗試 3 次仍失敗（最後原因: {last_reason}）")


def generate_metadata(
    channel: str,
    track_count: int,
    volume: str = "1",
    provider: str = "minimax",
    content_signals: Optional[Dict] = None,
) -> dict:
    if content_signals is None:
        content_signals = _get_content_signals_from_vaults(channel)
    if channel == "light_music":
        return _generate_light_music_metadata(track_count, volume, provider, content_signals)
    if channel == "lofi":
        return _generate_lofi_metadata(track_count, volume, provider, content_signals)
    _fatal_exit("Config", f"不支援的 channel: {channel}")


def main() -> None:
    parser = argparse.ArgumentParser(description="v15.9 雙語版 數位唱片企劃引擎")
    parser.add_argument("--channel", type=str, default="lofi", choices=["lofi", "light_music"])
    parser.add_argument("--volume", type=str, default="X")
    parser.add_argument(
        "--provider",
        type=str,
        default="minimax",
        choices=["zhipu", "gemini", "minimax"],
        help="LLM：minimax（預設）| zhipu | gemini",
    )
    args = parser.parse_args()

    export_dir = config.workspace_root / "assets" / "final_exports" / args.channel
    export_dir.mkdir(parents=True, exist_ok=True)

    wav_files = list(export_dir.glob("*.wav"))
    if wav_files:
        print(f"[METADATA] ℹ️ 找到 {len(wav_files)} 支母帶 WAV（可供企劃引用）")
    else:
        print(
            f"[METADATA] ⚠️ {export_dir} 尚無 WAV 母帶（Phase 4 縫合後再補）—— 仍允許生成 metadata"
        )

    vault_dir = config.workspace_root / "assets" / "audio" / "vault_ready_for_mix" / args.channel
    track_count = len(list(vault_dir.glob("*.wav"))) if vault_dir.exists() else 15
    track_count = max(5, min(track_count, 20))

    metadata_dict = generate_metadata(
        args.channel, track_count, args.volume, provider=args.provider
    )

    tl_raw = metadata_dict.get("track_list", [])
    tl_use: List[str] = tl_raw if isinstance(tl_raw, list) else []
    at = str(metadata_dict.get("album_title", ""))
    master_tl_text: Optional[str] = None
    mp4s_for_tl = sorted(export_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if mp4s_for_tl:
        from scripts.common.tracklist_pick import pick_tracklist_txt_for_mp4

        _tl_path = pick_tracklist_txt_for_mp4(export_dir, mp4s_for_tl[-1])
        if _tl_path and _tl_path.is_file():
            try:
                master_tl_text = _tl_path.read_text(encoding="utf-8")
            except OSError:
                master_tl_text = None
    if args.channel == "light_music":
        metadata_dict["youtube_seo_description"] = compose_light_music_youtube_seo(
            at, tl_use, master_tracklist_file_text=master_tl_text
        )
    else:
        metadata_dict["youtube_seo_description"] = compose_lofi_youtube_seo(
            at, tl_use, master_tracklist_file_text=master_tl_text
        )

    output_path = export_dir / f"metadata_distrokid_{args.channel}.json"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sheet_path = export_dir / f"DistroKid_Sheet_{ts}.txt"

    copyright_year = datetime.now().year
    copyright_notice = f"© {copyright_year} R&S Echoes. All rights reserved."

    record = MetadataRecord(
        album_title=metadata_dict.get("album_title", "R&S Echoes"),
        track_list=metadata_dict.get("track_list", []),
        spotify_subgenre=metadata_dict.get("spotify_subgenre", "lo-fi hip hop"),
        youtube_seo_description=metadata_dict.get(
            "youtube_seo_description", "Enjoy the music. 享受音樂。"
        ),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        youtube_copyright=copyright_notice,
    )

    if args.channel == "light_music":
        val_errs = validate_light_music_metadata_record(record, track_count)
        if val_errs:
            for msg in val_errs:
                print(f"❌ [light_music 驗證] {msg}")
            _fatal_exit(
                "light_music 驗證",
                "中繼資料未通過驗證，已中止寫入（JSON / DistroKid Sheet 皆未輸出）",
            )

    try:
        atomic_write_json(output_path, asdict(record), indent=2)
        print(f"[METADATA] ✅ 雙語中繼資料 JSON 已保存: {output_path.name}")
    except Exception as e:
        _fatal_exit("Output Write", f"無法寫入 JSON: {e}")

    print(f"\n[SHEET] 正在生成 CEO 手動上架 DistroKid Sheet...")
    sheet_content = _build_distrokid_sheet_content(record, args.channel)

    try:
        atomic_write_text(sheet_path, sheet_content)
        print(f"[SHEET] ✅ DistroKid Sheet 已產出: {sheet_path}")
    except Exception as e:
        _fatal_exit("DistroKid Sheet Write", f"無法寫入 Sheet: {e}")

    if args.channel == "light_music":
        print_light_music_human_readable_report(
            record,
            json_path=str(output_path.resolve()),
            distrokid_sheet_path=str(sheet_path.resolve()),
            expected_tracks=track_count,
        )


if __name__ == "__main__":
    main()
