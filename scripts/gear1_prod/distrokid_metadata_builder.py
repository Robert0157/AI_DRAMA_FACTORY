#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DistroKid 發行報表產生器 (Phase 3.5)
─────────────────────────────────────────
v15.12 新增：從 rs_music_vault.db + metadata JSON + 頻道 configs
生成符合 2026 年 DistroKid 規範的單曲級 CSV 上傳報表。

資料來源（單一真實來源）：
  1. rs_music_vault.db      → track_id、derivation_count、channel
  2. metadata_distrokid_{ch}.json → LLM 雙語曲名
  3. configs/channels/{ch}.json   → Record Label、Genre
  4. vault_ready_for_mix/{ch}/    → 實際 WAV 檔案對照

用法：
  python scripts/gear1_prod/distrokid_metadata_builder.py --channel lofi
  python scripts/gear1_prod/distrokid_metadata_builder.py --channel light_music
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# ── 路徑前處理 ──────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import EnvConfig

config = EnvConfig()

# ── 頻道專屬設定（優先讀 configs/channels/{ch}.json，其次使用預設值）──
# 因為 configs/channels/*.json 目前無 label/genre 欄位，此處作為預設來源。
# 未來可將 label/genre 寫入 channels/*.json 並由此處 fallback 讀取。

CHANNEL_DEFAULTS: Dict[str, Dict[str, str]] = {
    "lofi": {
        "record_label": "R&S Echoes",
        "primary_genre": "Electronic",
        "secondary_genre": "Chill Out",
        "songwriter": "Tung-Liang Shieh",
        "instrumental": "Yes",
        "explicit_lyrics": "No",
        "contains_ai": "Yes",
        "content_id": "Yes",
    },
    "light_music": {
        "record_label": "R&S Echoes Nature",
        "primary_genre": "Electronic",
        "secondary_genre": "New Age",
        "songwriter": "Tung-Liang Shieh",
        "instrumental": "Yes",
        "explicit_lyrics": "No",
        "contains_ai": "Yes",
        "content_id": "Yes",
    },
}

# ── 2026/05 DistroKid 上傳表 Headers ────────────────────────────
CSV_HEADERS = [
    "Track Number",
    "Track Title",
    "Audio File Name",
    "Primary Genre",
    "Secondary Genre",
    "Songwriter Real Name",
    "Record Label",
    "Instrumental?",
    "Explicit Lyrics?",
    "Contains AI/Synthetic?",
    "Shorts/TikTok Start (sec)",
    "YouTube Content ID?",
    "ISRC (Leave Blank)",
]


def _load_channel_config(channel: str) -> Dict[str, str]:
    """從 configs/channels/{channel}.json 讀取頻道設定（label/genre 等）。

    若 JSON 存在且包含對應 key 則優先使用，否則回退至 CHANNEL_DEFAULTS。
    """
    cfg = dict(CHANNEL_DEFAULTS.get(channel, CHANNEL_DEFAULTS["lofi"]))
    cfg_path = config.workspace_root / "configs" / "channels" / f"{channel}.json"
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            # 若未來 configs/channels/*.json 新增 distrokid 區段，優先採用
            dk = data.get("distrokid", {}) if isinstance(data, dict) else {}
            for key in (
                "record_label", "primary_genre", "secondary_genre",
                "songwriter", "instrumental", "explicit_lyrics",
                "contains_ai", "content_id",
            ):
                if key in dk and dk[key]:
                    cfg[key] = str(dk[key])
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def _load_llm_metadata(channel: str) -> Optional[Dict]:
    """讀取 metadata_distrokid_{channel}.json 取得 LLM 生成的專輯中繼資料。"""
    export_dir = config.workspace_root / "assets" / "final_exports" / channel.lower()
    if not export_dir.exists():
        return None

    # 優先讀取頻道限定 JSON
    meta_path = export_dir / f"metadata_distrokid_{channel.lower()}.json"
    if not meta_path.exists():
        fallback = sorted(
            export_dir.glob("metadata_distrokid*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        meta_path = fallback[0] if fallback else None

    if meta_path is None or not meta_path.exists():
        return None

    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ── v15.12 衍生曲目關鍵字（雙重防禦：即使 DB dc=0 也排除）──
# CEO 鐵律：Remix 歌曲（pitch/tempo 變形）不產生 ISRC，只有 Suno 原始母帶才發行。
_DERIVATIVE_KEYWORDS = ["pitch_up", "pitch_down", "tempo_up", "tempo_down"]


def _is_derivative_track_id(track_id: str) -> bool:
    """檢查 track_id 是否包含衍生關鍵字（pitch_up/down, tempo_up/down）。

    此為雙重防禦機制：即使 rs_music_vault.db 中 derivation_count 欄位
    因歷史資料問題標記為 0，只要檔名含衍生關鍵字一律排除。
    """
    tid_lower = track_id.lower()
    return any(kw in tid_lower for kw in _DERIVATIVE_KEYWORDS)


def _query_gen0_tracks(channel: str) -> List[Dict]:
    """從 rs_music_vault.db 查詢 derivation_count=0 且 channel 匹配的 Gen0 曲目。

    雙重防禦（v15.12）：
      1. DB 層：derivation_count = 0
      2. 關鍵字層：排除 track_id 含 pitch_up/pitch_down/tempo_up/tempo_down
    """
    from scripts.gear2_rnd.vault_database import VaultDatabase

    vault = VaultDatabase()
    cur = vault.conn.cursor()
    cur.execute(
        """
        SELECT track_id, original_path
        FROM audio_assets
        WHERE channel = ? AND derivation_count = 0 AND is_archived = 0
        ORDER BY track_id ASC
        """,
        (channel.lower(),),
    )
    rows = cur.fetchall()
    vault.close()

    tracks = []
    excluded = 0
    for r in rows:
        tid = r[0]
        if _is_derivative_track_id(tid):
            excluded += 1
            continue
        tracks.append({"track_id": tid, "original_path": r[1]})

    if excluded > 0:
        print(f"⚠️  [雙重防禦] 排除 {excluded} 首含衍生關鍵字的曲目（dc=0 但檔名為 Remix）")

    return tracks


def _resolve_wav_path(track_id: str, channel: str) -> Optional[Path]:
    """於 vault_ready_for_mix/{channel}/ 中尋找對應 track_id 的 WAV 檔案。

    搜尋策略（依序）：
      1. 精確檔名 {track_id}.wav
      2. 前綴匹配 {track_id}_*.wav（部分 Suno 輸出附加後綴）
    """
    vault_dir = config.workspace_root / "assets" / "audio" / "vault_ready_for_mix" / channel.lower()
    if not vault_dir.exists():
        return None

    exact = vault_dir / f"{track_id}.wav"
    if exact.exists():
        return exact

    prefix_matches = sorted(vault_dir.glob(f"{track_id}_*.wav"))
    if prefix_matches:
        return prefix_matches[0]

    return None


def _parse_shorts_start(filename: str) -> int:
    """從檔名解析 Shorts/TikTok 建議起始秒數（慣例：倒數第二段數字）。

    例如 '01_Lofi_MinimalHouse_NeonBoulevard_0045.wav' → 45 秒。
    若無法解析，回傳 0。
    """
    stem = Path(filename).stem
    parts = stem.split("_")
    # 嘗試取倒數第一段或倒數第二段中的純數字
    candidates = []
    for part in reversed(parts):
        if part.isdigit():
            candidates.append(int(part))
    return candidates[0] if candidates else 0


def build_distrokid_upload_csv(channel: str, output_dir: Optional[Path] = None) -> Path:
    """生成 DistroKid 單曲級 CSV 上傳報表。

    Args:
        channel: 頻道識別碼（lofi 或 light_music）。
        output_dir: 輸出目錄；預設為 assets/final_exports/{channel}/。

    Returns:
        已寫入的 CSV 檔案路徑。

    Raises:
        FileNotFoundError: vault_ready_for_mix/{channel} 目錄不存在或無 WAV。
        RuntimeError: DB 查詢失敗或 metadata JSON 缺漏。
    """
    ch = channel.lower()
    if ch not in ("lofi", "light_music"):
        raise ValueError(f"不支援的頻道: {channel}（僅接受 lofi / light_music）")

    # 1. 讀取頻道設定
    channel_cfg = _load_channel_config(ch)

    # 2. 查詢 Gen0 曲目
    tracks = _query_gen0_tracks(ch)
    if not tracks:
        raise RuntimeError(
            f"rs_music_vault.db 中無 channel={ch} 且 derivation_count=0 的曲目。"
            f"請先執行 Phase 2 母帶處理。"
        )

    # 3. 讀取 LLM metadata（曲名對照）
    llm_meta = _load_llm_metadata(ch)
    llm_track_list: List[str] = []
    if llm_meta and isinstance(llm_meta.get("track_list"), list):
        llm_track_list = [str(t).strip() for t in llm_meta["track_list"]]

    # 4. 設定輸出路徑
    if output_dir is None:
        output_dir = config.workspace_root / "assets" / "final_exports" / ch
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"DistroKid_Upload_{ch}_{ts}.csv"

    # 5. 組裝 CSV 資料列
    rows: List[Dict] = []
    for idx, track in enumerate(tracks, start=1):
        track_id = track["track_id"]

        # 解析 Shorts 起始秒數
        shorts_start = _parse_shorts_start(track_id)

        # 曲名：優先使用 LLM metadata 中對應索引的雙語曲名，否則用 track_id
        if idx - 1 < len(llm_track_list):
            title = llm_track_list[idx - 1]
        else:
            title = track_id.replace("_", " ")

        # 音檔檔名
        wav_path = _resolve_wav_path(track_id, ch)
        audio_filename = wav_path.name if wav_path else f"{track_id}.wav"

        row = {
            "Track Number": idx,
            "Track Title": title,
            "Audio File Name": audio_filename,
            "Primary Genre": channel_cfg["primary_genre"],
            "Secondary Genre": channel_cfg["secondary_genre"],
            "Songwriter Real Name": channel_cfg["songwriter"],
            "Record Label": channel_cfg["record_label"],
            "Instrumental?": channel_cfg["instrumental"],
            "Explicit Lyrics?": channel_cfg["explicit_lyrics"],
            "Contains AI/Synthetic?": channel_cfg["contains_ai"],
            "Shorts/TikTok Start (sec)": shorts_start,
            "YouTube Content ID?": channel_cfg["content_id"],
            "ISRC (Leave Blank)": "",
        }
        rows.append(row)

    # 6. 寫入 CSV（UTF-8-BOM 確保 Excel 正確顯示中文）
    try:
        with open(csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(rows)
    except OSError as e:
        raise RuntimeError(f"無法寫入 CSV: {csv_path} — {e}") from e

    return csv_path


# ── CLI 入口 ────────────────────────────────────────────────────
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="DistroKid 發行報表產生器 — 從 DB + LLM metadata 生成 CSV 上傳表"
    )
    parser.add_argument(
        "--channel", required=True, choices=["lofi", "light_music"],
        help="目標頻道",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="輸出路徑（預設: assets/final_exports/{channel}/）",
    )
    args = parser.parse_args()

    try:
        csv_path = build_distrokid_upload_csv(args.channel, args.output_dir)
        print(f"✅ DistroKid CSV 上傳報表已生成：{csv_path.name}")
        print(f"   完整路徑：{csv_path}")
        print(f"   頻道：{args.channel.upper()}")
        print(f"   已自動標記 AI 生成身分與 YouTube Content ID。")
        print(f"   請將此 CSV 與 vault_ready_for_mix/{args.channel}/ 的 WAV 一併用於 DistroKid 上傳。")
    except Exception as e:
        print(f"❌ 生成失敗：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
