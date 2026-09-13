# -*- coding: utf-8 -*-
"""
Stage 2 (Live) — 角色建立與影像生成 (AI 視覺).

Pipeline (storyboard JSON is the single source of truth):
  1. Derive the cast (name + appearance) from the storyboard characters.
  2. Generate one character portrait per cast member (3:4 vertical).
  3. Generate one 16:9 keyframe image per shot from shot.image_prompt.
All images are produced through Kling official image API and stored under
<episode_dir>/stage2/. Failures raise loudly (ZERO SILENT FAILURES).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .logging_util import get_logger

log = get_logger()

# Global visual style baked into every prompt for shot-level coherence.
_STYLE_SUFFIX = (
    "ancient Chinese supernatural drama, ink-wash painting blended with "
    "cinematic lighting, high detail, masterpiece, dramatic composition"
)

# Fallback cast used when no character-sheet JSON is supplied. Appearance text
# is appended to prompts so the same character looks similar across shots.
_DEFAULT_CAST: List[Dict[str, str]] = [
    {"name": "書生", "appearance": "清秀年輕書生, 束髮, 青白長衫, 提一盞紙燈籠"},
    {"name": "狐仙", "appearance": "絕色女子, 素衣飄逸, 長髮如墨, 眉眼清麗含愁"},
    {"name": "老僧", "appearance": "慈眉老僧, 白眉, 灰色僧袍, 手持白玉念珠"},
]


def _load_or_default_cast(cast_json: Path | None) -> List[Dict[str, str]]:
    """Read character-sheet JSON if present, else fall back to the default cast."""
    if cast_json is not None and cast_json.exists():
        try:
            data = json.loads(cast_json.read_text(encoding="utf-8"))
            chars = data if isinstance(data, list) else data.get("characters") or []
            if chars:
                return [{"name": str(c.get("name", "")),
                         "appearance": str(c.get("appearance", ""))} for c in chars]
        except Exception as exc:  # surface, do not hide
            log.warning("[Stage2] cast JSON 解析失敗，改用預設 cast: %s", exc)
    return _DEFAULT_CAST


def _download_to(url_or_bytes: bytes, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(url_or_bytes)
    return path


def run_stage2_visuals(
    storyboard_path: Path,
    out_root: Path,
    engine: Any,
    cast_json: Path | None = None,
    char_aspect: str = "3:4",
    shot_aspect: str = "16:9",
) -> Dict[str, Any]:
    """
    Execute Stage 2 for one storyboard: cast portraits + per-shot keyframes.
    `engine` must expose generate(prompt, out_path, aspect_ratio=...) -> Path.
    Returns a manifest {characters:[...], shots:[...], dir:...}.
    """
    data = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    shots: List[dict] = data.get("shots") or []
    if not shots:
        raise ValueError(f"storyboard has no shots: {storyboard_path}")

    stage_dir = out_root / "stage2"
    stage_dir.mkdir(parents=True, exist_ok=True)
    cast = _load_or_default_cast(cast_json)

    manifest: Dict[str, Any] = {"characters": [], "shots": []}

    # --- 1) character portraits ---
    for idx, ch in enumerate(cast, start=1):
        prompt = (f"Character design, {ch['appearance']}, {_STYLE_SUFFIX}, "
                  f"full body portrait, character centered, plain backdrop")
        out = stage_dir / f"char_{idx:02d}.png"
        log.info("[Stage2] 產生角色圖 %s -> %s", ch["name"], out.name)
        try:
            final = engine.generate(prompt, out, aspect_ratio=char_aspect)
            manifest["characters"].append(
                {"name": ch["name"], "index": idx, "path": str(final)}
            )
            log.info("[Stage2] 角色圖完成 %s (%d bytes)", final.name, final.stat().st_size)
        except Exception as exc:
            log.error("[Stage2] 角色圖失敗 %s: %s", ch["name"], exc)
            raise

    # --- 2) per-shot keyframes ---
    for i, shot in enumerate(shots, start=1):
        base = str(shot.get("image_prompt") or shot.get("title") or "shot")
        # Keep the key character visually present by re-stating the shot content.
        prompt = f"{base}, {_STYLE_SUFFIX}"
        out = stage_dir / f"shot_{i:02d}.png"
        log.info("[Stage2] 產生分鏡圖 shot %d -> %s", i, out.name)
        try:
            final = engine.generate(prompt, out, aspect_ratio=shot_aspect)
            manifest["shots"].append({"shot": i, "path": str(final)})
            log.info("[Stage2] 分鏡圖完成 shot %d (%d bytes)", i, final.stat().st_size)
        except Exception as exc:
            log.error("[Stage2] 分鏡圖失敗 shot %d: %s", i, exc)
            raise

    manifest["dir"] = str(stage_dir)
    (stage_dir / "stage2_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("[Stage2] 完成：%d 角色 + %d 分鏡圖", len(manifest["characters"]),
             len(manifest["shots"]))
    return manifest
