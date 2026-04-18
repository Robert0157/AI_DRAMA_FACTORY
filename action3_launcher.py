#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Action 3 啟動器 - 啟動 Telegram 背景監聽守護程序
監控 CEO 的 [✅ 採用] 或 [❌ 放棄] 決策
"""
import subprocess
import sys
from pathlib import Path

print("\n" + "=" * 80)
print("📋 Action 3: Telegram 決策層守護程序")
print("=" * 80)
print("\n狀態:")
print("  ✅ Action 2 已完成 (4 個 Demo 已發送至 CEO Telegram)")
print("  ⏳ CEO 現在可以在 Telegram 上決策:")
print("     [✅ 採用] → 母帶進入佇列")
print("     [❌ 放棄] → 拒絕，返回")
print("  📊 每日配額: 10 首 (達到後自動觸發 Phase 2)")

print("\n" + "=" * 80)
print("🚀 正在啟動 Telegram 決策層守護程序...")
print("=" * 80)

try:
    cmd = [
        sys.executable,
        "-B",
        "scripts/gear1_prod/telegram_approval_gate.py",
        "--daemon"
    ]
    
    print("\n命令: " + " ".join(cmd))
    print("\n⏳ 守護程序運行中...\n")
    
    result = subprocess.run(cmd, cwd="f:/AI_DRAMA_FACTORY")
    
    if result.returncode == 0:
        print("\n✅ 守護程序啟動成功")
    else:
        print(f"\n⚠️  守護程序退出 (exit code: {result.returncode})")
        print("\n💡 如果看到 'asyncio event loop' 錯誤，請執行:")
        print("   python scripts/gear1_prod/telegram_approval_gate.py --enqueue")
    
    sys.exit(result.returncode)
    
except Exception as e:
    print(f"\n❌ 啟動失敗: {e}")
    sys.exit(1)
