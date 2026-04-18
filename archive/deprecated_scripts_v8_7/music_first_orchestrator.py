#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 齒輪一 (生產部) - Music First 節拍分鏡中樞 (v8.0 分卷切割版)
檔案名稱: music_first_orchestrator.py

【v8.0 核動力鐵律】：
  1. 解除總時長限制，支援 5-10 分鐘長大片 (Epic Long-Form)。
  2. 分卷切割 (Chunking)：自動將長音軌每 60 秒切分為一個獨立卷宗 (Volume)。
  3. 強制調用 scripts.common.llm_client 輸出 100% 結構化 JSON。
  4. 產出多份 vol_1.json, vol_2.json... 供 Veo API 引擎進行首尾繼承算圖。
"""

import os
import sys
import random
import datetime
import argparse
from pathlib import Path

# ── 引入 v8.0 三大底層護法 ─────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.common.atomic_io import atomic_write_json
from scripts.common.llm_client import generate_structured_json

try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

# ============================================================
# 參數鎖定 (v8.0 分卷設定)
# ============================================================
CHUNK_DURATION_SEC = 60.0   # 每個卷宗(Volume)的長度：60秒
SEG_MIN_SEC = 3.0           # 最短分鏡 3 秒
SEG_MAX_SEC = 5.5           # 最長分鏡 5.5 秒

def _sec_to_timestamp(sec: float) -> str:
    m, s = int(sec // 60), int(sec % 60)
    return f"{m:02d}:{s:02d}"

def analyze_beats_epic(audio_path: Path) -> tuple[list[dict], float]:
    """使用 librosa 進行節拍追蹤，並將整首長歌切割為多個 60 秒的 Chunk。"""
    if not LIBROSA_AVAILABLE:
        raise RuntimeError("librosa 未安裝，請執行 pip install librosa")

    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    raw_duration = float(librosa.get_duration(y=y, sr=sr))
    print(f"   ⏱️ 原始史詩音頻長度: {raw_duration:.1f} 秒")

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_arr, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    chunks = []
    chunk_idx = 1
    current_start = 0.0

    # 開始分卷切割邏輯
    while current_start < raw_duration:
        current_end = min(current_start + CHUNK_DURATION_SEC, raw_duration)
        
        # 取出屬於這個 60 秒區間內的節拍
        chunk_beats = [b for b in beat_times if current_start <= b <= current_end]
        
        segments = []
        seg_start = current_start
        for bt in chunk_beats:
            if bt - seg_start >= SEG_MIN_SEC:
                seg_end = min(bt, seg_start + SEG_MAX_SEC, current_end)
                segments.append((round(seg_start, 2), round(seg_end, 2)))
                seg_start = seg_end if seg_end < bt else bt

        # 收尾剩餘時間
        if current_end - seg_start >= 2.0:
            segments.append((round(seg_start, 2), round(current_end, 2)))
            
        # 👑 硬鎖定 15 鏡防護 (確保 Veo API 每個 Volume 不會超過配額)
        segments = segments[:15]
        
        chunks.append({
            "vol_id": f"vol_{chunk_idx}",
            "start_sec": current_start,
            "end_sec": current_end,
            "segments": segments
        })
        
        print(f"   🎬 成功切割 {chunks[-1]['vol_id']} ({current_start:.1f}s - {current_end:.1f}s) → {len(segments)} 鏡")
        
        chunk_idx += 1
        current_start = current_end
        
    return chunks, raw_duration

def generate_storyboard_with_llm(segments: list, theme: str, vol_id: str) -> list[dict]:
    """呼叫護法 llm_client 為單一卷宗產出 Structured JSON 分鏡"""
    total_shots = len(segments)
    beat_info = "\n".join([f"Shot {i+1}: {_sec_to_timestamp(s)}-{_sec_to_timestamp(e)}" for i, (s, e) in enumerate(segments)])

    sys_prompt = (
        "你是一位台灣職場微電影的視覺導演。請為其中 60 秒的音樂段落生成分鏡。\n"
        "【嚴格規範】\n"
        "1. 純視覺定格動畫 MV，絕對禁止出現任何對話、旁白或字幕提示。\n"
        "2. 主角為破舊的木偶/布偶，場景為 1990 年代復古辦公室。\n"
        "3. 必須且只能回傳一個 JSON Object，包含 `shots` 陣列。"
    )

    user_prompt = (
        f"主題：{theme}\n"
        f"目前卷宗：{vol_id}\n"
        f"時間區間：\n{beat_info}\n\n"
        f"請生成 {total_shots} 鏡分鏡 JSON，格式必須為：\n"
        f"{{\n"
        f"  \"shots\": [\n"
        f"    {{\"visual_prompt\": \"英文視覺描述 (含定格動畫特徵)\", \"action\": \"中文動作描述 (無對白)\", \"is_loopable\": true}}\n"
        f"  ]\n"
        f"}}"
    )

    print(f"   🤖 呼叫 GLM-4-Flash 為 {vol_id} 結構化輸出 ({total_shots} 鏡)...")
    result_json = generate_structured_json(sys_prompt, user_prompt)
    shots = result_json.get("shots", [])
    
    # 補齊防呆
    while len(shots) < total_shots:
        shots.append(shots[-1] if shots else {"visual_prompt": "puppet in office", "action": "發呆", "is_loopable": True})
    
    return shots[:total_shots]

def orchestrate(audio_path_str: str, theme: str, episode_id: str):
    workspace = Path(config.workspace_root)
    audio_path = workspace / audio_path_str if not Path(audio_path_str).is_absolute() else Path(audio_path_str)
    
    print("\n" + "=" * 60)
    print(f"🧠 Music First 分卷大腦啟動 | 劇集: {episode_id}")
    print("=" * 60)
    
    chunks, actual_duration = analyze_beats_epic(audio_path)
    
    # v8.0: 建立該集數專屬的腳本目錄
    script_dir = workspace / "assets" / "scripts" / episode_id
    script_dir.mkdir(parents=True, exist_ok=True)
    
    # 開始逐卷呼叫 LLM 並存檔
    output_files = []
    for chunk in chunks:
        vol_id = chunk["vol_id"]
        segments = chunk["segments"]
        
        # 呼叫大模型寫這 60 秒的劇本
        shots = generate_storyboard_with_llm(segments, theme, vol_id)
        
        # 封裝該卷宗資料
        sequence = []
        for i, ((start_sec, end_sec), shot) in enumerate(zip(segments, shots)):
            sequence.append({
                "shot_id": f"shot_{i+1:02d}",
                "start_sec": start_sec,
                "end_sec": end_sec,
                "visual_prompt": shot.get("visual_prompt", ""),
                "action": shot.get("action", "")
            })

        storyboard = {
            "episode_metadata": {
                "episode_id": episode_id, 
                "theme": theme, 
                "volume": vol_id,
                "total_shots": len(sequence)
            },
            "storyboard_sequence": sequence
        }

        # 👑 透過護法原子寫入 vol_n.json
        out_path = script_dir / f"{vol_id}.json"
        atomic_write_json(out_path, storyboard)
        print(f"   ✅ {vol_id}.json 原子寫入完成: {out_path.name}")
        output_files.append(out_path)
        
    print(f"\n🎉 總譜分析與分卷完成！共產出 {len(output_files)} 個卷宗。")
    return output_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--theme", default="台灣職場社畜的生存幻想")
    parser.add_argument("--episode-id", default=datetime.datetime.now().strftime("%Y%m%d_%H%M"))
    args = parser.parse_args()
    orchestrate(args.audio, args.theme, args.episode_id)