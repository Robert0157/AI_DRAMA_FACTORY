import os
import sys
import json
import time
import urllib.request
import urllib.error

# 🚀 CTO 強制路徑防禦 (永遠鎖死外接硬碟)
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "/Volumes/AI_Workspace/AI_DRAMA_FACTORY")
AUDIO_OUT_DIR = os.path.join(WORKSPACE_ROOT, "assets/audio")

# 從 .env 讀取中國大陸低成本音樂 API 配置
CHINESE_AUDIO_API_URL = os.getenv("CHINESE_AUDIO_API_URL", "https://api.example.com/v1/audio/generation")
CHINESE_AUDIO_API_KEY = os.getenv("CHINESE_AUDIO_API_KEY", "")

def generate_arbitrage_audio(base_prompt, duration_sec, output_path):
    """成本套利呼叫：使用大陸低價 API，但強制輸出全球化無國界音樂"""
    print(f"🌍 Triggering Chinese API for Global Content. Base prompt: '{base_prompt}'", file=sys.stderr)
    
    if not CHINESE_AUDIO_API_KEY:
        print("❌ Error: CHINESE_AUDIO_API_KEY missing in .env", file=sys.stderr)
        return False

    try:
        # 💡 CTO 提示詞綁架機制：強制注入全球化、無國界、純器樂的標籤
        globalized_prompt = f"{base_prompt}, universal lofi hip hop, cinematic ambient, strictly instrumental, NO vocals, NO language, borderless global aesthetic"
        
        # 準備 Payload
        payload = json.dumps({
            "prompt": globalized_prompt, 
            "duration": float(duration_sec),
            "make_instrumental": True # 雙重防險：要求模型強制純樂器
        }).encode('utf-8')
        
        req = urllib.request.Request(CHINESE_AUDIO_API_URL, data=payload, headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {CHINESE_AUDIO_API_KEY}'
        })
        
        print("⏳ Waiting for cloud generation (Timeout: 120s)...", file=sys.stderr)
        
        # 發送請求並直接將音軌結果寫入 Mac M4 的外接 APFS 硬碟
        os.makedirs(AUDIO_OUT_DIR, exist_ok=True)
        with urllib.request.urlopen(req, timeout=120) as response, open(output_path, 'wb') as out_file:
            out_file.write(response.read())
            
        print(f"✅ Arbitrage generation successful. Saved to: {output_path}", file=sys.stderr)
        return True
        
    except urllib.error.HTTPError as e:
        print(f"❌ API HTTP Error: {e.code} - {e.read().decode('utf-8')}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Cloud Generation crashed: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"status": "ERROR", "feedback": "Usage: python chinese_api_audio_engine.py '<PROMPT>' <DURATION>"}, ensure_ascii=False))
        sys.exit(1)

    prompt_text = sys.argv[1]
    target_duration = sys.argv[2]
    out_file = os.path.join(AUDIO_OUT_DIR, f"lofi_global_{int(time.time())}.wav")

    # 執行套利生成
    success = generate_arbitrage_audio(prompt_text, target_duration, out_file)

    if success:
        # 回傳純淨的 JSON 供 Openclaw 解析
        print(json.dumps({"status": "SUCCESS", "audio_file": out_file}, ensure_ascii=False))
        sys.exit(0)
    else:
        print(json.dumps({"status": "ERROR", "feedback": "Chinese Audio API generation failed."}, ensure_ascii=False))
        sys.exit(1)
		