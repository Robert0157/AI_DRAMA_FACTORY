#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zaouli Test 002 影片生成批處理器

4 個 Kling Prompt：
- Shot A: 開場沙漠建立鏡頭
- Shot B: 細節特寫與節奏
- Shot C: 超現實舞蹈核心
- Shot D: 重拍定格與魔法
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.gear1_prod.kling_api_engine import KlingAPIEngine
from scripts.common.env_manager import config


ZAOULI_PROMPTS = [
    {
        "shot_name": "shot_01",
        "description": "開場沙漠建立鏡頭 (Setting the Scene)",
        "prompt": "A cinematic wide shot of a vast surreal African desert dune at golden hour. A single majestic Zaouli dancer stands completely still, wearing a vibrant, intricately patterned traditional mask and colorful fringe garments. Dramatic volumetric lighting, photorealistic, 8k resolution, hyper-detailed. Slow dolly in camera movement.",
    },
    {
        "shot_name": "shot_02",
        "description": "細節特寫與節奏 (The Beat Kicks In)",
        "prompt": "Extreme close-up shot on a dancer's feet adorned with intricate silver ankle bells. The feet are rapidly and fiercely stomping on fine desert sand, kicking up dynamic clouds of dust. High shutter speed, hyper-detailed textures, cinematic lighting. Slight camera shake, fast and energetic dynamic motion.",
    },
    {
        "shot_name": "shot_03",
        "description": "超現實舞蹈核心 (The Core Dance)",
        "prompt": "A low angle medium shot tracking a surreal African dancer. The dancer's upper body and mask are completely stoic and motionless, while their lower body and legs move at an incredibly fast, blurring speed in a traditional Zaouli dance. Vividly colored costume fringes sway rapidly. Realistic physics, high contrast, surrealistic mood, 4K, dynamic sweeping camera.",
    },
    {
        "shot_name": "shot_04",
        "description": "重拍定格與魔法元素 (The Climax)",
        "prompt": "Dynamic fast zoom-in shot of a tribal dancer stomping hard on the ground. Glowing magical dust and subtle light ripples emit from the ground where the foot impacts. Hyper-realistic, dramatic shadows, neon accents on traditional tribal patterns, cinematic action composition.",
    },
]


def generate_zaouli_shots(job_id: str = "zaouli_test_002") -> None:
    """
    批量生成 4 個 Zaouli 鏡頭。
    
    每個鏡頭約 5 秒，最終用於縫合成完整影片。
    """
    workspace = Path(config.workspace_root)
    shots_dir = workspace / "assets" / "video_clips" / job_id / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[ZAOULI_GENERATOR] generating {len(ZAOULI_PROMPTS)} shots for {job_id}")
    print(f"[ZAOULI_GENERATOR] output directory: {shots_dir}")
    
    # 初始化 Kling API
    kling = KlingAPIEngine()
    
    for idx, shot_config in enumerate(ZAOULI_PROMPTS):
        shot_name = shot_config["shot_name"]
        description = shot_config["description"]
        prompt = shot_config["prompt"]
        
        print(f"\n[ZAOULI_GENERATOR] [{idx+1}/{len(ZAOULI_PROMPTS)}] generating {shot_name}")
        print(f"  Description: {description}")
        print(f"  Prompt: {prompt[:60]}...")
        
        # 建立 shot 配置
        shot_config_obj = {
            "shot_id": shot_name,
            "prompt": prompt,
            "duration": 5,  # 5 秒
        }
        
        try:
            # 使用 Kling API 生成影片
            output_path = shots_dir / f"{shot_name}.mp4"
            
            # ⚠️ TODO: 實際呼叫 Kling API
            # 目前使用佔位符，待整合真實 API
            print(f"  [PENDING] awaiting Kling API integration: {output_path}")
            
        except Exception as exc:
            print(f"  [ERROR] failed to generate {shot_name}: {exc}")
            raise
    
    print(f"\n[ZAOULI_GENERATOR] all shots queued for generation")


if __name__ == "__main__":
    try:
        generate_zaouli_shots()
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}")
        sys.exit(1)
