#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import random
import shutil
import sys
import traceback
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.gear1_prod.suno_lofi_generator import _generate_prompt_batch
from scripts.gear1_prod.suno_api_engine import generate_instrumental


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch generate/download Suno tracks into vault")
    parser.add_argument("--target-new", type=int, default=10, help="Minimum new tracks to add")
    parser.add_argument("--attempts", type=int, default=15, help="Max prompt attempts")
    parser.add_argument("--seed", type=int, default=0, help="Random seed (0=auto)")
    args = parser.parse_args()

    seed = args.seed if args.seed != 0 else random.randint(1000, 999999)
    random.seed(seed)

    workspace = Path(config.workspace_root)
    vault_dir = workspace / "assets" / "audio" / "vault_ready_for_mix"
    vault_dir.mkdir(parents=True, exist_ok=True)

    before = len([p for p in vault_dir.iterdir() if p.is_file()])
    print(f"[BATCH] seed={seed}")
    print(f"[BATCH] vault={vault_dir}")
    print(f"[BATCH] before_count={before}")

    batch = _generate_prompt_batch(count=args.attempts, seed=seed)
    added = 0
    used_attempts = 0

    for idx, item in enumerate(batch, start=1):
        used_attempts += 1
        title = item.get("title", f"SunoBatch_{idx}")
        prompt = item.get("prompt", "")
        style = item.get("tags", "")

        print(f"\n[{idx:02d}] generating: {title}")
        try:
            result = generate_instrumental(
                prompt=prompt,
                style=style,
                title=title,
                download=True,
            )
            local_paths = result.get("local_paths", [])
            if not local_paths:
                print("  [WARN] no local_paths returned")
                continue

            for p in local_paths:
                src = Path(p)
                if not src.exists():
                    print(f"  [WARN] downloaded file missing: {src}")
                    continue

                dst = vault_dir / src.name
                if dst.exists():
                    dst = vault_dir / f"{dst.stem}_{idx:02d}{dst.suffix}"

                shutil.copy2(src, dst)
                added += 1
                print(f"  [OK] copied -> {dst.name}")

                if added >= args.target_new:
                    print("\n[TARGET] reached requested new track count.")
                    break

            if added >= args.target_new:
                break

        except Exception as e:  # noqa: BLE001
            print(f"  [ERR] generation failed: {e}")
            traceback.print_exc()

    after = len([p for p in vault_dir.iterdir() if p.is_file()])
    print("\n" + "=" * 70)
    print(f"[SUMMARY] attempts_used={used_attempts}, added={added}, before={before}, after={after}")
    print("=" * 70)

    if added < args.target_new:
        sys.exit(2)


if __name__ == "__main__":
    main()
