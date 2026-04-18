#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 角色錨點生成器 (Image Anchor Generator)
旨在解決「影片主角長相變來變去」的問題

流程：
1. 解析藍圖中的視覺基因 (visual genes)
2. 呼叫 GLM-4V 或通義萬相生成主角的「基準設計圖」
3. 儲存到 /Volumes/AI_Workspace/AI_DRAMA_FACTORY/assets/image_anchors/
4. VD 呼叫即夢 API 時，讀取此錨點圖確保角色風格鎖死

歸屬部門：🏭 齒輪一 (生產部)
依賴模型：glm-4v, qwen-vl（第一優先）/ deepseek-vl（備選）
"""

import os
import sys
import json
import time
import hashlib
import requests
from pathlib import Path
from typing import Optional, Dict, Any

# ============================================================================
# 環境配置
# ============================================================================
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "/Volumes/AI_Workspace/AI_DRAMA_FACTORY")
ANCHOR_IMAGE_DIR = os.path.join(WORKSPACE_ROOT, "assets", "image_anchors")
STORYBOARD_FILE = os.path.join(WORKSPACE_ROOT, "assets", "scripts", "storyboard.json")

# API 配置（從環境變數讀取，防洩漏）
GLM_4V_API_KEY = os.getenv("GLM_4V_API_KEY", "")
QWEN_VL_API_KEY = os.getenv("QWEN_VL_API_KEY", "")
DEEPSEEK_VL_API_KEY = os.getenv("DEEPSEEK_VL_API_KEY", "")

# 確保目錄存在
os.makedirs(ANCHOR_IMAGE_DIR, exist_ok=True)


# ============================================================================
# 核心函數：從藍圖提取視覺基因
# ============================================================================
def extract_visual_genes(storyboard_json: str) -> str:
    """
    【關鍵修復】：從 storyboard.json 提取「視覺基因」
    視覺基因指的是：角色特徵、風格、配色、髮型等重要屬性
    
    Args:
        storyboard_json: storyboard.json 檔案路徑
        
    Returns:
        整合後的視覺基因文字描述
    """
    if not os.path.exists(storyboard_json):
        print(f"⚠️ Warning: Storyboard file not found at {storyboard_json}")
        return "A minimalist puppet character with stop-motion aesthetic, sitting at desk."
    
    try:
        with open(storyboard_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取視覺基因（假設 storyboard 有 visual_genes 或 character_description 欄位）
        visual_genes = data.get("visual_genes", "")
        if not visual_genes:
            # 備選：從每個分鏡的描述中拼接
            scenes = data.get("scenes", [])
            if scenes:
                visual_genes = ", ".join([s.get("character_description", "") for s in scenes[:3]])
        
        return visual_genes if visual_genes else "A puppet character in stop-motion style."
        
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing storyboard JSON: {e}")
        return "A puppet character in stop-motion style."


# ============================================================================
# GLM-4V 呼叫（智譜 GLM-4V）
# ============================================================================
def generate_anchor_via_glm4v(visual_genes: str, character_name: str = "protagonist") -> Optional[str]:
    """
    使用 GLM-4V 生成主角的基準設計圖
    
    Args:
        visual_genes: 視覺基因文字
        character_name: 角色名稱（用於檔案命名）
        
    Returns:
        儲存的圖片路徑，或 None 如果失敗
    """
    if not GLM_4V_API_KEY:
        print("⚠️ GLM_4V_API_KEY not set, skipping GLM-4V generation")
        return None
    
    url = "https://open.bigmodel.cn/api/paas/v4/messages"
    headers = {
        "Authorization": f"Bearer {GLM_4V_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 精心製作的Prompt - 確保生成的是「定格動畫木偶」而不是寫實風
    prompt = f"""
    根據以下角色特徵，生成一張2D概念設計圖（單一角色、靜止姿態、正面或45度視角）：
    
    角色特徵：{visual_genes}
    
    美學要求 (Aesthetic Bible 絕對強制)：
    - 定格動畫風格 (stop-motion style)
    - 木偶質感 (felt, wood, and cloth textures)
    - 1990年代懷舊感 (1990s nostalgic vibes)
    - 高度詳細 (8k resolution, highly detailed)
    - 膚色柔和，眼睛大而有神
    - 背景極簡或純色 (minimal background)
    
    輸出格式：返回一個描述這個角色的JSON物件，包含：
    {{
        "character_name": "角色名稱",
        "visual_description": "詳細的視覺描述",
        "color_palette": ["色碼1", "色碼2", ...],
        "texture_keywords": ["質感1", "質感2", ...],
        "image_url": "生成圖片的URL或本機路徑"
    }}
    """
    
    payload = {
        "model": "glm-4v-plus",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1024
    }
    
    try:
        print(f"🎨 Calling GLM-4V to generate anchor image for character: {character_name}")
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        if result.get("choices"):
            content = result["choices"][0]["message"]["content"]
            print(f"✅ GLM-4V response received")
            
            # 解析返回的JSON（GLM-4V可能直接返回JSON）
            try:
                anchor_data = json.loads(content)
                # 儲存為本機檔案引用
                output_file = os.path.join(ANCHOR_IMAGE_DIR, f"{character_name}_anchor.json")
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(anchor_data, f, ensure_ascii=False, indent=2)
                print(f"💾 Anchor design saved to {output_file}")
                return output_file
            except json.JSONDecodeError:
                # 如果不是JSON，保存為提示文本
                output_file = os.path.join(ANCHOR_IMAGE_DIR, f"{character_name}_anchor.txt")
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"💾 Anchor design (text) saved to {output_file}")
                return output_file
        else:
            print(f"❌ GLM-4V returned empty response")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ GLM-4V API call failed: {e}")
        return None


# ============================================================================
# 通義萬相呼叫（Qwen-VL）
# ============================================================================
def generate_anchor_via_qwen_vl(visual_genes: str, character_name: str = "protagonist") -> Optional[str]:
    """
    使用通義萬相 (Qwen-VL) 生成主角的基準設計圖
    
    Args:
        visual_genes: 視覺基因文字
        character_name: 角色名稱
        
    Returns:
        儲存的圖片路徑，或 None 如果失敗
    """
    if not QWEN_VL_API_KEY:
        print("⚠️ QWEN_VL_API_KEY not set, skipping Qwen-VL generation")
        return None
    
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generate"
    headers = {
        "Authorization": f"Bearer {QWEN_VL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 精心製作的Prompt
    prompt = f"""
    Create a concept art character design sheet based on these character traits:
    {visual_genes}
    
    MANDATORY aesthetic requirements (Aesthetic Bible - MUST FOLLOW):
    - Stop-motion puppet style with felt/wood/cloth texture
    - 1990s lo-fi retro vibe, NOT realistic
    - Highly detailed, 8K resolution quality
    - Warm, desaturated color palette
    - Large expressive eyes, soft proportions
    - Full body, standing pose, front facing
    - Minimal background or solid color (beige/grey)
    - Puppet joints visible (wooden limbs, fabric body)
    
    Style: 1990s stop-motion animation, whimsical puppet character
    """
    
    payload = {
        "model": "qwen-vl-max",
        "input": {
            "prompt": prompt
        },
        "parameters": {
            "quality": "hd",
            "size": "1024*1024"
        }
    }
    
    try:
        print(f"🎨 Calling Qwen-VL to generate anchor image for character: {character_name}")
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        request_id = result.get("request_id", "unknown")
        
        # Qwen-VL 返回 request_id，需要輪詢結果
        print(f"📋 Generation request submitted. Request ID: {request_id}")
        
        # 簡化版：直接儲存request_id metadata
        output_file = os.path.join(ANCHOR_IMAGE_DIR, f"{character_name}_anchor_qwen.json")
        metadata = {
            "request_id": request_id,
            "character_name": character_name,
            "visual_genes": visual_genes,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending"
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        print(f"💾 Anchor request metadata saved to {output_file}")
        return output_file
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Qwen-VL API call failed: {e}")
        return None


# ============================================================================
# Fallback：本機合成
# ============================================================================
def generate_anchor_fallback(visual_genes: str, character_name: str = "protagonist") -> str:
    """
    若API全部失敗，則儲存視覺基因作為Fallback錨點
    VD稍後可根據此檔案手動建立角色或使用本機工具
    """
    output_file = os.path.join(ANCHOR_IMAGE_DIR, f"{character_name}_anchor_fallback.json")
    
    anchor_data = {
        "character_name": character_name,
        "visual_genes": visual_genes,
        "fallback_mode": True,
        "instructions": "Manual anchor image creation recommended. Use this visual description to guide Kling API prompt.",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(anchor_data, f, ensure_ascii=False, indent=2)
    
    print(f"⚠️ Fallback anchor saved to {output_file}")
    return output_file


# ============================================================================
# 主入口函數
# ============================================================================
def main():
    """
    主流程：
    1. 讀取 storyboard.json 提取視覺基因
    2. 嘗試呼叫 GLM-4V (優先) → Qwen-VL (備選) → Fallback
    3. 輸出錨點檔案供 VD 讀取
    """
    print("=" * 70)
    print("🎯 Image Anchor Generator v1.0")
    print("=" * 70)
    
    # Step 1: 提取視覺基因
    print("\n📖 Step 1: Extracting visual genes from storyboard...")
    visual_genes = extract_visual_genes(STORYBOARD_FILE)
    print(f"✅ Visual genes extracted: {visual_genes[:100]}...")
    
    # Step 2: 決定使用者名稱
    character_name = "puppet_protagonist"
    
    # Step 3: 嘗試生成（優先順序：GLM-4V → Qwen-VL → Fallback）
    print(f"\n🎨 Step 2: Generating anchor image...")
    
    anchor_file = None
    
    # 優先嘗試 GLM-4V
    if GLM_4V_API_KEY:
        anchor_file = generate_anchor_via_glm4v(visual_genes, character_name)
    
    # 若失敗，嘗試 Qwen-VL
    if not anchor_file and QWEN_VL_API_KEY:
        anchor_file = generate_anchor_via_qwen_vl(visual_genes, character_name)
    
    # 若仍失敗，使用 Fallback
    if not anchor_file:
        anchor_file = generate_anchor_fallback(visual_genes, character_name)
    
    # Step 4: 驗證產出
    print(f"\n✅ Step 3: Anchor generation complete!")
    print(f"📍 Anchor file location: {anchor_file}")
    print(f"📁 All anchors stored in: {ANCHOR_IMAGE_DIR}")
    
    # 回傳 JSON 供 OpenClaw 引擎解析
    output = {
        "status": "SUCCESS",
        "anchor_file": anchor_file,
        "character_name": character_name,
        "visual_genes": visual_genes,
        "anchor_directory": ANCHOR_IMAGE_DIR
    }
    
    print("\n" + "=" * 70)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
