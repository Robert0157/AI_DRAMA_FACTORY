#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common/llm_client.py
v15.3 軍規級 API 防護：三引擎大模型安全通訊網關
強制 Structured Outputs (JSON Schema)，內建重試與日誌瘦身，環境變數統一派發。

【v15.3 三引擎架構】
✅ 引擎1 zhipu  — 智譜 GLM-4（預設，省錢穩定）
✅ 引擎2 gemini — Google Gemini 2.5 Flash（視覺解構備用）
✅ 引擎3 minimax— MiniMax M2.7 230B MoE via NVIDIA NIM
             相容 OpenAI 協定，base_url = https://integrate.api.nvidia.com/v1
✅ 所有密鑰由 env_manager.py 統一派發，自動從 .env 讀取
✅ 全部採用 lazy import，避免未安裝套件干擾其他引擎
"""

import sys
import json
import time
import random
from pathlib import Path
from typing import Dict, Any, Optional

# 【CTO 強制執行】確保腳本能找到專案根目錄並載入 common 模組
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

# 顏色碼（終端機輸出）
RED = "\033[91m"
RESET = "\033[0m"

# Gemini API 初始化旗標（lazy — 只有 provider="gemini" 時才初始化）
_gemini_configured: bool = False
_genai = None  # lazy import placeholder


def _ensure_gemini_configured() -> None:
    """
    確保 Gemini API 已用 GEMINI_API_KEY 完成初始化（單次執行）。
    【v15.3 修復】將 google.generativeai import 移至此處（lazy import），
    避免 zhipu 路徑觸發廢棄套件警告，也防止套件版本不相容時崩潰影響其他功能。
    """
    global _gemini_configured, _genai
    if _gemini_configured:
        return

    try:
        import google.generativeai as genai_mod
        _genai = genai_mod
    except ImportError:
        raise ImportError(
            "❌ 缺少 google-generativeai 套件。"
            "請執行: pip install google-generativeai"
        )

    api_key = config.GEMINI_API_KEY
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY 環境變數未在 .env 中設定。\n"
            "請檢查 WORKSPACE_ROOT/.env 是否包含有效的 GEMINI_API_KEY。"
        )
    _genai.configure(api_key=api_key)
    _gemini_configured = True


def _clean_json_response(response_text: str) -> str:
    """
    強化 JSON 暴力解析：
    1. 剝除 Markdown 代碼塊
    2. 從文字中萃取第一個完整 {...} JSON 物件（應對 LLM 前置說明文字）
    3. 自動補全因 max_tokens 截斷造成的未閉合括號
    """
    import re as _re
    text = response_text.strip()

    # 剝除 ```json ... ``` 或 ``` ... ``` 包裝
    text = _re.sub(r'```(?:json)?\s*\n?', '', text, flags=_re.IGNORECASE)
    text = _re.sub(r'\n?```', '', text)
    text = text.strip()

    # 若文字不以 { 開頭（LLM 前置了說明文字），嘗試從第一個 { 開始截取
    brace_start = text.find('{')
    if brace_start > 0:
        text = text[brace_start:]

    # 自動補全因 max_tokens 截斷造成的未閉合括號
    open_b = text.count('{')
    close_b = text.count('}')
    if open_b > close_b:
        text += '}' * (open_b - close_b)
    open_sq = text.count('[')
    close_sq = text.count(']')
    if open_sq > close_sq:
        text += ']' * (open_sq - close_sq)

    return text.strip()


def _log_fatal_slim(error_context: str, exception: Exception) -> None:
    """
    CTO 鐵律：Log Sanitization (日誌瘦身)。
    只擷取 Exception Name 與最後一行訊息，避免污染 project_learning.md。
    """
    error_type = type(exception).__name__
    last_line = str(exception).strip().split("\n")[-1][:200]
    slim_msg = f"[{error_context}] {error_type}: {last_line}"
    print(f"⚠️ LLM Client Error: {slim_msg}")



def _generate_minimax(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_retries: int,
) -> Optional[Dict[str, Any]]:
    """
    【引擎3】MiniMax M2.7 230B MoE — NVIDIA NIM (OpenAI 相容協定)
    temperature=1.0, top_p=0.95 為官方建議最佳實踐。
    """
    api_key = config.NVIDIA_API_KEY
    if not api_key or api_key.startswith("nvapi-填入"):
        raise EnvironmentError(
            "NVIDIA_API_KEY 未設定。請至 https://build.nvidia.com/ 取得金鑰"
            "並填入 .env 中的 NVIDIA_API_KEY 欄位。"
        )
    try:
        from openai import OpenAI as _OpenAI
    except ImportError:
        raise ImportError("缺少 openai 套件，請執行: pip install openai")

    # timeout=180s：NVIDIA NIM MiniMax 230B 實測 ~100s，180s 給足安全邊際
    client = _OpenAI(
        base_url=config.NVIDIA_BASE_URL,
        api_key=api_key,
        timeout=180.0,
    )
    target_model = model or "minimaxai/minimax-m2.7"
    last_exc = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=target_model,
                messages=[
                    {"role": "system", "content": system_prompt or ""},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=1.0,
                top_p=0.95,
                max_tokens=4096,  # 從 2048 提升至 4096，確保 20 首雙語曲名不截斷
            )
            raw = response.choices[0].message.content or ""
            if not raw:
                raise Exception("MiniMax API 回傳空內容")
            cleaned = _clean_json_response(raw)
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            _log_fatal_slim("MiniMax JSON Parse", e)
            last_exc = e
            if attempt < max_retries:
                backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
                print(f"  ⚠️ MiniMax JSON 解析失敗，重試 {attempt}/{max_retries}，{backoff:.1f}s 後再試")
                time.sleep(backoff)
        except Exception as e:
            last_exc = e
            _log_fatal_slim(f"MiniMax API attempt {attempt}", e)
            if attempt < max_retries:
                backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
                print(f"  ⚠️ MiniMax API 重試 {attempt}/{max_retries}：{e}，{backoff:.1f}s 後再試")
                time.sleep(backoff)
    raise Exception(f"MiniMax API 最終失敗: {last_exc}")


def generate_structured_json(
    system_prompt: str,
    user_prompt: str,
    provider: str = "minimax",
    model: str = None,
    max_retries: int = 3,
    timeout: tuple = (30, 300)
) -> Optional[Dict[str, Any]]:
    """
    三引擎 LLM JSON 生成器
    provider: "minimax"（預設，MiniMax M2.7 230B NVIDIA NIM）| "zhipu"（智譜 GLM-4）| "gemini"（Google）
    """
    if provider == "minimax":
        return _generate_minimax(system_prompt, user_prompt, model, max_retries)

    if provider == "gemini":
        _ensure_gemini_configured()   # lazy import + configure
        target_model = model or "gemini-2.5-flash"
        gemini_model = _genai.GenerativeModel(
            model_name=target_model,
            generation_config=_genai.GenerationConfig(
                temperature=0.87,
                response_mime_type="application/json",
            ),
        )
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                response = gemini_model.generate_content(
                    f"{system_prompt}\n\n{user_prompt}",
                    request_options={"timeout": 120},
                )
                raw_content = response.text
                if not raw_content:
                    raise Exception("Gemini API 回傳空內容")
                cleaned_content = _clean_json_response(raw_content)
                parsed_json = json.loads(cleaned_content)
                return parsed_json
            except json.JSONDecodeError as e:
                _log_fatal_slim("JSON Parse Error (after cleaning)", e)
                last_exc = e
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
                    print(f"  ⚠️ Gemini API JSON 解析失敗，重試 {attempt}/{max_retries}，{backoff:.1f}s 後再試")
                    time.sleep(backoff)
                    continue
                raise Exception(f"無法解析 Gemini JSON 輸出: {e}") from e
            except Exception as e:
                last_exc = e
                _log_fatal_slim(f"Gemini API attempt {attempt}", e)
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
                    print(f"  ⚠️ Gemini API 重試 {attempt}/{max_retries}：{e}，{backoff:.1f}s 後再試")
                    time.sleep(backoff)
                    continue
                raise Exception(f"Gemini API 最終失敗: {e}") from e
        if last_exc:
            raise Exception(f"Gemini API 無回應: {last_exc}")
    else:
        # 路由到 Zhipu GLM-4
        from scripts.common.llm_client_zhipu import generate_structured_json_zhipu
        prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
        target_model = model or "glm-4"
        return generate_structured_json_zhipu(prompt, model=target_model, max_retries=max_retries)