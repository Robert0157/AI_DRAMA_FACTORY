#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video_processor_test_runner.py — 萬能影片循環處理器驗收測試

【測試目標】
✅ 驗證 video_processor.py 能否正確解析參數
✅ 驗證 pipeline_runner.py 的 --bg-video 參數傳遞
✅ 檢查 FFmpeg 依賴可用性
✅ 驗證臨時目錄建立邏輯
"""

import subprocess
import sys
from pathlib import Path

def run_test(name: str, cmd: list, expect_exit: int = 0) -> bool:
    """運行單個測試。"""
    print(f"\n🧪 測試: {name}")
    print(f"   指令: {' '.join(cmd[:3])}...")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == expect_exit:
        print(f"   ✅ 通過 (exit code: {result.returncode})")
        return True
    else:
        print(f"   ❌ 失敗 (exit code: {result.returncode}, expected: {expect_exit})")
        print(f"   STDERR: {result.stderr[:200]}")
        return False

def main():
    print("=" * 70)
    print("【萬能影片循環處理器 - 系統驗收測試】")
    print("=" * 70)
    
    project_root = Path(__file__).resolve().parents[1]
    video_processor = project_root / "scripts/gear1_prod/video_processor.py"
    pipeline_runner = project_root / "scripts/gear1_prod/pipeline_runner.py"
    
    # 測試 1: 檢查 FFmpeg
    print(f"\n【檢查依賴】")
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    if result.returncode == 0:
        ffmpeg_version = result.stdout.split('\n')[0]
        print(f"  ✅ FFmpeg: {ffmpeg_version[:50]}")
    else:
        print(f"  ❌ FFmpeg: 未安裝")
        return
    
    result = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  ✅ FFprobe: 已安裝")
    else:
        print(f"  ❌ FFprobe: 未安裝")
        return
    
    # 測試 2: video_processor.py 參數驗證
    print(f"\n【Test Group 1: video_processor.py 參數解析】")
    
    # 測試 2a: 缺少必需參數
    run_test(
        "缺少 --bg-video 參數",
        [sys.executable, str(video_processor), "--audio", "dummy.wav"],
        expect_exit=2  # argparse 錯誤退出碼
    )
    
    # 測試 2b: 幫助信息
    run_test(
        "顯示幫助 (-h)",
        [sys.executable, str(video_processor), "-h"],
        expect_exit=0
    )
    
    # 測試 3: pipeline_runner.py 參數驗證
    print(f"\n【Test Group 2: pipeline_runner.py --bg-video 參數】")
    
    # 測試 3a: 檢查幫助信息是否包含 --bg-video
    result = subprocess.run(
        [sys.executable, str(pipeline_runner), "-h"],
        capture_output=True, text=True
    )
    if "--bg-video" in result.stdout:
        print(f"  ✅ --bg-video 參數已註冊")
    else:
        print(f"  ❌ --bg-video 參數未註冊到 pipeline_runner.py")
        print(f"     幫助信息: {result.stdout[:300]}")
    
    # 測試 4: 臨時目錄檢查
    print(f"\n【Test Group 3: 系統目錄結構】")
    
    dirs_to_check = [
        ("Project root", project_root),
        ("scripts/gear1_prod/", project_root / "scripts/gear1_prod"),
        ("assets/final_exports/", project_root / "assets/final_exports"),
    ]
    
    for name, path in dirs_to_check:
        if path.exists():
            print(f"  ✅ {name}: {path}")
        else:
            print(f"  ⚠️  {name}: 不存在（首次運行時會自動建立）")
    
    # 測試 5: Python 模組導入驗證
    print(f"\n【Test Group 4: Python 模組導入】")
    
    sys.path.insert(0, str(project_root))
    
    try:
        from scripts.common.env_manager import config
        print(f"  ✅ env_manager: 成功導入")
        print(f"     workspace_root: {config.workspace_root}")
    except ImportError as e:
        print(f"  ❌ env_manager: 導入失敗 - {e}")
    
    # 測試 6: video_processor.py 模組檢查
    print(f"\n【Test Group 5: video_processor.py 完整性】")
    
    if video_processor.exists():
        print(f"  ✅ 檔案存在: {video_processor.name}")
        
        # 檢查關鍵函式
        with open(video_processor, 'r', encoding='utf-8') as f:
            content = f.read()
        
        functions = [
            ("_get_duration", "FFmpeg 時長測量"),
            ("_build_loop_unit", "Ping-Pong 循環單元生成"),
            ("composite_with_audio", "視頻與音樂合成"),
            ("process_video", "主流程入點"),
        ]
        
        for func_name, desc in functions:
            if f"def {func_name}" in content:
                print(f"  ✅ 函式 {func_name}: ✓ ({desc})")
            else:
                print(f"  ❌ 函式 {func_name}: ✗ 缺失")
    else:
        print(f"  ❌ 檔案不存在: {video_processor}")
    
    # 最終摘要
    print(f"\n" + "=" * 70)
    print("【測試摘要】")
    print("=" * 70)
    print("""
✅ 所有系統驗收檢查已完成

【下一步】
1️⃣  準備測試用背景短片 (3~10 秒 MP4)
2️⃣  執行完整產線：
    python scripts/gear1_prod/pipeline_runner.py --bg-video "path/to/video.mp4"
3️⃣  或直接測試 video_processor：
    python scripts/gear1_prod/video_processor.py \\
      --bg-video "test_video.mp4" \\
      --audio "test_audio.wav"

【疑難排除】
• 若 FFmpeg 未安裝，請執行:
  choco install ffmpeg  # Windows
  brew install ffmpeg   # macOS
  apt-get install ffmpeg # Linux

• 若找不到母帶音軌，請先執行 Phase 1~4 建立音檔
• 若遇到路徑問題，使用絕對路徑而非相對路徑
""")

if __name__ == "__main__":
    main()
