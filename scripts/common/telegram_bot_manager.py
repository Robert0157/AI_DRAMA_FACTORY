#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【Telegram 遠端遙控儀表板】CEO Bot Manager
與 Protocol L 資產保鮮庫深度整合的雲端控制中心

功能：
  1. 遠端啟動 / 監控產線
  2. 即時查詢金庫庫存
  3. 動態選擇視覺 + 聽覺素材
  4. 自動發送成品 (YouTube CheatSheet + 影片)
  
安全機制：
  - 身份驗證 (TELEGRAM_ALLOWED_USER_ID)
  - Mutex Lock (防重複觸發)
  - 非同步執行 (async/await)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

# 嘗試導入 Protocol L 模塊
try:
    from scripts.gear2_rnd.vault_database import VaultDatabase
    PROTOCOL_L_AVAILABLE = True
except ImportError:
    PROTOCOL_L_AVAILABLE = False

# ============================================================================
# 全域設定
# ============================================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", 0)) if os.getenv("TELEGRAM_ALLOWED_USER_ID") else None

# 產線 Mutex Lock
PIPELINE_LOCK = asyncio.Lock()
PIPELINE_RUNNING = False

# 動態狀態追蹤
EXECUTION_STATE = {
    "current_task": None,
    "status": "idle",  # idle, running, completed, failed
    "selected_video": None,
    "selected_sfx": None,
    "last_output": None
}

# ============================================================================
# 日誌與錯誤處理
# ============================================================================

def _log(msg: str, level: str = "INFO"):
    """統一日誌輸出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[TELEGRAM_BOT][{timestamp}][{level}] {msg}")


def _is_authorized(user_id: int) -> bool:
    """驗證用戶身份"""
    if not ALLOWED_USER_ID:
        _log(f"警告：未設定 TELEGRAM_ALLOWED_USER_ID，無法驗證用戶 {user_id}", "WARN")
        return False
    return user_id == ALLOWED_USER_ID


# ============================================================================
# 指令處理器
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start 指令 - 顯示主菜單
    """
    user_id = update.effective_user.id
    
    if not _is_authorized(user_id):
        await update.message.reply_text(
            f"❌ 無授權的訪問。您的 ID: {user_id}\n"
            f"僅允許 TELEGRAM_ALLOWED_USER_ID 帳號操作。"
        )
        return
    
    await show_main_menu(update, context)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /menu 指令 - 顯示主菜單
    """
    user_id = update.effective_user.id
    
    if not _is_authorized(user_id):
        await update.message.reply_text("❌ 無授權的訪問")
        return
    
    await show_main_menu(update, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /status 指令 - 顯示系統狀態
    """
    user_id = update.effective_user.id
    
    if not _is_authorized(user_id):
        await update.message.reply_text("❌ 無授權的訪問")
        return
    
    status_text = f"""
📊 **系統狀態報告**

🔄 產線狀態: {EXECUTION_STATE['status'].upper()}
📝 當前任務: {EXECUTION_STATE['current_task'] or '無'}
🎬 選定視頻: {EXECUTION_STATE['selected_video'] or '無'}
🎧 選定音效: {EXECUTION_STATE['selected_sfx'] or '無'}

⏰ 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    await update.message.reply_text(status_text, parse_mode="Markdown")


# ============================================================================
# 菜單生成
# ============================================================================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    顯示主菜單 (Inline Keyboard)
    """
    global PIPELINE_RUNNING
    
    # 判斷產線是否正在運行
    button_start_text = "🚀 啟動全自動產線"
    if PIPELINE_RUNNING:
        button_start_text = "⏳ 產線運轉中..."
    
    keyboard = [
        [
            InlineKeyboardButton(button_start_text, callback_data="action_start_pipeline")
        ],
        [
            InlineKeyboardButton("🧠 獲取明日靈感", callback_data="action_get_prompts")
        ],
        [
            InlineKeyboardButton("🎬 自訂視覺發行", callback_data="action_custom_visual")
        ],
        [
            InlineKeyboardButton("💰 查詢音樂金庫", callback_data="action_query_vault")
        ],
        [
            InlineKeyboardButton("🧹 靶場重置", callback_data="action_reset_targets")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    greeting = f"""
🎛️ **CEO 遠端遙控儀表板 (v1.0)**

歡迎，{update.effective_user.first_name}！

選擇以下操作：
    """
    
    if update.message:
        await update.message.reply_text(greeting, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text(greeting, reply_markup=reply_markup, parse_mode="Markdown")


# ============================================================================
# Callback 處理器
# ============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    處理 Inline Button 點擊
    """
    query = update.callback_query
    user_id = query.from_user.id
    
    if not _is_authorized(user_id):
        await query.answer("❌ 無授權的訪問", show_alert=True)
        return
    
    action = query.data
    
    # 確認按鈕點擊
    await query.answer()
    
    if action == "action_start_pipeline":
        await handle_start_pipeline(query, context)
    elif action == "action_get_prompts":
        await handle_get_prompts(query, context)
    elif action == "action_custom_visual":
        await handle_custom_visual(query, context)
    elif action == "action_query_vault":
        await handle_query_vault(query, context)
    elif action == "action_reset_targets":
        await handle_reset_targets(query, context)
    elif action.startswith("select_video_"):
        await handle_video_selection(query, context, action)
    elif action.startswith("select_sfx_"):
        await handle_sfx_selection(query, context, action)
    elif action == "confirm_custom_run":
        await handle_confirm_custom_run(query, context)
    elif action == "back_to_menu":
        await show_main_menu(query.message.edit_text, context)


async def handle_start_pipeline(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【操作】啟動全自動產線 (CTO 修正：立即返回，背景運行)
    
    CTO 指令：嚴禁阻塞 Event Loop。使用 asyncio.create_task() 讓產線獨立運行。
    CEO 應立刻收到："✅ 產線已在背景啟動"，然後可用 /status 查詢進度。
    """
    global PIPELINE_RUNNING
    
    async with PIPELINE_LOCK:
        if PIPELINE_RUNNING:
            await query.message.reply_text("⏳ 產線正在運轉，請勿重複啟動！")
            return
        
        PIPELINE_RUNNING = True
        EXECUTION_STATE["status"] = "running"
        EXECUTION_STATE["current_task"] = "pipeline_startup"
    
    # ✨ 【CTO 關鍵修正】立即回覆 CEO
    await query.message.reply_text(
        "🚀 **產線已在背景啟動！**\n\n"
        "🔄 正在進行過場混音處理...\n"
        "📊 可用 /status 查詢進度"
    )
    
    # 【CTO 關鍵修正】使用 asyncio.create_task() 在背景運行
    # 這樣不會阻塞 Event Loop，CEO 能立刻收到回應！
    asyncio.create_task(_run_pipeline_background(query, context))


async def _run_pipeline_background(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【背景工作】在背景執行產線，完成時發送通知
    
    這是 asyncio.create_task() 的目標函數，不會阻塞 Bot 的 Event Loop。
    """
    try:
        _log("🔄 背景產線啟動中...", "INFO")
        
        # 非同步執行 pipeline_runner.py
        result = await run_pipeline_async(context)
        
        # 產線完成後發送通知
        if result:
            await query.message.reply_text(
                "✅ **產線完工！**\n\n"
                "🎵 新的 1 小時混音已生成\n"
                "📁 已保存到: assets/final_exports/"
            )
            EXECUTION_STATE["status"] = "completed"
            
            # 嘗試發送成品文件
            await send_finished_artifacts(query.message, context)
        else:
            await query.message.reply_text("❌ 產線執行失敗，請檢查日誌")
            EXECUTION_STATE["status"] = "failed"
    
    except Exception as e:
        await query.message.reply_text(f"❌ 異常: {e}")
        EXECUTION_STATE["status"] = "failed"
        _log(f"背景產線執行異常: {e}", "ERROR")
    
    finally:
        async with PIPELINE_LOCK:
            global PIPELINE_RUNNING
            PIPELINE_RUNNING = False
            EXECUTION_STATE["current_task"] = None
        _log("🛑 背景產線已完全終止", "INFO")



async def handle_get_prompts(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【操作】呼叫 GLM 生成明日靈感
    """
    try:
        await query.message.reply_text("🧠 正在喚醒靈感兵工廠，請稍候...")
        
        result = await run_script_async(
            "scripts/gear1_prod/generate_ceo_prompts.py",
            ["--batch-size", "5"],
            context
        )
        
        if result:
            await query.message.reply_text(
                "✅ 5 組靈感配方已生成！\n"
                "📁 位置: assets/.ceo_prompts/daily_prompts_*.txt"
            )
        else:
            await query.message.reply_text("❌ 靈感生成失敗")
    
    except Exception as e:
        await query.message.reply_text(f"❌ 異常: {e}")


async def handle_custom_visual(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【操作】進入自訂視覺發行 (素材選擇)
    """
    # 掃描視頻
    video_dir = Path(config.workspace_root) / "assets" / "video_clips"
    video_files = sorted([f for f in video_dir.glob("*.mp4") if f.is_file()]) if video_dir.exists() else []
    
    if not video_files:
        await query.message.reply_text(
            "❌ 找不到任何背景影片！\n"
            "📂 請先將短片 (.mp4) 放入：\n"
            f"   {video_dir}"
        )
        return
    
    # 生成視頻選擇按鈕
    keyboard = []
    for video_file in video_files[:10]:  # 限制 10 個
        size_mb = video_file.stat().st_size / (1024 ** 2)
        button_text = f"🎬 {video_file.name} ({size_mb:.1f}MB)"
        keyboard.append([
            InlineKeyboardButton(button_text, callback_data=f"select_video_{video_file.name}")
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ 返回菜單", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "🎬 **請選擇背景影片**\n\n",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def handle_video_selection(query, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    """
    【回調】視頻選擇
    """
    video_name = action.replace("select_video_", "")
    EXECUTION_STATE["selected_video"] = video_name
    
    # 進入 SFX 選擇
    sfx_dir = Path(config.workspace_root) / "assets" / "sfx"
    sfx_files = sorted([f for f in sfx_dir.glob("*") if f.suffix.lower() in {'.wav', '.mp3'}]) if sfx_dir.exists() else []
    
    keyboard = [
        [InlineKeyboardButton("🔇 無環境音", callback_data="select_sfx_None")]
    ]
    
    for sfx_file in sfx_files[:10]:  # 限制 10 個
        size_mb = sfx_file.stat().st_size / (1024 ** 2)
        button_text = f"🎧 {sfx_file.name} ({size_mb:.1f}MB)"
        keyboard.append([
            InlineKeyboardButton(button_text, callback_data=f"select_sfx_{sfx_file.name}")
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ 返回菜單", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"🎧 **已選視頻：** {video_name}\n\n"
        f"**請選擇環境音效：**\n\n",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def handle_sfx_selection(query, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    """
    【回調】SFX 選擇 - 確認並執行
    """
    sfx_name = action.replace("select_sfx_", "")
    EXECUTION_STATE["selected_sfx"] = sfx_name if sfx_name != "None" else None
    
    # 確認菜單
    keyboard = [
        [InlineKeyboardButton("✅ 確認並啟動", callback_data="confirm_custom_run")],
        [InlineKeyboardButton("🔄 重新選擇", callback_data="action_custom_visual")],
        [InlineKeyboardButton("◀️ 返回菜單", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    sfx_display = sfx_name if sfx_name != "None" else "（無環境音）"
    
    await query.message.edit_text(
        f"🎬 **視頻：** {EXECUTION_STATE['selected_video']}\n"
        f"🎧 **音效：** {sfx_display}\n\n"
        f"**確認上述選擇嗎？**\n",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def handle_confirm_custom_run(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【操作】確認並執行自訂視覺發行 (CTO 修正：立即返回，背景運行)
    """
    global PIPELINE_RUNNING
    
    async with PIPELINE_LOCK:
        if PIPELINE_RUNNING:
            await query.message.reply_text("⏳ 產線正在運轉，請勿重複啟動！")
            return
        
        PIPELINE_RUNNING = True
        EXECUTION_STATE["status"] = "running"
    
    video_name = EXECUTION_STATE["selected_video"]
    sfx_name = EXECUTION_STATE["selected_sfx"]
    
    # ✨ 【CTO 關鍵修正】立即回覆
    await query.message.reply_text(
        f"🚀 **自訂視覺發行已在背景啟動！**\n\n"
        f"🎬 視頻：{video_name}\n"
        f"🎧 音效：{sfx_name or '（無）'}\n\n"
        f"📊 可用 /status 查詢進度"
    )
    
    # 【CTO 關鍵修正】背景執行
    asyncio.create_task(_run_custom_visual_background(query, context, video_name, sfx_name))


async def _run_custom_visual_background(query, context: ContextTypes.DEFAULT_TYPE, video_name: str, sfx_name: str) -> None:
    """
    【背景工作】在背景執行自訂視覺發行
    """
    try:
        _log(f"🔄 自訂視覺發行背景啟動：{video_name}", "INFO")
        
        # 組合指令
        video_path = f"assets/video_clips/{video_name}"
        cmd = [sys.executable, "scripts/gear1_prod/pipeline_runner.py", "--bg-video", video_path]
        
        if sfx_name and sfx_name != "None":
            sfx_path = f"assets/sfx/{sfx_name}"
            cmd.extend(["--sfx", sfx_path])
        
        result = await run_command_async(cmd, context)
        
        # 產線完成後發送通知
        if result:
            await query.message.reply_text(
                f"✅ **自訂視覺發行完工！**\n\n"
                f"🎬 視頻：{video_name}\n"
                f"🎧 音效：{sfx_name or '（無）'}\n"
                f"📁 已保存到: assets/final_exports/"
            )
            await send_finished_artifacts(query.message, context)
        else:
            await query.message.reply_text("❌ 自訂視覺發行失敗，請檢查日誌")
    
    except Exception as e:
        await query.message.reply_text(f"❌ 異常: {e}")
        _log(f"自訂視覺發行異常: {e}", "ERROR")
    
    finally:
        async with PIPELINE_LOCK:
            global PIPELINE_RUNNING
            PIPELINE_RUNNING = False
            EXECUTION_STATE["current_task"] = None
        _log("🛑 自訂視覺發行已完全終止", "INFO")


async def handle_query_vault(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【操作】查詢 Protocol L 音樂金庫
    """
    if not PROTOCOL_L_AVAILABLE:
        await query.message.reply_text("❌ Protocol L 模塊不可用")
        return
    
    try:
        vault = VaultDatabase()
        stats = vault.get_statistics()
        
        vault_text = f"""
📊 **音樂資產保鮮庫統計**

✅ 總音檔數：{stats['total_tracks']}
📈 總衍生次數：{stats['total_derivations']}
📊 平均衍生次數：{stats['avg_derivations']}
💾 庫大小：{stats['database_size_mb']} MB

🔝 **最常使用的音檔：**
        """
        
        popular = vault.get_most_used_tracks(limit=5)
        for idx, track in enumerate(popular, 1):
            vault_text += f"\n{idx}. {track['track_id']} (衍生 {track['derivation_count']} 次)"
        
        await query.message.edit_text(vault_text, parse_mode="Markdown")
    
    except Exception as e:
        await query.message.reply_text(f"❌ 查詢失敗: {e}")


async def handle_reset_targets(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【操作】靶場重置 - 確認
    """
    keyboard = [
        [InlineKeyboardButton("⚠️ 確認清空", callback_data="confirm_reset")],
        [InlineKeyboardButton("❌ 取消", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "⚠️ **警告：這將清空所有庫存與產出！**\n\n"
        "確認嗎？",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


# ============================================================================
# 非同步執行引擎
# ============================================================================

async def run_pipeline_async(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    非同步執行 pipeline_runner.py
    """
    try:
        cmd = [sys.executable, "scripts/gear1_prod/pipeline_runner.py"]
        result = await run_command_async(cmd, context)
        return result
    except Exception as e:
        _log(f"Pipeline 執行失敗: {e}", "ERROR")
        return False


async def run_script_async(script_path: str, args: List[str], context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    非同步執行任意 Python 腳本
    """
    try:
        cmd = [sys.executable, script_path] + args
        result = await run_command_async(cmd, context)
        return result
    except Exception as e:
        _log(f"腳本執行失敗: {e}", "ERROR")
        return False


async def run_command_async(cmd: List[str], context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    非同步執行外部指令
    使用 asyncio 避免阻塞 Bot 事件循環
    """
    try:
        # 在執行緒池中運行 subprocess
        loop = asyncio.get_event_loop()
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=3600)  # 1 小時超時
        
        return process.returncode == 0
    
    except asyncio.TimeoutError:
        _log(f"指令超時: {' '.join(cmd)}", "ERROR")
        return False
    except Exception as e:
        _log(f"指令執行異常: {e}", "ERROR")
        return False


async def send_finished_artifacts(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【資產交付】發送生成的成品檔案給 CEO
    
    - youtube_sheet_*.txt
    - *.mp4 影片（如果大小允許）
    """
    try:
        final_exports = Path(config.workspace_root) / "assets" / "final_exports"
        
        if not final_exports.exists():
            return
        
        # 發送 YouTube 上架文案（含頻道子目錄）
        cheatsheet_candidates = set(final_exports.rglob("youtube_sheet_*.txt"))
        cheatsheet_files = sorted(cheatsheet_candidates, key=lambda p: p.stat().st_mtime)
        if cheatsheet_files:
            cheatsheet_file = cheatsheet_files[-1]  # 最新的
            await message.reply_document(
                document=open(cheatsheet_file, "rb"),
                caption="📋 YouTube CheatSheet (發行參考)"
            )
        
        # 發送 MP4 影片（限制 50MB）
        mp4_files = list(final_exports.glob("*.mp4"))
        for mp4_file in mp4_files[-1:]:  # 只發送最新的
            file_size_mb = mp4_file.stat().st_size / (1024 ** 2)
            if file_size_mb > 50:
                await message.reply_text(
                    f"ℹ️ 影片檔案過大 ({file_size_mb:.1f}MB)，無法透過 Telegram 發送\n"
                    f"📁 請手動下載: {mp4_file.name}"
                )
            else:
                await message.reply_video(
                    video=open(mp4_file, "rb"),
                    caption=f"🎬 {mp4_file.name}"
                )
    
    except Exception as e:
        _log(f"資產交付發送失敗: {e}", "ERROR")


# ============================================================================
# Bot 啟動與主循環
# ============================================================================

async def main():
    """
    啟動 Telegram Bot
    """
    if not BOT_TOKEN:
        print("❌ 未設定 TELEGRAM_BOT_TOKEN")
        sys.exit(1)
    
    _log("🤖 Telegram Bot Manager 啟動中...", "INFO")
    
    # 創建 Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # 註冊指令處理器
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # 註冊 Callback 處理器
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # 啟動 Bot - 直接調用非 async 版本
    _log("✅ Bot 已連接，等待 CEO 指令...", "INFO")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


def main_sync():
    """
    同步包裝，用於啟動腳本
    """
    if not BOT_TOKEN:
        print("❌ 未設定 TELEGRAM_BOT_TOKEN")
        sys.exit(1)
    
    _log("🤖 Telegram Bot Manager 啟動中...", "INFO")
    
    # 創建 Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # 註冊指令處理器
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # 註冊 Callback 處理器
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # 啟動 Bot - 直接調用非 async 版本
    _log("✅ Bot 已連接，等待 CEO 指令...", "INFO")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log("Bot 已關閉", "INFO")
        sys.exit(0)
    except Exception as e:
        _log(f"Bot 啟動失敗: {e}", "ERROR")
        sys.exit(1)
