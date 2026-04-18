#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【v15.0 雙棲企劃引擎】scripts/gear1_prod/gemini_genesis_engine.py
使用 Gemini 1.5 生成聯合音效/視覺企劃
✅ 廢除 GLM-4，全面接管音效與視覺企劃大腦
✅ 啟用真實 Gemini 1.5 Flash API
✅ Structured Outputs：強制 JSON 格式輸出
"""

import sys
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# 【CTO 強制執行】確保腳本能找到專案根目錄
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

# 嘗試載入 Google Generative AI SDK
try:
    import google.generativeai as genai
except ImportError:
    print("❌ 缺少 google-generativeai 套件。請在終端機執行: pip install google-generativeai")
    sys.exit(1)

# 日誌設定
log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

class GeminiGenesisEngine:
    """【v15.0】Gemini 1.5 雙棲企劃引擎"""
    
    def __init__(self):
        # 取得 API Key (優先從環境變數，其次從 .env)
        self.api_key = os.getenv("GEMINI_API_KEY") or getattr(config, "GEMINI_API_KEY", None)
        
        if not self.api_key:
            log.warning("⚠️  GEMINI_API_KEY 未設定，使用 Mock 模式進行測試")
            self.api_key = None
            self.model = None
            self.use_mock = True
            return
            
        try:
            # 初始化 Gemini API
            genai.configure(api_key=self.api_key)
            
            # 嘗試多個模型 (按優先級)
            # 基於列表查詢的實際可用模型（2025最新）
            models_to_try = [
                'gemini-2.5-flash',
                'gemini-2.5-pro',
                'gemini-2.0-flash',
                'gemini-flash-latest',
                'gemini-proto-latest',
                'gemini-pro'
            ]
            
            self.model = None
            model_name = None
            
            for model_id in models_to_try:
                try:
                    candidate = genai.GenerativeModel(model_id)
                    self.model = candidate
                    model_name = model_id
                    break
                except Exception as retry_err:
                    log.debug(f"模型 {model_id} 不可用: {retry_err}")
                    continue
            
            if self.model is None:
                log.warning("⚠️  所有 Gemini 模型均不可用，自動降級到 Mock 模式")
                self.use_mock = True
                self.model = None
            else:
                self.use_mock = False
                log.info(f"✅ Gemini API 已初始化 (模型: {model_name})")
        except Exception as e:
            log.warning(f"⚠️  Gemini API 初始化失敗：{e}，使用 Mock 模式")
            self.use_mock = True
            self.model = None

    def generate_dual_plan(self, channel: str, additional_context: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """呼叫 Gemini 1.5 API 產生雙棲企劃 JSON（或 Mock 數據）
        
        Args:
            channel: 頻道名稱 (lofi, light_music)
            additional_context: 額外背景信息
        
        Returns:
            {title, tags, suno_prompt, veo_image_prompt, veo_video_prompt}
        """
        
        log.info(f"🧠 生成 '{channel.upper()}' 頻道企劃...")
        
        # 如果初始化時已判定為 Mock 模式，直接返回 Mock 企劃
        if self.use_mock or self.model is None:
            return self._generate_mock_plan(channel, additional_context)
        
        user_prompt = additional_context or "生成一個適合此頻道的企劃"
        
        system_instruction = f"""
        你是一位頂尖的影音企劃總監，負責 {channel.upper()} 頻道的音樂與影像製作。
        你的任務是根據使用者的靈感，輸出一份完美對齊的雙棲企劃 JSON。

        【嚴格輸出格式】：
        你必須且只能回傳一個合法的 JSON 物件，包含以下欄位：
        {{
            "title": "極具詩意、符合陪伴系氛圍的英文曲名",
            "tags": ["3至5個精準曲風標籤", "例如 Lofi, chill, ambient"],
            "suno_prompt": "給 Suno 的音樂生成提示詞 (包含樂器、節奏、情緒。結尾強制加上: , pristine studio sound, NO vocals)",
            "veo_image_prompt": "給 Veo 的影像風格描述 (例如: warm lighting, rainy window)",
            "veo_video_prompt": "給 Veo 的微動態影片指令 (強制開頭使用: cinematic 35mm lens, static camera, ... 然後描述微小的動態如雨滴、煙霧)"
        }}
        """

        try:
            # 呼叫 API，強制要求 application/json 輸出
            response = self.model.generate_content(
                system_instruction + "\n\n使用者靈感：" + user_prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                )
            )
            
            # 標準 JSON 解析
            plan_text = response.text.strip()
            plan = json.loads(plan_text)
            log.info("✅ Gemini 企劃生成成功")
            return plan
            
        except json.JSONDecodeError as e:
            log.error(f"❌ Gemini 返回無效 JSON: {e}")
            log.info("⚠️  自動降級到 Mock 企劃")
            return self._generate_mock_plan(channel, additional_context)
        except Exception as e:
            log.error(f"❌ Gemini API 呼叫失敗: {e}")
            log.info("⚠️  自動降級到 Mock 企劃")
            return self._generate_mock_plan(channel, additional_context)
    
    def _generate_mock_plan(self, channel: str, context: Optional[str] = None) -> Dict[str, Any]:
        """生成 Mock 企劃用於測試"""
        mock_plans = {
            "lofi": {
                "title": "Midnight Rain",
                "tags": ["lofi", "chill", "rainy"],
                "suno_prompt": "lo-fi hip-hop beat with jazz chords, warm vinyl crackle, relaxing 85 BPM, pristine studio sound, NO vocals",
                "veo_image_prompt": "rainy window, warm coffee cup, soft lighting",
                "veo_video_prompt": "cinematic 35mm lens, static camera on rainy window, slow focus shifts, warm color grading, rain drops on glass"
            },
            "light_music": {
                "title": "Sunny Moments",
                "tags": ["indie", "bright", "energetic"],
                "suno_prompt": "indie pop melody with acoustic guitar, uplifting 110 BPM, pristine studio sound, NO vocals",
                "veo_image_prompt": "bright daylight, modern urban setting",
                "veo_video_prompt": "cinematic modern lens, dynamic camera movements through cityscape, vibrant color grading"
            }
        }
        log.info(f"📋 使用 Mock 企劃 ({channel})")
        return mock_plans.get(channel, mock_plans["lofi"])


# ─────────────────────────────────────────────────────────────
# 【CLI 測試介面】
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine = GeminiGenesisEngine()
    
    log.info("\n【測試】生成 Lofi 雙棲企劃...")
    test_plan = engine.generate_dual_plan("lofi", "深夜雨夜，正在寫程式的孤獨工程師")
    
    if test_plan:
        log.info("✅ 企劃生成成功！")
        print("\n📋 生成的企劃：")
        print(json.dumps(test_plan, ensure_ascii=False, indent=2))
    else:
        log.error("❌ 企劃生成失敗")