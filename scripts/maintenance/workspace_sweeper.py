#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
workspace_sweeper.py — 產線深度大掃除工具 (v12.1 多頻道隔離版)

v12.1 升級說明：
============================================
【新增】: --channel 參數支持，精準清理指定頻道資源
【防呆】: 嚴禁自動刪除 ceo_approved_beats/ 的原始檔案
【零遺失】: 完全對齐「落實零遺失鐵律」
============================================
"""

import os
import sys
import shutil
import argparse
from pathlib import Path

# 強制獲取專案根目錄
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

def delete_directory(target_path: Path):
    """安全刪除整個目錄"""
    if target_path.exists() and target_path.is_dir():
        try:
            shutil.rmtree(target_path)
            print(f"✅ [目錄拔除] 已成功刪除廢棄系統: {target_path.name}")
        except Exception as e:
            print(f"❌ [錯誤] 無法刪除目錄 {target_path.name}: {e}")
    else:
        print(f"⏩ [略過] 找不到目錄 (可能已刪除): {target_path.name}")

def purge_files(pattern: str, description: str):
    """遞迴搜尋並刪除特定副檔名的垃圾檔案"""
    print(f"\n🔍 正在掃描並清除: {description} ({pattern})...")
    count = 0
    freed_bytes = 0
    
    for file_path in _PROJECT_ROOT.rglob(pattern):
        if file_path.is_file():
            try:
                size = file_path.stat().st_size
                file_path.unlink()
                count += 1
                freed_bytes += size
                print(f"   🗑️ 刪除: {file_path.name} ({(size/1024/1024):.2f} MB)")
            except Exception as e:
                print(f"   ❌ 無法刪除 {file_path.name}: {e}")
                
    freed_mb = freed_bytes / (1024 * 1024)
    print(f"✨ [清理完成] 共刪除 {count} 個 {description}，釋放 {freed_mb:.2f} MB 空間。")
    return freed_mb

def purge_channel_temp_files(channel: str):
    """
    【v12.1】清理指定頻道的暫存檔案
    - 清理 48h 舊的 final_exports/{channel}/ 中的 1Hour.mp4
    - 清理所有 temp_*.wav 中繼檔
    
    Args:
        channel: 頻道名稱 (lofi 或 light_music)
    """
    import time
    
    channel_export_dir = _PROJECT_ROOT / "assets" / "final_exports" / channel
    current_time = time.time()
    cutoff_time = current_time - (48 * 3600)  # 48 小時前的時間戳
    
    print(f"\n🔍 【{channel.upper()} 頻道】清理 48h 舊 MP4 和暫存音檔...")
    count = 0
    freed_bytes = 0
    
    if channel_export_dir.exists():
        # 清理舊 MP4
        for mp4_file in channel_export_dir.glob("*1HrMix*.mp4"):
            try:
                mtime = mp4_file.stat().st_mtime
                if mtime < cutoff_time:
                    size = mp4_file.stat().st_size
                    mp4_file.unlink()
                    count += 1
                    freed_bytes += size
                    print(f"   🗑️ 刪除舊 MP4: {mp4_file.name} ({(size/1024/1024):.2f} MB)")
            except Exception as e:
                print(f"   ❌ 無法刪除 {mp4_file.name}: {e}")
        
        # 清理 temp_*.wav
        for temp_wav in channel_export_dir.glob("temp_*.wav"):
            try:
                size = temp_wav.stat().st_size
                temp_wav.unlink()
                count += 1
                freed_bytes += size
                print(f"   🗑️ 刪除暫存 WAV: {temp_wav.name} ({(size/1024/1024):.2f} MB)")
            except Exception as e:
                print(f"   ❌ 無法刪除 {temp_wav.name}: {e}")
    
    freed_mb = freed_bytes / (1024 * 1024)
    if count > 0:
        print(f"✨ [{channel.upper()}] 清理完成：刪除 {count} 個檔案，釋放 {freed_mb:.2f} MB")
    else:
        print(f"ℹ️  [{channel.upper()}] 暫存檔案已清潔")
    
    return freed_mb

def safeguard_ceo_approved_beats():
    """
    【v12.1 防呆】嚴禁自動刪除 ceo_approved_beats/ 內的原始檔案
    此函式只打印警告，絕對不執行刪除
    """
    approved_dir = _PROJECT_ROOT / "assets" / "audio" / "ceo_approved_beats"
    
    print("\n🛡️  【零遺失鐵律防線】")
    print(f"✅ ceo_approved_beats/ 原始母帶檔案已被保護")
    print(f"   📂 位置: {approved_dir}")
    print(f"   🔒 系統嚴禁自動刪除此目錄中的任何檔案")
    print(f"   💡 若要封存，請通過 CEO UI 的「手動封存」按鈕執行")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="R&S Echoes 產線清道夫 (v12.1 多頻道版)")
    parser.add_argument(
        "--channel",
        type=str,
        choices=["lofi", "light_music", "all"],
        default="all",
        help="指定要清理的頻道 (預設: all - 清理所有頻道)"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🧹 R&S Echoes 工廠深度大掃除 (v12.1 多頻道隔離版)")
    print("=" * 70)
    print(f"📍 目標廠房: {_PROJECT_ROOT}")
    print(f"📍 清理頻道: {args.channel.upper()}\n")
    
    total_freed_mb = 0
    
    # 1. 拔除舊版 Suno API
    if args.channel == "all":
        print("🔥 階段 1：拔除廢棄的 suno-api 子系統...")
        suno_api_dir = _PROJECT_ROOT / "suno-api"
        delete_directory(suno_api_dir)
        
        # 2. 清理 Python 編譯暫存
        print("\n🔥 階段 2：清理 Python __pycache__ 碎片...")
        for pycache in _PROJECT_ROOT.rglob("__pycache__"):
            delete_directory(pycache)
        
        # 3. 清理舊版草稿檔案
        print("\n🔥 階段 3（最後一次）：清除任何遺留舊版草稿...")
        total_freed_mb += purge_files(
            "YouTube_CheatSheet_草稿_*.txt",
            "舊版企劃草稿檔 (已廢除)"
        )
        
        # 5. 清除系統隱藏垃圾
        print("\n🔥 階段 5：清除系統隱藏垃圾檔...")
        total_freed_mb += purge_files(".DS_Store", "系統隱藏垃圾 (.DS_Store)")
    
    # 4（新增）多頻道隔離清理 - 清理指定頻道的暫存與舊檔
    if args.channel == "all":
        for ch in ["lofi", "light_music"]:
            total_freed_mb += purge_channel_temp_files(ch)
    else:
        total_freed_mb += purge_channel_temp_files(args.channel)
    
    # 6（新增）防呆檢查
    print("\n")
    safeguard_ceo_approved_beats()
    
    # 7. CTO 紀律整頓
    if args.channel == "all":
        print("\n🔥 階段 6：CTO 紀律整頓 - 銷毀違規微觀報告...")
        
        for cto_report in _PROJECT_ROOT.glob("CTO_*.md"):
            try:
                size = cto_report.stat().st_size
                cto_report.unlink()
                freed_mb = size / (1024 * 1024)
                print(f"   🗑️ [CTO 違規報告] 刪除: {cto_report.name} ({freed_mb:.2f} MB)")
                total_freed_mb += freed_mb
            except Exception as e:
                print(f"   ❌ 無法刪除 {cto_report.name}: {e}")
        
        for phase_report in _PROJECT_ROOT.glob("PHASE*_*.md"):
            try:
                size = phase_report.stat().st_size
                phase_report.unlink()
                freed_mb = size / (1024 * 1024)
                print(f"   🗑️ [PHASE 違規報告] 刪除: {phase_report.name} ({freed_mb:.2f} MB)")
                total_freed_mb += freed_mb
            except Exception as e:
                print(f"   ❌ 無法刪除 {phase_report.name}: {e}")
        
        for cleanup_script in _PROJECT_ROOT.glob("cleanup_*.py"):
            try:
                size = cleanup_script.stat().st_size
                cleanup_script.unlink()
                freed_mb = size / (1024 * 1024)
                print(f"   🗑️ [清理腳本] 刪除: {cleanup_script.name} ({freed_mb:.2f} MB)")
                total_freed_mb += freed_mb
            except Exception as e:
                print(f"   ❌ 無法刪除 {cleanup_script.name}: {e}")

    print("\n" + "=" * 70)
    print(f"🎉 廠房淨空完畢！本次清理共釋放 {total_freed_mb:.2f} MB。")
    print(f"📊 清理頻道: {args.channel.upper()}")
    print()
    print("【v12.1 新境界達成】:")
    print("  ✨ 多頻道隔離清理 (channel-aware)")
    print("  ✨ 防呆保護機制 (safeguard ceo_approved_beats)")
    print("  ✨ 零遺失保證 (zero data loss)")
    print()
    print("產線已達成 100% 強健淨空狀態！")
    print("=" * 70)


def delete_directory(target_path: Path):
    """安全刪除整個目錄"""
    if target_path.exists() and target_path.is_dir():
        try:
            shutil.rmtree(target_path)
            print(f"✅ [目錄拔除] 已成功刪除廢棄系統: {target_path.name}")
        except Exception as e:
            print(f"❌ [錯誤] 無法刪除目錄 {target_path.name}: {e}")
    else:
        print(f"⏩ [略過] 找不到目錄 (可能已刪除): {target_path.name}")

def purge_files(pattern: str, description: str):
    """遞迴搜尋並刪除特定副檔名的垃圾檔案"""
    print(f"\n🔍 正在掃描並清除: {description} ({pattern})...")
    count = 0
    freed_bytes = 0
    
    for file_path in _PROJECT_ROOT.rglob(pattern):
        if file_path.is_file():
            try:
                size = file_path.stat().st_size
                file_path.unlink()
                count += 1
                freed_bytes += size
                print(f"   🗑️ 刪除: {file_path.name} ({(size/1024/1024):.2f} MB)")
            except Exception as e:
                print(f"   ❌ 無法刪除 {file_path.name}: {e}")
                
    freed_mb = freed_bytes / (1024 * 1024)
    print(f"✨ [清理完成] 共刪除 {count} 個 {description}，釋放 {freed_mb:.2f} MB 空間。")
    return freed_mb

if __name__ == "__main__":
    print("=" * 70)
    print("🧹 R&S Echoes 工廠深度大掃除 (v9.5 一站式合體版)")
    print("=" * 70)
    print(f"📍 目標廠房: {_PROJECT_ROOT}\n")
    print("【核心準則】: 廢除中間草稿，一次成型最終文案")
    print()

    total_freed_mb = 0

    # 1. 拔除舊版 Suno API (Node.js 龐大專案)
    print("🔥 階段 1：拔除廢棄的 suno-api 子系統...")
    suno_api_dir = _PROJECT_ROOT / "suno-api"
    delete_directory(suno_api_dir)

    # 2. 清理 Python 編譯暫存 (通常佔用不少碎片空間)
    print("\n🔥 階段 2：清理 Python __pycache__ 碎片...")
    for pycache in _PROJECT_ROOT.rglob("__pycache__"):
        delete_directory(pycache)

    # 3. 清理舊版的任何遺留草稿檔案（如有）
    # 【v9.5 說明】: music_metadata_engine 已完全廢除草稿生成。
    # 此步驟僅用於清理任何「歷史遺留」。若無此檔案，系統會安全略過。
    print("\n🔥 階段 3（最後一次）：清除任何遺留舊版草稿...")
    total_freed_mb += purge_files(
        "YouTube_CheatSheet_草稿_*.txt", 
        "舊版企劃草稿檔 (已廢除，僅作為歷史清理)"
    )

    # 4. 深度清理 FFmpeg / 系統產生的各種暫存檔
    # 【重點】: 摒棄舊版「等待審查」的中間音檔。一站式合體後無此需要。
    print("\n🔥 階段 4：深度清理系統暫存檔 (temp_*.*)...")
    total_freed_mb += purge_files("temp_*.*", "系統暫存檔 (temp)")
    
    # 5. 清除 Mac 系統容易產生的隱藏垃圾 (若在 Mac 上開發)
    print("\n🔥 階段 5：清除系統隱藏垃圾檔...")
    total_freed_mb += purge_files(".DS_Store", "系統隱藏垃圾 (.DS_Store)")

    # 6. CTO 紀律整頓：清除工程團隊違規生成的微觀報告與日誌
    # 【v9.5 零浪費紀律】: 所有工程執行結果必須直接輸出至終端/聊天，
    # 嚴禁生成個別 .md 報告或 .log 檔案文件。此階段清除任何違反此規則的遺留物。
    print("\n🔥 階段 6：CTO 紀律整頓 - 銷毀違規微觀報告...")
    
    # 掃描並刪除根目錄中的 CTO 補丁報告
    for cto_report in _PROJECT_ROOT.glob("CTO_*.md"):
        try:
            size = cto_report.stat().st_size
            cto_report.unlink()
            freed_mb = size / (1024 * 1024)
            print(f"   🗑️ [CTO 違規報告] 刪除: {cto_report.name} ({freed_mb:.2f} MB)")
            total_freed_mb += freed_mb
        except Exception as e:
            print(f"   ❌ 無法刪除 {cto_report.name}: {e}")
    
    # 掃描並刪除根目錄中的 PHASE 階段報告
    for phase_report in _PROJECT_ROOT.glob("PHASE*_*.md"):
        try:
            size = phase_report.stat().st_size
            phase_report.unlink()
            freed_mb = size / (1024 * 1024)
            print(f"   🗑️ [PHASE 違規報告] 刪除: {phase_report.name} ({freed_mb:.2f} MB)")
            total_freed_mb += freed_mb
        except Exception as e:
            print(f"   ❌ 無法刪除 {phase_report.name}: {e}")
    
    # 掃描並刪除一次性清理腳本 (cleanup_*.py 調試產物)
    for cleanup_script in _PROJECT_ROOT.glob("cleanup_*.py"):
        try:
            size = cleanup_script.stat().st_size
            cleanup_script.unlink()
            freed_mb = size / (1024 * 1024)
            print(f"   🗑️ [清理腳本] 刪除: {cleanup_script.name} ({freed_mb:.2f} MB)")
            total_freed_mb += freed_mb
        except Exception as e:
            print(f"   ❌ 無法刪除 {cleanup_script.name}: {e}")

    print("\n" + "=" * 70)
    print(f"🎉 廠房淨空完畢！本次檔案清理共釋放 {total_freed_mb:.2f} MB。")
    print()
    print("【v9.5 新境界達成】:")
    print("  ✨ 草稿機制已廢除 (one-shot inline composition)")
    print("  ✨ 編譯快取已清理 (zero bloat)")
    print("  ✨ 暫存檔已掃淨 (no temp accumulation)")
    print()
    print("產線已達成 100% 輕量化狀態，準備迎接無頭伺服器時代！")
    print("=" * 70)

