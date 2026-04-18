#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【直接 HTTP Telegram Demo 發送】v9.1 - 簡化版
不依賴 telegram-bot-api，純 requests HTTP 發送
"""

import os
import sys
import json
from pathlib import Path
import requests
from dotenv import load_dotenv

# 加載 .env
workspace_root = Path(__file__).resolve().parent
env_file = workspace_root / ".env"
load_dotenv(env_file)

# 從 .env 讀取配置
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DEMO_DIR = workspace_root / "assets" / "audio" / "mastered_tracks" / "_demo_60sec"

print("\n" + "=" * 80)
print("📤 【CEO 決策層】Telegram Demo 直接發送 v9.1 (HTTP)")
print("=" * 80)

if not BOT_TOKEN or not CHAT_ID:
    print("❌ 缺少 Telegram 認證，無法發送")
    print(f"   Token: {BOT_TOKEN[:20] if BOT_TOKEN else '未設定'}...")
    print(f"   Chat ID: {CHAT_ID if CHAT_ID else '未設定'}")
    sys.exit(1)

print(f"✅ 配置已載入")
print(f"   Bot Token: {BOT_TOKEN[:30]}...")
print(f"   chat_id: {CHAT_ID}")
print(f"   Demo 資料夾: {DEMO_DIR}\n")

# 列舉所有 demo 檔案
demo_files = sorted(DEMO_DIR.glob("*.mp3")) if DEMO_DIR.exists() else []

if not demo_files:
    print(f"❌ 找不到 demo 檔案在: {DEMO_DIR}")
    sys.exit(1)

print(f"📋 發現 {len(demo_files)} 個 demo 檔案：")
for f in demo_files:
    size_mb = f.stat().st_size / (1024 * 1024)
    print(f"   📁 {f.name} ({size_mb:.1f} MB)")

# =============================================================================
# 直接發送函式
# =============================================================================

def send_audio_via_http(demo_path: Path, track_name: str) -> bool:
    """使用 HTTP 發送音檔到 Telegram"""
    if not demo_path.exists():
        print(f"    ❌ 檔案不存在")
        return False
    
    try:
        print(f"    ⏳ 上傳中...", end="", flush=True)
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendAudio"
        
        with open(demo_path, "rb") as audio_file:
            files = {"audio": audio_file}
            data = {
                "chat_id": CHAT_ID,
                "title": track_name,
                "performer": "R&S Echoes - AI Music",
                "caption": f"🎵 Demo (60 秒): {track_name}\n\n請決策：✅ 採用 或 ❌ 放棄",
                "parse_mode": "Markdown",
            }
            
            response = requests.post(url, files=files, data=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                msg_id = result.get("result", {}).get("message_id", "?")
                print(f" ✅ (Message ID: {msg_id})")
                return True
            else:
                error_desc = result.get("description", "Unknown error")
                print(f" ❌ {error_desc}")
                return False
        else:
            print(f" ❌ HTTP {response.status_code}")
            return False
                
    except Exception as e:
        print(f" ❌ {e}")
        return False

# =============================================================================
# 主程序
# =============================================================================


print("\n🚀 開始發送...\n")

success_count = 0
failed_count = 0

for idx, demo_file in enumerate(demo_files, 1):
    track_name = demo_file.stem.replace("_demo_60sec", "")
    print(f"【{idx}/{len(demo_files)}】 {track_name}")
    
    if send_audio_via_http(demo_file, track_name):
        success_count += 1
    else:
        failed_count += 1

print("\n" + "=" * 80)
print(f"📊 發送完成: {success_count}/{len(demo_files)} 成功  ({failed_count} 失敗)")
print("=" * 80)

if success_count > 0:
    print("\n✅ CEO 應該已在 Telegram 上收到 Demo！")
    print("   等待 CEO 決策：✅ 採用 或 ❌ 放棄")
    sys.exit(0)
else:
    print("\n❌ 所有發送都失敗了")
    sys.exit(1)

