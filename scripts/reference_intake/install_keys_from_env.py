#!/usr/bin/env python3
"""Import stock-API keys from a transient env file into the host keychain.

Used to move keys to the Mac without ever echoing the values (the file is
deleted after a fully successful import). Values are never printed; only the
per-key OK / SKIP / FAILED status is shown.

Usage (on the target host):
  python install_keys_from_env.py /tmp/reference_keys.env
"""
from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from scripts.common.secrets_manager import get_secrets  # noqa: E402

KEYS = (
    "PEXELS_API_KEY",
    "PIXABAY_API_KEY",
    "UNSPLASH_ACCESS_KEY",
    # Vision analysis for the CP-D world-proposal engine (Gemini Flash).
    "GEMINI_API_KEY",
    "GLM_4V_API_KEY",
)


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser (quotes and blank lines tolerated)."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: install_keys_from_env.py <env-file>", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    if not source.is_file():
        print(f"[FATAL] source env file not found: {source}", file=sys.stderr)
        return 2

    data = parse_env_file(source)
    secrets = get_secrets()
    imported: list[str] = []
    expected: list[str] = []
    for key in KEYS:
        value = (data.get(key) or "").strip()
        if not value:
            print(f"{key}: SKIP (absent in source)")
            continue
        expected.append(key)
        ok = secrets.set(key, value)
        print(f"{key}: {'IMPORTED' if ok else 'FAILED'}")
        if ok:
            imported.append(key)

    if expected and len(imported) == len(expected):
        source.unlink()
        print("SOURCE_DELETED")
    print(f"SUMMARY imported={len(imported)}/{len(expected)}")
    return 0 if imported else 1


if __name__ == "__main__":
    raise SystemExit(main())
