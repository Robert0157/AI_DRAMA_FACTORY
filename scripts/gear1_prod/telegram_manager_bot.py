#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【Telegram 遠端中控台 v2.0】CEO Machine Control Interface
與 v9.5 選曲引擎 + 產線產生器深度整合

功能：
  1. /status - 戰情報表 (庫存 0/1/2/>=3 分佈)
  2. /build - 遠端啟動產線 (SFX 選擇 → 模式選擇 → 背景執行)
  3. 非同步進度報告與成品通知

設計理念：
  - 完全異步 (避免阻塞 Event Loop)
  - 背景執行 pipeline_runner.py (subprocess.run)
  - 實時日誌監控與通知推送
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

# 嘗試導入 VaultDatabase
try:
    from scripts.gear2_rnd.vault_database import VaultDatabase
    VAULT_DB_AVAILABLE = True
except ImportError:
    VAULT_DB_AVAILABLE = False
    print("⚠️  Warning: VaultDatabase not available")

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
    "selected_sfx": None,
    "selected_sfx_mode": None,
    "selected_video": None,
    "last_output": None,
    "last_message_id": None
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
# /status 命令
# ============================================================================

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /status 指令 - 顯示戰情報表 (庫存 0/1/2/>=3 分佈)
    """
    user_id = update.effective_user.id
    
    if not _is_authorized(user_id):
        await update.message.reply_text("❌ 無授權的訪問")
        return
    
    if not VAULT_DB_AVAILABLE:
        await update.message.reply_text("❌ VaultDatabase 不可用，請檢查環境配置")
        return
    
    try:
        _log("查詢庫存戰情報表...", "INFO")

        vault = VaultDatabase()
        cursor = vault.conn.cursor()

        # ── 按頻道 × derivation_count 分層統計 ──────────────────────────
        cursor.execute("""
            SELECT channel, derivation_count, COUNT(*) AS cnt
            FROM audio_assets
            GROUP BY channel, derivation_count
            ORDER BY channel, derivation_count ASC
        """)
        rows = cursor.fetchall()

        # 整理成 {channel: {deriv_count: cnt}} 結構
        ch_data: dict = {}
        for row in rows:
            ch = row["channel"] or "unknown"
            d  = row["derivation_count"]
            c  = row["cnt"]
            ch_data.setdefault(ch, {})
            ch_data[ch][d] = c

        def _channel_block(ch: str, tiers: dict) -> str:
            t0   = tiers.get(0, 0)
            t1   = tiers.get(1, 0)
            t2   = tiers.get(2, 0)
            t3p  = sum(v for k, v in tiers.items() if k >= 3)
            active = t0 + t1 + t2
            total  = active + t3p

            def pct(n): return f"{n/active*100:4.0f}%" if active > 0 else "  -  "

            ch_label = {
                "lofi":        "🎵 Lofi",
                "light_music": "🌟 Light Music",
            }.get(ch, f"❓ {ch}")

            return (
                f"{ch_label}  ▸  活水 {active} 首 / 總計 {total} 首\n"
                f"  🆕 全新(0次)   {t0:3d} 首 {pct(t0)}\n"
                f"  ♻️ 一次使用    {t1:3d} 首 {pct(t1)}\n"
                f"  🔄 兩次使用    {t2:3d} 首 {pct(t2)}\n"
                f"  ⚠️ 歸檔(≥3次) {t3p:3d} 首\n"
            )

        channels = ["lofi", "light_music"]
        blocks = []
        grand_active = 0
        for ch in channels:
            tiers = ch_data.get(ch, {})
            blocks.append(_channel_block(ch, tiers))
            grand_active += sum(v for k, v in tiers.items() if k < 3)

        # 其他未知頻道（若有）
        for ch, tiers in ch_data.items():
            if ch not in channels:
                blocks.append(_channel_block(ch, tiers))
                grand_active += sum(v for k, v in tiers.items() if k < 3)

        divider = "─" * 28
        body = f"\n{divider}\n".join(blocks)

        status_text = (
            f"📊 <b>R&amp;S Echoes 金庫即時戰情報表</b>\n"
            f"{divider}\n"
            f"{body}"
            f"{divider}\n"
            f"🟢 全頻道活水合計：<b>{grand_active} 首</b>\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await update.message.reply_text(status_text, parse_mode="HTML")
        _log(f"戰情報表已發送: 全頻道活水={grand_active}", "INFO")

    except Exception as e:
        await update.message.reply_text(f"❌ 查詢失敗: {e}")
        _log(f"戰情報表查詢異常: {e}", "ERROR")


# ============================================================================
# /vault_cleanup 命令 - 檢查冷庫容量
# ============================================================================

async def vault_cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /vault_cleanup 指令 - 檢查冷庫容量，若達 90% 則提示 CEO 清理
    """
    user_id = update.effective_user.id
    
    if not _is_authorized(user_id):
        await update.message.reply_text("❌ 無授權的訪問")
        return
    
    if not VAULT_DB_AVAILABLE:
        await update.message.reply_text("❌ VaultDatabase 不可用")
        return
    
    try:
        _log("檢查冷庫容量...", "INFO")
        
        # 導入 cloud_archiver 以獲取容量檢查邏輯
        sys.path.insert(0, str(Path(__file__).parent))
        from cloud_archiver import check_vault_capacity_and_notify, MAX_VAULT_CAPACITY
        
        current, should_notify = check_vault_capacity_and_notify()
        
        status_text = f"""
🏦 **【冷庫容量檢查】**

📊 當前狀態:
  已封存軌道: {current}/{MAX_VAULT_CAPACITY} ({current/MAX_VAULT_CAPACITY*100:.1f}%)
  
閘門設定: 90% ({int(MAX_VAULT_CAPACITY*0.9)} 首)
"""
        
        if should_notify:
            keyboard = [
                [InlineKeyboardButton("✅ 批准清理", callback_data="vault_cleanup_approve")],
                [InlineKeyboardButton("⏭️ 稍後再清", callback_data="vault_cleanup_ignore")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            status_text += f"""
🚨 **容量已達 90% 預警！**

建議立即執行 FIFO 50% 清理，將回收空間至 50 首 ({MAX_VAULT_CAPACITY//2})

是否批准清理？
"""
            await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            status_text += "✅ 冷庫容量健康，無需清理"
            await update.message.reply_text(status_text, parse_mode="Markdown")
    
    except Exception as e:
        _log(f"冷庫檢查失敗: {e}", "ERROR")
        await update.message.reply_text(f"❌ 冷庫檢查失敗: {e}")


async def handle_vault_cleanup_approval(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    CEO 批准冷庫加權FIFO清理 + 生成審計報告
    """
    try:
        _log("執行加權FIFO冷庫清理...", "INFO")
        
        sys.path.insert(0, str(Path(__file__).parent))
        from cloud_archiver import trigger_fifo_cleanup, generate_purge_audit_report
        
        # 執行加權FIFO清理
        deleted_tracks, preserved_tracks, audit_data = trigger_fifo_cleanup()
        
        # 生成審計報告
        report_path = generate_purge_audit_report(audit_data)
        
        # 生成CEO摘要
        summary_text = f"""✅ **【加權FIFO冷庫清理完成】**

🧬 基因強度豁免機制已啟動
  • 已刪除: {len(deleted_tracks)} 首無效/衍生曲
  • 已保留: {len(preserved_tracks)} 首高價值母帶
  
📊 SSD空間回收
  • 釋放空間: {audit_data['space_freed_mb']:.1f}MB
  
📄 詳細報告
  • 審計報告已生成
  • 檔案: purge_report_{audit_data['timestamp']}.txt
"""
        
        await query.message.edit_text(summary_text, parse_mode="Markdown")
        
        # 若報告檔案存在，嘗試發送摘要
        if report_path and Path(report_path).exists():
            with open(report_path, 'r', encoding='utf-8') as f:
                report_content = f.read()
            
            # 發送報告摘要（前1000字）
            summary_snippet = report_content[:1000] + "\n...[略]"
            await query.message.reply_text(
                f"📄 **審計報告摘要**\n\n```\n{summary_snippet}\n```",
                parse_mode="Markdown"
            )
        
        _log(f"FIFO 清理完成，已刪除 {deleted} 首軌道", "INFO")
    
    except Exception as e:
        _log(f"FIFO 清理失敗: {e}", "ERROR")
        await query.message.reply_text(f"❌ FIFO 清理異常: {e}")


# ============================================================================
# /build 命令 - 多層選單流程
# ============================================================================

async def build_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /build 指令 - 遠端啟動產線流程
    Step 1: 呈現可用 SFX 列表
    """
    user_id = update.effective_user.id
    
    if not _is_authorized(user_id):
        await update.message.reply_text("❌ 無授權的訪問")
        return
    
    _log("/build 命令已啟動 - 進入 SFX 選擇流程", "INFO")
    
    # 掃描 SFX 目錄
    sfx_dir = Path(config.workspace_root) / "assets" / "sfx"
    sfx_files = sorted([f for f in sfx_dir.glob("*") if f.suffix.lower() in {'.wav', '.mp3'}]) if sfx_dir.exists() else []
    
    # 構建按鈕菜單
    keyboard = [
        [InlineKeyboardButton("🔇 無環境音", callback_data="build_sfx_None")]
    ]
    
    for sfx_file in sfx_files[:10]:  # 限制 10 個
        button_text = f"🎧 {sfx_file.name}"
        keyboard.append([
            InlineKeyboardButton(button_text, callback_data=f"build_sfx_{sfx_file.name}")
        ])
    
    keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="build_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    greeting = """
🎛️ **遠端產線啟動嚮導**

**Step 1: 請選擇環境音效 (SFX)**

💡 提示：「無環境音」將產生純漫步音樂；選擇環保音效將進行層疊混音。
    """
    
    await update.message.reply_text(greeting, reply_markup=reply_markup, parse_mode="Markdown")


# ============================================================================
# Callback 處理器 - /build 流程
# ============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    處理 Inline Button 點擊 (/build 流程 或 冷庫清理)
    """
    query = update.callback_query
    user_id = query.from_user.id
    
    if not _is_authorized(user_id):
        await query.answer("❌ 無授權的訪問", show_alert=True)
        return
    
    action = query.data
    
    # 確認按鈕點擊
    await query.answer()
    
    # 路由冷庫清理相關操作
    if action == "vault_cleanup_approve":
        await handle_vault_cleanup_approval(query, context)
        return
    elif action == "vault_cleanup_ignore":
        await query.message.edit_text("❌ 【金庫清理】已取消")
        return
    
    # 路由 /build 相關操作
    if action == "build_cancel":
        await query.message.edit_text("❌ 已取消產線啟動")
    elif action.startswith("build_sfx_"):
        await handle_build_sfx_selection(query, context, action)
    elif action.startswith("build_mode_"):
        await handle_build_mode_selection(query, context, action)
    elif action == "build_confirm_and_run":
        await handle_build_confirm_and_run(query, context)


async def handle_build_sfx_selection(query, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    """
    【Step 1 → Step 2】SFX 選擇 → 進入模式選擇
    """
    sfx_name = action.replace("build_sfx_", "")
    EXECUTION_STATE["selected_sfx"] = sfx_name if sfx_name != "None" else None
    
    _log(f"SFX 已選擇: {sfx_name}", "INFO")
    
    # 如果選擇了「無環境音」，直接進行 (略過模式選擇)
    if sfx_name == "None":
        EXECUTION_STATE["selected_sfx_mode"] = None
        # 直接進入確認
        await show_build_confirmation(query, context)
        return
    
    # 否則進入模式選擇
    keyboard = [
        [InlineKeyboardButton("🎭 換歌過場 (Transition)", callback_data="build_mode_transition")],
        [InlineKeyboardButton("🌍 全域背景 (Global)", callback_data="build_mode_global")],
        [InlineKeyboardButton("◀️ 返回", callback_data="build_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    mode_text = f"""
🎛️ **Step 2: 選擇 SFX 播放模式**

✅ 已選 SFX: `{sfx_name}`

**請選擇播放模式：**

🎭 **換歌過場 (Transition)**
   - 音效在歌曲交疊時淡入淡出
   - 效果：溫和的背景襯托

🌍 **全域背景 (Global)**
   - 音效以固定音量貫穿全曲
   - 效果：連貫的環保陪伴感
    """
    
    await query.message.edit_text(mode_text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_build_mode_selection(query, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    """
    【Step 2 → Step 3】模式選擇 → 確認並啟動產線
    """
    mode = action.replace("build_mode_", "")
    EXECUTION_STATE["selected_sfx_mode"] = mode
    
    _log(f"SFX 模式已選擇: {mode}", "INFO")
    
    # 進入確認頁面
    await show_build_confirmation(query, context)


async def show_build_confirmation(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【Step 3】顯示確認頁面並準備啟動
    """
    sfx_name = EXECUTION_STATE["selected_sfx"]
    sfx_mode = EXECUTION_STATE["selected_sfx_mode"]
    
    sfx_display = sfx_name if sfx_name else "（無環境音）"
    mode_display = "換歌過場" if sfx_mode == "transition" else ("全域背景" if sfx_mode == "global" else "（N/A）")
    
    keyboard = [
        [InlineKeyboardButton("✅ 確認並啟動", callback_data="build_confirm_and_run")],
        [InlineKeyboardButton("❌ 取消", callback_data="build_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    confirm_text = f"""
🎛️ **Step 3: 確認參數並啟動產線**

**您的配置：**
  🎧 SFX 音效: {sfx_display}
  📊 播放模式: {mode_display}

**產線將執行以下操作：**
  1. 啟動 v9.5 智能選曲引擎 (50/25/25 配額)
  2. 進行 FFmpeg acrossfade 縫合
  3. 應用 SFX 層疊混音 (依選擇)
  4. 輸出 44.1kHz/24-bit 標準母帶
  5. 將成品備好供 YouTube 發行

📝 預估耗時: 15-30 分鐘

確認無誤嗎？
    """
    
    await query.message.edit_text(confirm_text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_build_confirm_and_run(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【最終】啟動背景產線執行
    """
    global PIPELINE_RUNNING
    
    async with PIPELINE_LOCK:
        if PIPELINE_RUNNING:
            await query.message.reply_text("⏳ 產線正在運轉，請勿重複啟動！")
            return
        
        PIPELINE_RUNNING = True
        EXECUTION_STATE["status"] = "running"
        EXECUTION_STATE["current_task"] = "pipeline_startup"
        EXECUTION_STATE["last_message_id"] = query.message.message_id
    
    # 立即回複 CEO
    sfx_name = EXECUTION_STATE["selected_sfx"]
    sfx_mode = EXECUTION_STATE["selected_sfx_mode"]
    sfx_display = sfx_name if sfx_name else "無環境音"
    
    await query.message.reply_text(
        f"🚀 **收到指令，產線已啟動！**\n\n"
        f"🎧 SFX: {sfx_display}\n"
        f"📊 模式: {'換歌過場' if sfx_mode == 'transition' else '全域背景'}\n\n"
        f"正在為您縫合 1 小時大片...\n"
        f"⏳ 請耐心等待，完成後將發送通知"
    )
    
    _log(f"背景產線啟動: SFX={sfx_name}, Mode={sfx_mode}", "INFO")
    
    # 啟動背景工作執行產線
    asyncio.create_task(_run_pipeline_background(query, context))


async def _run_pipeline_background(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    【背景工作】執行 pipeline_runner.py with parameters
    
    在背景線程中執行 subprocess.run 以避免阻塞 Event Loop
    """
    try:
        sfx_name = EXECUTION_STATE["selected_sfx"]
        sfx_mode = EXECUTION_STATE["selected_sfx_mode"]
        
        # 構建 pipeline_runner.py 的參數
        cmd = [sys.executable, "scripts/gear1_prod/pipeline_runner.py"]
        
        # 如果選擇了 SFX，添加參數
        if sfx_name and sfx_name != "None":
            sfx_path = Path(config.workspace_root) / "assets" / "sfx" / sfx_name
            if sfx_path.exists():
                cmd.extend(["--sfx", str(sfx_path)])
                if sfx_mode:
                    cmd.extend(["--sfx-mode", sfx_mode])
        
        _log(f"執行命令: {' '.join(cmd)}", "INFO")
        
        # 在線程池中執行 subprocess，避免阻塞 Event Loop
        loop = asyncio.get_event_loop()
        
        # 執行產線
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=config.workspace_root
        )
        
        _log("產線進程已啟動，等待完成...", "INFO")
        
        # 等待完成（超時設為 1 小時）
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=3600)
            returncode = process.returncode
        except asyncio.TimeoutError:
            _log("產線執行超時（1 小時），強制終止", "ERROR")
            process.kill()
            await query.message.reply_text("❌ 產線執行超時（1 小時），已強制終止")
            return
        
        if returncode == 0:
            _log("產線完成成功！", "INFO")
            
            # 檢查輸出檔案
            output_dir = Path(config.workspace_root) / "assets" / "final_exports"
            if output_dir.exists():
                # 查找最新生成的 WAV 檔案
                wav_files = sorted(output_dir.glob("*.wav"), key=lambda f: f.stat().st_mtime, reverse=True)
                if wav_files:
                    latest_wav = wav_files[0]
                    size_mb = latest_wav.stat().st_size / (1024 ** 2)
                    
                    await query.message.reply_text(
                        f"✅ **報告 CEO，1 小時影片已產出完成！**\n\n"
                        f"📊 成品資訊：\n"
                        f"  📂 檔案: {latest_wav.name}\n"
                        f"  💾 大小: {size_mb:.1f} MB\n"
                        f"  ⏰ 生成時間: {datetime.fromtimestamp(latest_wav.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"🎉 YouTube CheatSheet 已備妥，隨時可發行！"
                    )
                    EXECUTION_STATE["last_output"] = str(latest_wav)
                else:
                    await query.message.reply_text(
                        "✅ 產線完成，但找不到輸出檔案。請檢查 assets/final_exports/ 目錄"
                    )
            else:
                await query.message.reply_text(
                    "✅ 產線完成，但輸出目錄不存在。請檢查配置"
                )
            
            EXECUTION_STATE["status"] = "completed"
        else:
            _log(f"產線執行失敗，返回碼: {returncode}", "ERROR")
            
            # 嘗試提取 stderr 中的錯誤訊息
            error_msg = stderr.decode("utf-8", errors="ignore")[-500:] if stderr else "未知錯誤"
            
            await query.message.reply_text(
                f"❌ 產線執行失敗\n\n"
                f"**錯誤訊息：**\n"
                f"```\n{error_msg}\n```"
            )
            
            EXECUTION_STATE["status"] = "failed"
    
    except Exception as e:
        _log(f"背景產線異常: {e}", "ERROR")
        await query.message.reply_text(f"❌ 產線執行異常: {e}")
        EXECUTION_STATE["status"] = "failed"
    
    finally:
        async with PIPELINE_LOCK:
            global PIPELINE_RUNNING
            PIPELINE_RUNNING = False
            EXECUTION_STATE["current_task"] = None
        _log("背景產線已完全終止", "INFO")


# ============================================================================
# Bot 主程序 (v15.4 Polling / Webhook 雙模式)
# ============================================================================

def _build_application() -> "Application":
    """建立並註冊 Handler 的 Application 實例（兩種模式共用）"""
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start",  lambda u, c: u.message.reply_text("👋 請使用 /status 或 /build")))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("build",  build_command))
    application.add_handler(CommandHandler("vault_cleanup", vault_cleanup_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    return application


def _get_webhook_secret() -> str:
    """取得 Webhook Secret Token：優先讀 .env，否則自動生成隨機值"""
    import secrets
    secret = config.telegram_webhook_secret
    if not secret:
        secret = secrets.token_hex(32)
        _log(f"⚠️  TELEGRAM_WEBHOOK_SECRET 未設定，本次使用隨機值: {secret[:8]}...", "WARN")
    return secret


def start_polling():
    """Polling 模式（開發機 / 無公網 IP 環境）"""
    _log("🔄 啟動模式：POLLING（長輪詢）", "INFO")
    application = _build_application()
    _log("✅ Bot 已連接，等待 CEO 指令（Polling）...", "INFO")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


def start_webhook(webhook_url: str, port: int):
    """
    Webhook 模式（生產伺服器 / ngrok 隧道）

    Telegram 允許的 Webhook 埠：443 / 80 / 88 / 8443
    webhook_url 必須是 HTTPS。

    運作流程：
      1. 本函式啟動 aiohttp Web Server 監聽 0.0.0.0:{port}
      2. 呼叫 Telegram setWebhook API，告訴 Telegram 把更新 POST 到 {webhook_url}/{token}
      3. 每次 CEO 傳訊息時，Telegram 主動推送 → 比 Polling 延遲更低、CPU 更省

    Args:
        webhook_url: 對外 HTTPS 根 URL，例如 https://abc123.ngrok-free.app
        port:        本機監聽埠，例如 8443
    """
    secret = _get_webhook_secret()
    full_webhook_url = f"{webhook_url.rstrip('/')}/{BOT_TOKEN}"

    _log(f"🌐 啟動模式：WEBHOOK", "INFO")
    _log(f"   監聽埠    : {port}", "INFO")
    _log(f"   Webhook URL: {full_webhook_url[:60]}...", "INFO")

    application = _build_application()

    _log("✅ Bot 已連接，等待 Telegram 推送（Webhook）...", "INFO")
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,            # 路徑即 Token，安全且無需額外路由
        webhook_url=full_webhook_url,
        secret_token=secret,           # Telegram 簽名驗證，防偽造請求
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


def main():
    """
    主入口：自動偵測模式
      - TELEGRAM_WEBHOOK_URL 已設定 → Webhook 模式
      - 否則                         → Polling 模式（安全降級）
    也可透過 --mode polling/webhook 覆蓋
    """
    import argparse
    parser = argparse.ArgumentParser(description="R&S Echoes Telegram Bot (v15.4)")
    parser.add_argument(
        "--mode",
        choices=["polling", "webhook", "auto"],
        default="auto",
        help="啟動模式：auto（自動依 .env 決定）/ polling / webhook（預設 auto）",
    )
    parser.add_argument(
        "--webhook-url",
        default="",
        help="覆蓋 .env 的 TELEGRAM_WEBHOOK_URL（webhook 模式專用）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="覆蓋 .env 的 TELEGRAM_WEBHOOK_PORT（webhook 模式專用）",
    )
    args = parser.parse_args()

    if not BOT_TOKEN:
        print("❌ 未設定 TELEGRAM_BOT_TOKEN")
        sys.exit(1)
    if not ALLOWED_USER_ID:
        print("⚠️  建議設定 TELEGRAM_ALLOWED_USER_ID 以限制訪問")

    _log("🤖 R&S Echoes Telegram Bot (v15.4) 啟動中...", "INFO")

    # 解析 webhook 參數
    webhook_url = args.webhook_url or config.telegram_webhook_url
    port = args.port or config.telegram_webhook_port

    # 決定模式
    mode = args.mode
    if mode == "auto":
        mode = "webhook" if webhook_url else "polling"

    if mode == "webhook":
        if not webhook_url:
            print("❌ Webhook 模式需要設定 TELEGRAM_WEBHOOK_URL（或傳入 --webhook-url）")
            print("   本地開發請先執行: ngrok http 8443")
            sys.exit(1)
        start_webhook(webhook_url, port)
    else:
        start_polling()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _log("Bot 已關閉", "INFO")
        sys.exit(0)
    except Exception as e:
        _log(f"Bot 啟動失敗: {e}", "ERROR")
        sys.exit(1)
