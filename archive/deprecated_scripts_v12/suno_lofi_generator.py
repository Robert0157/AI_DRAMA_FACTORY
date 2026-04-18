#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
suno_lofi_generator.py

Suno AI 提示詞矩陣生成器 (Suno Prompt Matrix Randomizer)

取代傳統 LLM 提示詞生成的方式，使用預定義的 Prompt 矩陣進行隨機抽籤，
生成多樣化且有品牌風格一致性的 Lo-Fi / Chill Hop 音樂提示詞。

結構說明：
- 情境 (Scenario): 工作/學習/冥想/休閒
- 節奏 (Tempo): slow/medium/upbeat  
- 樂器 (Instruments): piano/lofi-hiphop-drums/modular-synth/ambient-pad
- 情緒 (Mood): melancholic/peaceful/introspective/nostalgic
- 效果 (Effects): vinyl-crackle/reverb/delay/lo-fi-filter
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 讓腳本可直接以檔案路徑執行
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.atomic_io import atomic_write_json, atomic_write_text
from scripts.common.env_manager import config


AUTHOR_NAME = "R&S Echoes"
GEO_TAGS = {
    "taipei", "brooklyn", "kyoto", "seoul", "tokyo", "london", "paris", "osaka",
    "newyork", "new york", "berlin", "shanghai", "taiwan", "japan", "korea",
}


def _quota_file() -> Path:
    return Path(config.workspace_root) / "assets" / ".daily_quota.json"


def _load_quota_payload() -> dict:
    quota_path = _quota_file()
    if quota_path.exists():
        try:
            return json.loads(quota_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "quotas": {}}


def _reserve_daily_sequences(count: int) -> tuple[int, str]:
    """預留當日序號區間，回傳 (起始序號, 日期字串MMDDYY)。"""
    payload = _load_quota_payload()
    today_key = datetime.now().strftime("%Y-%m-%d")
    date_mmddyy = datetime.now().strftime("%m%d%y")

    quotas = payload.setdefault("quotas", {})
    rec = quotas.get(today_key, {
        "date": today_key,
        "approved_count": 0,
        "rejected_count": 0,
        "pending_count": 0,
        "approved_tracks": [],
    })

    existing_generated = int(rec.get("generated_count", 0))
    if existing_generated <= 0:
        existing_generated = int(rec.get("approved_count", 0)) + int(rec.get("rejected_count", 0)) + int(rec.get("pending_count", 0))

    start_seq = existing_generated
    rec["generated_count"] = existing_generated + count
    quotas[today_key] = rec
    payload["generated_at"] = datetime.now().isoformat(timespec="seconds")

    atomic_write_json(_quota_file(), payload, indent=2)
    return start_seq, date_mmddyy


def generate_industrial_title(tags_list: list[str], daily_sequence: int, date_str: str) -> str:
    """生成 [16字母]_[MMDDYY]_[00X] 工業級標題，且排除地理標籤。"""
    seq_str = f"{daily_sequence:03d}"

    non_geo_tags: list[str] = []
    for idx, tag in enumerate(tags_list):
        normalized = re.sub(r"[^A-Za-z]", "", tag).lower()
        if idx == 0:
            continue
        if normalized in GEO_TAGS:
            continue
        non_geo_tags.append(tag)

    camel_tokens: list[str] = []
    for tag in non_geo_tags:
        words = re.findall(r"[A-Za-z]+", tag)
        if not words:
            continue
        camel_tokens.append("".join(w.capitalize() for w in words))

    clean_str = "".join(camel_tokens)
    if len(clean_str) >= 16:
        name_16 = clean_str[:16]
    else:
        name_16 = (clean_str + "LofiVibeTrack")[:16]

    return f"{name_16}_{date_str}_{seq_str}"


# ==================== Suno Prompt 矩陣定義 ====================

SUNO_PROMPT_MATRIX = {
    # 【CTO v13.0 - 極簡標籤與括號引導法 (Minimalist Tags + Parentheses Directives)】
    
    # 核心樂器組合 (2-3 個樂器)
    "instruments": [
        "mellow piano",
        "soft guitar",
        "warm synth pads",
        "lo-fi drums",
        "jazzy lounge vibes",
        "ambient strings layer",
    ],
    
    # 核心曲風 (1-2 個曲風)
    "sub_genres": [
        "Slowcore",
        "Indietronica",
        "Bedroom Pop",
        "Dream Pop",
    ],
    
    # 情緒色彩 (1-2 個情緒)
    "moods": [
        "introspective",
        "peaceful",
        "melancholic",
        "nostalgic",
    ],
    
    # 【CTO v15.1 - 時間膨脹硬編碼】嚴格對齊 CEO 驗證成功的 prompt 樣式
    "time_expansion_stages": [
        {
            "label": "[Atmospheric Intro]",
            "directive": "(Keep it short)",
            "spacer_count": 1,
        },
        {
            "label": "[Extended Main Lo-Fi Beat]",
            "directive": "(Introduce mellow bass)",
            "spacer_count": 2,
        },
        {
            "label": "[Extended Instrumental Verse]",
            "directive": "(Tight lines)",
            "spacer_count": 3,
        },
        {
            "label": "[Continuous Groove]",
            "directive": "(Maintain energy)",
            "spacer_count": 2,
        },
        {
            "label": "[Breakdown]",
            "directive": "(Space + contrast, strip drums)",
            "spacer_count": 1,
        },
        {
            "label": "[Outro]",
            "directive": "(Leave room for crossfade, atmospheric pads only)",
            "spacer_count": 0,
        },
    ],
}


# ==================== 提示詞生成函式 ====================

def _build_suno_prompt(
    scenario: Optional[str] = None,
    tempo: Optional[str] = None,
    lead: Optional[str] = None,
    rhythm: Optional[str] = None,
    mood: Optional[str] = None,
    effect: Optional[str] = None,
    technique: Optional[str] = None,
    seed: int = 42,
) -> tuple[str, str, list[str]]:
    """
    【CTO v15.1 - 低密度訊號系統 + 時間膨脹硬編碼】
    
    實施三大改進：
    1. Tags 欄位實施「低密度訊號」（強制約束）
       - 嚴格限制：1 個地理/曲風 + 1 個情緒 + 1-2 個樂器
       - 防護咒語：seamless loop, pristine studio sound, NO vocals, NO vinyl crackle, NO tape hiss
       - 總長限制：< 120 字元
    
        2. Prompt 欄位實施「時間膨脹」硬編碼格式
             - 使用 Extended 關鍵字、空白行與 ... 佔位符放慢段落推進
             - 嚴格對齊 CEO 驗證成功的段落數量與字面內容
             - 透過真實送出的 \n 與 ... 強迫 Suno 延長每個段落的處理時間
    
    Args:
        seed: 隨機種子
        
    Returns:
        (tags, prompt) 元組
        - tags：低密度逗號分隔字符串（< 120 字元）
        - prompt：6 段時間膨脹結構（包含空白行與 ... 佔位符）
    """
    random.seed(seed)
    
    # =============== TAGS 欄位（低密度訊號）===============
    # 嚴格遵守：1 曲風 + 1 情緒 + 1-2 樂器
    geographic = random.choice(["Taipei Indie", "Brooklyn Nights", "Kyoto Dawn"])  # 地理標籤（僅供命名過濾測試）
    sub_genre = random.choice(SUNO_PROMPT_MATRIX["sub_genres"])              # 1 個曲風
    mood = random.choice(SUNO_PROMPT_MATRIX["moods"])                        # 1 個情緒
    instrument_1 = random.choice(SUNO_PROMPT_MATRIX["instruments"])          # 1 個樂器
    instrument_2 = random.choice(SUNO_PROMPT_MATRIX["instruments"])          # 2 個樂器
    
    # 避免樂器重複
    while instrument_2 == instrument_1:
        instrument_2 = random.choice(SUNO_PROMPT_MATRIX["instruments"])
    
    # 【CTO v14.0】低密度組件：按重要性排序
    # 前置權重優先，防護咒語最後
    tags_parts = [
        sub_genre,                      # 曲風帶頭
        instrument_1,                   # 主樂器
        instrument_2,                   # 副樂器
        mood,                           # 情緒收尾
        "75 bpm",                      # 技術參數
        "seamless loop, pristine studio sound, NO vocals, NO vinyl crackle, NO tape hiss"  # 防護咒語
    ]
    
    tags = ", ".join(tags_parts)
    
    # 驗證長度（緊急縮減）
    if len(tags) > 120:
        tags_parts = [
            sub_genre,
            instrument_1,
            instrument_2,
            "75 bpm",
            "pristine, NO vocals, NO crackle, seamless loop"
        ]
        tags = ", ".join(tags_parts)
    
    # =============== PROMPT 欄位（時間膨脹結構）===============
    # 【CTO v15.1】必須保留真實換行與 ...，不能被 strip 或壓縮
    stages = SUNO_PROMPT_MATRIX["time_expansion_stages"]

    prompt_sections: list[str] = []
    for stage in stages:
        prompt_sections.append(f"{stage['label']} {stage['directive']}")
        for _ in range(stage["spacer_count"]):
            prompt_sections.append("...")
            prompt_sections.append("")

    while prompt_sections and prompt_sections[-1] == "":
        prompt_sections.pop()

    prompt = "\n".join(prompt_sections)
    
    naming_tags = [geographic, sub_genre, mood, instrument_1, instrument_2]
    return tags, prompt, naming_tags


def _generate_prompt_batch(count: int = 5, seed: int = 42) -> list[dict]:
    """
    【CTO v12.0 - 雙軌批次生成】
    生成一批唯一的 Suno 提示詞（分離 tags 和 prompt）
    
    Args:
        count: 要生成的提示詞數量
        seed: 隨機種子
        
    Returns:
        包含各提示詞的字典列表，每個字典包含 tags 和 prompt 分離欄位
    """
    random.seed(seed)
    batch = []
    start_seq, date_mmddyy = _reserve_daily_sequences(count)
    
    for idx in range(count):
        tags, prompt, naming_tags = _build_suno_prompt(seed=seed + idx)
        daily_sequence = start_seq + idx + 1
        title = generate_industrial_title(naming_tags, daily_sequence, date_mmddyy)
        batch.append({
            "id": idx + 1,
            "title": title,
            "author": AUTHOR_NAME,
            "tags": tags,              # 【新】技術風格參數（逗號分隔）
            "prompt": prompt,          # 【新】結構元標籤（換行分隔）
            "seed": seed + idx,
            "daily_sequence": daily_sequence,
            "generated_at": datetime.now().isoformat(timespec="seconds")
        })
    
    return batch


def _build_arg_parser() -> argparse.ArgumentParser:
    """建立命令行參數解析器"""
    parser = argparse.ArgumentParser(
        description="R&S Echoes Suno Prompt 矩陣生成器"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="生成提示詞數量（預設 5）"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="隨機種子（預設 42）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="suno_prompt_batch.json",
        help="輸出檔案名稱"
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="列印所有生成的提示詞"
    )
    return parser


def main() -> None:
    """
    主程序入口
    
    【CTO v10.0 CEO 控制機制】
    支援外部提示詞注入（Method B: File Injection）
    - 優先檢查 assets/.ceo_prompts/*.txt 中是否存在 CEO 提交的提示詞
    - 若存在，直接使用，跳過矩陣生成
    - 若不存在，使用 Underground Formula 隨機生成
    """
    args = _build_arg_parser().parse_args()
    
    workspace_root = Path(config.workspace_root)
    export_dir = workspace_root / "assets" / "final_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    # 【File Injection Point】檢查 CEO 提交目錄
    ceo_prompts_dir = workspace_root / "assets" / ".ceo_prompts"
    ceo_prompts_dir.mkdir(parents=True, exist_ok=True)
    
    # 掃描是否有 CEO 提交的提示詞文件
    prompt_files = list(ceo_prompts_dir.glob("*.txt"))
    
    output_path = export_dir / args.output
    batch = []
    
    if prompt_files:
        # 【CEO Direct Control - Method B】使用外部提示詞
        print(f"\n【CEO 控制層】📨 檢測到 {len(prompt_files)} 個外部提示詞檔案")
        
        for file_idx, prompt_file in enumerate(prompt_files, 1):
            try:
                external_prompt = prompt_file.read_text(encoding="utf-8").strip()
                if external_prompt:
                    print(f"  ✅ 檔案 {file_idx}: {prompt_file.name} ({len(external_prompt)} 字元)")
                    batch.append({
                        "id": file_idx,
                        "author": AUTHOR_NAME,
                        "prompt": external_prompt,
                        "source": "CEO_FILE_INJECTION",
                        "filename": prompt_file.name,
                        "generated_at": datetime.now().isoformat(timespec="seconds")
                    })
                else:
                    print(f"  ⚠️  檔案 {file_idx}: {prompt_file.name} 為空，跳過")
            except Exception as e:
                print(f"  ❌ 檔案 {file_idx} 讀取失敗: {e}")
        
        if batch:
            print(f"\n【CEO 控制層】✅ 已載入 {len(batch)} 個 CEO 提交的提示詞")
        else:
            print("\n【CEO 控制層】⚠️  所有外部檔案皆為空或讀取失敗，回退至自動生成")
    
    # 【Fallback to Underground Formula】若無 CEO 提示詞，使用自動生成
    if not batch:
        print(f"\n【Underground Formula】🎵 使用 Underground Formula 自動生成 {args.count} 個提示詞（seed={args.seed}）...")
        batch = _generate_prompt_batch(count=args.count, seed=args.seed)
    else:
        # CEO 外部注入也套用工業命名規範
        start_seq, date_mmddyy = _reserve_daily_sequences(len(batch))
        for idx, item in enumerate(batch):
            daily_sequence = start_seq + idx + 1
            tag_basis = [
                "Taipei Indie",
                Path(item.get("filename", f"Prompt{idx+1}")).stem,
                "Slowcore",
                "Mellow Piano",
            ]
            item["title"] = generate_industrial_title(tag_basis, daily_sequence, date_mmddyy)
            item["daily_sequence"] = daily_sequence
    
    # 若要求列印
    if args.print:
        print("\n" + "=" * 80)
        for item in batch:
            print(f"\n📝 Prompt {item['id']}:")
            print(item['prompt'])
            print("-" * 80)
        print("=" * 80)
    
    # 保存為 JSON
    try:
        atomic_write_json(output_path, batch, indent=2)
        print(f"\n[SUNO_GENERATOR] ✅ 提示詞批次已保存至 {output_path}")
        print(f"[SUNO_GENERATOR] 總計 {len(batch)} 個提示詞")
    except Exception as e:
        print(f"[SUNO_GENERATOR][FATAL] 無法寫入 JSON: {e}")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit("Error: Must be run via pipeline_runner.py per PIPELINE_MANIFESTO")
