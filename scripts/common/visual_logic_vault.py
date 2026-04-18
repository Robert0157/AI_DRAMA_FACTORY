#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【v11.0 視覺邏輯金庫 - Config-Driven 版本】
從 configs/channels/*.json 動態加載視覺配置。
支援多頻道，零耦合。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = _PROJECT_ROOT / "configs" / "channels"


def _load_channel_config(channel: str) -> Optional[Dict[str, Any]]:
    """從 JSON 動態加載頻道配置。"""
    config_file = CONFIG_DIR / f"{channel.lower()}.json"
    if not config_file.exists():
        return None

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# 輔助函式
# ════════════════════════════════════════════════════════════════


def get_visual_config(channel: str = "lofi") -> Dict[str, Any]:
    """
    取得指定頻道的視覺配置。
    優先從 JSON 加載，若失敗則返回預設值。
    """
    channel_lower = channel.lower()
    config = _load_channel_config(channel_lower)

    if config:
        return config

    # 【回滾友善】若 JSON 遺失，返回基礎預設值
    if channel_lower == "light_music":
        return {
            "channel_name": "Light_Music",
            "type": "landscape_only",
            "image_prompt_template": "Beautiful landscape. {scene}. Professional quality.",
            "video_prompt_template": "Beautiful landscape video. {scene}. Static camera.",
            "negative_prompt": "人, 人物, 臉, face, people, human, person",
            "no_people_suffix": ", no people, no humans, landscape only, 4k scenic view, static camera",
            "time_dilation_enabled": True,
        }
    else:  # lofi (default)
        return {
            "channel_name": "Lofi_Chill",
            "type": "with_people",
            "image_prompt_template": "Lofi illustration. {mood}. Warm lighting.",
            "video_prompt_template": "Lofi animation. {mood}. Subtle motion.",
            "negative_prompt": "",
            "time_dilation_enabled": True,
        }


def get_available_channels() -> List[str]:
    """列出所有可用的視覺頻道。"""
    channels = []
    if CONFIG_DIR.exists():
        for config_file in CONFIG_DIR.glob("*.json"):
            channels.append(config_file.stem)
    return channels if channels else ["lofi", "light_music"]


def validate_channel(channel: str) -> bool:
    """驗證頻道名稱是否有效。"""
    available = get_available_channels()
    return channel.lower() in [c.lower() for c in available]


def inject_negative_prompt_into_image_prompt(
    image_prompt: str, channel: str = "light_music"
) -> str:
    """
    【邏輯鎖死】light_music 頻道時，強制在 Image Prompt 末尾串接負面提示詞。
    """
    if channel.lower() != "light_music":
        return image_prompt

    config = get_visual_config("light_music")
    negative = config.get("negative_prompt", "")

    if not negative:
        return image_prompt

    return f"{image_prompt}\n\nNegative: {negative}"


def append_no_people_suffix(prompt: str, channel: str = "light_music") -> str:
    """
    【Task 3 邏輯】light_music 時，自動在末尾追加無人物後綴。
    """
    if channel.lower() != "light_music":
        return prompt

    config = get_visual_config("light_music")
    suffix = config.get("no_people_suffix", "")

    if not suffix:
        return prompt

    return f"{prompt}{suffix}"
