#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""測試啟動腳本診斷"""

import os
import sys
from pathlib import Path

print("【1】Python 版本:", sys.version)

# 加載 .env
from dotenv import load_dotenv
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
env_file = _PROJECT_ROOT / ".env"
print(f"【2】加載 .env: {env_file.exists()}")
load_dotenv(env_file)

# 檢查環境變數
print("【3】環境變數:")
print(f"  TELEGRAM_BOT_TOKEN: {bool(os.getenv('TELEGRAM_BOT_TOKEN'))}")
print(f"  TELEGRAM_ALLOWED_USER_ID: {os.getenv('TELEGRAM_ALLOWED_USER_ID')}")

# 添加路徑
sys.path.insert(0, str(_PROJECT_ROOT))
print(f"【4】Python 路徑: {_PROJECT_ROOT}")

# 嘗試導入模組
try:
    from scripts.common.telegram_bot_manager import main, _log
    print("【5】✅ 模組導入成功")
except Exception as e:
    print(f"【5】❌ 模組導入失敗: {e}")
    sys.exit(1)

print("\n✅ 所有診斷完成！可以啟動 Bot")
