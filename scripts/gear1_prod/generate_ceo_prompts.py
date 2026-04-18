#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CEO 審批提示詞生成系統 - v15.3 Gemini 2.5 Flash Unified Edition

【v15.3 API 統一化升級】：
✅ 100% 純 Gemini 2.5 Flash 生成（全面汰除 GLM-4）
✅ ZERO SILENT FAILURES：API 失敗 → sys.exit(1) + 紅色警告
✅ 源頭防呆驗證：嚴格檢查 Tags + Prompt 結構
✅ 允許部分結果：不足 20 組也可存儲，但絕不偽造
✅ 寧可失敗報警，也不輸出沒有靈魂的假 Prompt
"""

from __future__ import annotations

import argparse
import datetime
import random
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.common.atomic_io import atomic_write_text
from scripts.common.llm_client import generate_structured_json
from scripts.common.visual_logic_vault import (
    get_visual_config,
    validate_channel,
    inject_negative_prompt_into_image_prompt,
    append_no_people_suffix,
)


# ────────────────────────────────────────────────────────────────
# 設定常數
# ────────────────────────────────────────────────────────────────

PROMPT_MD_PATH = Path(config.workspace_root) / ".openclaw" / "GL_4M_Suno_prompt.md"
CEP_OUTPUT_DIR = Path(config.workspace_root) / "assets" / ".ceo_prompts"
CEP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 源頭防呆檢查的必要標籤
REQUIRED_TAGS = {
    "pristine studio sound",
    "NO vocals",
    "NO vinyl crackle",
    "NO tape hiss",
    "NO background noise",
}

# 顏色碼（終端機輸出）
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


# ────────────────────────────────────────────────────────────────
# 核心邏輯
# ────────────────────────────────────────────────────────────────

def _fatal_exit(error_code: str, details: str) -> None:
    """
    【ZERO SILENT FAILURES 鐵律】
    致命錯誤：強制 sys.exit(1)，紅色警告，詳細日誌記錄。
    絕不允許沉默失敗或虛假輸出。
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_line = str(details).strip().splitlines()[-1][:240]
    
    # 紅色警告訊息到終端機
    warning_msg = (
        f"\n{RED}{'='*80}{RESET}\n"
        f"{RED}🚨 [FATAL] {error_code}{RESET}\n"
        f"{RED}{last_line}{RESET}\n"
        f"{RED}{'='*80}{RESET}\n"
    )
    print(warning_msg)
    
    # 記錄到 project_learning.md
    entry = (
        f"\n### [{timestamp}] generate_ceo_prompts.py: {error_code}\n"
        f"- Cause: {last_line}\n"
        f"- Action: FATAL_EXIT (sys.exit(1)). Zero product output.\n"
    )
    try:
        log_path = Path(config.workspace_root) / "project_learning.md"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception:
        pass
    
    sys.exit(1)


def _read_gene_pool(channel: str = "lofi") -> str:
    """
    【v12.2 基因隔離 + 警報強化】根據頻道讀取對應的音樂基因庫。
    如果 light_music 回落至 Lofi 基因，拋出顯眼的紅色警告。
    
    Args:
        channel: 頻道名稱 (lofi 或 light_music)
        
    Returns:
        音樂基因庫內容
    """
    try:
        # 嘗試從配置 JSON 讀取 music_gene_pool 路徑
        config_file = Path(config.workspace_root) / "configs" / "channels" / f"{channel.lower()}.json"
        
        fallback_used = False  # 【v12.2】追蹤是否使用了 fallback
        
        if config_file.exists():
            try:
                import json
                with open(config_file, "r", encoding="utf-8") as f:
                    channel_config = json.load(f)
                    music_gene_pool = channel_config.get("music_gene_pool")
                    
                    if music_gene_pool:
                        gene_pool_path = Path(config.workspace_root) / music_gene_pool
                        if gene_pool_path.exists():
                            with open(gene_pool_path, "r", encoding="utf-8") as fh:
                                print(f"  {YELLOW}📚 {channel} 頻道: 使用 {music_gene_pool}{RESET}")
                                return fh.read()
                        else:
                            print(f"  {YELLOW}⚠️  {music_gene_pool} 路徑不存在，回落至預設{RESET}")
                            fallback_used = True
                    else:
                        print(f"  {YELLOW}⚠️  {config_file} 中未找到 music_gene_pool，回落至預設{RESET}")
                        fallback_used = True
            except Exception as e:
                print(f"  {YELLOW}⚠️  JSON 配置讀取失敗: {e}，回落至預設{RESET}")
                fallback_used = True
        else:
            fallback_used = True
        
        # Fallback 至預設 Lofi 基因文件
        if not PROMPT_MD_PATH.exists():
            _fatal_exit(
                "GENE_POOL_MISSING",
                f"GL_4M_Suno_prompt.md not found: {PROMPT_MD_PATH}"
            )
        
        # 【v12.2 紅色警告】如果是 light_music 頻道且使用了 fallback，發出警告
        if fallback_used and channel == "light_music":
            error_msg = (
                f"\n{RED}{'='*80}{RESET}"
                f"\n{RED}🚨 【基因污染警報】 {RESET}"
                f"\n{RED}Light Music 基因庫加載失敗，系統回落到 Lofi 基因庫。{RESET}"
                f"\n{RED}當前生成的提示詞可能不適合 Light Music 頻道！{RESET}"
                f"\n{RED}  • 檢查: configs/channels/light_music.json 是否存在且有效{RESET}"
                f"\n{RED}  • 檢查: 指定的 music_gene_pool 文件是否存在{RESET}"
                f"\n{RED}  狀態：【非純淨模式】 本次生成不符合 Light Music 純淨要求{RESET}"
                f"\n{RED}{'='*80}{RESET}\n"
            )
            print(error_msg)
        
        with open(PROMPT_MD_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
            
    except Exception as exc:
        _fatal_exit("GENE_POOL_READ_ERROR", str(exc))


def _validate_tags(tags_str: str) -> bool:
    """
    源頭防呆：驗證 Tags 是否包含所有必要標籤。
    """
    tags_lower = tags_str.lower()
    for required in REQUIRED_TAGS:
        if required.lower() not in tags_lower:
            return False
    return True


def _auto_fix_tags(tags_str: str) -> str:
    """
    【v15.3 Gemini 適配】自動補齊缺失的必要標籤。
    Gemini 2.5 Flash 不像 GLM-4 會機械式複製全部要求標籤，
    偶爾會漏掉 1-2 個。改為自動補齊而非驗退重試。
    """
    tags_lower = tags_str.lower()
    missing = [t for t in REQUIRED_TAGS if t.lower() not in tags_lower]
    if missing:
        tags_str = tags_str.rstrip().rstrip(",") + ", " + ", ".join(missing)
    return tags_str


def _validate_prompt_structure(prompt_str: str) -> bool:
    """
    源頭防呆：驗證 Prompt 是否具備必要結構。
    """
    import re
    
    # 檢查分段標籤數量
    section_count = len(re.findall(r"\[.*?\]", prompt_str))
    if section_count < 6:
        return False
    
    # 檢查是否以 [Outro] 結尾
    if not re.search(r"\[Outro\].*$", prompt_str, re.DOTALL):
        return False
    
    return True


def _inject_time_dilation(prompt: str) -> str:
    """
    【CTO v10.4 結構化重組版】
    不再使用補丁式替換，改用結構化拆解重建。
    1. 徹底清除所有舊的刪節號與過多空白。
    2. 以段落標籤為界拆分。
    3. 在標籤之間精準注入「雙重獨佔行」刪節號。
    4. 自動確保 [Outro] 後方淨空。
    """
    import re
    
    # 第一步：物理清潔 - 移除所有既存的刪節號與重複換行
    clean_text = re.sub(r'\.{2,}', '', prompt)  # 移除所有 .. ... ....
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()
    
    # 第二步：定義膨脹補丁 (確保獨佔行)
    dilation_patch = "\n\n...\n...\n\n"
    
    # 第三步：使用正則拆分段落，但保留標籤
    # 匹配 [Tag] (Desc) 或 [Tag]
    parts = re.split(r'(\[.*?\](?:\s*\(.*?\))?)', clean_text)
    
    reconstructed = []
    last_tag_index = -1
    
    # 找到最後一個標籤的位置 (通常是 Outro)
    for i in range(len(parts)-1, -1, -1):
        if parts[i].startswith('['):
            last_tag_index = i
            break
            
    for i in range(len(parts)):
        segment = parts[i].strip()
        if not segment:
            continue
        
        reconstructed.append(segment)
        
        # 如果當前部分是標籤，且不是最後一個標籤，則注入補丁
        if segment.startswith('[') and i < last_tag_index:
            reconstructed.append(dilation_patch)
            
    return "".join(reconstructed).strip()


def _generate_visual_prompts(
    song_title: str, music_style: str, channel: str = "lofi"
) -> Dict[str, str]:
    """
    【v11.0 雙棲視覺提示詞生成】
    根據音樂風格和頻道，生成對應的 Image Prompt 和 Video Prompt。
    
    【v11.0 改進】：
    - 支援 JSON 配置驅動
    - light_music 自動追加無人物後綴
    
    Args:
        song_title: 曲名
        music_style: 音樂風格標籤
        channel: 視覺頻道（lofi 或 light_music）
        
    Returns:
        包含 image_prompt 和 video_prompt 的字典
    """
    if not validate_channel(channel):
        channel = "lofi"
    
    config = get_visual_config(channel)
    
    # 根據頻道選擇場景建議或心情建議
    if channel.lower() == "light_music":
        suggestions = config.get("scene_suggestions", [])
        default_scene = suggestions[0] if suggestions else "beautiful landscape"
        image_template = config["image_prompt_template"].format(scene=default_scene)
        video_template = config["video_prompt_template"].format(scene=default_scene)
    else:  # lofi
        suggestions = config.get("mood_suggestions", [])
        default_mood = suggestions[0] if suggestions else "peaceful moment"
        image_template = config["image_prompt_template"].format(mood=default_mood)
        video_template = config["video_prompt_template"].format(mood=default_mood)
    
    # light_music 時強制注入負面提示詞
    if channel.lower() == "light_music":
        image_template = inject_negative_prompt_into_image_prompt(image_template, channel)
        # 【Task 3】自動追加無人物後綴
        image_template = append_no_people_suffix(image_template, channel)
        video_template = append_no_people_suffix(video_template, channel)
    
    return {
        "image_prompt": image_template,
        "video_prompt": video_template,
    }


def _generate_prompts_batch_from_glm4(
    gene_pool: str,
    batch_size: int = 20,
    max_retries: int = 3,
    channel: str = "lofi",
    provider: str = "minimax"
) -> Optional[List[Dict[str, str]]]:
    """
    【v8.8 單發連發 (Iterative Generation) 模式】
    100% 純 Gemini 2.5 Flash 生成，每次 API 呼叫只要求 1 組。
    
    策略改變：
    ✅ 外層迴圈：生成 batch_size 次
    ✅ 每次呼叫：獨立要求 1 組 (1 Tag + 1 Prompt)
    ✅ 單次失敗：局部重試 max_retries 次，若失敗則跳過
    【v12.7 多樣性熵值擴張】每組生成都會隨機注入不同的樂器核心 + 情境氛圍
    ✅ 禁止重複：強制要求同批次不同樂器選擇
    ✅ 溫度調升：溫度 0.87 增加創意方差
    ✅ 隨機種子池：7 種樂器 × 7 種情境 = 49 種淨配置組合
    """
    validated_prompts = []
    
    # 【v12.7 多樣性熵池】強制多樣化種子注入
    instrument_pool = [
        "Piano (鋼琴核心，溫暖深邃)",
        "Saxophone (Mellow Tenor Saxophone，醇厚溫暖)" if channel == "lofi" else "Saxophone (Ethereal Soprano Saxophone，如風如歌)",
        "Cello (大提琴核心，蒼涼深沉)",
        "Acoustic Guitar (木吉他核心，溫和朴實)",
        "Ambient Synth (氛圍電子合成器，超越距離)",
        "String Quartet (弦樂四重奏，典雅莊重)",
        "Violin (小提琴核心，高遠遼闊)"
    ]
    
    mood_pool = [
        "Serenity (寧靜致遠)",
        "Melancholy (淡淡憂傷)",
        "Introspection (內在深思)",
        "Sacred (聖潔寄託)",
        "Profound (眾妙之門)",
        "Ethereal (飄然若思)",
        "Peaceful (靜水深流)"
    ]
    
    # 追蹤已使用的樂器，確保同批不重複
    used_instruments_in_batch = set()

    for group_idx in range(1, batch_size + 1):
        _display_map = {
            "gemini":  "Gemini 2.5 Flash",
            "minimax": "MiniMax M2.7 (NVIDIA NIM)",
            "zhipu":   "Zhipu GLM-4",
        }
        engine_display = _display_map.get(provider, provider.upper())
        print(f"\n【第 {group_idx}/{batch_size} 組】{engine_display} 單發生成...")
        
        # 每組最多重試 max_retries 次
        local_attempt = 0
        success = False
        
        while local_attempt < max_retries and not success:
            local_attempt += 1
            
            # 【多樣性隨機注入】從池中選擇本組的樂器 + 情境
            local_instrument = random.choice(instrument_pool)
            # 確保同批次不重複 (輪詢可用樂器)
            available_instruments = [i for i in instrument_pool if i not in used_instruments_in_batch]
            if available_instruments:
                local_instrument = random.choice(available_instruments)
                used_instruments_in_batch.add(local_instrument)
            else:
                # 若已耗盡，重置並重新選擇
                used_instruments_in_batch.clear()
                local_instrument = random.choice(instrument_pool)
                used_instruments_in_batch.add(local_instrument)
            
            local_mood = random.choice(mood_pool)
            
            # 【單發提示】每次只要求 1 組 + 【v12.2 頻道化 User Prompt】
            # 根據頻道選擇不同的音樂風格要求
            if channel == "light_music":
                music_style_desc = "Pure Ambient Therapeutic Music"
            else:
                music_style_desc = "Lofi Chillhop"
            
            # 【v12.7 批次多樣性意識】強制要求每組差異化，注入樂器 + 情境種子
            user_prompt = (
                f"請為 Suno AI 生成高品質的 {music_style_desc} 提示詞（第 {group_idx}/{batch_size} 組，全批共需 {batch_size} 組）。\n"
                f"【強制多樣性要求】此批次將生成 {batch_size} 組音樂配方，必須確保：\n"
                f"  • 每組音樂必須從 不同的主導樂器核心 中選擇\n"
                f"  • 嚴禁同批次中超過 3 組使用相同的樂器或標籤子串\n"
                f"  • 當前組 [{group_idx}] 的強制核心：{local_instrument}，情境氛圍：{local_mood}\n"
                f"  • 不要創變通，必須充分融入上述樂器特色與情感氛圍\n"
                f"必須輸出以下 JSON 結構（直接 JSON，無其他文字）：\n"
                f"{{\n"
                f'  "title": "英文曲名或短標題（例：Midnight Rain, Coffee and Code）",\n'
                f'  "tags": "tag1, tag2, tag3, ...",\n'
                f'  "prompt": "[Intro] ...\\n[Verse 1] ...\\n[Chorus] ...\\n[Verse 2] ...\\n[Bridge] ...\\n[Outro] ..."\n'
                f"}}\n"
                f"其中 title 必須是富有詩意但簡潔的英文標題（3-5 詞）。\n"
                f"tags 必須包含：pristine studio sound, NO vocals, NO vinyl crackle, NO tape hiss, NO background noise\n"
                f"prompt 必須包含至少 6 個分段標籤，並在語詞中多次提及上述樂器與氛圍。\n"
                f"...\n..."  # 時間膨脹刪節號
            )
            
            try:
                # 【單發呼叫】每次獨立呼叫，要求 1 組
                _model_map = {
                    "gemini":  "gemini-2.5-flash",
                    "minimax": "minimaxai/minimax-m2.7",
                    "zhipu":   "glm-4",
                }
                result = generate_structured_json(
                    system_prompt=gene_pool,
                    user_prompt=user_prompt,
                    provider=provider,
                    model=_model_map.get(provider, "glm-4"),
                    max_retries=1  # 每組只重試 1 次
                )
                # 【簡潔解析】直接用 json.loads() 讀取標準 JSON
                if not isinstance(result, dict):
                    print(f"  ⚠️ LLM 回傳非 dict: {type(result).__name__}")
                    continue  # 重試
                # 直接提取 tags、prompt 和 title
                title = result.get("title", "").strip()
                tags = result.get("tags", "").strip()
                prompt = result.get("prompt", "").strip()
                if not title or not tags or not prompt:
                    print(f"  ⚠️ 缺失 title、tags 或 prompt 欄位")
                    print(f"     返回鍵值: {list(result.keys())}")
                    continue  # 重試
                # 防呆驗証 1: Tags 自動補齊（v15.3 Gemini 適配）
                tags = _auto_fix_tags(tags)
                if not _validate_tags(tags):
                    # 理論上 _auto_fix_tags 後不應再失敗，但保底
                    missing = [t for t in REQUIRED_TAGS if t.lower() not in tags.lower()]
                    print(f"  ❌ Tags 補齊後仍缺失: {missing}")
                    continue  # 重試
                
                # 防呆驗証 2: Prompt 結構檢查
                if not _validate_prompt_structure(prompt):
                    # 【詳細調試】為什麼結構失敗？
                    import re
                    section_count = len(re.findall(r"\[.*?\]", prompt))
                    outro_found = bool(re.search(r"\[Outro\]", prompt))
                    print(f"  ❌ Prompt 結構失敗（分段不足或缺 [Outro]），重試 {local_attempt}/{max_retries}")
                    print(f"     分段數: {section_count}/6, [Outro]: {outro_found}")
                    print(f"     Prompt 前 200 字: {repr(prompt[:200])}")
                    continue  # 重試
                
                # ✅ 驗証通過！
                print(f"  {GREEN}✅ 驗証通過{RESET}，成功生成 [{group_idx}/{batch_size}]")
                
                # 【物理時間膨脹注入】在存檔前強制插入 ... 刪節號
                prompt_with_dilation = _inject_time_dilation(prompt)
                
                # 【v10.5 視覺提示詞生成】根據頻道生成對應的視覺提示詞
                visual_prompts = _generate_visual_prompts(title, tags, channel=channel)
                
                validated_prompts.append({
                    "title": title,
                    "tags": tags,
                    "prompt": prompt_with_dilation,
                    "image_prompt": visual_prompts["image_prompt"],
                    "video_prompt": visual_prompts["video_prompt"],
                })
                success = True
                
            except Exception as e:
                print(f"  ⚠️ 單發呼叫異常: {e}")
                # 發生異常時會繼續 while 迴圈進行重試
                
        if not success:
            print(f"  ❌ 第 {group_idx} 組經過 {max_retries} 次重試後仍失敗，跳過此組。")

# 外層 for 迴圈結束後，檢查最終結果
    if not validated_prompts:
        _fatal_exit(
            "NO_VALID_PROMPTS_GENERATED",
            f"無法從 Gemini 2.5 Flash / GLM-4 產生任何合格的提示詞。\n累計嘗試：{batch_size} 組 × {max_retries} 次重試\n請檢查 API 狀態與網路連線。"
        )
    
    return validated_prompts


def _save_prompts(prompts: List[Dict[str, str]], channel: str = "lofi") -> Path:
    """【v12.6 精簡化重構】保存驗證通過的提示詞，使用工業標籤格式。
    
    格式變更：
    - 移除冗長 CEO 指南和步驟說明
    - 頂部僅保留：頻道、日期、下載路徑、CHANNEL 標籤
    - 添加工業標籤包裹每個欄位 (TAGS, LYRICS, VIDEO_PROMPT)
    """
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    output_file = CEP_OUTPUT_DIR / f"daily_prompts_{channel.upper()}_{date_str}.txt"
    
    import os
    ceo_download_dir = str(_PROJECT_ROOT / "assets" / "audio" / "ceo_approved_beats" / channel.lower()) + os.sep
    
    lines = []
    lines.append("="*80 + "\n")
    lines.append(f"【R&S Echoes CEO 提示詞集合 - v12.6 工業標籤版】\n")
    lines.append("="*80 + "\n")
    lines.append(f"[CHANNEL: {channel.upper()}]\n")
    lines.append(f"生成時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"下載路徑: {ceo_download_dir}\n")
    lines.append(f"總數量: {len(prompts)} 組\n")
    lines.append("="*80 + "\n\n")
    
    for idx, item in enumerate(prompts, 1):
        lines.append(f"【Group {idx}】 Title: {item['title']}\n")
        lines.append("[[[SUNO_TAGS_START]]]\n")
        lines.append(f"{item['tags']}\n")
        lines.append("[[[SUNO_TAGS_END]]]\n\n")
        
        lyric_content = item['prompt'].strip()
        import re
        lyric_content = re.sub(r'(\.{2,}\s*)+$', '', lyric_content).strip()
        lyric_content = f"{lyric_content}\n\n...\n..."
        
        lines.append("[[[SUNO_LYRICS_START]]]\n")
        lines.append(f"{lyric_content}\n")
        lines.append("[[[SUNO_LYRICS_END]]]\n\n")
        
        lines.append("[[[VIDEO_PROMPT_START]]]\n")
        lines.append(f"【Image Prompt】\n{item.get('image_prompt', 'N/A')}\n\n")
        lines.append(f"【Video Prompt】\n{item.get('video_prompt', 'N/A')}\n")
        lines.append("[[[VIDEO_PROMPT_END]]]\n\n")
        lines.append("-"*80 + "\n\n")
    
    content = "".join(lines)
    
    try:
        atomic_write_text(output_file, content)
        print(f"\n✅ 提示詞已儲存: {output_file}")
        return output_file
    except Exception as exc:
        _fatal_exit("PROMPT_SAVE_ERROR", str(exc))


# ────────────────────────────────────────────────────────────────
# 主入口
# ────────────────────────────────────────────────────────────────

def main() -> None:
    """主程式入口。"""
    parser = argparse.ArgumentParser(
        description="CEO 審批提示詞生成系統 (v15.3 雙棲視覺版)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="目標提示詞組數（預設 5）"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Gemini 最大重試次數（預設 3）"
    )
    parser.add_argument(
        "--channel",
        type=str,
        default="lofi",
        choices=["lofi", "light_music"],
        help="視覺頻道：lofi（有人物）或 light_music（無人物風景），預設 lofi"
    )
    # 新增 provider 參數以支援雙引擎切換
    parser.add_argument(
        "--provider",
        type=str,
        default="minimax",
        choices=["zhipu", "gemini", "minimax"],
        help="LLM 引擎 (zhipu/gemini/minimax)"
    )
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("【🚀 CEO 提示詞生成系統啟動】- Dual Engine Edition (v15.3 雙棲視覺版)")
    print("="*80)
    print(f"目標: 生成 {args.batch_size} 組高品質提示詞")
    print(f"視覺頻道: {args.channel.upper()}")
    print(f"LLM 引擎: {args.provider.upper()}")
    print(f"重試次數: 最多 {args.max_retries} 輪")
    print(f"品質承諾: 寧可失敗報警，也不偽造虛假 Prompt\n")
    
    print("📖 讀取基因庫規則...")
    gene_pool = _read_gene_pool(channel=args.channel)
    print(f"✅ 基因庫已載入 ({len(gene_pool)} 字元)\n")
    
    print(f"🎲 啟動 {args.provider.upper()} 生成...")
    prompts = _generate_prompts_batch_from_glm4(
        gene_pool,
        batch_size=args.batch_size,
        max_retries=args.max_retries,
        channel=args.channel,
        provider=args.provider
    )
    
    print("\n💾 保存提示詞...")
    output_path = _save_prompts(prompts, channel=args.channel)
    
    print(f"\n{GREEN}✅ CEO 審批提示詞已準備就緒！{RESET}")
    print(f"📄 檔案位置: {output_path}")
    print(f"📋 包含：音樂提示詞 + Image Prompt + Video Prompt")
    print(f"🎨 視覺頻道: {args.channel.upper()}")
    if args.channel == "light_music":
        print(f"⚠️  已強制禁止人物/臉部/室內元素")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()