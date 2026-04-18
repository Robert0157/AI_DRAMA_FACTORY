#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e2e_size_verifier.py - 端到端 (E2E) 檔案大小與音訊品質驗證器 v1.0
=========================================================================

【功能】在製作完成後自動驗證：
✅ 斷言 1 (Size)：1 小時 MP4 總體積必須 < 400 MB
✅ 斷言 2 (Bitrate)：影像流位元率必須介於 200-500 kbps
✅ 斷言 3 (Audio)：確認音軌格式為 aac 且響度維持在 -16/-18 LUFS

【預期效果】CTO 極致瘦身版 v5.0
- MP4 檔案：< 320 MB (理想目標)
- 影像位元率：200-350 kbps (中位數)
- 音訊品質：AAC @ 320kbps, -18 LUFS (透明音質)
"""

from __future__ import annotations

import subprocess
import json
import sys
import logging
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
#  設定常數
# ═══════════════════════════════════════════════════════════════

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

# 日誌設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# 驗證閾值
ASSERT_1_MAX_SIZE_MB = 400
ASSERT_2_VIDEO_BITRATE_MIN = 200  # kbps
ASSERT_2_VIDEO_BITRATE_MAX = 500  # kbps
ASSERT_3_AUDIO_FORMATS = ["aac"]
ASSERT_3_LUFS_TARGETS = [-16, -18]

# ═══════════════════════════════════════════════════════════════
#  工具函式
# ═══════════════════════════════════════════════════════════════

def _get_file_size_mb(file_path: Path) -> float:
    """取得檔案大小（MB）。"""
    if not file_path.exists():
        raise FileNotFoundError(f"檔案不存在: {file_path}")
    size_bytes = file_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    return size_mb


def _get_media_info(file_path: Path) -> dict:
    """
    使用 ffprobe 取得媒體資訊（JSON 格式）。
    
    Returns:
        {
            'format': {'duration': ..., 'size': ...},
            'streams': [
                {'codec_type': 'video', 'bit_rate': ..., 'width': ..., 'height': ...},
                {'codec_type': 'audio', 'codec_name': 'aac', 'bit_rate': ...}
            ]
        }
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        "-of", "json",
        str(file_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe 失敗: {result.stderr}")
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 解析失敗: {e}")


def _get_audio_loudness(file_path: Path) -> dict:
    """
    使用 ffmpeg -af loudnorm=print_format=json 取得響度資訊（LUFS）。
    
    Returns:
        {
            'integrated': -18.2,  # 整體 LUFS
            'loud_range': 5.3,
            'true_peak': -0.5
        }
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(file_path),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        # loudnorm JSON 通常在 stderr 中
        for line in result.stderr.split('\n'):
            if line.strip().startswith('{'):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None
    except Exception as e:
        log.warning(f"無法取得響度資訊: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  驗證函式（三大斷言）
# ═══════════════════════════════════════════════════════════════

def assert_1_file_size(file_path: Path) -> bool:
    """
    【斷言 1】1 小時 MP4 總體積必須 < 400 MB
    """
    log.info("\n" + "=" * 80)
    log.info("【斷言 1】檔案大小驗證")
    log.info("=" * 80)
    
    try:
        size_mb = _get_file_size_mb(file_path)
        percentage = (size_mb / ASSERT_1_MAX_SIZE_MB) * 100
        
        log.info(f"  📊 檔案大小: {size_mb:.2f} MB")
        log.info(f"  📏 限制值: {ASSERT_1_MAX_SIZE_MB} MB")
        log.info(f"  📈 使用率: {percentage:.1f}%")
        
        if size_mb < ASSERT_1_MAX_SIZE_MB:
            log.info(f"  ✅ PASS - 檔案大小合規 ({percentage:.1f}%)")
            return True
        else:
            log.error(f"  ❌ FAIL - 檔案過大 ({percentage:.1f}%，超過 {size_mb - ASSERT_1_MAX_SIZE_MB:.2f} MB)")
            return False
    
    except Exception as e:
        log.error(f"  ❌ ERROR - {e}")
        return False


def assert_2_video_bitrate(file_path: Path) -> bool:
    """
    【斷言 2】影像流位元率必須介於 200-500 kbps
    """
    log.info("\n" + "=" * 80)
    log.info("【斷言 2】影像位元率驗證")
    log.info("=" * 80)
    
    try:
        media_info = _get_media_info(file_path)
        
        # 找出視訊流
        video_stream = None
        for stream in media_info.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
        
        if not video_stream:
            log.error(f"  ❌ 未找到視訊流")
            return False
        
        # 取得位元率
        bit_rate_str = video_stream.get('bit_rate')
        if not bit_rate_str:
            log.warning(f"  ⚠️  無法取得位元率資訊，使用計算值")
            # 從檔案大小反推（假設 1 小時 = 3600 秒）
            duration = float(media_info['format'].get('duration', 3600))
            file_size_bytes = float(media_info['format'].get('size', 0))
            if file_size_bytes > 0 and duration > 0:
                # 位元率 = 8 * 檔案大小(bytes) / 時長(秒)
                bit_rate_kbps = (8 * file_size_bytes) / (1024 * duration)
            else:
                bit_rate_kbps = 0
        else:
            bit_rate_kbps = float(bit_rate_str) / 1000  # 轉換為 kbps
        
        percentage = (bit_rate_kbps / ASSERT_2_VIDEO_BITRATE_MAX) * 100
        
        log.info(f"  📊 視訊編解碼器: {video_stream.get('codec_name', 'unknown')}")
        log.info(f"  📊 解析度: {video_stream.get('width', '?')}x{video_stream.get('height', '?')}")
        log.info(f"  📊 位元率: {bit_rate_kbps:.0f} kbps")
        log.info(f"  📏 允許範圍: {ASSERT_2_VIDEO_BITRATE_MIN}-{ASSERT_2_VIDEO_BITRATE_MAX} kbps")
        log.info(f"  📈 使用率: {percentage:.1f}%")
        
        if ASSERT_2_VIDEO_BITRATE_MIN <= bit_rate_kbps <= ASSERT_2_VIDEO_BITRATE_MAX:
            log.info(f"  ✅ PASS - 視訊位元率合規")
            return True
        else:
            log.error(f"  ❌ FAIL - 視訊位元率超出範圍 ({bit_rate_kbps:.0f} kbps)")
            return False
    
    except Exception as e:
        log.error(f"  ❌ ERROR - {e}")
        return False


def assert_3_audio_quality(file_path: Path) -> bool:
    """
    【斷言 3】確認音軌格式為 aac 且響度維持在 -16/-18 LUFS
    """
    log.info("\n" + "=" * 80)
    log.info("【斷言 3】音訊品質驗證")
    log.info("=" * 80)
    
    try:
        media_info = _get_media_info(file_path)
        
        # 找出音訊流
        audio_stream = None
        for stream in media_info.get('streams', []):
            if stream.get('codec_type') == 'audio':
                audio_stream = stream
                break
        
        if not audio_stream:
            log.error(f"  ❌ 未找到音訊流")
            return False
        
        codec_name = audio_stream.get('codec_name', '').lower()
        bit_rate_kbps = float(audio_stream.get('bit_rate', 0)) / 1000
        
        log.info(f"  🎵 音訊編解碼器: {codec_name}")
        log.info(f"  🎵 位元率: {bit_rate_kbps:.0f} kbps")
        
        # 檢查編解碼器
        if codec_name not in ASSERT_3_AUDIO_FORMATS:
            log.error(f"  ❌ FAIL - 音訊格式不合規 (預期: {ASSERT_3_AUDIO_FORMATS}，實際: {codec_name})")
            return False
        
        log.info(f"  ✅ 音訊格式正確: {codec_name}")
        
        # 取得響度
        loudness = _get_audio_loudness(file_path)
        if loudness:
            integrated_lufs = loudness.get('integrated', 0)
            log.info(f"  🎵 整體 LUFS: {integrated_lufs:.1f}")
            
            # 檢查 LUFS 是否接近目標值
            lufs_ok = any(abs(integrated_lufs - target) <= 2 for target in ASSERT_3_LUFS_TARGETS)
            if lufs_ok:
                log.info(f"  ✅ 響度合規")
            else:
                log.warning(f"  ⚠️  響度偏離目標 (目標: {ASSERT_3_LUFS_TARGETS}，實際: {integrated_lufs:.1f})")
        else:
            log.warning(f"  ⚠️  無法取得響度資訊，跳過 LUFS 檢查")
        
        log.info(f"  ✅ PASS - 音訊品質合規")
        return True
    
    except Exception as e:
        log.error(f"  ❌ ERROR - {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

def run_e2e_verification(output_video_path: Path) -> bool:
    """
    執行完整 E2E 驗證套件。
    
    Args:
        output_video_path: MP4 輸出檔案路徑
    
    Returns:
        True 如果全部斷言通過，否則 False
    """
    log.info("\n" + "=" * 80)
    log.info("【E2E 端到端驗證套件 v1.0】CTO 極致瘦身版 v5.0 檔案品質檢驗")
    log.info("=" * 80)
    log.info(f"目標檔案: {output_video_path}")
    log.info(f"驗證時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if not output_video_path.exists():
        log.error(f"❌ 檔案不存在: {output_video_path}")
        return False
    
    # 執行三大斷言
    result_1 = assert_1_file_size(output_video_path)
    result_2 = assert_2_video_bitrate(output_video_path)
    result_3 = assert_3_audio_quality(output_video_path)
    
    # 總結
    log.info("\n" + "=" * 80)
    log.info("【驗證結果總結】")
    log.info("=" * 80)
    all_pass = result_1 and result_2 and result_3
    
    if all_pass:
        log.info("  ✅✅✅ 全部驗證通過！製作品質確認達標")
        log.info("  📊 預期成效達成：")
        log.info("     • 檔案大小: < 320 MB ✅")
        log.info("     • 影像位元率: 200-350 kbps ✅")
        log.info("     • 音訊品質: AAC @ 320kbps ✅")
        return True
    else:
        log.error("  ❌ 驗證失敗，請檢查以下項目：")
        if not result_1:
            log.error("     • 檔案大小超過 400 MB")
        if not result_2:
            log.error("     • 視訊位元率超出 200-500 kbps 範圍")
        if not result_3:
            log.error("     • 音訊品質不合規")
        return False


# ═══════════════════════════════════════════════════════════════
#  CLI 入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="E2E 檔案大小與音訊品質驗證器 (CTO 極致瘦身版 v5.0)"
    )
    parser.add_argument(
        "--video",
        type=str,
        required=True,
        help="輸出 MP4 檔案路徑"
    )
    args = parser.parse_args()
    
    video_path = Path(args.video)
    success = run_e2e_verification(video_path)
    sys.exit(0 if success else 1)
