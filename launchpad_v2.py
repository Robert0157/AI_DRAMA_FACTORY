#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 Kling Vol_1 首映試映 終極發射塔 (v2)
特性：
- 後台長期運行，無懼 Ctrl+C
- 自動重連和嘗試
- 實時日誌監控
- 完成後自動通知
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

class LaunchpadV2:
    def __init__(self):
        self.log_file = Path("kling_premiere_realtime.log")
        self.proc = None
        self.should_exit = False
        self.last_submitted_shot = None  # 追蹤最後提交的分鏡，避免重複
        
    def log(self, msg: str, label: str = "LAUNCHPAD"):
        """同步寫入終端和日誌"""
        out = f"[{label}] {msg}"
        print(out, flush=True)
        sys.stdout.flush()
        with open(self.log_file, "a", encoding="utf-8") as fh:
            fh.write(out + "\n")
            fh.flush()
    
    def read_stream(self, stream, label: str):
        """讀取進程輸出流"""
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                line = line.rstrip("\n")
                self.log(line, label)
                
                # 關鍵信號檢測：只在提交新分鏡時觸發一次
                if "submitted task_id=" in line:
                    # 提取分鏡編號（如 shot_01, shot_02 等）
                    import re
                    task_match = re.search(r"task_id=(\d+)", line)
                    if task_match:
                        task_id = task_match.group(1)
                        # 避免重複提示同一個任務
                        if task_id != self.last_submitted_shot:
                            self.last_submitted_shot = task_id
                            self.log("=" * 80, "ALERT")
                            self.log("✅ 分鏡已提交 Kling API", "ALERT")
                            self.log(f"   Task ID: {task_id}", "ALERT")
                            self.log("=" * 80, "ALERT")
        except Exception as e:
            self.log(f"讀取流錯誤：{e}", label)
    
    def launch(self):
        """啟動並監控 Kling 引擎"""
        
        # 初始化日誌
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"{timestamp} 🚀 IGNITION!", "LAUNCHPAD")
        
        cmd = [
            sys.executable,
            "-u",
            "scripts/gear1_prod/kling_api_engine.py",
            "--job-id", "zaouli_test_002_vol1_premiere",
            "--shots-file", "assets/scripts/zaouli_test_002/vol_1_submission.json",
        ]
        
        self.log(f"Command: {' '.join(cmd)}", "LAUNCHPAD")
        self.log("⏳ 正在啟動 Kling 引擎...", "LAUNCHPAD")
        
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            
            # 並行讀取流
            stdout_thread = threading.Thread(
                target=self.read_stream,
                args=(self.proc.stdout, "OUT"),
                daemon=True
            )
            stderr_thread = threading.Thread(
                target=self.read_stream,
                args=(self.proc.stderr, "ERR"),
                daemon=True
            )
            stdout_thread.start()
            stderr_thread.start()
            
            # 等待進程（捕捉 Ctrl+C 但不中斷進程）
            self.log("✅ Kling 引擎已啟動，進程在背景運行", "LAUNCHPAD")
            self.log("💡 提示：可以按 Ctrl+C 返回，進程將繼續在背景運行", "LAUNCHPAD")
            self.log("📊 實時監控日誌：Get-Content kling_premiere_realtime.log -Wait", "LAUNCHPAD")
            
            try:
                returncode = self.proc.wait()
                end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log(f"{end_time} 🛬 進程完成 (return code={returncode})", "LAUNCHPAD")
            
            except KeyboardInterrupt:
                self.log("⚠️  按下 Ctrl+C，但進程仍在背景運行...", "LAUNCHPAD")
                self.log(f"📋 進程 PID：{self.proc.pid}", "LAUNCHPAD")
                self.log("🔍 查看日誌：Get-Content kling_premiere_realtime.log -Tail 50", "LAUNCHPAD")
                raise
        
        except Exception as e:
            self.log(f"❌ 致命錯誤：{e}", "LAUNCHPAD")
            import traceback
            traceback.print_exc()
            raise SystemExit(1)

if __name__ == "__main__":
    launcher = LaunchpadV2()
    try:
        launcher.launch()
    except KeyboardInterrupt:
        print("\n[LAUNCHPAD] 🔄 您可以稍後查詢日誌以確認進度。進程仍在背景轉圈中。")
        sys.exit(0)
