#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【Telegram Demo 直接發送工具】

用途：直接發送已生成的 Demo 文件至 CEO Telegram
（繞過混音引擎的發送邏輯）
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[0]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.gear1_prod.telegram_approval_gate import TelegramApprovalGate

print("\n" + "="*80)
print("📤 Telegram Demo 直接發送工具")
print("="*80)

gate = TelegramApprovalGate()
demo_root = _PROJECT_ROOT / "assets" / "audio" / "mastered_tracks" / "_demo_60sec"

# 待發送的 Pending 音軌
pending_tracks = [
    "Midnight screen, a gentle glow",
    "Midnight Study Lamp",
    "Vast Stillness"
]

print("\n【待發送的 Demo】")
for track_name in pending_tracks:
    demo_file = demo_root / f"{track_name}_demo_60sec.mp3"
    if demo_file.exists():
        size_mb = demo_file.stat().st_size / (1024*1024)
        print(f"  ✅ {track_name} ({size_mb:.1f} MB)")
    else:
        print(f"  ❌ {track_name} (檔案不存在)")

print("\n【開始發送】")
import asyncio
from telegram.ext import Application
import json

async def send_all_demos():
    """統一使用一個 Application 發送所有 Demo"""
    app = Application.builder().token(gate.telegram_token).build()
    sent_count = 0
    
    for track_name in pending_tracks:
        demo_file = demo_root / f"{track_name}_demo_60sec.mp3"
        if not demo_file.exists():
            print(f"⏭️  跳過 {track_name} (檔案不存在)")
            continue
        
        print(f"\n正在發送: {track_name}...")
        
        try:
            # 加入審核佇列
            track_id = gate.enqueue_track_for_approval(
                track_name=track_name,
                demo_path=demo_file,
            )
            print(f"  ✅ 已加入佇列 (ID: {track_id})")
            
            # 從 JSON 檔案讀取所有記錄，找出最新的
            with open(gate.approval_queue, "r", encoding="utf-8") as f:
                queue_data = json.load(f)
            
            # 在 queue 陣列中查找該 track_id
            target_record = None
            for record in queue_data.get("queue", []):
                if record.get("track_id") == track_id:
                    target_record = record
                    break
            
            if not target_record:
                print(f"  ❌ 佇列記錄不存在 (ID: {track_id})")
                continue
            
            # 發送音檔
            with open(demo_file, "rb") as f:
                msg = await app.bot.send_audio(
                    chat_id=gate.telegram_chat_id,
                    audio=f,
                    caption=f"🎵 新音軌試聽：{track_name}\n\n請做出決策👇",
                    parse_mode="Markdown",
                    reply_markup=gate._build_decision_keyboard(track_id),
                    read_timeout=30,
                    write_timeout=30,
                    connect_timeout=30,
                    pool_timeout=30,
                )
            
            # 更新記錄中的 demo_url_telegram
            target_record["demo_url_telegram"] = msg.audio.file_id
            target_record["status"] = "pending"
            
            with open(gate.approval_queue, "w", encoding="utf-8") as f:
                json.dump(queue_data, f, ensure_ascii=False, indent=2)
            
            print(f"  ✅ 已發送至 CEO Telegram (File ID: {msg.audio.file_id[:20]}...)")
            sent_count += 1
            
        except asyncio.TimeoutError as e:
            print(f"  ❌ 超時 (30秒): {e}")
        except Exception as e:
            print(f"  ❌ 發送失敗: {e}")
            import traceback
            traceback.print_exc()
    
    return sent_count

sent_count = asyncio.run(send_all_demos())

print("\n" + "="*80)
print(f"📊 發送完成: {sent_count}/{len(pending_tracks)} 首")
print("="*80)
print("\n✅ CEO 應該已在 Telegram 中收到新 Demo")
print("   請等待 CEO 的決策: [✅ 採用] 或 [❌ 放棄]\n")
