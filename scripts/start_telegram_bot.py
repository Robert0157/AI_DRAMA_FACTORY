#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【啟動指令】R&S Echoes Telegram CEO Bot (v15.4)

使用方式：
  python scripts/start_telegram_bot.py               # 自動模式（依 .env 決定）
  python scripts/start_telegram_bot.py --polling     # 強制 Polling 模式
  python scripts/start_telegram_bot.py --webhook     # 強制 Webhook 模式（需 TELEGRAM_WEBHOOK_URL）
  python scripts/start_telegram_bot.py --ngrok       # 自動啟動 ngrok 並切換 Webhook 模式

環境變數要求：
  必填：TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID
  Webhook：TELEGRAM_WEBHOOK_URL（或搭配 --ngrok 自動填入）
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    print(f"❌ 找不到 .env 文件: {env_file}")
    sys.exit(1)

from scripts.common.env_manager import config


# ─────────────────────────────────────────────────────────────────────────────
# 環境檢查
# ─────────────────────────────────────────────────────────────────────────────

def check_environment(need_webhook: bool = False) -> bool:
    print("🔍 檢查環境配置...")

    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USER_ID"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"❌ 缺少必要環境變數: {', '.join(missing)}")
        print("   請在 .env 中設定這些變數")
        return False

    print("✅ TELEGRAM_BOT_TOKEN 已設定")
    print(f"✅ TELEGRAM_ALLOWED_USER_ID: {os.getenv('TELEGRAM_ALLOWED_USER_ID')}")

    if need_webhook:
        wh = config.telegram_webhook_url
        if wh:
            print(f"✅ TELEGRAM_WEBHOOK_URL: {wh}")
        else:
            print("⚠️  TELEGRAM_WEBHOOK_URL 未設定（請填入 .env 或使用 --ngrok）")

    try:
        from scripts.gear2_rnd.vault_database import VaultDatabase  # noqa
        print("✅ Protocol L 模塊已就緒")
    except ImportError:
        print("⚠️  Protocol L 模塊不可用（可選）")

    try:
        import telegram
        print(f"✅ python-telegram-bot 版本: {telegram.__version__}")
    except ImportError:
        import sys as _sys
        python_exe = _sys.executable
        print("❌ python-telegram-bot 未安裝於當前 Python 環境")
        print(f"   請執行（使用當前 venv 的 Python）：")
        print(f"   {python_exe} -m pip install python-telegram-bot pyngrok")
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# ngrok 自動隧道
# ─────────────────────────────────────────────────────────────────────────────

def _start_ngrok(port: int) -> str:
    """
    自動啟動 ngrok 並等待公網 URL。
    回傳 HTTPS URL（例如 https://abc123.ngrok-free.app）。
    若 ngrok 未安裝或 authtoken 未設定則報錯並退出。
    """
    # 從 .env 讀取 authtoken
    ngrok_authtoken = os.environ.get("NGROK_AUTHTOKEN", "").strip()

    try:
        import pyngrok.ngrok as ngrok_mod        # type: ignore
        import pyngrok.conf as ngrok_conf        # type: ignore

        # 設定 authtoken（必要步驟，ngrok 2022 年後強制要求）
        if ngrok_authtoken:
            ngrok_conf.get_default().auth_token = ngrok_authtoken
        else:
            print("❌ NGROK_AUTHTOKEN 未設定，無法建立 ngrok 隧道。")
            print()
            print("   請依以下步驟取得免費 authtoken：")
            print("   1. 前往 https://dashboard.ngrok.com/signup 免費註冊")
            print("   2. 登入後到 https://dashboard.ngrok.com/get-started/your-authtoken")
            print("   3. 複製 authtoken，貼到 .env 的 NGROK_AUTHTOKEN= 後方")
            print()
            print("   設定完成後重新執行：python scripts/start_telegram_bot.py --ngrok")
            sys.exit(1)

        print(f"🚇 正在透過 pyngrok 建立 ngrok 隧道（port {port}）...")
        tunnel = ngrok_mod.connect(port, "http")
        public_url = tunnel.public_url
        if public_url.startswith("http://"):
            public_url = "https://" + public_url[7:]
        print(f"✅ ngrok 隧道已建立：{public_url}")
        return public_url
    except ImportError:
        pass

    # 嘗試直接呼叫 ngrok CLI
    try:
        # 若有 authtoken，先執行 authtoken 設定指令
        if ngrok_authtoken:
            subprocess.run(["ngrok", "config", "add-authtoken", ngrok_authtoken],
                           capture_output=True, check=False)
        elif not ngrok_authtoken:
            print("❌ NGROK_AUTHTOKEN 未設定，無法建立 ngrok 隧道。")
            print("   請到 https://dashboard.ngrok.com/get-started/your-authtoken 取得 token")
            print("   並填入 .env 的 NGROK_AUTHTOKEN=")
            sys.exit(1)

        proc = subprocess.Popen(
            ["ngrok", "http", str(port), "--log=stdout"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        print(f"🚇 等待 ngrok CLI 建立隧道（port {port}）...")
        time.sleep(4)

        import urllib.request, json as _json
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=5) as resp:
            data = _json.loads(resp.read())
        for t in data.get("tunnels", []):
            url = t.get("public_url", "")
            if url.startswith("https://"):
                print(f"✅ ngrok 隧道已建立：{url}")
                return url
        print("❌ 無法從 ngrok API 取得公網 URL")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ 找不到 ngrok。請先安裝：")
        print("   方式 A（推薦）: pip install pyngrok")
        print("   方式 B：下載 https://ngrok.com/download 並設定 PATH")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ngrok 啟動失敗: {e}")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def main_entry():
    parser = argparse.ArgumentParser(
        description="R&S Echoes Telegram Bot 啟動器 (v15.4)"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--polling", action="store_true", help="強制 Polling 模式")
    mode_group.add_argument("--webhook", action="store_true", help="強制 Webhook 模式（需 TELEGRAM_WEBHOOK_URL）")
    mode_group.add_argument("--ngrok",   action="store_true", help="自動啟動 ngrok 隧道並使用 Webhook 模式")
    args = parser.parse_args()

    print("=" * 62)
    print("🎛️  R&S Echoes CEO Telegram Bot (v15.4)")
    print("=" * 62)

    # 決定啟動模式
    if args.ngrok:
        mode = "webhook"
        need_wh = False  # ngrok 會自動產生 URL，不需要預先設定
    elif args.webhook:
        mode = "webhook"
        need_wh = True
    elif args.polling:
        mode = "polling"
        need_wh = False
    else:
        # auto：有 TELEGRAM_WEBHOOK_URL → webhook，否則 polling
        mode = "webhook" if config.telegram_webhook_url else "polling"
        need_wh = (mode == "webhook")

    print(f"📡 啟動模式：{'WEBHOOK' if mode == 'webhook' else 'POLLING'}")
    print()

    if not check_environment(need_webhook=need_wh):
        sys.exit(1)

    print()
    print("=" * 62)

    # 取得 webhook URL
    webhook_url = ""
    port = config.telegram_webhook_port

    if mode == "webhook":
        if args.ngrok:
            webhook_url = _start_ngrok(port)
        else:
            webhook_url = config.telegram_webhook_url
            if not webhook_url:
                print("❌ Webhook 模式需要 TELEGRAM_WEBHOOK_URL，請填入 .env 或改用 --ngrok")
                sys.exit(1)

    # 呼叫 telegram_manager_bot.main()（傳遞模式參數）
    print("🚀 啟動 Bot 服務...")
    print(f"   按 Ctrl+C 停止")
    print("=" * 62)
    print()

    # 把參數注入 sys.argv 後直接呼叫 bot main()
    original_argv = sys.argv[:]
    sys.argv = [sys.argv[0], "--mode", mode]
    if mode == "webhook" and webhook_url:
        sys.argv += ["--webhook-url", webhook_url, "--port", str(port)]

    try:
        from scripts.gear1_prod.telegram_manager_bot import main as bot_main
        bot_main()
    except KeyboardInterrupt:
        print()
        print("[Bot] 服務已停止 (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        print(f"[Bot] 服務啟動失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    main_entry()
