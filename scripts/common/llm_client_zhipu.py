
# -*- coding: utf-8 -*-
"""
ZhipuAI (GLM-4) LLM 客戶端 for Dual-Engine
【v15.3 熱修復】廢除官方 zhipuai SDK 依賴，改用原生 requests 確保環境相容性。
"""
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

# 確保載入 env_manager
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

def _generate_jwt_token(apikey: str, exp_seconds: int = 300) -> str:
    """生成智譜 API 需要的 JWT Token (免安裝 pyjwt)"""
    import time
    import hmac
    import hashlib
    import base64
    import json

    try:
        id, secret = apikey.split(".")
    except ValueError:
        raise ValueError("智譜 API Key 格式不正確")

    header = {
        "alg": "HS256",
        "sign_type": "SIGN"
    }
    payload = {
        "api_key": id,
        "exp": int(time.time() * 1000) + exp_seconds * 1000,
        "timestamp": int(time.time() * 1000)
    }

    def b64url_encode(data):
        return base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode('utf-8')).decode('utf-8').rstrip('=')

    header_b64 = b64url_encode(header)
    payload_b64 = b64url_encode(payload)
    sign_data = f"{header_b64}.{payload_b64}"

    signature = hmac.new(secret.encode('utf-8'), sign_data.encode('utf-8'), hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')

    return f"{sign_data}.{signature_b64}"


def _clean_json_response(response_text: str) -> str:
    """清除 Markdown 代碼塊"""
    response_text = response_text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    return response_text.strip()


def generate_structured_json_zhipu(prompt: str, model: str = "glm-4-flash", max_retries: int = 3) -> dict:
    """
    呼叫智譜 GLM-4，強制要求回傳 JSON，使用原生 urllib。
    """
    api_key = config.ZHIPUAI_API_KEY
    if not api_key:
        raise EnvironmentError("ZHIPUAI_API_KEY 未設定於 .env，請聯繫 CTO 配置！")
    
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    
    data = json.dumps(payload).encode("utf-8")
    last_exc = None
    
    for attempt in range(1, max_retries + 1):
        try:
            token = _generate_jwt_token(api_key)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body)
                
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise ValueError("智譜 API 回傳空內容")
                    
                cleaned_content = _clean_json_response(content)
                return json.loads(cleaned_content)
                
        except urllib.error.HTTPError as http_err:
            error_msg = http_err.read().decode("utf-8")
            last_exc = Exception(f"HTTP {http_err.code}: {error_msg}")
        except Exception as e:
            last_exc = e
            
        if attempt < max_retries:
            import random
            backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
            print(f"  ⚠️ Zhipu GLM-4 API 失敗，重試 {attempt}/{max_retries}，{backoff:.1f}s 後再試: {last_exc}")
            time.sleep(backoff)
            continue
            
    raise Exception(f"Zhipu GLM-4 API 最終失敗: {last_exc}")
