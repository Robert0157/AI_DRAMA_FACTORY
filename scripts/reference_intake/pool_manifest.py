#!/usr/bin/env python3
"""Build the first-frame pool manifest under CEO/02_素材與CP-D/.

Pool sources (2026-09-14):
  - first_frames/                    system-generated Flux first frames
  - VEO_download/                    CEO manual Flow/VEO image exports (top level)
  - VEO_download/Approved_material/  CEO-vetted stock material (daily intake picks)

Writes manifest.json (schema ceo.first_frame_pool.v1) with per-file sha256,
dimensions and naming checks. Images themselves are never committed to git.

Usage:
  python scripts/reference_intake/pool_manifest.py
  python scripts/reference_intake/pool_manifest.py --root "F:/AI_DRAMA_FACTORY/CEO/02_素材與CP-D"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from PIL import Image  # type: ignore
except Exception:  # noqa: BLE001 - dims are best-effort when Pillow is unavailable
    Image = None  # type: ignore

WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = WORKSPACE / "CEO" / "02_素材與CP-D"
SOURCE_DIRS = ("first_frames", "VEO_download", "VEO_download/Approved_material")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
FORBIDDEN = set('\\/:*?"<>|｜')
COPY_SUFFIX = " - 複製"


def naming_issues(name: str) -> list[str]:
    """Flags matching CEO/00_命名規則 (spaces, copy suffixes)."""
    issues: list[str] = []
    if " " in name:
        issues.append("space")
    if COPY_SUFFIX in name:
        issues.append("copy-suffix")
    if any(ch in FORBIDDEN for ch in name):
        issues.append("forbidden-char")
    if len(name) > 60:
        issues.append("too-long")
    return issues


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(root: Path) -> dict:
    files: list[dict] = []
    for source in SOURCE_DIRS:
        directory = root / source
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            entry: dict = {
                "dir": source,
                "name": path.name,
                "ext": path.suffix.lower(),
                "size": path.stat().st_size,
                "naming_issues": naming_issues(path.name),
            }
            entry["sha256"] = sha256_of(path)
            if Image is not None:
                try:
                    with Image.open(path) as im:
                        entry["dims"] = [im.width, im.height, im.format]
                except Exception:  # noqa: BLE001 - keep the record even if unreadable
                    entry["dims"] = None
            files.append(entry)
    return {
        "schema": "ceo.first_frame_pool.v1",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_dirs": list(SOURCE_DIRS),
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="pool root override (defaults to CEO/02_素材與CP-D)")
    args = parser.parse_args()
    root = Path(args.root) if args.root else DEFAULT_ROOT
    payload = build(root)
    target = root / "manifest.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    flagged = sum(1 for f in payload["files"] if f["naming_issues"])
    print(f"POOL files={len(payload['files'])} naming_issues={flagged} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
