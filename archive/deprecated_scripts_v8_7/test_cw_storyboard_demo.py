#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenClaw 故事板生成器 - 演示版本（帶模擬數據）
用於展示完整的工作流，無需實時 API 呼叫
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict

# 模擬的分鏡表數據
MOCK_STORYBOARD = [
    {
        "frame": 1,
        "visual_description": "Wide shot of a corporate office at 9:55 AM, fluorescent lights flickering, clock on wall showing 9:55. Main character sits at desk with laptop, coffee cup, documents scattered everywhere. Surreal distortion effect like a David Lynch painting, with dark shadows creeping across the floor. Color palette: cold blues, grays, and sickly greens.",
        "narration_or_subtitle": "每天早上，同樣的景象。只是時間好像走得特別慢......"
    },
    {
        "frame": 2,
        "visual_description": "Close-up of clock face, hands moving in reverse and forward erratically. Time stretches and warps. Surreal animation style mixing rotoscope and abstract elements. The clock face dissolves into a swirling vortex of office supplies (pens, papers, sticky notes).",
        "narration_or_subtitle": "10 分鐘遲到。只是 10 分鐘。"
    },
    {
        "frame": 3,
        "visual_description": "Character enters conference room. Boss's face zooms in unnaturally close, mouth moving but no sound (like a haunting silent film). Surreal perspective distortion. Other colleagues morph into shadowy figures. Red emergency light casting ominous glow. Atmosphere reminiscent of German Expressionism.",
        "narration_or_subtitle": "「你為什麼遲到了？」導演的表情，我見過一百次。"
    },
    {
        "frame": 4,
        "visual_description": "Split-screen: top half shows character typing frantically at desk surrounded by floating documents and code scrolling in air (Tron-like digital aesthetic). Bottom half shows the character's hands trapped in crystalline ice blocks. Surreal color correction with oversaturated reds and blues.",
        "narration_or_subtitle": "2 小時寫檢討書。400 字。每個字都是懺悔。"
    },
    {
        "frame": 5,
        "visual_description": "Character submitting the document. The paper transforms into a feather, then into ashes as it reaches boss's hands. The boss dissolves into countless copies of the same face. Surreal gravity effect where the room rotates 90 degrees. Film noir lighting with extreme contrast.",
        "narration_or_subtitle": "這不是懺悔。這是儀式。"
    },
    {
        "frame": 6,
        "visual_description": "Wide shot returning to desk at day's end, same fluorescent lights, clock now showing 6:00 PM. The character has become semi-transparent, almost melting into the chair. Surreal temporal distortion: multiple versions of the character's face visible like memories. Fade to black with only the clock visible, hands frozen at 10:10.",
        "narration_or_subtitle": "明天又會遲到。然後重複同樣的儀式。永遠不變。"
    }
]


def display_demo():
    """展示演示版本分鏡表"""

    print("\n" + "=" * 120)
    print("🎬 【OpenClaw 微電影故事板】開會遲到 10 分鐘，卻要花 2 小時寫檢討書")
    print("=" * 120)
    print("🎭 美學風格: Theme_Zit1izlGZq0 (超現實黑色幽默)")
    print("🎵 配樂風格: 深邃、陰沉的電影配樂，帶有忐忑不安的緊張感")
    print("=" * 120 + "\n")

    for frame_data in MOCK_STORYBOARD:
        frame_num = frame_data["frame"]
        visual = frame_data["visual_description"]
        narration = frame_data["narration_or_subtitle"]

        print(f"\n【分鏡 {frame_num}】")
        print("┌─────────────────────────────────────────────────────────")
        print("│ 📸 Visual Prompt (給 Midjourney/DALL-E 3 用):")
        print(f"│ {visual}")
        print("├─────────────────────────────────────────────────────────")
        print("│ 🎙️ 旁白/字幕 (配音指引):")
        print(f"│ {narration}")
        print("└─────────────────────────────────────────────────────────")

    print("\n" + "=" * 120)
    print("✅ 分鏡表完成！")
    print("=" * 120)

    output = {
        "metadata": {
            "title": "【微電影短劇】開會遲到 10 分鐘，卻要花 2 小時寫檢討書",
            "style_theme": "Theme_Zit1izlGZq0",
            "pain_point": "開會遲到 10 分鐘，卻要花 2 小時寫檢討書",
            "audio_style": "Dark, cinematic electronic score with melancholic undertones",
            "visual_style": "Surreal, David Lynch-inspired aesthetic with German Expressionism",
            "generated_at": datetime.now().isoformat(),
            "total_frames": 6,
            "demo_mode": True
        },
        "frames": MOCK_STORYBOARD,
        "usage_instructions": {
            "midjourney": "直接複製 visual_description 投放給 Midjourney v6: /imagine prompt: [visual_description]",
            "narration": "使用 narration_or_subtitle 進行配音、字幕或音效製作",
            "music": "配樂風格: 深邃、陰沉的電影配樂，帶有忐忑不安的緊張感，樂器包括小提琴、鋼琴、合成器",
            "video_edit": "建議在 DaVinci Resolve 或 Adobe Premiere 中組合所有元素"
        }
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"storyboard_demo_meeting_incident_{timestamp}.json"

    output_dir = Path(__file__).parent.parent / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 已儲存: {output_path}")
    print(f"\n📋 完整 JSON 輸出:\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))

    print(f"\n✨ 演示完成！")
    print("【快速開始】")
    print("  1️⃣  Midjourney: 複製任意 visual_description 並前綴 '/imagine prompt:'")
    print("  2️⃣  配音: 使用 narration_or_subtitle 透過 ElevenLabs 或本地 TTS")
    print("  3️⃣  配樂: 使用 audio_style 提示詞透過 Udio 或 Suno 生成音樂")
    print("  4️⃣  合成: 在視頻編輯軟體中組合所有元素\n")


if __name__ == "__main__":
    print("\n" + "🎬" * 60)
    print("OpenClaw 微電影故事板生成器 - 演示版本")
    print("🎬" * 60)
    print(f"\n📊 演示使用真實風格資料庫中抽取的美學")

    display_demo()