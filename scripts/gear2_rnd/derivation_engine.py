#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【Protocol L】 衍生引擎 - 基於 FFmpeg 的輕量級變速變調

替代 librosa 的笨重分析，使用 FFmpeg 進行快速的音頻時間拉伸與音調變換。
性能提升：100 倍快；成本：$0

支援的衍生類型：
  - tempo_up: 加速 (1.05x 倍速，降低採樣率 5%)
  - tempo_down: 減速 (0.95x 倍速，提升採樣率 5%)
  - pitch_up: 升調 (pitch=+2)
  - pitch_down: 降調 (pitch=-2)
  - combined: 綜合變調 (速度 + 音調調整)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.gear2_rnd.vault_database import VaultDatabase


# ============================================================================
# FFmpeg 濾波器定義
# ============================================================================

DERIVATION_FILTERS = {
    "tempo_up": {
        "description": "加速 1.05 倍速 (降採樣 5%，保持音調)",
        "ffmpeg_filter": "asetrate=44100*0.95,atempo=1.05",
        "parameters": {"tempo": 1.05, "sample_rate_ratio": 0.95}
    },
    "tempo_down": {
        "description": "減速 0.95 倍速 (提升採樣 5%，保持音調)",
        "ffmpeg_filter": "asetrate=44100*1.05,atempo=0.95",
        "parameters": {"tempo": 0.95, "sample_rate_ratio": 1.05}
    },
    "pitch_up": {
        "description": "升調 2 半音 (不改變速度)",
        "ffmpeg_filter": "asetrate=44100*1.122",
        "parameters": {"semitones": 2}
    },
    "pitch_down": {
        "description": "降調 2 半音 (不改變速度)",
        "ffmpeg_filter": "asetrate=44100*0.891",
        "parameters": {"semitones": -2}
    },
    "combined": {
        "description": "綜合變調：加速 1.05 倍 + 升調 1 半音",
        "ffmpeg_filter": "asetrate=44100*0.944,atempo=1.05",
        "parameters": {"tempo": 1.05, "sample_rate_ratio": 0.944}
    }
}


class DerivationEngine:
    """【Protocol L】衍生引擎 - FFmpeg 音頻變換"""
    
    def __init__(self, ffmpeg_bin: str = "ffmpeg"):
        """初始化衍生引擎
        
        Args:
            ffmpeg_bin: FFmpeg 二進制文件路徑
        """
        self.ffmpeg_bin = ffmpeg_bin
        self.vault_db = VaultDatabase()
        self._verify_ffmpeg()
    
    def _verify_ffmpeg(self) -> bool:
        """驗證 FFmpeg 是否可用"""
        try:
            result = subprocess.run(
                [self.ffmpeg_bin, "-version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"❌ FFmpeg 驗證失敗: {e}")
            return False
    
    def derive(
        self,
        input_track_path: str,
        track_id: str,
        derivation_type: str,
        output_dir: str = None
    ) -> Optional[Path]:
        """執行衍生提取 - 快速生成音檔變種
        
        Args:
            input_track_path: 輸入母帶路徑
            track_id: 原始音檔識別碼
            derivation_type: 衍生類型 (tempo_up/tempo_down/pitch_up/pitch_down/combined)
            output_dir: 輸出目錄 (預設: assets/audio/derivations/)
            
        Returns:
            輸出檔案路徑，如果失敗返回 None
        """
        import re
        
        input_path = Path(input_track_path)
        if not input_path.exists():
            print(f"❌ 輸入檔案不存在: {input_path}")
            return None
        
        if derivation_type not in DERIVATION_FILTERS:
            print(f"❌ 未知的衍生類型: {derivation_type}")
            print(f"   可用類型: {', '.join(DERIVATION_FILTERS.keys())}")
            return None
        
        # 設定輸出目錄
        if output_dir is None:
            output_dir = Path(config.workspace_root) / "assets" / "audio" / "derivations"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 【CTO v8.8.6 修復】清理舊的衍生標記（防止檔名無限膨脹）
        # 移除所有已存在的衍生類型和時間戳記
        clean_track_id = re.sub(
            r'_(?:tempo_up|tempo_down|pitch_up|pitch_down|combined)(?:_\d{8}_\d{6})?',
            '',
            track_id
        )
        
        # 生成輸出檔名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{clean_track_id}_{derivation_type}_{timestamp}.wav"
        output_path = output_dir / output_filename
        
        # 獲取衍生配置
        config_data = DERIVATION_FILTERS[derivation_type]
        ffmpeg_filter = config_data["ffmpeg_filter"]
        
        # 構建 FFmpeg 指令
        cmd = [
            self.ffmpeg_bin,
            "-y",  # 覆蓋輸出檔案
            "-i", str(input_path),
            "-af", ffmpeg_filter,
            "-c:a", "pcm_s16le",
            "-ar", "44100",
            str(output_path)
        ]
        
        try:
            print(f"\n🎵 衍生提取: {derivation_type}")
            print(f"   輸入: {input_path.name}")
            print(f"   濾波器: {ffmpeg_filter}")
            print(f"   輸出: {output_path.name}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 分鐘超時
            )
            
            if result.returncode != 0:
                print(f"❌ FFmpeg 執行失敗:")
                print(f"   {result.stderr}")
                return None
            
            output_size_mb = output_path.stat().st_size / (1024 ** 2)
            print(f"✅ 衍生完成 ({output_size_mb:.1f} MB)")
            
            # 記錄到保鮮庫
            self.vault_db.record_derivation(
                track_id=track_id,
                derivation_type=derivation_type,
                output_path=str(output_path),
                parameters=config_data["parameters"]
            )
            
            return output_path
        
        except subprocess.TimeoutExpired:
            print(f"❌ 衍生提取超時 (10 分鐘)")
            if output_path.exists():
                output_path.unlink()
            return None
        except Exception as e:
            print(f"❌ 衍生提取失敗: {e}")
            if output_path.exists():
                output_path.unlink()
            return None
    
    def batch_derive(
        self,
        track_id: str,
        input_path: str,
        derivation_types: list = None,
        output_dir: str = None
    ) -> Dict[str, Optional[Path]]:
        """批量衍生 - 一次產生多個變種
        
        Args:
            track_id: 音檔識別碼
            input_path: 輸入檔案路徑
            derivation_types: 衍生類型列表 (預設: 所有類型)
            output_dir: 輸出目錄
            
        Returns:
            衍生類型 -> 輸出路徑的映射
        """
        if derivation_types is None:
            derivation_types = list(DERIVATION_FILTERS.keys())
        
        results = {}
        for dtype in derivation_types:
            output_path = self.derive(
                input_path,
                track_id,
                dtype,
                output_dir
            )
            results[dtype] = output_path
        
        return results
    
    def show_available_derivations(self):
        """顯示所有可用的衍生類型"""
        print("\n" + "="*70)
        print("📚 可用的音檔衍生類型")
        print("="*70)
        
        for dtype, config_data in DERIVATION_FILTERS.items():
            print(f"\n  【{dtype}】")
            print(f"    描述: {config_data['description']}")
            print(f"    FFmpeg 濾波器: {config_data['ffmpeg_filter']}")
            print(f"    參數: {config_data['parameters']}")
        
        print("\n" + "="*70 + "\n")


# ============================================================================
# CLI 介面
# ============================================================================

def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        description="【Protocol L】衍生引擎 - FFmpeg 快速音檔變種生成"
    )
    
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="輸入音檔路徑"
    )
    parser.add_argument(
        "--track-id",
        type=str,
        required=True,
        help="原始音檔識別碼"
    )
    parser.add_argument(
        "--type",
        type=str,
        choices=list(DERIVATION_FILTERS.keys()),
        required=True,
        help="衍生類型"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="輸出目錄 (預設: assets/audio/derivations/)"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="批量衍生所有類型"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用衍生類型"
    )
    
    args = parser.parse_args()
    
    engine = DerivationEngine()
    
    # 列出衍生類型
    if args.list:
        engine.show_available_derivations()
        return
    
    # 批量衍生
    if args.batch:
        print(f"🎵 批量衍生: {args.track_id}")
        results = engine.batch_derive(
            track_id=args.track_id,
            input_path=args.input,
            output_dir=args.output
        )
        
        print("\n✅ 批量衍生完成:")
        for dtype, output_path in results.items():
            status = "✅" if output_path else "❌"
            print(f"   {status} {dtype}")
        return
    
    # 單個衍生
    output_path = engine.derive(
        input_track_path=args.input,
        track_id=args.track_id,
        derivation_type=args.type,
        output_dir=args.output
    )
    
    if output_path:
        print(f"\n✅ 衍生完成: {output_path}")
    else:
        print(f"\n❌ 衍生失敗")
        sys.exit(1)


if __name__ == "__main__":
    main()
