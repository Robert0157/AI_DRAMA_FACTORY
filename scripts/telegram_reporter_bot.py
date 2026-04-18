#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【Telegram 遠端推播引擎】Reporter Bot
建立推播通道，將系統事件（財報、預警、統計）推送至 CEO Telegram

功能：
  1. 非同步發送每日財報至 Telegram
  2. 庫存預警推播（< 20 首警告）
  3. 心跳守護程序的定時通知
  4. HTTP 本地接口，供 factory_heartbeat.py 遠端呼叫

安全機制：
  - 環境變數 TELEGRAM_BOT_TOKEN、TELEGRAM_ALLOWED_USER_ID
  - 防止 Token 寫死在代碼中
  - 非同步安全（asyncio）
  - MacOS 部署防禦（無阻塞）
"""

import asyncio
import json
import os
import sys
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from enum import Enum

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

# ============================================================================
# 全域配置
# ============================================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID")

# 訊息類別
class MessageType(Enum):
    DAILY_REPORT = "daily_report"
    INVENTORY_WARNING = "inventory_warning"
    ERROR_ALERT = "error_alert"
    SUCCESS_NOTIFICATION = "success_notification"


# ============================================================================
# 日誌與驗證
# ============================================================================

def _log(msg: str, level: str = "INFO"):
    """統一日誌輸出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[TELEGRAM_REPORTER][{timestamp}][{level}] {msg}")


def _validate_environment():
    """
    驗證 Telegram 環境變數
    """
    if not BOT_TOKEN:
        _log("❌ 缺少 TELEGRAM_BOT_TOKEN 環境變數", "ERROR")
        return False
    
    if not ALLOWED_USER_ID:
        _log("❌ 缺少 TELEGRAM_ALLOWED_USER_ID 環境變數", "ERROR")
        return False
    
    _log("✅ Telegram 環境變數已驗證", "INFO")
    return True


# ============================================================================
# 推播核心函數 (同步版本 - 供 factory_heartbeat.py 直接呼叫)
# ============================================================================

def send_telegram_report(
    message_title: str,
    message_body: str,
    message_type: str = "daily_report",
    emoji: str = "📊"
) -> Dict:
    """
    【核心推播函數】同步版本 - 供 factory_heartbeat.py 遠端呼叫

    Args:
        message_title: 訊息標題（例如「每日財報」）
        message_body: 訊息主體（Markdown 格式）
        message_type: 訊息類別（daily_report / inventory_warning / error_alert）
        emoji: 訊息頭部 emoji（預設 📊）

    Returns:
        dict: 發送結果 {"success": bool, "message": str, "response": ...}
    
    使用範例：
        result = send_telegram_report(
            message_title="每日財報 - 2026-04-09",
            message_body="Lofi 頻道: 120 首\\nLight Music: 85 首\\n總衍生: 450 次",
            message_type="daily_report",
            emoji="📊"
        )
    """
    
    if not _validate_environment():
        return {
            "success": False,
            "error": "Telegram 環境變數未配置",
            "message": "無法推播 - 缺少配置"
        }
    
    try:
        # 【Telegram Bot API】使用 sendMessage 方法
        # API 端點: https://api.telegram.org/bot<TOKEN>/sendMessage
        
        api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        # 構建 Markdown 格式的訊息
        formatted_message = f"""
{emoji} **{message_title}**

{message_body}

---
🤖 *自動發送* | *時間*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # 準備請求負載
        payload = {
            "chat_id": ALLOWED_USER_ID,
            "text": formatted_message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        
        # 發送 HTTP POST 請求至 Telegram API
        _log(f"📤 正在推播 {message_type}: {message_title}", "INFO")
        
        response = requests.post(api_url, json=payload, timeout=10)
        
        if response.status_code == 200:
            _log(f"✅ 推播成功: {message_title}", "INFO")
            return {
                "success": True,
                "message": f"✅ 訊息已發送至 Telegram",
                "response": response.json()
            }
        else:
            _log(f"❌ Telegram API 錯誤: {response.status_code} - {response.text}", "ERROR")
            return {
                "success": False,
                "error": f"Telegram API 錯誤 ({response.status_code})",
                "response": response.text,
                "message": "推播失敗"
            }
    
    except requests.Timeout:
        _log("❌ 推播超時 (>10秒)", "ERROR")
        return {
            "success": False,
            "error": "網路超時",
            "message": "推播失敗 - 網路超時"
        }
    
    except Exception as e:
        _log(f"❌ 推播異常: {str(e)}", "ERROR")
        return {
            "success": False,
            "error": str(e),
            "message": f"推播失敗: {str(e)}"
        }


# ============================================================================
# 非同步推播函數 (供其他非同步場景使用)
# ============================================================================

async def send_telegram_report_async(
    message_title: str,
    message_body: str,
    message_type: str = "daily_report",
    emoji: str = "📊"
) -> Dict:
    """
    【非同步推播函數】供 asyncio 環境使用

    使用範例：
        asyncio.run(send_telegram_report_async(
            message_title="財報通知",
            message_body="...",
            emoji="💰"
        ))
    """
    
    # 在執行緒池中執行同步函數
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        send_telegram_report,
        message_title,
        message_body,
        message_type,
        emoji
    )
    
    return result


# ============================================================================
# 專業報表生成函數
# ============================================================================

def generate_daily_financial_report(audit_data: Dict) -> str:
    """
    生成每日財務報表訊息

    Args:
        audit_data: 從 VaultDatabase.get_asset_audit_data() 返回的數據

    Returns:
        str: Markdown 格式的報表
    """
    
    try:
        global_stats = audit_data.get("global_stats", {})
        channels = audit_data.get("channels", {})
        hall_of_fame = audit_data.get("hall_of_fame", [])
        
        # 【第一部分】全局統計
        report = "🌍 **全局統計**\n"
        report += f"• 總曲目: {global_stats.get('total_tracks', 0)} 首\n"
        report += f"• 衍生次數: {global_stats.get('total_derivations', 0)} 次\n"
        report += f"• 平均衍生: {global_stats.get('avg_derivations', 0):.1f} 次/曲\n"
        report += f"• 資料庫大小: {global_stats.get('database_size_mb', 0):.1f} MB\n\n"
        
        # 【第二部分】頻道分布
        report += "🎧 **頻道分布**\n"
        for channel, stats in channels.items():
            ready = stats.get("ready_to_work_count", 0)
            service = stats.get("in_service_count", 0)
            report += f"• {channel.upper()}\n"
            report += f"  └─ 待命: {ready} | 服役: {service}\n"
        
        report += "\n"
        
        # 【第三部分】功勳英雄榜 (Top 3)
        if hall_of_fame:
            report += "🏆 **功勳英雄榜 (Top 3)**\n"
            for idx, track in enumerate(hall_of_fame[:3]):
                report += f"• #{idx+1}: {track.get('track_id', 'N/A')} ({track.get('derivation_count', 0)} 次)\n"
        
        return report
    
    except Exception as e:
        return f"❌ 報表生成失敗: {str(e)}"


def generate_inventory_warning(low_channels: Dict) -> str:
    """
    生成庫存預警訊息

    Args:
        low_channels: {channel_name: count, ...}

    Returns:
        str: Markdown 格式的預警訊息
    """
    
    report = "⚠️ **庫存預警**\n\n"
    report += "以下頻道庫存不足 20 首:\n\n"
    
    for channel, count in low_channels.items():
        report += f"• {channel.upper()}: {count} 首 🚨\n"
    
    report += f"\n*請立即補充庫存*"
    
    return report


# ============================================================================
# 單元測試
# ============================================================================

if __name__ == "__main__":
    # 測試環境驗證
    print("=" * 60)
    print("【Telegram Reporter Bot - 單元測試】")
    print("=" * 60)
    
    if not _validate_environment():
        print("\n❌ 環境配置缺失，請設定：")
        print("   export TELEGRAM_BOT_TOKEN=your_token")
        print("   export TELEGRAM_ALLOWED_USER_ID=your_id")
        sys.exit(1)
    
    # 測試 1: 發送簡單報告
    print("\n【測試 1】發送簡單報告...")
    result = send_telegram_report(
        message_title="系統心跳檢查",
        message_body="✅ Factory Heartbeat 正常運作\n• 時長: 65 分鐘\n• 品質: 正常",
        message_type="success_notification",
        emoji="💓"
    )
    print(f"結果: {result}")
    
    # 測試 2: 發送財務報表
    print("\n【測試 2】發送財務報表...")
    mock_audit_data = {
        "global_stats": {
            "total_tracks": 250,
            "total_derivations": 450,
            "avg_derivations": 1.8,
            "database_size_mb": 125.5
        },
        "channels": {
            "lofi": {"ready_to_work_count": 80, "in_service_count": 120},
            "light_music": {"ready_to_work_count": 30, "in_service_count": 20}
        },
        "hall_of_fame": [
            {"track_id": "track_001", "derivation_count": 12},
            {"track_id": "track_002", "derivation_count": 9},
            {"track_id": "track_003", "derivation_count": 7}
        ]
    }
    
    financial_report = generate_daily_financial_report(mock_audit_data)
    result = send_telegram_report(
        message_title="每日財務報表 - 2026-04-09",
        message_body=financial_report,
        message_type="daily_report",
        emoji="📊"
    )
    print(f"結果: {result}")
    
    print("\n✅ 單元測試完成")
