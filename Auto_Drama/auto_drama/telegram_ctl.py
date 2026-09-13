# -*- coding: utf-8 -*-
"""
Telegram remote control (Human-in-the-Loop) for Auto_Drama.

Commands (HTML parse_mode is mandatory — never MarkdownV2):
  /start        — 顯示可用指令
  /status       — 最近任務狀態
  /runmock      — 以 mock 模式跑一次樣本章節 demo

Design notes:
- Non-blocking review flow uses asyncio so other shots keep generating.
- This controller is a thin HITL layer; the full Telegram review loop for
  shots/episodes lives in the original system (scripts/gear1_prod) which we
  intentionally do NOT modify.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_telegram():
    try:
        from telegram import Update  # noqa: F401
        from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "python-telegram-bot is not installed. "
            "Run: pip install -r requirements.txt"
        ) from exc
    return Update, ApplicationBuilder, CommandHandler, ContextTypes


def start_telegram(token: str = "") -> int:
    """Blocking entry: starts the Telegram bot polling loop (Ctrl+C to stop)."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("[AUTO-DRAMA] telegram: 需要 --token 或環境變數 TELEGRAM_BOT_TOKEN", file=__import__("sys").stderr)
        return 1

    Update, ApplicationBuilder, CommandHandler, ContextTypes = _require_telegram()

    async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "<b>Auto_Drama 遠端控制</b>\n"
            "/status — 任務狀態\n/runmock — 跑 mock demo",
            parse_mode="HTML",
        )

    async def _status(update: Update, context: ContextTypes.DEFAULT_TYPE):
        from .config import load_settings
        from .paths import Paths
        from .state import JobStore

        settings = load_settings(_PROJECT_ROOT)
        paths = Paths(settings)
        store = JobStore(paths.job_db_path())
        lines = ["<b>最近任務</b>"]
        for job in store.list_jobs(limit=5):
            lines.append(
                f"• {job['job_id']} <code>{job['series']}</code> → {job['status']}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _runmock(update: Update, context: ContextTypes.DEFAULT_TYPE):
        from .config import load_settings
        from .orchestrator import run_book_pipeline

        sample = _PROJECT_ROOT / "sample_inputs" / "yuewei_sample.txt"
        summary = run_book_pipeline(
            source_text=sample.read_text(encoding="utf-8"),
            book_title="閱微草堂筆記（Mock 樣本）",
            series="yuewei",
            mode="mock",
            settings=load_settings(_PROJECT_ROOT),
        )
        await update.message.reply_text(
            f"<b>Mock demo 完成</b>\njob_id: <code>{summary['job_id']}</code>\n"
            f"status: {summary['status']}\n輸出: <code>{summary['episode_dir']}</code>",
            parse_mode="HTML",
        )

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("status", _status))
    app.add_handler(CommandHandler("runmock", _runmock))

    print("[AUTO-DRAMA] Telegram bot polling started. Ctrl+C to stop.")
    app.run_polling()
    return 0
