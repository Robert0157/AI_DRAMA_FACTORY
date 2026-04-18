#!/usr/bin/env python3
"""
【VANGUARD MP3 DURATION ANALYSIS】
利用 mutagen 或 ffprobe 讀取精確時長
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# 試試使用 mutagen (需要 pip install mutagen)
try:
    from mutagen.mp3 import MP3
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

TRACK_DIR = Path(r"F:\AI_DRAMA_FACTORY\assets\audio\raw_tracks")

def get_mp3_duration_mutagen(filepath):
    """使用 mutagen 讀取 MP3 時長"""
    try:
        audio = MP3(str(filepath))
        duration_sec = audio.info.length
        return duration_sec
    except Exception as e:
        return None

def get_mp3_duration_windows(filepath):
    """
    使用 Windows Shell 物件讀取 MP3 Metadata
    """
    try:
        import subprocess
        # 使用 ffprobe (如果已安裝)
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1:nokey=1',
            str(filepath)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except:
        pass
    
    return None

def analyze_all_tracks():
    """讀取並分析所有 MP3 檔案的實際時長"""
    mp3_files = sorted(TRACK_DIR.glob("*.mp3"))
    
    if not mp3_files:
        print("❌ 未找到任何 MP3 檔案")
        return None
    
    # 先嘗試安裝 mutagen
    if not HAS_MUTAGEN:
        print("🔧 正在安裝 mutagen...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "mutagen", "-q"], 
                         check=True, timeout=30)
            from mutagen.mp3 import MP3
            globals()['HAS_MUTAGEN'] = True
        except:
            print("⚠️ mutagen 安裝失敗，使用備用方案")
    
    results = []
    
    print("=" * 90)
    print("🎵 【音檔時長驗收報告】")
    print("=" * 90)
    print()
    
    for idx, f in enumerate(mp3_files, 1):
        size_bytes = f.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        
        # 優先用 mutagen 讀取
        duration_sec = None
        if HAS_MUTAGEN:
            duration_sec = get_mp3_duration_mutagen(f)
        
        # 備用方案：ffprobe
        if duration_sec is None:
            duration_sec = get_mp3_duration_windows(f)
        
        # 最後備用：根據 bitrate 估算
        if duration_sec is None:
            # 假設平均 bitrate 256kbps = 32KB/s
            duration_sec = size_bytes / 32000
        
        duration_min = duration_sec / 60 if duration_sec else 0
        duration_str = f"{int(duration_sec//60)}:{int(duration_sec%60):02d}" if duration_sec else "N/A"
        
        # 狀態判定
        if duration_sec and duration_sec >= 150:
            status = "✅ 符合"
            emoji = "✓"
        elif duration_sec and duration_sec >= 120:
            status = "⚠️ 略短"
            emoji = "~"
        else:
            status = "❌ 過短"
            emoji = "✗"
        
        results.append({
            "filename": f.name,
            "size_mb": round(size_mb, 2),
            "duration_sec": round(duration_sec, 1) if duration_sec else None,
            "duration_min": round(duration_min, 2) if duration_sec else None,
            "status": status
        })
        
        print(f"{idx:2d}. {f.name[:50]:<50}")
        print(f"    📊 {size_mb:.2f} MB  |  ⏱️  {duration_str} ({duration_min:.2f}m)  {emoji}  {status}")
        print()
    
    # 統計分析
    durations = [r["duration_sec"] for r in results if r["duration_sec"]]
    standard_count = len([d for d in durations if d >= 150])
    short_count = len([d for d in durations if 120 <= d < 150])
    very_short_count = len([d for d in durations if d < 120])
    
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    print("=" * 90)
    print("📈 【統計摘要】")
    print("=" * 90)
    print(f"✅ 符合 (≥150s): {standard_count}/{len(results)} 首  ({standard_count*100//len(results)}%)")
    print(f"⚠️ 略短 (120-150s): {short_count}/{len(results)} 首")
    print(f"❌ 過短 (<120s):   {very_short_count}/{len(results)} 首")
    print()
    print(f"平均時長:     {avg_duration:.1f} 秒 ({avg_duration/60:.2f} 分)")
    if durations:
        print(f"最長:        {max(durations):.1f} 秒 ({max(durations)/60:.2f} 分)")
        print(f"最短:        {min(durations):.1f} 秒 ({min(durations)/60:.2f} 分)")
    print()
    
    # CTO 評估
    if standard_count >= len(results) * 0.7:
        cto_verdict = "✅ PASS - 大部分符合「150秒+」要求"
    elif standard_count + short_count >= len(results) * 0.7:
        cto_verdict = "⚠️ MARGINAL - 需微調生成策略"
    else:
        cto_verdict = "❌ FAIL - 品質未達標準"
    
    print("🎯 【CTO 評估】")
    print(f"{cto_verdict}")
    print()
    
    return results

if __name__ == "__main__":
    results = analyze_all_tracks()
