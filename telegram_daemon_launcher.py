#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【Telegram 決策層守護程序啟動器】v8.7 CTO 修復版

功能：
- 啟動 Telegram 背景監聽
- 【CTO 修復】使用同步版本，避免 asyncio 事件迴圈衝突
- 監聽 CEO 的 [✅ 採用] / [❌ 放棄] 決策
- 實時寫入 .approval_queue.json & .daily_quota.json

用法：
  python telegram_daemon_launcher.py    # 啟動守護程序
  Ctrl+C                                  # 安全停止
"""

import subprocess
import sys
from pathlib import Path

print("\n" + "="*80)
print("🚀 Telegram 決策層守護程序啟動器 (v8.7 CTO 修復版)")
print("="*80)
print("\n【修復內容】")
print("  ✅ 使用同步 app.run_polling()，避免 asyncio event loop 衝突")
print("  ✅ 直接獨占事件迴圈，無層級嵌套")
print("  ✅ Telegram callback 實時寫入統計")
print("  ✅ Ctrl+C 安全停止\n")

try:
    cmd = [
        sys.executable,
        "-B",
        "scripts/gear1_prod/telegram_approval_gate.py",
        "--daemon"
    ]
    
    print(f"命令: {' '.join(cmd)}\n")
    print("="*80)
    print("📡 守護程序已啟動，正在監聽...\n")
    
    result = subprocess.run(cmd, cwd="f:/AI_DRAMA_FACTORY")
    
    if result.returncode == 0:
        print("\n✅ Telegram 守護程序正常停止")
    else:
        print(f"\n⚠️  守護程序結束 (exit code: {result.returncode})")
    
    sys.exit(result.returncode)
    
except KeyboardInterrupt:
    print("\n✋ 收到中斷信號")
    print("✅ 守護程序已停止\n")
    sys.exit(0)
except Exception as e:
    print(f"\n❌ 啟動失敗: {e}")
    sys.exit(1)
