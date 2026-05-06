#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common/pipeline_state_machine.py
v15.10 產線狀態機 — 統一管理 Phase 轉移 + 雙庫預檢

功能：
- PipelineState 列舉：明確的產線階段定義
- PipelineContext：跨 Phase 共享狀態（庫存、新鮮度、錯誤）
- preflight_dual_vault()：Phase 1 雙庫同步預檢
- 狀態轉移日誌：每個轉移自動記錄
"""

from __future__ import annotations

import sys
import json
import time
import sqlite3
from pathlib import Path
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


# ============================================================================
# PipelineState — 產線階段列舉
# ============================================================================

class PipelineState(Enum):
    """產線狀態機 — 明確的階段定義"""

    INIT = auto()                   # 初始化
    PREFLIGHT_VAULT = auto()        # 雙庫預檢（音樂 + 視覺）
    FRESHNESS_GATE = auto()         # 新鮮度閘門檢查
    INVENTORY_CHECK = auto()        # 庫存盤點
    MASTERING = auto()              # 母帶處理 (Phase 2)
    METADATA = auto()               # LLM 中繼資料 (Phase 3)
    TTAPI_BACKFILL = auto()         # TTAPI 補彈
    ASSEMBLER = auto()              # 無縫混音 (Phase 4)
    VISUAL_COMPOSE = auto()         # 視覺合成 (Phase 5)
    PUBLISH = auto()                # 發布（CheatSheet 生成）
    COMPLETED = auto()              # 完成
    FAILED = auto()                 # 失敗（可從此狀態恢復）


# 狀態轉移表（定義在 Enum 外部以避免 Enum 成員衝突）
_PIPELINE_TRANSITIONS = {
    PipelineState.INIT:                [PipelineState.PREFLIGHT_VAULT],
    PipelineState.PREFLIGHT_VAULT:     [PipelineState.FRESHNESS_GATE, PipelineState.FAILED],
    PipelineState.FRESHNESS_GATE:      [PipelineState.INVENTORY_CHECK, PipelineState.TTAPI_BACKFILL, PipelineState.FAILED],
    PipelineState.INVENTORY_CHECK:     [PipelineState.MASTERING, PipelineState.TTAPI_BACKFILL, PipelineState.FAILED],
    PipelineState.MASTERING:           [PipelineState.METADATA, PipelineState.FAILED],
    PipelineState.METADATA:            [PipelineState.ASSEMBLER, PipelineState.FAILED],
    PipelineState.TTAPI_BACKFILL:      [PipelineState.INVENTORY_CHECK, PipelineState.FAILED],
    PipelineState.ASSEMBLER:           [PipelineState.VISUAL_COMPOSE, PipelineState.FAILED],
    PipelineState.VISUAL_COMPOSE:      [PipelineState.PUBLISH, PipelineState.FAILED],
    PipelineState.PUBLISH:             [PipelineState.COMPLETED, PipelineState.FAILED],
    PipelineState.COMPLETED:           [],
    PipelineState.FAILED:              [PipelineState.PREFLIGHT_VAULT, PipelineState.INVENTORY_CHECK],
}

# v15.10 P3-#1: 在 Enum 類別上掛載別名，供 hasattr(PipelineState, ...) 測試通過
PipelineState._TRANSITIONS = _PIPELINE_TRANSITIONS  # type: ignore[attr-defined]


def can_transition(from_state: PipelineState, to_state: PipelineState) -> bool:
    """檢查狀態轉移是否合法"""
    allowed = _PIPELINE_TRANSITIONS.get(from_state, [])
    return to_state in allowed


def transitions_from(from_state: PipelineState) -> List[PipelineState]:
    """取得允許的下一個狀態列表"""
    return _PIPELINE_TRANSITIONS.get(from_state, [])

# v15.10 P3-#1: can_transition 也掛載到類別上
PipelineState.can_transition = staticmethod(can_transition)  # type: ignore[attr-defined]

# ============================================================================
# PipelineContext — 跨 Phase 共享狀態
# ============================================================================

@dataclass
class VaultPreflightReport:
    """雙庫預檢報告"""
    channel: str
    audio_total: int = 0
    audio_available: int = 0        # dc < 3
    visual_total: int = 0
    visual_available: int = 0       # dc < 2
    new_track_count: int = 0        # dc = 0
    new_track_ratio: float = 0.0
    passed: bool = False
    bottleneck: str = ""            # "audio" | "visual" | "none"
    recommendations: List[str] = field(default_factory=list)
    checked_at: str = ""


@dataclass
class PipelineContext:
    """產線執行上下文 — 跨 Phase 共享"""
    channel: str = "lofi"
    state: PipelineState = PipelineState.INIT
    started_at: float = field(default_factory=time.time)

    # 庫存狀態
    vault_preflight: Optional[VaultPreflightReport] = None
    freshness_passed: bool = False
    inventory_count: int = 0

    # 錯誤追蹤
    errors: List[Dict[str, Any]] = field(default_factory=list)
    state_history: List[Dict[str, Any]] = field(default_factory=list)

    # 重試
    max_retries: int = 3
    retry_count: int = 0

    def transition_to(self, new_state: PipelineState) -> bool:
        """執行狀態轉移（含合法性檢查與日誌）"""
        if not can_transition(self.state, new_state):
            self._log_error(
                f"非法狀態轉移: {self.state.name} → {new_state.name}",
                fatal=False,
            )
            return False

        old_state = self.state
        self.state = new_state
        self.state_history.append({
            "from": old_state.name,
            "to": new_state.name,
            "timestamp": datetime.now().isoformat(),
            "elapsed_s": time.time() - self.started_at,
        })

        print(f"  🔄 [StateMachine] {old_state.name} → {new_state.name} "
              f"(+{self.state_history[-1]['elapsed_s']:.0f}s)")
        return True

    def mark_failed(self, error: Exception, fatal: bool = True) -> None:
        """標記失敗並記錄錯誤"""
        self.errors.append({
            "state": self.state.name,
            "error": type(error).__name__,
            "message": str(error)[:500],
            "fatal": fatal,
            "timestamp": datetime.now().isoformat(),
        })

        if fatal:
            self.transition_to(PipelineState.FAILED)

    def _log_error(self, message: str, fatal: bool = False) -> None:
        print(f"  {'❌' if fatal else '⚠️'} [StateMachine] {message}")

    def can_retry(self) -> bool:
        """檢查是否可重試"""
        return self.retry_count < self.max_retries

    def summary(self) -> str:
        """產生狀態摘要"""
        elapsed = time.time() - self.started_at
        lines = [
            f"📊 Pipeline 狀態摘要 [{self.channel}]",
            f"  狀態: {self.state.name}",
            f"  耗時: {elapsed:.0f}s",
            f"  轉移次數: {len(self.state_history)}",
            f"  錯誤數: {len(self.errors)}",
            f"  重試: {self.retry_count}/{self.max_retries}",
        ]
        if self.vault_preflight:
            v = self.vault_preflight
            lines.append(f"  庫存: 🎵{v.audio_available}/{v.audio_total} 🎬{v.visual_available}/{v.visual_total}")
            lines.append(f"  新鮮度: {v.new_track_ratio:.0%} ({'✅' if v.passed else '❌'})")
        return "\n".join(lines)


# ============================================================================
# preflight_dual_vault() — 雙庫同步預檢
# ============================================================================

def preflight_dual_vault(channel: str) -> VaultPreflightReport:
    """
    【v15.10 P2-#6】Phase 1 雙庫同步預檢。
    
    在產線一開始就同時檢查音樂庫與視覺庫，
    避免消耗前置 Phase 的計算資源後才發現資源不足。
    
    Args:
        channel: 頻道名稱
    
    Returns:
        VaultPreflightReport: 包含雙庫存狀態與建議
    """
    report = VaultPreflightReport(
        channel=channel,
        checked_at=datetime.now().isoformat(),
    )

    try:
        # --- 音樂庫檢查 ---
        music_db = config.music_db_path
        if music_db.exists():
            conn = sqlite3.connect(str(music_db))
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE channel = ?", (channel,))
            report.audio_total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM audio_assets WHERE channel = ? AND derivation_count < 3 AND is_archived = 0",
                (channel,)
            )
            report.audio_available = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM audio_assets WHERE channel = ? AND derivation_count = 0",
                (channel,)
            )
            report.new_track_count = cursor.fetchone()[0]
            report.new_track_ratio = report.new_track_count / max(report.audio_total, 1)

            conn.close()

        # --- 視覺庫檢查 ---
        visual_db = config.visual_db_path
        if visual_db.exists():
            conn = sqlite3.connect(str(visual_db))
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM video_assets WHERE channel = ?", (channel,))
            report.visual_total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM video_assets WHERE channel = ? AND derivation_count < 2",
                (channel,)
            )
            report.visual_available = cursor.fetchone()[0]

            conn.close()

        # --- 判斷瓶頸 ---
        AUDIO_MIN = 10
        VISUAL_MIN = 3

        audio_ok = report.audio_available >= AUDIO_MIN
        visual_ok = report.visual_available >= VISUAL_MIN

        if not audio_ok and not visual_ok:
            report.bottleneck = "both"
            report.recommendations.append(f"音樂庫存不足 ({report.audio_available}/{AUDIO_MIN})，建議啟動 TTAPI 補彈")
            report.recommendations.append(f"視覺庫存不足 ({report.visual_available}/{VISUAL_MIN})，建議上傳新影片素材")
        elif not audio_ok:
            report.bottleneck = "audio"
            report.recommendations.append(f"音樂庫存不足 ({report.audio_available}/{AUDIO_MIN})，建議啟動 TTAPI 補彈或上傳新曲")
        elif not visual_ok:
            report.bottleneck = "visual"
            report.recommendations.append(f"視覺庫存不足 ({report.visual_available}/{VISUAL_MIN})，建議上傳新影片素材")
        else:
            report.bottleneck = "none"

        report.passed = audio_ok and visual_ok

    except Exception as e:
        report.recommendations.append(f"預檢異常: {type(e).__name__}: {str(e)[:200]}")
        report.passed = False
        report.bottleneck = "error"

    # 輸出預檢報告
    icon = "✅" if report.passed else "❌"
    print(f"\n  {icon} [Preflight] {channel.upper()} 雙庫預檢:")
    print(f"     🎵 音樂: {report.audio_available}/{report.audio_total} (可用/總計) | 新歌: {report.new_track_ratio:.0%}")
    print(f"     🎬 視覺: {report.visual_available}/{report.visual_total} (可用/總計)")
    print(f"     🔍 瓶頸: {report.bottleneck}")
    for rec in report.recommendations:
        print(f"     💡 {rec}")

    return report


# ============================================================================
# CLI 入口
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="R&S Echoes 產線狀態機")
    parser.add_argument("--channel", default="lofi", help="頻道名稱")
    parser.add_argument("--preflight", action="store_true", help="執行雙庫預檢")
    args = parser.parse_args()

    if args.preflight:
        report = preflight_dual_vault(args.channel)
        if not report.passed:
            print(f"\n❌ 預檢未通過 — 瓶頸: {report.bottleneck}")
            sys.exit(1)
        else:
            print(f"\n✅ 預檢通過 — 可啟動產線")
