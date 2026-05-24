#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CEO 審批提示詞生成系統 - v15.10 llm_client 統一路由版

【v15.10 更新】：
✅ 透過 llm_client 統一路由（預設 MiniMax M2.7，支援 --provider gemini/zhipu）
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

PROMPT_MD_PATH = Path(config.workspace_root) / ".openclaw" / "GL_4M_Suno_prompt.md"  # 容器路徑（由 backend._switch_container_gene_pool 覆寫後讀取）
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


def _parse_gene_pool_tags(content: str) -> list | None:
    """
    【v15.11 動態 Tags — 防護字串行解析】
    直接從 gene pool 提示詞內容中的「防護字串：」行提取 tags，無需額外標記。

    解析目標格式（新版 gene pool .md 防護字串行）：
        ⚠️ 結尾必須永遠固定包含這句防護字串：, tag1, tag2, tag3, ...

    CEO 換風格時只需修改防護字串行，tags 護城河自動更新，不必維護任何其他地方。
    若未找到防護字串行，回傳 None（呼叫方降級至 channel config 或 REQUIRED_TAGS）。
    """
    import re
    match = re.search(r'防護字串[：:]\s*,?\s*(.+)', content)
    if match:
        tags_raw = match.group(1).strip()
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
        return tags if tags else None
    return None


def _read_gene_pool(channel: str = "lofi", override_path: str | None = None) -> tuple:
    """
    【v15.11 動態 Tags】根據頻道讀取對應的音樂基因庫，並解析內嵌的防護字串行。
    
    Args:
        channel: 頻道名稱 (lofi 或 light_music)
        override_path: 執行期覆寫路徑（空頻道動態注入模式）
            例: `.openclaw/music_genes_JESS_music.md`
            若提供，完全跳過 lofi.json 的 music_gene_pool 設定。
            該檔案必須含有 防護字串： 行，否則立即 fatal exit。
        
    Returns:
        tuple (gene_pool_content: str, dynamic_tags: list | None)
        dynamic_tags 為 None 時表示 gene pool 檔案未設定，呼叫方應 fallback 至 channel config。
    """
    try:
        # 【空頻道動態注入模式】CLI --gene-pool 覆寫，完全跳過 channel config JSON
        if override_path:
            override_full = Path(config.workspace_root) / override_path
            if not override_full.exists():
                _fatal_exit(
                    "GENE_POOL_OVERRIDE_MISSING",
                    f"--gene-pool 覆寫路徑不存在: {override_full}\n"
                    f"  確認檔案名稱拼寫正確後重新執行。"
                )
            with open(override_full, "r", encoding="utf-8") as fh:
                content = fh.read()
            dynamic_tags = _parse_gene_pool_tags(content)
            if not dynamic_tags:
                _fatal_exit(
                    "GENE_POOL_OVERRIDE_NO_MOAT",
                    f"--gene-pool 覆寫的基因庫缺少 防護字串： 行: {override_full}\n"
                    f"  動態注入模式下，tags 護城河必須直接嵌入基因庫文件，不得回落 lofi.json。\n"
                    f"  解法：在 {override_path} 添加一行：『⚠️ 結尾必須永遠固定包含這句防護字串：, tag1, tag2, ...』"
                )
            print(f"  {YELLOW}📌 空頻道動態注入: {override_path}{RESET}")
            print(f"  {YELLOW}🏷️  防護字串 Tags（{len(dynamic_tags)} 個）: {', '.join(dynamic_tags)}{RESET}")
            return content, dynamic_tags

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
                                content = fh.read()
                            dynamic_tags = _parse_gene_pool_tags(content)
                            if dynamic_tags:
                                print(f"  {YELLOW}📚 {channel} 頻道: 使用 {music_gene_pool}{RESET}")
                                print(f"  {YELLOW}🏷️  動態 Tags 已從基因庫解析（{len(dynamic_tags)} 個標籤）{RESET}")
                            else:
                                print(f"  {YELLOW}📚 {channel} 頻道: 使用 {music_gene_pool}（無動態 Tags 標記，將使用 config fallback）{RESET}")
                            return content, dynamic_tags
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
        
        # Fallback 至容器基因文件（应由 backend._switch_container_gene_pool 從對應子風格來源顯寫）
        if not PROMPT_MD_PATH.exists():
            _fatal_exit(
                "GENE_POOL_MISSING",
                f"容器 GL_4M_Suno_prompt.md 不存在: {PROMPT_MD_PATH}\n"
                "  解法：確認 .openclaw/GL_4M_Suno_prompt.md 存在，或检查 backend._switch_container_gene_pool 是否正常執行。"
            )
        
        # 【v15.11 基因隔離鐵律】light_music 頻道若 fallback 到 Lofi 基因庫 → 立即中止
        # 警告 → fatal_exit：防止基因污染導致 light_music 輸出 lofi 風格提示詞
        if fallback_used and channel == "light_music":
            _fatal_exit(
                "GENE_POOL_CONTAMINATION",
                "light_music 基因庫載入失敗，拒絕以 Lofi 基因庫替代以防止基因污染。\n"
                "  • 確認 configs/channels/light_music.json 存在且含有效 music_gene_pool 欄位\n"
                f"  • 確認 .openclaw/music_genes_light_music.md 存在\n"
                "  解法：修復基因庫路徑後重新執行。"
            )

        with open(PROMPT_MD_PATH, "r", encoding="utf-8") as fh:
            content = fh.read()
        dynamic_tags = _parse_gene_pool_tags(content)
        return content, dynamic_tags
            
    except Exception as exc:
        _fatal_exit("GENE_POOL_READ_ERROR", str(exc))


def _validate_tags(tags_str: str, required_tags=None) -> bool:
    """
    源頭防呆：驗證 Tags 是否包含所有必要標籤。
    required_tags: 可傳入頻道專屬標籤集合，預設使用全域 REQUIRED_TAGS。
    """
    tags_lower = tags_str.lower()
    check_set = required_tags if required_tags is not None else REQUIRED_TAGS
    for required in check_set:
        if required.lower() not in tags_lower:
            return False
    return True


def _auto_fix_tags(tags_str: str, required_tags=None) -> str:
    """
    【v15.3 Gemini 適配】自動補齊缺失的必要標籤。
    Gemini 2.5 Flash 不像 GLM-4 會機械式複製全部要求標籤，
    偶爾會漏掉 1-2 個。改為自動補齊而非驗退重試。
    required_tags: 可傳入頻道專屬標籤集合，預設使用全域 REQUIRED_TAGS。
    """
    check_set = required_tags if required_tags is not None else REQUIRED_TAGS
    tags_lower = tags_str.lower()
    missing = [t for t in check_set if t.lower() not in tags_lower]
    if missing:
        tags_str = tags_str.rstrip().rstrip(",") + ", " + ", ".join(missing)
    return tags_str


def _validate_title_format(title: str) -> bool:
    """
    v15.11 供彈標題格式驗證：必須為「風格名稱_英文檔名」格式。
    規則：StyleName 與 EnglishTitle 皆為純英數字，底線連結，無空格、無中文、無特殊符號。
    例：CelticFolk_MorningDew ✅ | TechHouse_UrbanGrid ✅ | Midnight Rain ❌
    """
    import re
    return bool(re.match(r'^[A-Za-z][A-Za-z0-9]*_[A-Za-z][A-Za-z0-9]*$', title))


def _validate_prompt_structure(prompt_str: str) -> bool:
    """
    源頭防呆：驗證 Prompt 是否具備必要結構。
    v15.11 Shorts 格式：段落數 5-7 個，結尾標籤形式自由（無強制 Outro）。
    """
    import re
    
    # 檢查分段標籤數量（Shorts 格式：5 至 7 個段落）
    section_count = len(re.findall(r"\[.*?\]", prompt_str))
    if section_count < 5:
        return False
    
    return True


def _inject_time_dilation(prompt: str) -> str:
    """
    【v15.4 雙棲向下相容版】無損升級！
    向下相容純音樂 (兩層式)，同時完美支援人聲歌詞 (垂直三層式)。
    確保時間膨脹 (...) 只會插入在「完整的段落區塊（標籤+微操+歌詞）」之間。
    """
    import re

    # 第一步：物理清潔 - 移除所有既存的刪節號與重複換行
    clean_text = re.sub(r'\.{2,}', '', prompt)  # 移除所有 .. ... ....
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()

    # 第二步：定義膨脹補丁 (確保獨佔行)
    dilation_patch = "\n\n...\n...\n\n"

    # 第三步：以「換行後緊接的 [ 」作為切割點
    # 這樣會將「[段落標籤] + (微操) + 歌詞」整個視為一個不可分割的 Block
    temp_text = "\n" + clean_text
    blocks = re.split(r'\n(?=\[)', temp_text)

    reconstructed = []
    # 過濾空字串
    valid_blocks = [b.strip() for b in blocks if b.strip()]

    for i, block in enumerate(valid_blocks):
        reconstructed.append(block)

        # 只要不是最後一個 Block，就在後面補上時間膨脹符號
        if i < len(valid_blocks) - 1:
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
    provider: str = "minimax",
    gene_pool_tags: list | None = None
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
    
    # 【v15.12 動態風格輪詢】自動偵測基因庫中的風格數量 (支援 4大、5大等任意數量)
    import re
    # 掃描基因庫中類似 "▶ 風格 A：" 或 "▶ 風格 E：" 的標記
    detected_pillars = re.findall(r'▶\s*風格\s*([A-Z])\s*[：:]', gene_pool)
    # 去除重複並排序，若未偵測到則保底使用 A~D
    detected_pillars = sorted(list(set(detected_pillars))) if detected_pillars else ["A", "B", "C", "D"]

    print(f"  🎡 動態風格輪詢矩陣: {' → '.join(detected_pillars)} (共 {len(detected_pillars)} 種)")

    # 【v15.11 動態 Tags 優先鏈】基因庫防護字串 → channel config → REQUIRED_TAGS
    import json as _json
    _ch_cfg_path = Path(config.workspace_root) / "configs" / "channels" / f"{channel.lower()}.json"
    _ch_cfg = {}
    try:
        with open(_ch_cfg_path, "r", encoding="utf-8") as _f:
            _ch_cfg = _json.load(_f)
    except Exception as _e:
        print(f"  ⚠️ 無法讀取頻道設定 {_ch_cfg_path.name}: {_e}，使用預設值")

    if gene_pool_tags:
        channel_required_tags = gene_pool_tags
        print(f"  🏷️  Tags 來源: 基因庫防護字串（{len(gene_pool_tags)} 個，隨風格自動更新）")
    else:
        channel_required_tags = _ch_cfg.get("suno_tags_required", list(REQUIRED_TAGS))
        print(f"  🏷️  Tags 來源: channel config（{_ch_cfg_path.name}）")
    channel_tags_moat = ", ".join(channel_required_tags)
    print(f"  🛡️ Tags 護城河: {channel_tags_moat}")

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
            
            # 【v15.12 動態多樣性指令】依偵測到的風格數量進行餘數輪詢
            style_hint = detected_pillars[(group_idx - 1) % len(detected_pillars)]
            
            # 【v15.11 頻道感知 user_prompt 範例】light_music 顯示自然風格前綴
            _title_example = (
                "CelticFolk_MorningDew" if channel == "light_music"
                else "TechHouse_UrbanGrid"
            )
            user_prompt = (
                f"請依照系統提示詞的指引，生成第 {group_idx}/{batch_size} 組 Suno AI 短影音音樂提示詞。\n"
                f"【多樣性指令】本批次共 {batch_size} 組，本組請優先採用「風格 {style_hint}」以確保批次中的風格多樣性。\n"
                f"必須輸出以下 JSON 結構（直接 JSON，無其他文字）：\n"
                f"{{\n"
                f'  "title": "StyleName_EnglishTitle（例：{_title_example}，無空格無中文無特殊符號）",\n'
                f'  "tags": "嚴格遵循選定風格的 Tags + 護城河字串",\n'
                f'  "prompt": "[開場標籤] (氛圍描述)\\n(若是允許人聲的風格，請在此換行填寫原創歌詞；若是純音樂則嚴格留空)...\\n\\n...\\n\\n[段落標籤] (樂器變化)\\n(歌詞或留空)...\\n\\n...\\n\\n[結尾標籤] (Fade to silence...)"\n'
                f"}}\n"
                f"title 必須嚴格遵守「風格名稱_英文檔名」格式，不得含空格、中文字或特殊符號。\n"
                f"tags 結尾必須包含護城河：{channel_tags_moat}\n"
                f"prompt 段落數量必須控制在 5 至 7 個標籤之間（短影音 180 秒）。\n"
                f"⚠️ JSON 輸出安全規則：所有字串值內嚴禁使用雙引號 \"（會破壞 JSON 結構）；如需強調請改用單引號 ' 或省略引號。\n"
            )
            
            try:
                # 【v15.10 三引擎降級鏈】preferred → zhipu → gemini（架構鐵律）
                # 單組 LLM 呼叫失敗（含 429 Rate Limit）→ 自動切換備援引擎，不重打同一引擎
                _model_map = {
                    "gemini":  "gemini-2.5-flash",
                    "minimax": "minimaxai/minimax-m2.7",
                    "zhipu":   "glm-4",
                }
                _prov_chain = [provider] + [p for p in ["minimax", "zhipu", "gemini"] if p != provider]
                result = None
                _last_prov_exc: Exception | None = None
                for _prov in _prov_chain:
                    try:
                        result = generate_structured_json(
                            system_prompt=gene_pool,
                            user_prompt=user_prompt,
                            provider=_prov,
                            model=_model_map.get(_prov, "glm-4"),
                            max_retries=1  # 每引擎各試 1 次
                        )
                        if _prov != provider:
                            print(f"  ✅ [{_prov.upper()}] 備援引擎成功")
                        break
                    except Exception as _pe:
                        print(f"  ⚠️ [{_prov.upper()}] 失敗: {type(_pe).__name__}，嘗試備援引擎...")
                        _last_prov_exc = _pe
                if result is None:
                    raise (_last_prov_exc or Exception("三引擎全失敗"))
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
                # v15.11 供彈標題格式驗證：必須為 StyleName_EnglishTitle
                if not _validate_title_format(title):
                    print(f"  ❌ title 格式不符 StyleName_EnglishTitle 規範: {title}")
                    print(f"     正確格式: CelticFolk_MorningDew / TechHouse_UrbanGrid")
                    continue  # 重試
                # 防呆驗証 1: Tags 自動補齊（v15.11：使用頻道專屬護城河，非全域 REQUIRED_TAGS）
                tags = _auto_fix_tags(tags, required_tags=channel_required_tags)
                if not _validate_tags(tags, required_tags=channel_required_tags):
                    # 理論上 _auto_fix_tags 後不應再失敗，但保底
                    missing = [t for t in channel_required_tags if t.lower() not in tags.lower()]
                    print(f"  ❌ Tags 補齊後仍缺失: {missing}")
                    continue  # 重試
                
                # 防呆驗証 2: Prompt 結構檢查
                if not _validate_prompt_structure(prompt):
                    import re
                    section_count = len(re.findall(r"\[.*?\]", prompt))
                    print(f"  ❌ Prompt 結構失敗（分段不足），重試 {local_attempt}/{max_retries}")
                    print(f"     分段數: {section_count}（需要 5-7 個）")
                    print(f"     Prompt 前 200 字: {repr(prompt[:200])}")
                    continue  # 重試
                
                # ✅ 驗証通過！
                print(f"  {GREEN}✅ 驗証通過{RESET}，成功生成 [{group_idx}/{batch_size}]")
                
                # 【物理時間膨脹注入】在存檔前強制插入 ... 刪節號
                prompt_with_dilation = _inject_time_dilation(prompt)
                
                validated_prompts.append({
                    "title": title,
                    "tags": tags,
                    "prompt": prompt_with_dilation,
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
    parser.add_argument(
        "--gene-pool",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "空頻道動態注入：覆寫 channel config 的 music_gene_pool，"
            "執行期直接指定基因庫。\n"
            "例: .openclaw/music_genes_JESS_music.md"
        )
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
    gene_pool, gene_pool_tags = _read_gene_pool(channel=args.channel, override_path=args.gene_pool)
    print(f"✅ 基因庫已載入 ({len(gene_pool)} 字元)\n")
    if gene_pool_tags:
        print(f"🏷️  動態 Tags 護城河（來自基因庫）: {', '.join(gene_pool_tags)}\n")
    else:
        print(f"🏷️  動態 Tags: 未設定，將使用 channel config 或預設值\n")
    
    print(f"🎲 啟動 {args.provider.upper()} 生成...")
    prompts = _generate_prompts_batch_from_glm4(
        gene_pool,
        batch_size=args.batch_size,
        max_retries=args.max_retries,
        channel=args.channel,
        provider=args.provider,
        gene_pool_tags=gene_pool_tags
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