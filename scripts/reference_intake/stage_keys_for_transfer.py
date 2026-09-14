#!/usr/bin/env python3
"""Stage stock-API keys from the PC .env into a transfer file (PC side only).

The staged file is meant to be scp'd to the target host and imported there via
scripts/reference_intake/install_keys_from_env.py, which deletes it afterwards.
Values are never printed; only the staged file path and key count are shown.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

KEYS = (
    "PEXELS_API_KEY",
    "PIXABAY_API_KEY",
    "UNSPLASH_ACCESS_KEY",
    # Vision analysis for the CP-D world-proposal engine (Gemini Flash).
    "GEMINI_API_KEY",
    "GLM_4V_API_KEY",
)
WORKSPACE = Path(__file__).resolve().parents[2]


def main() -> int:
    values = dotenv_values(WORKSPACE / ".env")
    lines: list[str] = []
    for key in KEYS:
        value = (values.get(key) or "").strip().strip('"').strip("'")
        if value:
            lines.append(f"{key}={value}")
    if not lines:
        print("[FATAL] no stock keys found in .env", flush=True)
        return 1
    target = Path(os.environ.get("TEMP", "/tmp")) / "reference_keys_stage.env"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"STAGED {len(lines)} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
