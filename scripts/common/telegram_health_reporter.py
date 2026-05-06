#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common/telegram_health_reporter.py
v15.10 跨平台健康回報器 — Telegram Bot 即時告警。

功能：
- 音樂庫 / 視覺庫存量定時檢查
- 直播連線狀態監控
- 臨界故障預警（≤5 分鐘延遲）
- 非同步架構不卡主流程
"""

import asyncio
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ============================================================================
# 【v15.11 P2#11】臨界值輔助函式 — 讀取 freshness_policy.json 的 inventory_thresholds
# ============================================================================
def _get_inventory_thresholds(channel: str) -> dict:
    """
    回傳指定頻道的庫存告警臨界值。

    讀取順序（高 → 低優先）：
      1. config.freshness_policy.inventory_thresholds.channels[channel]
      2. config.freshness_policy.inventory_thresholds（全域）
      3. 硬回退預設值

    Returns:
        {
            "audio_critical": int,   # 音樂庫存危急臨界值（預設 3）
            "audio_low":      int,   # 音樂庫存偏低臨界值（預設 5）
            "visual_critical": int,  # 視覺庫存危急臨界值（預設 2）
            "ratio_stale":    float, # 新歌佔比「STALE」臨界值（預設 0.3）
            "ratio_warn":     float, # 新歌佔比告警臨界值（預設 0.2）
        }
    """
    defaults = {
        "audio_critical": 3,
        "audio_low": 5,
        "visual_critical": 2,
        "ratio_stale": 0.3,
        "ratio_warn": 0.2,
    }
    try:
        from scripts.common.env_manager import config as _cfg
        policy = getattr(_cfg, "freshness_policy", {}) or {}
        inv = policy.get("inventory_thresholds", {}) or {}
        ch_inv = (inv.get("channels") or {}).get(channel, {})
        merged = dict(defaults)
        merged.update({k: v for k, v in inv.items() if k in defaults})
        merged.update({k: v for k, v in ch_inv.items() if k in defaults})
        return merged
    except Exception:
        return defaults


# ============================================================================
# 健康狀態資料模型
# ============================================================================


@dataclass
class ChannelHealth:
    """單一頻道健康狀態"""
    channel: str
    audio_available: int = 0
    audio_total: int = 0
    visual_available: int = 0
    visual_total: int = 0
    new_tracks_ratio: float = 0.0           # dc=0 佔比
    last_export_age_hours: float = -1.0     # 最後成品距今時數
    streaming_active: bool = False
    streaming_uptime_hours: float = 0.0
    error_count: int = 0
    warnings: List[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """綜合健康狀態（v15.11 P2#11：臨界值從 config 讀取，含硬回退）"""
        thr = _get_inventory_thresholds(self.channel)
        if self.error_count > 0:
            return "🔴 CRITICAL"
        if self.audio_available < thr["audio_critical"] or self.visual_available < thr["visual_critical"]:
            return "🟡 WARNING"
        if self.audio_available < thr["audio_low"]:
            return "🟠 LOW"
        if self.new_tracks_ratio < thr["ratio_stale"]:
            return "🟠 STALE"
        return "🟢 HEALTHY"

    @property
    def alerts(self) -> List[str]:
        """需要推送的告警訊息（v15.11 P2#11：臨界值從 config 讀取，含硬回退）"""
        thr = _get_inventory_thresholds(self.channel)
        alerts = []
        if self.audio_available < thr["audio_critical"]:
            alerts.append(f"🚨 音樂庫存危急：{self.audio_available} 首可用（{self.channel}）")
        elif self.audio_available < thr["audio_low"]:
            alerts.append(f"⚠️ 音樂庫存偏低：{self.audio_available} 首可用（{self.channel}）")
        if self.visual_available < thr["visual_critical"]:
            alerts.append(f"🚨 視覺庫存危急：{self.visual_available} 個可用（{self.channel}）")
        if self.new_tracks_ratio < thr["ratio_warn"]:
            alerts.append(f"📉 新歌佔比過低：{self.new_tracks_ratio:.0%}（{self.channel}）")
        if self.streaming_active and self.last_export_age_hours > 24:
            alerts.append(f"⏰ 最後成品超過 24hr（{self.channel}）")
        return alerts


@dataclass
class HealthReport:
    """全域健康報告"""
    timestamp: float = field(default_factory=time.time)
    channels: Dict[str, ChannelHealth] = field(default_factory=dict)
    system_errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """純文字摘要（Telegram 用）"""
        lines = [f"📊 <b>R&S Echoes 健康報告</b>"]
        lines.append(f"⏱ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        for ch_name, ch in self.channels.items():
            lines.append(f"<b>[{ch_name.upper()}]</b> {ch.status}")
            lines.append(f"  🎵 音樂：{ch.audio_available}/{ch.audio_total} | 新歌佔比：{ch.new_tracks_ratio:.0%}")
            lines.append(f"  🎬 視覺：{ch.visual_available}/{ch.visual_total}")
            if ch.streaming_active:
                lines.append(f"  📡 直播中：{ch.streaming_uptime_hours:.1f}h")
            if ch.warnings:
                for w in ch.warnings[:3]:
                    lines.append(f"  ⚠️ {w}")
            lines.append("")

        if self.system_errors:
            lines.append("<b>❌ 系統錯誤：</b>")
            for err in self.system_errors[:5]:
                lines.append(f"  • {err}")

        return "\n".join(lines)


# ============================================================================
# 健康檢查器
# ============================================================================


class HealthChecker:
    """
    執行健康檢查，收集所有頻道的庫存與狀態。
    設計為同步方法（可由非同步排程呼叫）。
    """

    def __init__(self):
        self.workspace_root = _PROJECT_ROOT

    def check_channel(self, channel: str) -> ChannelHealth:
        """檢查單一頻道健康狀態"""
        health = ChannelHealth(channel=channel)

        try:
            # --- 音樂庫檢查（v15.11 P2#8：改用 VaultDatabase threading.local 連線） ---
            from scripts.gear2_rnd.vault_database import VaultDatabase
            music_db_path = self.workspace_root / "assets" / "data" / "rs_music_vault.db"
            if music_db_path.exists():
                vdb = VaultDatabase(music_db_path)
                cursor = vdb.conn.cursor()

                cursor.execute(
                    "SELECT COUNT(*) FROM audio_assets WHERE channel = ?",
                    (channel,)
                )
                health.audio_total = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM audio_assets WHERE channel = ? AND derivation_count = 0",
                    (channel,)
                )
                new_count = cursor.fetchone()[0]
                health.new_tracks_ratio = new_count / max(health.audio_total, 1)

                # 可用曲目（derivation_count < 3）
                cursor.execute(
                    "SELECT COUNT(*) FROM audio_assets WHERE channel = ? AND derivation_count < 3 AND is_archived = 0",
                    (channel,)
                )
                health.audio_available = cursor.fetchone()[0]
                # threading.local 連線無需 close()

            # --- 視覺庫檢查（v15.11 P2#8：改用 VaultDatabase threading.local 連線） ---
            from scripts.gear2_rnd.vault_database import VaultDatabase as _VDB
            visual_db_path = self.workspace_root / "assets" / "data" / "veo_visual_vault.db"
            if visual_db_path.exists():
                vvdb = _VDB(visual_db_path)
                cursor = vvdb.conn.cursor()

                cursor.execute(
                    "SELECT COUNT(*) FROM video_assets WHERE channel = ?",
                    (channel,)
                )
                health.visual_total = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM video_assets WHERE channel = ? AND derivation_count < 2",
                    (channel,)
                )
                health.visual_available = cursor.fetchone()[0]
                # threading.local 連線無需 close()

            # --- 最後成品時間 ---
            final_dir = self.workspace_root / "assets" / "final_exports" / channel
            if final_dir.exists():
                mp4_files = list(final_dir.glob("*.mp4"))
                if mp4_files:
                    latest = max(f.stat().st_mtime for f in mp4_files)
                    health.last_export_age_hours = (time.time() - latest) / 3600

        except Exception as e:
            health.warnings.append(f"檢查異常：{type(e).__name__}: {str(e)[:100]}")

        return health

    def check_all(self, channels: List[str] = None) -> HealthReport:
        """檢查所有頻道"""
        if channels is None:
            channels = ["lofi", "light_music"]

        report = HealthReport()

        for ch in channels:
            try:
                report.channels[ch] = self.check_channel(ch)
            except Exception as e:
                report.system_errors.append(f"{ch}: {type(e).__name__}: {str(e)[:200]}")

        return report


# ============================================================================
# Telegram 推送器
# ============================================================================


class TelegramHealthPusher:
    """
    將健康報告推送到 Telegram。
    支援同步與非同步模式。
    """

    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")

    async def push_async(self, report: HealthReport) -> bool:
        """非同步推送到 Telegram"""
        if not self.bot_token or not self.chat_id:
            print("⚠️ [HealthReporter] Telegram 未設定（缺 TELEGRAM_BOT_TOKEN 或 TELEGRAM_ADMIN_CHAT_ID）")
            return False

        try:
            import aiohttp

            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": report.summary(),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        return True
                    print(f"⚠️ [HealthReporter] Telegram 推送失敗: HTTP {resp.status}")
                    return False
        except ImportError:
            # aiohttp 不可用時降級為同步 requests
            return self._push_sync(report)
        except Exception as e:
            print(f"❌ [HealthReporter] Telegram 推送異常: {e}")
            return False

    def _push_sync(self, report: HealthReport) -> bool:
        """同步推送（aiohttp 不可用時的降級方案）"""
        try:
            import urllib.request
            import urllib.parse

            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": self.chat_id,
                "text": report.summary(),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }).encode("utf-8")

            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"❌ [HealthReporter] 同步推送失敗: {e}")
            return False

    def push_alerts(self, report: HealthReport) -> List[str]:
        """擷取所有頻道的告警訊息列表"""
        alerts = []
        for ch in report.channels.values():
            alerts.extend(ch.alerts)
        return alerts


# ============================================================================
# 定時排程
# ============================================================================


class HealthReportScheduler:
    """
    健康檢查排程器。
    每 N 分鐘執行一次檢查並推送（若有必要）。
    """

    def __init__(self, interval_minutes: int = 15, channels: List[str] = None):
        self.interval = interval_minutes * 60
        self.channels = channels or ["lofi", "light_music"]
        self.checker = HealthChecker()
        self.pusher = TelegramHealthPusher()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """啟動排程（非同步背景執行）"""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        print(f"📡 [HealthReporter] 排程已啟動 (每 {self.interval // 60} 分鐘)")

    async def stop(self):
        """停止排程"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("📡 [HealthReporter] 排程已停止")

    async def _run_loop(self):
        """排程主迴圈"""
        while self._running:
            try:
                report = self.checker.check_all(self.channels)
                alerts = self.pusher.push_alerts(report)

                if alerts or time.time() - report.timestamp > 3600:
                    # 有告警 或 超過 1 小時無報告 → 推送
                    success = await self.pusher.push_async(report)
                    if success and alerts:
                        print(f"🚨 [HealthReporter] 已推送 {len(alerts)} 條告警")
                    elif success:
                        print(f"📊 [HealthReporter] 定時報告已推送")

            except Exception as e:
                print(f"❌ [HealthReporter] 檢查迴圈異常: {e}")

            await asyncio.sleep(self.interval)

    async def check_now(self) -> HealthReport:
        """手動觸發一次檢查並推送"""
        report = self.checker.check_all(self.channels)
        await self.pusher.push_async(report)
        return report


# ============================================================================
# CLI 入口（用於獨立測試）
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="R&S Echoes 健康回報器")
    parser.add_argument("--channels", nargs="+", default=["lofi", "light_music"],
                        help="要檢查的頻道")
    parser.add_argument("--interval", type=int, default=15,
                        help="檢查間隔（分鐘）")
    parser.add_argument("--once", action="store_true",
                        help="只執行一次檢查後退出")
    args = parser.parse_args()

    async def main():
        if args.once:
            checker = HealthChecker()
            pusher = TelegramHealthPusher()
            report = checker.check_all(args.channels)
            print(report.summary())
            await pusher.push_async(report)
        else:
            scheduler = HealthReportScheduler(
                interval_minutes=args.interval,
                channels=args.channels,
            )
            await scheduler.start()
            # 保持執行直到 Ctrl+C
            try:
                while True:
                    await asyncio.sleep(60)
            except KeyboardInterrupt:
                await scheduler.stop()

    asyncio.run(main())
