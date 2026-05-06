#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common/freshness_counter.py
v15.11 新鮮度配額共用工具 — FreshnessCounter

解決問題：
  VaultSelection.run()（lofi_assembler）與 _check_freshness_quota()（pipeline_runner）
  各自重複讀取 config.freshness_policy 並計算 min_new_ratio，兩處邏輯若不同步
  會導致閘門判定不一致。

  v15.11 起，所有新鮮度配置讀取統一透過本模組，確保單一真實來源 (Single Source of Truth)。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def get_channel_freshness_config(channel: str) -> dict:
    """
    讀取並回傳指定頻道的新鮮度配置（單一真實來源）。

    Returns:
        {
            "enabled":      bool,        # 新鮮度鐵律是否啟用
            "enforcement":  "strict"|"warn",
            "min_new_ratio": float,      # dc=0 最低佔比（0.0~1.0）
        }

    優先順序（高 → 低）：
      1. config.freshness_policy.channels[channel].min_new_ratio
      2. config.freshness_policy.min_new_ratio（全域預設）
      3. 硬回退 0.5
    """
    try:
        policy = getattr(config, "freshness_policy", {}) or {}
        enabled = bool(policy.get("enabled", True))
        enforcement = str(policy.get("enforcement", "strict")).lower()
        ch_cfg = (policy.get("channels") or {}).get(channel, {})
        # 頻道專屬 > 全域 > 硬回退
        if "min_new_ratio" in ch_cfg:
            min_ratio = float(ch_cfg["min_new_ratio"])
        elif "min_new_ratio" in policy:
            min_ratio = float(policy["min_new_ratio"])
        else:
            min_ratio = 0.5
    except Exception:
        enabled = True
        enforcement = "strict"
        min_ratio = 0.5

    return {
        "enabled": enabled,
        "enforcement": enforcement,
        "min_new_ratio": min_ratio,
    }


def calc_quota_new(target_tracks: int, channel: str) -> int:
    """
    計算指定頻道在 target_tracks 選曲目標下需要的 dc=0 新歌配額。

    Returns:
        int  — ceil(target_tracks × min_new_ratio)
    """
    cfg = get_channel_freshness_config(channel)
    return math.ceil(target_tracks * cfg["min_new_ratio"])
