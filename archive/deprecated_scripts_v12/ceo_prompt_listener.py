#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【CEO 提示詞注入監聽器】v10.0

功能：
- 監聽 Telegram Bot 接收到的消息
- 檢測包含 CEO 提示詞的消息
- 自動保存到 assets/.ceo_prompts/ 供生成工具讀取
- 支援命令：
  * /prompt_inject [PROMPT TEXT] - 單行提示詞
  * /submit_prompt - CEO 直接貼上長提示詞文本
  * /generate_now - 立即使用 CEO 提示詞觸發生成

設計原則：
✅ 無 asyncio 死鎖：使用純 urllib HTTP 輪詢
✅ 超時保護：每次請求 30秒 timeout
✅ 交易式寫入：使用 atomic_write_text 防止檔案損毀
✅ 跨平台：所有路徑使用 pathlib

實作方法：
1. 定期呼叫 Telegram Bot API getUpdates 獲取新消息
2. 篩選 offset（避免重複處理）
3. 查找 CEO_CHAT_ID 且包含觸發詞的消息
4. 解析提示詞內容
5. 保存到 assets/.ceo_prompts/
6. 選擇性觸發 suno_lofi_generator.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.atomic_io import atomic_write_text
from scripts.common.env_manager import config


# ════════════════════════════════════════════════════════════════════════════
# 配置與常數
# ════════════════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = config.telegram_bot_token
TELEGRAM_CHAT_ID = config.telegram_chat_id
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# CEO 可用的觸發命令
TRIGGER_COMMANDS = ("/prompt_inject", "/submit_prompt", "/generate_now")

# 監聽狀態檔案路徑
LAST_UPDATE_ID_FILE = Path(config.workspace_root) / "assets" / ".telegram_last_update_id"
CEO_PROMPTS_DIR = Path(config.workspace_root) / "assets" / ".ceo_prompts"
GENERATION_LOG = Path(config.workspace_root) / "assets" / ".ceo_generation_log.json"

# 請求超時
HTTP_TIMEOUT = 30


# ════════════════════════════════════════════════════════════════════════════
# HTTP 工具函式（純 urllib，避免 asyncio 問題）
# ════════════════════════════════════════════════════════════════════════════

def _http_get(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    純 HTTP GET 請求（無 asyncio）
    
    Args:
        endpoint: Telegram API 端點 (e.g., "getUpdates")
        params: 查詢參數
        
    Returns:
        API 回應 JSON
        
    Raises:
        urllib.error.URLError: 網路錯誤
        json.JSONDecodeError: 解析錯誤
    """
    url = f"{TELEGRAM_API_URL}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
            body = response.read()
            return json.loads(body.decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"❌ HTTP 請求失敗 ({endpoint}): {e}")
        raise
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失敗 ({endpoint}): {e}")
        raise


def _get_last_update_id() -> int:
    """讀取上次處理的 update_id（避免重複處理）"""
    if LAST_UPDATE_ID_FILE.exists():
        try:
            return int(LAST_UPDATE_ID_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            return 0
    return 0


def _save_last_update_id(update_id: int) -> None:
    """保存已處理的 update_id"""
    atomic_write_text(LAST_UPDATE_ID_FILE, str(update_id))


def _get_new_messages() -> list[dict[str, Any]]:
    """
    從 Telegram Bot 獲取新消息
    
    Returns:
        消息列表 (Telegram Update 物件)
    """
    last_id = _get_last_update_id()
    params = {
        "offset": last_id + 1 if last_id > 0 else 1,
        "timeout": 5,  # 長輪詢 5 秒
    }
    
    try:
        response = _http_get("getUpdates", params)
    except Exception as e:
        print(f"❌ 無法獲取新消息: {e}")
        return []
    
    if not response.get("ok", False):
        print(f"❌ Telegram 回應錯誤: {response}")
        return []
    
    updates = response.get("result", [])
    if updates:
        latest_id = max(u.get("update_id", 0) for u in updates)
        _save_last_update_id(latest_id)
    
    return updates


def _parse_ceo_prompt(message_text: str) -> str | None:
    """
    從消息文本中提取 CEO 提示詞
    
    支援格式：
    1. /prompt_inject SINGLE LINE PROMPT
    2. /submit_prompt\\n[多行提示詞文本]
    3. 任何包含提示詞的長文本
    
    Args:
        message_text: 消息內容
        
    Returns:
        提示詞文本，若無法解析則返回 None
    """
    lines = message_text.strip().split("\n")
    
    if not lines:
        return None
    
    first_line = lines[0].strip()
    
    # 【情況 1】/prompt_inject + 提示詞（同行或下行）
    if first_line.startswith("/prompt_inject"):
        remaining = first_line[len("/prompt_inject"):].strip()
        if remaining:
            return remaining
        elif len(lines) > 1:
            return "\n".join(lines[1:]).strip()
        return None
    
    # 【情況 2】/submit_prompt + 提示詞（下行開始）
    if first_line.startswith("/submit_prompt"):
        if len(lines) > 1:
            return "\n".join(lines[1:]).strip()
        return None
    
    # 【情況 3】長提示詞文本（直接貼上）
    if len(message_text.strip()) > 50:  # 至少 50 字元的提示詞
        return message_text.strip()
    
    return None


def _save_ceo_prompt(prompt: str, source: str = "telegram") -> Path:
    """
    保存 CEO 提示詞到檔案
    
    Args:
        prompt: 提示詞文本
        source: 來源標籤 ("telegram" | "file" | etc.)
        
    Returns:
        保存的檔案路徑
    """
    CEO_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # 使用時間戳記建立唯一檔案名稱
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ceo_prompt_{source}_{timestamp}.txt"
    file_path = CEO_PROMPTS_DIR / filename
    
    # 交易式寫入
    atomic_write_text(file_path, prompt)
    
    return file_path


def _trigger_generation() -> bool:
    """
    觸發 suno_lofi_generator.py 進行生成
    
    Returns:
        成功觸發返回 True，否則 False
    """
    import subprocess
    
    script_path = Path(__file__).resolve().parents[0] / "suno_lofi_generator.py"
    
    try:
        print(f"🚀 觸發生成進程: {script_path}")
        result = subprocess.run(
            [sys.executable, str(script_path), "--print"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode == 0:
            print("✅ 生成進程完成")
            return True
        else:
            print(f"❌ 生成進程失敗: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏱️  生成進程超時")
        return False
    except Exception as e:
        print(f"❌ 無法觸發生成進程: {e}")
        return False


def _log_generation_event(prompt_preview: str, success: bool) -> None:
    """記錄 CEO 提示詞注入事件"""
    GENERATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    
    event = {
        "timestamp": datetime.now().isoformat(),
        "prompt_preview": prompt_preview[:100] + "..." if len(prompt_preview) > 100 else prompt_preview,
        "success": success,
    }
    
    try:
        # 載入現有日誌
        if GENERATION_LOG.exists():
            logs = json.loads(GENERATION_LOG.read_text(encoding="utf-8"))
        else:
            logs = []
        
        logs.append(event)
        
        # 保持最近 100 條記錄
        logs = logs[-100:]
        
        atomic_write_text(GENERATION_LOG, json.dumps(logs, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"⚠️  無法記錄事件: {e}")


# ════════════════════════════════════════════════════════════════════════════
# 主監聽迴圈
# ════════════════════════════════════════════════════════════════════════════

def listen_for_ceo_prompts(continuous: bool = False, interval_sec: int = 5) -> None:
    """
    監聽 CEO 提示詞注入
    
    Args:
        continuous: 是否持續監聽（True = 24/7，False = 單次掃描）
        interval_sec: 輪詢間隔（秒）
    """
    print("=" * 80)
    print("【CEO 提示詞監聽器】v10.0 - 啟動")
    print(f"  Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"  Prompts Dir: {CEO_PROMPTS_DIR}")
    print(f"  輪詢間隔: {interval_sec} 秒")
    print(f"  模式: {'持續' if continuous else '單次'}")
    print("=" * 80)
    
    iteration = 0
    
    while True:
        iteration += 1
        print(f"\n【迴圈 {iteration}】{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            messages = _get_new_messages()
            
            if messages:
                print(f"  📨 收到 {len(messages)} 條消息")
            
            processed = 0
            
            for update in messages:
                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "")
                from_id = message.get("from", {}).get("id")
                
                # 【過濾】僅處理來自 CEO 的消息
                if chat_id != int(TELEGRAM_CHAT_ID):
                    continue
                
                # 【過濾】檢查是否包含觸發詞
                is_trigger = any(cmd in text for cmd in TRIGGER_COMMANDS) or (
                    len(text.strip()) > 50 and "/generate_now" in text
                )
                
                if not is_trigger:
                    continue
                
                print(f"\n  ✅ 檢測到 CEO 消息 (from={from_id})")
                
                # 【解析】提取提示詞
                prompt = _parse_ceo_prompt(text)
                
                if not prompt:
                    print("  ⚠️  無法解析提示詞，跳過")
                    continue
                
                print(f"  📝 提示詞長度: {len(prompt)} 字元")
                
                # 【保存】到檔案
                prompt_file = _save_ceo_prompt(prompt, source="telegram")
                print(f"  💾 已保存到: {prompt_file.name}")
                
                processed += 1
                
                # 【觸發】生成（若消息包含 /generate_now）
                if "/generate_now" in text:
                    print(f"  🚀 偵測到 /generate_now 指令，觸發生成...")
                    success = _trigger_generation()
                    _log_generation_event(prompt[:100], success)
            
            if processed > 0:
                print(f"\n  ✨ 本輪共處理 {processed} 個 CEO 提示詞")
        
        except Exception as e:
            print(f"  ❌ 處理錯誤: {e}")
        
        # 【迴圈判斷】
        if not continuous:
            print("\n【單次掃描完成】")
            break
        
        print(f"  ⏳ 等待 {interval_sec} 秒後重新掃描...")
        time.sleep(interval_sec)


def main() -> None:
    """命令行進入點"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="CEO 提示詞注入監聽器"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="持續監聽模式 (24/7)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="輪詢間隔（秒，預設 5）"
    )
    
    args = parser.parse_args()
    
    try:
        listen_for_ceo_prompts(continuous=args.continuous, interval_sec=args.interval)
    except KeyboardInterrupt:
        print("\n\n【監聽器】已停止")
        sys.exit(0)


if __name__ == "__main__":
    main()
