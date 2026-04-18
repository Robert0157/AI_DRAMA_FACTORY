#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenClaw 故事板生成器 (test_cw_storyboard.py)
================================================
功能：自動從 SQLite 風格金庫隨機抽出一個美學風格，結合職場痛點，
      呼叫智譜 GLM-4-Flash 生成可直接拿去算圖（Midjourney）與配樂的分鏡表 JSON。

使用方式：
    python test_cw_storyboard.py
    
輸出範例：能直接貼給 Midjourney 的 Prompt + 配音/配樂指引
"""

import os
import sys
import json
import sqlite3
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from urllib3.exceptions import InsecureRequestWarning

# 禁用 SSL 警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# 導入相依
sys.path.insert(0, str(Path(__file__).parent))
from style_database import StyleDatabase

# ================= 環境與路徑設定 =================

def load_api_key(key_name: str) -> str:
    """從環境變數或 .env 檔案讀取 API 按鍵"""
    api_key = os.getenv(key_name)
    
    if not api_key:
        env_file = Path(__file__).parent.parent.parent / ".env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(key_name):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    
    return api_key

# API 配置
ZHIPUAI_API_KEY = load_api_key("ZHIPUAI_API_KEY")
ZHIPUAI_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL_NAME = "glm-4-plus"

if not ZHIPUAI_API_KEY:
    print("❌ 錯誤: 找不到 ZHIPUAI_API_KEY（智譜 GLM-4-Flash API 按鍵）")
    sys.exit(1)

# User-Agent（模擬瀏覽器）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 初始化資料庫
db = StyleDatabase()
# ==================================================



# ================= 核心函式 =================

def get_random_style_from_db() -> Optional[Dict]:
    """【三基因融合協議】從 SQLite 金庫中隨機抽取 3 個不同美學風格進行基因縫合"""
    try:
        all_entries = db.get_all_entries()
        
        if not all_entries or len(all_entries) < 3:
            print("❌ 資料庫中沒有足夠的風格資料（需要至少 3 筆）")
            return None
        
        import random
        # 隨機抽取 3 個不同的記錄（無重複）
        three_random_entries = random.sample(all_entries, min(3, len(all_entries)))
        
        # 如果少於 3 個，就用重複抽取（允許重複）
        if len(three_random_entries) < 3:
            three_random_entries = [random.choice(all_entries) for _ in range(3)]
        
        # 整理三種基因的資訊
        genes = []
        for idx, entry in enumerate(three_random_entries, 1):
            genes.append({
                "gene_id": idx,
                "source_id": entry.get("source_id", f"Unknown-{idx}"),
                "theme_name": entry.get("theme_name", f"Unknown Theme {idx}"),
                "audio_prompt": entry.get("audio_prompt", ""),
                "video_prompt": entry.get("video_prompt", "")
            })
        
        # 返回三基因融合資料包
        return {
            "fusion_type": "chimera_three_genes",
            "genes": genes,
            "theme_names": [g["theme_name"] for g in genes],
            # 用於 Prompt 的文本資訊
            "visual_gene_1": genes[0]["video_prompt"],
            "visual_gene_2": genes[1]["video_prompt"],
            "visual_gene_3": genes[2]["video_prompt"],
            "audio_gene_1": genes[0]["audio_prompt"],
            "audio_gene_2": genes[1]["audio_prompt"],
            "audio_gene_3": genes[2]["audio_prompt"],
        }
    
    except Exception as e:
        print(f"❌ 資料庫讀取失敗: {e}")
        return None


def generate_storyboard_with_glm(pain_point: str, style_data: Dict) -> Optional[List[Dict]]:
    """
    【三基因融合煉金術】呼叫智譜 GLM-4-Plus API，將痛點與 3 種美學基因進行深度縫合
    """
    
    # 檢測是否使用三基因融合
    is_chimera = style_data.get("fusion_type") == "chimera_three_genes"
    
    if is_chimera:
        theme_display = f"【{style_data['theme_names'][0]}】+ 【{style_data['theme_names'][1]}】+ 【{style_data['theme_names'][2]}】"
        print(f"\n🧬 【三基因融合啟動】")
        print(f"🎭 三種美學基因: {theme_display}")
        print(f"   Gene 1: {style_data['theme_names'][0]}")
        print(f"   Gene 2: {style_data['theme_names'][1]}")
        print(f"   Gene 3: {style_data['theme_names'][2]}\n")
    else:
        print(f"\n🧠 正在呼叫編劇大腦 (GLM-4-Plus)...")
        print(f"🎭 美學風格: 【{style_data.get('theme_name', 'Unknown')}】\n")
    
    # 構建 Prompt（支援三基因融合或單基因）
    if is_chimera:
        prompt = f"""你是一位榮獲奧斯卡獎的「超現實黑色幽默」短片導演兼編劇。
現在，你要進行一個「基因煉金術」實驗 - 將 3 種完全不同的美學基因進行完美融合！

【輸入素材】
核心劇情 (社畜痛點)：{pain_point}

【三種視覺美學基因】
基因 1 (視覺)：{style_data['visual_gene_1']}
基因 2 (視覺)：{style_data['visual_gene_2']}
基因 3 (視覺)：{style_data['visual_gene_3']}

【三種音樂/配樂基因】
基因 1 (配樂)：{style_data['audio_gene_1']}
基因 2 (配樂)：{style_data['audio_gene_2']}
基因 3 (配樂)：{style_data['audio_gene_3']}

【基因融合任務】
不要選擇其中一種風格，而是要進行「完美的基因突變縫合」！
- 視覺層面：將這 3 種完全不同的視覺風格進行「混雜」，產生出從未見過的全新美學
- 配樂層面：將這 3 種音樂風格進行「疊加」，產生奇異且迷幻的音樂基因
- 敘事層面：在這個「混合怪物」的背景下，講述這個社畜痛點的故事

例如：如果基因是「複古定格木偶」「賽博龐克」「怪誕漫畫」，
那麼主角就是一個被線操控的賽博龐克木偶在怪誕辦公室裡工作的超現實景象！

【輸出格式】
只輸出 JSON 陣列，無任何 Markdown 標籤或其他文字。格式如下：

[
  {{"frame": 1, "visual_description": "詳細描述這個畫面的視覺構圖、光影與角色動作，完美融合了三種美學基因 (英文寫作，便於 Midjourney)", "narration_or_subtitle": "這張畫面搭配的旁白或字幕 (繁體中文，黑色幽默)"}},
  {{"frame": 2, "visual_description": "...", "narration_or_subtitle": "..."}},
  ...
  {{"frame": 6, "visual_description": "...", "narration_or_subtitle": "..."}}
]"""
    else:
        prompt = f"""你是一位榮獲奧斯卡獎的「超現實黑色幽默」短片導演兼編劇。
現在，你要製作一支 6 個分鏡的微電影短劇。

【輸入素材】
1. 核心劇情 (社畜痛點)：{pain_point}
2. 全局視覺美術風格：{style_data['video_prompt']}
3. 全局配樂風格：{style_data['audio_prompt']}

【任務要求】
- 將「接地氣的社畜痛點」完美融入「高級的視覺美術風格」中
- 例如：如果視覺風格是「復古定格木偶」，那主角就是一個被線牽著的疲憊木偶上班族
- 每個分鏡必須有明確的視覺細節，可以直接投餵 Midjourney 或其他 AI 算圖工具

【輸出格式】
只輸出 JSON 陣列，無任何 Markdown 標籤或其他文字。格式如下：

[
  {{"frame": 1, "visual_description": "詳細描述這個畫面的視覺構圖、光影與角色動作，必須嚴格遵循全局視覺美術風格 (英文寫作，便於 Midjourney)", "narration_or_subtitle": "這張畫面搭配的旁白或字幕 (繁體中文，黑色幽默)"}},
  {{"frame": 2, "visual_description": "...", "narration_or_subtitle": "..."}},
  ...
  {{"frame": 6, "visual_description": "...", "narration_or_subtitle": "..."}}
]"""
    
    try:
        print("⏳ API 請求中...")
        
        headers = {
            "Authorization": f"Bearer {ZHIPUAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 3000,
            "temperature": 0.8
        }
        
        response = requests.post(ZHIPUAI_API_URL, json=payload, headers=headers, timeout=60, verify=False)
        response.raise_for_status()
        
        result = response.json()
        print(f"✅ API 回應完成")
        
        if result.get("code") != 200 and "choices" not in result:
            error_msg = result.get('msg', result.get('error', result.get('message', '未知錯誤')))
            print(f"❌ API 錯誤: {error_msg}")
            return None
        
        # 提取回應內容
        choices = result.get("choices", [])
        if not choices:
            print("❌ 無有效回應")
            return None
        
        message_content = choices[0].get("message", {}).get("content", "").strip()
        
        # 清理可能的 Markdown 代碼塊
        if message_content.startswith("```json"):
            message_content = message_content[7:]
        elif message_content.startswith("```"):
            message_content = message_content[3:]
        
        if message_content.endswith("```"):
            message_content = message_content[:-3]
        
        message_content = message_content.strip()
        
        print(f"⏳ 解析 JSON 中...")
        
        # 解析 JSON
        storyboard = json.loads(message_content)
        
        # 驗證結構
        if isinstance(storyboard, list) and len(storyboard) > 0:
            print(f"✅ 成功生成 {len(storyboard)} 個分鏡")
            return storyboard
        else:
            print("❌ JSON 格式不正確")
            return None
    
    except requests.exceptions.RequestException as e:
        print(f"❌ API 請求失敗: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失敗: {e}")
        print(f"   原始回應: {message_content[:200] if 'message_content' in locals() else '無'}...")
        return None
    except Exception as e:
        print(f"❌ 生成失敗: {e}")
        import traceback
        traceback.print_exc()
        return None


def format_storyboard_output(storyboard: List[Dict], pain_point: str, style_data: Dict) -> Dict:
    """【三基因融合版】格式化輸出，包含完整的元資料與分鏡"""
    
    # 檢測是否為三基因融合
    if style_data.get("fusion_type") == "chimera_three_genes":
        return {
            "metadata": {
                "title": f"【微電影短劇】{pain_point}",
                "fusion_type": "chimera_three_genes",
                "style_theme_1": style_data["theme_names"][0],
                "style_theme_2": style_data["theme_names"][1],
                "style_theme_3": style_data["theme_names"][2],
                "pain_point": pain_point,
                "generated_at": datetime.now().isoformat(),
                "total_frames": len(storyboard)
            },
            "frames": storyboard,
            "gene_fusion_info": {
                "visual_gene_1": style_data["visual_gene_1"][:150] + "...",
                "visual_gene_2": style_data["visual_gene_2"][:150] + "...",
                "visual_gene_3": style_data["visual_gene_3"][:150] + "...",
                "audio_gene_1": style_data["audio_gene_1"][:150] + "...",
                "audio_gene_2": style_data["audio_gene_2"][:150] + "...",
                "audio_gene_3": style_data["audio_gene_3"][:150] + "..."
            },
            "usage_instructions": {
                "midjourney": "使用 visual_description 直接投放給 Midjourney v6 或 DALL-E 3 進行算圖",
                "narration": "使用 narration_or_subtitle 進行配音或字幕製作",
                "fusion_note": "本分鏡表是由 3 種不同美學基因進行深度融合產生的獨一無二創意"
            }
        }
    else:
        return {
            "metadata": {
                "title": f"【微電影短劇】{pain_point}",
                "style_theme": style_data.get("theme_name", "Unknown Theme"),
                "pain_point": pain_point,
                "audio_style": style_data.get("audio_prompt", "")[:100] + "...",
                "visual_style": style_data.get("video_prompt", "")[:100] + "...",
                "generated_at": datetime.now().isoformat(),
                "total_frames": len(storyboard)
            },
            "frames": storyboard,
            "usage_instructions": {
                "midjourney": "使用 visual_description 直接投放給 Midjourney v6 或 DALL-E 3 進行算圖",
                "narration": "使用 narration_or_subtitle 進行配音或字幕製作",
                "music": f"使用提供的配樂風格進行音樂製作: {style_data.get('audio_prompt', '')[:150]}..."
            }
        }


def save_storyboard_to_file(output: Dict, pain_point: str) -> str:
    """儲存分鏡表到檔案"""
    try:
        # 生成檔名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 清理檔名中的特殊字符
        safe_pain_point = "".join(c if c.isalnum() or c in "。，、" else "_" for c in pain_point[:30])
        filename = f"storyboard_{safe_pain_point}_{timestamp}.json"
        
        output_dir = Path(__file__).parent.parent / "outputs"
        output_dir.mkdir(exist_ok=True)
        
        output_path = output_dir / filename
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        return str(output_path)
    
    except Exception as e:
        print(f"⚠️  無法儲存檔案: {e}")
        return None


def display_storyboard(output: Dict):
    """【三基因融合版】在終端機中漂亮地顯示分鏡表"""
    
    metadata = output["metadata"]
    frames = output["frames"]
    
    print("\n" + "=" * 100)
    print(f"🎬 {metadata['title']}")
    print("=" * 100)
    
    # 顯示三基因融合信息或普通美學風格
    if metadata.get("fusion_type") == "chimera_three_genes":
        print(f"🧬 【三基因融合】")
        print(f"   基因 1: {metadata['style_theme_1']}")
        print(f"   基因 2: {metadata['style_theme_2']}")
        print(f"   基因 3: {metadata['style_theme_3']}")
    else:
        print(f"🎭 美學風格: {metadata.get('style_theme', 'Unknown')}")
    
    print(f"💾 生成時間: {metadata['generated_at']}\n")
    
    for frame_data in frames:
        frame_num = frame_data.get("frame", "?")
        visual = frame_data.get("visual_description", "")
        narration = frame_data.get("narration_or_subtitle", "")
        
        print(f"\n【分鏡 {frame_num}】")
        print(f"┌─ Visual (給 Midjourney 的 Prompt)")
        print(f"│  {visual[:150]}...")
        print(f"├─ Narration (旁白/字幕)")
        print(f"│  {narration}")
        print("└─")
    
    print("\n" + "=" * 100)
    print("✅ 分鏡表已完成！可直接複製使用。")
    print("=" * 100 + "\n")


def main():
    """主程式"""
    
    print("\n" + "🎬" * 50)
    print("OpenClaw 微電影故事板生成器 (CW Storyboard Generator)")
    print("🎬" * 50)
    print(f"\n📊 資料庫條目數: {db.count_entries()}")
    
    # 第 1 步：從資料庫隨機抽取風格
    print("\n【第 1 步】從風格金庫隨機抽取...")
    style_data = get_random_style_from_db()
    
    if not style_data:
        print("❌ 無法抽取風格，請確保資料庫中有資料")
        return
    
    print(f"✅ 成功抽取: {style_data['theme_name']}")
    
    # 第 2 步：取得使用者輸入的痛點
    print("\n【第 2 步】輸入職場痛點")
    print("（例如：'開會永遠遲到，卻要我簽到表' 或 '寫了一整天的程式碼，全被推翻重來'）\n")
    
    pain_point = input("🤔 請輸入你的職場痛點: ").strip()
    
    if not pain_point:
        print("❌ 痛點不能為空")
        return
    
    # 第 3 步：生成分鏡表
    print("\n【第 3 步】生成分鏡表...")
    storyboard = generate_storyboard_with_glm(pain_point, style_data)
    
    if not storyboard:
        print("❌ 分鏡表生成失敗")
        return
    
    # 第 4 步：格式化輸出
    print("\n【第 4 步】格式化輸出...")
    output = format_storyboard_output(storyboard, pain_point, style_data)
    
    # 第 5 步：儲存與顯示
    print("\n【第 5 步】輸出結果...")
    
    # 儲存檔案
    file_path = save_storyboard_to_file(output, pain_point)
    if file_path:
        print(f"💾 已儲存到: {file_path}")
    
    # 終端機顯示
    display_storyboard(output)
    
    # 輸出完整 JSON（方便複製）
    print("\n【完整 JSON 輸出】\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    
    print("\n✅ 所有步驟完成！")
    print(f"   🎨 視覺提示可直接投餵 Midjourney / DALL-E")
    print(f"   🎵 配樂風格: {style_data['audio_prompt'][:80]}...")
    print("\n")


if __name__ == "__main__":
    main()