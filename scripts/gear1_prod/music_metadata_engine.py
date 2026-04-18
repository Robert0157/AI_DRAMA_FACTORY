#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
music_metadata_engine.py
數位唱片企劃引擎 (Music Metadata & Distribution Engine) — v15.9 國際雙語版
Phase 3：llm_client.generate_structured_json（預設 MiniMax / NVIDIA NIM），不依賴 MJ/Kling。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
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


def _fatal_exit(step: str, reason: str) -> None:
    print(f"\n❌ [FATAL ERROR] {step} 失敗: {reason}")
    sys.exit(1)


def _strip_rs_echoes_vol_prefix(text: str) -> str:
    """與 CEO 偏好一致：album_title / youtube_seo 不重複 R&S Echoes Vol.N: 前綴。"""
    if not text or not text.strip():
        return text
    return re.sub(r"R&S Echoes Vol\.\d+:\s*", "", text).strip()


def generate_metadata(
    channel: str,
    track_count: int,
    volume: str = "1",
    provider: str = "minimax",
) -> dict:
    genre_hint = (
        "Lo-fi Hip Hop, Chillhop"
        if channel == "lofi"
        else "Light Music, Cinematic Ambient, Acoustic"
    )

    system_prompt = (
        'You are a top-tier Music Distributor and YouTube SEO Specialist '
        'for the record label "R&S Echoes". '
        "Always respond with valid JSON only, no markdown, no extra text."
    )

    user_prompt = f"""Generate the release metadata for a new {channel} album containing {track_count} tracks. Volume number is {volume}.

CRITICAL REQUIREMENT:
The `youtube_seo_description` MUST be fully BILINGUAL. Provide the English version first, followed by the Traditional Chinese (繁體中文) version.
Do NOT start either paragraph with "R&S Echoes Vol.X:" — the SEO body should jump straight into the creative description.
Use a clean bilingual album_title WITHOUT the "R&S Echoes Vol.X:" prefix — only "[Creative Title EN] / [Creative Title ZH]".

Brand Identity: R&S Echoes provides high-quality, seamless, and soul-healing background music.
Musical Style: {genre_hint}.

Output strictly in this JSON format:
{{
  "album_title": "[Creative Title EN] / [Creative Title ZH]",
  "track_list": ["Creative Track 1 Name (EN/ZH)", "Creative Track 2 Name (EN/ZH)"],
  "spotify_subgenre": "[Best matching Spotify subgenre, e.g., lo-fi hip hop]",
  "youtube_seo_description": "[EN Description]\\n\\n[ZH Description]\\n\\nHashtags: #rnsechoes #..."
}}"""

    _labels = {"zhipu": "智譜 GLM-4", "gemini": "Gemini 2.5 Flash", "minimax": "MiniMax M2.7 (NVIDIA NIM)"}
    engine_label = _labels.get(provider, provider)
    print(
        f"[METADATA] 正在呼叫 {engine_label} 生成雙語企劃 "
        f"(Channel: {channel}, Tracks: {track_count}, Provider: {provider})..."
    )

    try:
        response_json = generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=provider,
        )
        return response_json
    except Exception as e:
        _fatal_exit("LLM Generation", str(e))


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

    _seo = metadata_dict.get("youtube_seo_description", "Enjoy the music. 享受音樂。")
    metadata_dict["youtube_seo_description"] = (
        _strip_rs_echoes_vol_prefix(_seo) if isinstance(_seo, str) else _seo
    )
    _album = metadata_dict.get("album_title", "R&S Echoes")
    metadata_dict["album_title"] = _strip_rs_echoes_vol_prefix(_album) if isinstance(_album, str) else _album

    output_path = export_dir / f"metadata_distrokid_{args.channel}.json"
    cheatsheet_path = export_dir / f"DistroKid_CheatSheet_{args.channel}.txt"

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

    try:
        atomic_write_json(output_path, asdict(record), indent=2)
        print(f"[METADATA] ✅ 雙語中繼資料 JSON 已保存: {output_path.name}")
    except Exception as e:
        _fatal_exit("Output Write", f"無法寫入 JSON: {e}")

    print(f"\n[CHEATSHEET] 正在生成 CEO 手動上架雙語企劃書...")
    cheatsheet_content = f"""==================================================
【R&S Echoes 雙語發行企劃書 (DistroKid / Spotify)】
生成時間: {record.generated_at}
頻道戰區: {args.channel.upper()}
==================================================

🎧 [Album Title / 專輯名稱]
{record.album_title}

🏷️ [Primary Genre / 主要曲風]
Electronic / Ambient

🏷️ [Secondary Genre / 次要曲風 (Spotify)]
{record.spotify_subgenre}

📝 [YouTube SEO Description / 雙語宣傳文案]
{record.youtube_seo_description}

© [Copyright / 版權聲明]
{record.youtube_copyright}

==================================================
🎵 [Tracklist / 雙語曲目清單 (請逐一複製)]
==================================================
"""
    for idx, track_name in enumerate(record.track_list, 1):
        cheatsheet_content += f"{idx:02d}. {track_name}\n"

    try:
        atomic_write_text(cheatsheet_path, cheatsheet_content)
        print(f"[CHEATSHEET] ✅ 雙語 DistroKid CheatSheet 已產出: {cheatsheet_path}")
    except Exception as e:
        _fatal_exit("CheatSheet Write", f"無法寫入 CheatSheet: {e}")


if __name__ == "__main__":
    main()
