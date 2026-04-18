#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【SFX 系統編排器】- 環境音效整體管理

整合 sfx_curator.py (下載) + sfx_inventory_setup.py (映射) + 4% 音量壓制邏輯
提供統一的 SFX 生命週期管理介面

功能：
  1. 自動掃描 assets/sfx/ 庫存
  2. 驗證音檔格式 & 採樣率
  3. 與 lofi_assembler.py 的 4% 音量壓制邏輯協調
  4. 提供 CLI 與程式化介面
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict
import json
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


class SFXOrchestrator:
    """環境音效編排器 - 統一管理 SFX 工作流程"""
    
    def __init__(self, sfx_dir: str = None, ffmpeg_bin: str = "ffmpeg"):
        """初始化 SFX 編排器
        
        Args:
            sfx_dir: SFX 目錄路徑 (預設: assets/sfx/)
            ffmpeg_bin: FFmpeg 二進制路徑
        """
        if sfx_dir is None:
            sfx_dir = Path(config.workspace_root) / "assets" / "sfx"
        else:
            sfx_dir = Path(sfx_dir)
        
        self.sfx_dir = sfx_dir
        self.ffmpeg_bin = ffmpeg_bin
        self.supported_formats = {'.wav', '.mp3', '.flac', '.aiff', '.m4a'}
        
        # 確保目錄存在
        self.sfx_dir.mkdir(parents=True, exist_ok=True)
    
    def scan_library(self) -> List[Path]:
        """掃描 SFX 庫存中的所有音檔
        
        Returns:
            支援格式的音檔路徑列表
        """
        sfx_files = []
        
        if not self.sfx_dir.exists():
            return sfx_files
        
        for file_path in sorted(self.sfx_dir.glob("*")):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                # 跳過備份檔案
                if not file_path.name.startswith("_backup_"):
                    sfx_files.append(file_path)
        
        return sfx_files
    
    def get_audio_info(self, file_path: Path) -> Optional[Dict]:
        """使用 FFmpeg 獲取音頻信息
        
        Args:
            file_path: 音檔路徑
            
        Returns:
            音頻信息字典或 None
        """
        try:
            cmd = [
                self.ffmpeg_bin,
                "-hide_banner",
                "-i", str(file_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # FFmpeg 在獲取信息時通常回傳 code=1，所以不檢查 returncode
            stderr = result.stderr
            
            # 解析採樣率
            duration = None
            sample_rate = None
            channels = None
            
            for line in stderr.split('\n'):
                if "Duration:" in line:
                    # 例: "Duration: 00:01:00.00"
                    time_str = line.split("Duration:")[1].split(",")[0].strip()
                    parts = time_str.split(":")
                    if len(parts) >= 3:
                        duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                
                if "Hz" in line and ("Audio:" in line or "mono" in line or "stereo" in line):
                    # 例: "Audio: pcm_s16le, 44100 Hz, mono"
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if "Hz" in part and i > 0:
                            try:
                                sample_rate = int(parts[i-1])
                            except ValueError:
                                pass
                    
                    if "mono" in line:
                        channels = 1
                    elif "stereo" in line:
                        channels = 2
            
            if duration or sample_rate:
                return {
                    "file": file_path.name,
                    "path": str(file_path),
                    "format": file_path.suffix.lower(),
                    "duration": duration,
                    "sample_rate": sample_rate,
                    "channels": channels,
                    "size_mb": file_path.stat().st_size / (1024 ** 2)
                }
        
        except Exception as e:
            print(f"⚠️  無法讀取 {file_path.name}: {e}")
        
        return None
    
    def list_all_sfx(self) -> List[Dict]:
        """列出所有 SFX 及其信息
        
        Returns:
            SFX 信息列表
        """
        sfx_files = self.scan_library()
        result = []
        
        for file_path in sfx_files:
            info = self.get_audio_info(file_path)
            if info:
                result.append(info)
        
        return result
    
    def verify_compatibility(self) -> Dict[str, List]:
        """驗證 SFX 庫與 4% 音量壓制邏輯的相容性
        
        【相容性檢查】：
        - lofi_assembler.py 使用 FFmpeg volume=0.04 濾波器
        - 需要確保所有 SFX 能被 FFmpeg 正確讀取
        - 採樣率應標準化至 44100 Hz (可選)
        
        Returns:
            相容性檢查結果字典
        """
        results = {
            "compatible": [],
            "needs_conversion": [],
            "errors": []
        }
        
        sfx_list = self.list_all_sfx()
        
        for info in sfx_list:
            # 檢查是否可被 FFmpeg 讀取
            if not info.get("sample_rate"):
                results["errors"].append(f"{info['file']}: 無法讀取採樣率")
                continue
            
            # 檢查採樣率是否為標準的 44100 Hz
            if info["sample_rate"] != 44100:
                results["needs_conversion"].append({
                    "file": info["file"],
                    "current_rate": info["sample_rate"],
                    "target_rate": 44100
                })
            else:
                results["compatible"].append(info)
        
        return results
    
    def show_inventory(self):
        """顯示 SFX 庫存清單"""
        print("\n" + "="*70)
        print("📂 環境音效 (SFX) 庫存")
        print("="*70)
        
        sfx_list = self.list_all_sfx()
        
        if not sfx_list:
            print("\n⚠️  SFX 庫為空。請將音檔放入: assets/sfx/")
            return
        
        for idx, info in enumerate(sfx_list, 1):
            print(f"\n【{idx}】 {info['file']}")
            print(f"    格式: {info['format'].upper()}")
            if info['duration']:
                minutes = int(info['duration'] // 60)
                seconds = int(info['duration'] % 60)
                print(f"    長度: {minutes}:{seconds:02d}")
            if info['sample_rate']:
                print(f"    採樣率: {info['sample_rate']} Hz")
            if info['channels']:
                channels_txt = "單聲道" if info['channels'] == 1 else "立體聲"
                print(f"    聲道: {channels_txt}")
            print(f"    大小: {info['size_mb']:.2f} MB")
        
        print("\n" + "="*70 + "\n")
    
    def show_verification_report(self):
        """顯示 SFX 與 4% 音量壓制邏輯的相容性報告"""
        print("\n" + "="*70)
        print("✅ 4% 音量壓制相容性檢查")
        print("="*70)
        
        results = self.verify_compatibility()
        
        print(f"\n✅ 完全相容: {len(results['compatible'])} 個")
        for info in results['compatible']:
            print(f"   ✓ {info['file']} ({info['sample_rate']} Hz)")
        
        if results['needs_conversion']:
            print(f"\n⚠️  需要轉換: {len(results['needs_conversion'])} 個")
            print("   (採樣率不同，但仍可使用)")
            for item in results['needs_conversion']:
                print(f"   ⚠ {item['file']} ({item['current_rate']} → {item['target_rate']} Hz)")
        
        if results['errors']:
            print(f"\n❌ 讀取錯誤: {len(results['errors'])} 個")
            for error in results['errors']:
                print(f"   ✗ {error}")
        
        print("\n【說明】")
        print("  lofi_assembler.py 使用 FFmpeg volume=0.04 濾波器 (-28dB)")
        print("  所有標準音頻格式均相容。建議保持 44100 Hz 採樣率。")
        print("="*70 + "\n")


# ============================================================================
# CLI 介面
# ============================================================================

def main():
    """CLI 主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="【SFX 系統編排器】統一管理環境音效工作流程"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有 SFX 庫存"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="驗證 SFX 與 4% 音量壓制邏輯的相容性"
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="SFX 目錄路徑 (預設: assets/sfx/)"
    )
    
    args = parser.parse_args()
    
    orchestrator = SFXOrchestrator(sfx_dir=args.dir)
    
    if args.list:
        orchestrator.show_inventory()
    elif args.verify:
        orchestrator.show_verification_report()
    else:
        orchestrator.show_inventory()
        orchestrator.show_verification_report()


if __name__ == "__main__":
    main()
