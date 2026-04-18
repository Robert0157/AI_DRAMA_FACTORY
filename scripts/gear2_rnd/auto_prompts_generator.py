#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大腦擴寫器：基於種子 prompts，自動生成 60+ 個相似風格的分鏡 Kling prompt。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 種子 prompts（前 4 個不變）
SEED_PROMPTS = [
    "A cinematic wide shot of a vast surreal African desert dune at golden hour. A single majestic Zaouli dancer stands completely still, wearing a vibrant, intricately patterned traditional mask and colorful fringe garments. Dramatic volumetric lighting, photorealistic, 8k resolution, hyper-detailed. Slow dolly in camera movement.",
    "Extreme close-up shot on a dancer's feet adorned with intricate silver ankle bells. The feet are rapidly and fiercely stomping on fine desert sand, kicking up dynamic clouds of dust. High shutter speed, hyper-detailed textures, cinematic lighting. Slight camera shake, fast and energetic dynamic motion.",
    "A low angle medium shot tracking a surreal African dancer. The dancer's upper body and mask are completely stoic and motionless, while their lower body and legs move at an incredibly fast, blurring speed in a traditional Zaouli dance. Vividly colored costume fringes sway rapidly. Realistic physics, high contrast, surrealistic mood, 4K, dynamic sweeping camera.",
    "Dynamic fast zoom-in shot of a tribal dancer stomping hard on the ground. Glowing magical dust and subtle light ripples emit from the ground where the foot impacts. Hyper-realistic, dramatic shadows, neon accents on traditional tribal patterns, cinematic action composition.",
]

# 擴寫樣板（保持風格一致）
EXPANSION_TEMPLATES = [
    "Macro overhead drone shot of a Zaouli dancer creating geometric dust patterns on surreal desert dunes. Neon cyan light traces follow footsteps. Volumetric lighting, 8k, dynamic movement.",
    "Extreme close-up of intricately patterned tribal mask. Neon accents glow as deep bass reverberates. Hyper-detailed texture focus, photorealistic, high contrast lighting.",
    "Wide tracking shot of multiple phantom dancers appearing and disappearing through swirling desert dust clouds. Surrealistic atmosphere, ethereal silhouettes, glowing neon accents, cinematic depth of field.",
    "Fast cuts of rapid footsteps, ankle bells rattling in extreme close-up macro photography. Dust particles suspended mid-air catching light. High shutter speed, detailed textures, dynamic motion.",
    "Surreal medium shot: dancer's costume fringe creates trails of glowing light as legs move at inhuman speeds. Upper body completely frozen. Neon cyan and gold color grading, dreamlike mood.",
    "Dynamic low-altitude drone flyover of tribal dancer surrounded by geometric glow patterns. Desert sand reflects magical light ripples. Volumetric atmosphere, 4K cinematic composition.",
    "Extreme close-up of dancer's hands adorned with mystical jewelry, moving in ceremonial gestures against blurred desert backdrop. Neon glow on metals, photorealistic detail, surreal lighting.",
    "Wide shot of starlit desert night. Zaouli dancer in silhouette wearing glow-edged mask and costume. Swirling cosmic dust clouds, ethereal atmosphere, slow panning camera.",
    "Split-screen shot: left side crystal-clear close-up of facial mask details, right side kaleidoscopic abstraction of spinning dancer. Surrealistic visual synthesis, high contrast neon colors.",
    "Macro shot of sweat droplets splashing from intense stomp, catching light particles and creating rainbow refractions. Slow-motion capture, photorealistic, hyper-detailed.",
    "Aerial shot spinning around stationary dancer while legs perform impossible-speed movements. Desert landscape rotates. Dramatic shadows, volumetric light shafts, cinematic 8k.",
    "Extreme close-up of traditional tribal mask cracks revealing nebula cosmic energy within. Neon accents flash with music beat. Photorealistic texture meets surrealism, high contrast.",
]

def generate_all_prompts(target_shots: int = 72) -> list[dict]:
    """
    生成完整的分鏡列表。
    
    前 4 個：種子 prompts（不變）
    後續：循環擴寫樣板，直到達到目標數量
    """
    prompts = []
    
    # 前 4 個：種子 prompt
    for i, seed in enumerate(SEED_PROMPTS, 1):
        prompts.append({
            "shot_id": f"shot_{i:02d}",
            "duration": 5,
            "kling_prompt": seed,
            "is_seed": True,
        })
    
    # 後續：循環擴寫
    remaining = target_shots - len(SEED_PROMPTS)
    for i in range(remaining):
        template = EXPANSION_TEMPLATES[i % len(EXPANSION_TEMPLATES)]
        prompts.append({
            "shot_id": f"shot_{len(SEED_PROMPTS) + i + 1:02d}",
            "duration": 5,
            "kling_prompt": template,
            "is_seed": False,
            "template_idx": i % len(EXPANSION_TEMPLATES),
        })
    
    return prompts


def chunk_into_volumes(prompts: list[dict], shots_per_volume: int = 12) -> dict[int, list[dict]]:
    """
    將分鏡分卷：每卷 12 個 shot (60 秒)。
    """
    volumes = {}
    for vol_idx, i in enumerate(range(0, len(prompts), shots_per_volume), 1):
        volumes[vol_idx] = prompts[i:i + shots_per_volume]
    return volumes


def main(job_id: str = "zaouli_test_002", target_shots: int = 72) -> None:
    """
    主入口：生成所有 prompts 並分卷輸出。
    """
    print(f"[AUTO-PROMPTS] generating {target_shots} shots...")
    
    # 生成所有 prompts
    all_prompts = generate_all_prompts(target_shots)
    print(f"[AUTO-PROMPTS] generated {len(all_prompts)} prompts")
    
    # 分卷
    volumes = chunk_into_volumes(all_prompts, shots_per_volume=12)
    print(f"[AUTO-PROMPTS] chunked into {len(volumes)} volumes")
    
    # 輸出分卷
    output_dir = Path(_PROJECT_ROOT) / "assets" / "scripts" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for vol_num, vol_shots in volumes.items():
        vol_path = output_dir / f"vol_{vol_num}.json"
        with open(vol_path, "w", encoding="utf-8") as fh:
            json.dump(vol_shots, fh, indent=2, ensure_ascii=False)
        print(f"[AUTO-PROMPTS] wrote {vol_path.name} ({len(vol_shots)} shots, {len(vol_shots)*5}s)")
    
    print(f"[AUTO-PROMPTS] ✅ complete: {len(volumes)} volumes × 60s each = {len(volumes)*60}s total")


if __name__ == "__main__":
    main(job_id="zaouli_test_002", target_shots=72)
