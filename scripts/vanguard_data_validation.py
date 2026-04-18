#!/usr/bin/env python3
"""
【VANGUARD DATA VALIDATION】
10-Song Test Result Analysis & CTO Report Generator
"""

import os, sys
from pathlib import Path
import json
from datetime import datetime

# 【跨平台防線】以腳本位置動態推導專案根目錄
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_DIR = _PROJECT_ROOT / "assets" / "audio" / "raw_tracks"

def analyze_vanguard_files():
    """讀取並分析 10 首 VanguardGen 檔案"""
    mp3_files = sorted(TRACK_DIR.glob("VanguardGen_*.mp3"))
    
    if not mp3_files:
        print("❌ 未找到 VanguardGen 檔案")
        return None
    
    results = []
    
    print("=" * 70)
    print("🎵 【VANGUARD 10-SONG TEST RESULT VALIDATION】")
    print("=" * 70)
    print()
    
    for idx, f in enumerate(mp3_files, 1):
        size_bytes = f.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        
        # Estimate duration: MP3 avg bitrate ~256kbps = 32KB/s
        estimated_sec = size_bytes / 32000
        estimated_min = estimated_sec / 60
        
        # Status determination
        if size_mb < 2.0:
            status = "⚠️ EARLY_FADE_OUT"
            assessment = f"({estimated_min:.1f}m - 過短)"
        elif 3.0 <= size_mb <= 4.0:
            status = "✅ STANDARD"
            assessment = f"({estimated_min:.1f}m - 標準)"
        else:
            status = "✓ GOOD"
            assessment = f"({estimated_min:.1f}m)"
        
        results.append({
            "filename": f.name,
            "size_mb": round(size_mb, 2),
            "size_bytes": size_bytes,
            "estimated_duration_sec": round(estimated_sec, 1),
            "status": status
        })
        
        print(f"{idx:2d}. {f.name}")
        print(f"    📊 {size_mb:.2f} MB  {status} {assessment}")
        print()
    
    # 統計分析
    sizes = [r["size_mb"] for r in results]
    standard_count = len([s for s in sizes if 3.0 <= s <= 4.0])
    early_fade_count = len([s for s in sizes if s < 2.0])
    over_count = len([s for s in sizes if s > 4.0])
    
    avg_size = sum(sizes) / len(sizes)
    avg_dur = sum([r["estimated_duration_sec"] for r in results]) / len(results)
    
    print("=" * 70)
    print("📈 【STATISTICAL SUMMARY】")
    print("=" * 70)
    print(f"✅ 標準 (3-4MB):    {standard_count}/{len(sizes)} 首  ({standard_count*100/len(sizes):.0f}%)")
    print(f"⚠️ 提早收尾 (<2MB): {early_fade_count}/{len(sizes)} 首")
    print(f"📈 偏長 (>4MB):     {over_count}/{len(sizes)} 首")
    print()
    print(f"平均大小:     {avg_size:.2f} MB")
    print(f"平均時長:     {avg_dur:.1f} 秒 ({avg_dur/60:.2f}分)")
    print(f"最大:        {max(sizes):.2f} MB")
    print(f"最小:        {min(sizes):.2f} MB")
    print()
    
    # CTO 評估
    if standard_count >= 7:
        cto_verdict = "✅ PASS - v5.5 Native Generation Capability 符合預期"
    elif standard_count >= 5:
        cto_verdict = "⚠️ WARNING - 需要優化提示詞或模型參數"
    else:
        cto_verdict = "❌ FAIL - Extension API 協助可能必要"
    
    print("🎯 【CTO VERDICT】")
    print(f"{cto_verdict}")
    print()
    
    return results

if __name__ == "__main__":
    results = analyze_vanguard_files()
    
    # 儲存結果為 JSON
    if results:
        report = {
            "timestamp": datetime.now().isoformat(),
            "test_type": "10-song-validation",
            "files": results,
            "summary": {
                "total": len(results),
                "standard_count": len([r for r in results if 3.0 <= r["size_mb"] <= 4.0]),
                "early_fade_count": len([r for r in results if r["size_mb"] < 2.0]),
                "average_size_mb": round(sum([r["size_mb"] for r in results]) / len(results), 2)
            }
        }
        
        report_path = _PROJECT_ROOT / "assets" / "data" / "vanguard_validation_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 驗收報告已儲存: {report_path}")
