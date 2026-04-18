#!/usr/bin/env python3
"""快速音檔時長檢查工具"""

from pathlib import Path
from mutagen.mp3 import MP3

TRACK_DIR = Path(r"F:\AI_DRAMA_FACTORY\assets\audio\raw_tracks")

mp3_files = sorted(TRACK_DIR.glob("*.mp3"))

print("=" * 90)
print("🎵 【音檔時長驗收報告】")
print("=" * 90)
print()

results = []

for idx, f in enumerate(mp3_files, 1):
    try:
        audio = MP3(str(f))
        duration_sec = audio.info.length
    except:
        duration_sec = None
    
    size_mb = f.stat().st_size / (1024 * 1024)
    
    if duration_sec:
        duration_min = duration_sec / 60
        duration_str = f"{int(duration_sec//60)}:{int(duration_sec%60):02d}"
        
        if duration_sec >= 150:
            status = "✅ 符合"
            emoji = "✓"
        elif duration_sec >= 120:
            status = "⚠️ 略短"
            emoji = "~"
        else:
            status = "❌ 過短"
            emoji = "✗"
    else:
        duration_min = 0
        duration_str = "N/A"
        status = "❓ 無法讀取"
        emoji = "?"
    
    results.append({
        "filename": f.name,
        "size_mb": round(size_mb, 2),
        "duration_sec": duration_sec,
        "duration_min": round(duration_min, 2),
        "status": status
    })
    
    print(f"{idx:2d}. {f.name[:50]:<50}")
    print(f"    📊 {size_mb:.2f} MB  |  ⏱️  {duration_str} ({duration_min:.2f}m)  {emoji}  {status}")
    print()

# 統計分析
durations = [r["duration_sec"] for r in results if r["duration_sec"]]
vanguard = [r for r in results if "VanguardGen" in r["filename"]]
others = [r for r in results if "VanguardGen" not in r["filename"]]

if durations:
    standard_count = len([d for d in durations if d >= 150])
    short_count = len([d for d in durations if 120 <= d < 150])
    very_short_count = len([d for d in durations if d < 120])
    
    avg_duration = sum(durations) / len(durations)
    
    print("=" * 90)
    print("📈 【統計摘要】")
    print("=" * 90)
    print(f"✅ 符合 (≥150s): {standard_count}/{len(results)} 首  ({standard_count*100//len(results)}%)")
    print(f"⚠️ 略短 (120-150s): {short_count}/{len(results)} 首")
    print(f"❌ 過短 (<120s):   {very_short_count}/{len(results)} 首")
    print()
    print(f"平均時長:     {avg_duration:.1f} 秒 ({avg_duration/60:.2f} 分)")
    print(f"最長:        {max(durations):.1f} 秒 ({max(durations)/60:.2f} 分)")
    print(f"最短:        {min(durations):.1f} 秒 ({min(durations)/60:.2f} 分)")
    print()
    
    if vanguard:
        vanguard_durations = [r["duration_sec"] for r in vanguard if r["duration_sec"]]
        if vanguard_durations:
            vanguard_pass = len([d for d in vanguard_durations if d >= 150])
            vanguard_total = len(vanguard_durations)
            print(f"【VanguardGen 歌曲】: {vanguard_total} 首")
            print(f"  ✅ 符合 (≥150s): {vanguard_pass}/{vanguard_total}  ({vanguard_pass*100//vanguard_total}%)")
            print(f"  平均: {sum(vanguard_durations)/len(vanguard_durations):.1f}s")
            print()
    
    if others:
        others_durations = [r["duration_sec"] for r in others if r["duration_sec"]]
        if others_durations:
            print(f"【其他音檔】: {len(others)} 首")
            print(f"  平均: {sum(others_durations)/len(others_durations):.1f}s")
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
