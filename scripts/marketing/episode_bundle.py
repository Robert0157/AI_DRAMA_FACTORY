#!/usr/bin/env python3
"""Episode bundle builder/validator for video-native Shorts (A-line MV 175s etc.).

Bridges the content pipeline to the Mac upload automation:
  - validates the video (vertical 9:16-ish, duration <= 185s) via ffprobe when available
  - builds an `episode-short-v1` sidecar (title/description/tags/privacy/channel)
  - deposits <video>.mp4 + <video>.episode.json into Y:/Shorts_Queue/<channel>/episodes/

The Mac side picks the oldest sidecar first via publish_episode_shorts.sh (FIFO),
uploads with youtubeuploader, archives to episodes/_uploaded/ and appends the same
upload_history.jsonl the distribution ledger reads.

CEO policy: default privacy is "unlisted" (fail-closed); pass --privacy public only
after the episode passed its CP checkpoint.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "episode-short-v1"
VALID_PRIVACY = {"public", "unlisted", "private"}
MAX_DURATION_S = 185.0  # 175s target + tolerance
ASPECT_TOLERANCE = 0.06  # w/h within [9/16-0.06, 9/16+0.06] => [0.50, 0.62]
SOURCE_SYSTEM = "AI_DRAMA_FACTORY_WINDOWS"


def resolve_mac_root(explicit: str | None = None) -> Path:
    """Locate the Mac workspace tree (Y: on Windows, /Volumes/... on macOS)."""
    import os

    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("AI_DRAMA_MAC_ROOT")
    if env:
        candidates.append(Path(env))
    candidates.append(Path("/Volumes/AI_Workspace/AI_Drama_Factory"))
    candidates.append(Path("Y:/AI_Drama_Factory"))
    for cand in candidates:
        try:
            if cand.is_dir() and (cand / "Shorts_Queue").is_dir():
                return cand
        except OSError:
            continue
    return candidates[-1]


def _coerce_tags(tags: Any) -> Any:
    """Comma string -> list; other non-list values pass through so the validator can flag them."""
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return tags


def build_sidecar(
    *,
    video_file: str,
    channel: str,
    title: str,
    description: str,
    tags: list[str],
    privacy: str = "unlisted",
    slot_hint: str | None = None,
    contains_synthetic_media: bool = True,
    made_for_kids: bool = False,
) -> dict[str, Any]:
    """Compose the episode-short-v1 sidecar payload."""
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "video_file": video_file,
        "channel": channel,
        "title": (title or "").strip(),
        "description": description or "",
        "tags": _coerce_tags(tags),
        "privacy": privacy,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_system": SOURCE_SYSTEM,
        "containsSyntheticMedia": bool(contains_synthetic_media),
        "selfDeclaredMadeForKids": bool(made_for_kids),
    }
    if slot_hint:
        out["slot_hint"] = slot_hint
    return out


def validate_sidecar(body: dict[str, Any], video_path: Path | None = None) -> list[str]:
    """Return a list of human-readable problems (empty = valid)."""
    errs: list[str] = []
    if body.get("schema") != SCHEMA:
        errs.append(f"schema 必須為 {SCHEMA!r}")
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        errs.append("title 缺失或空白")
    elif len(title) > 100:
        errs.append("title 超過 100 字（YouTube 上限）")
    desc = body.get("description")
    if not isinstance(desc, str):
        errs.append("description 必須為字串")
    elif len(desc) > 5000:
        errs.append("description 超過 5000 字")
    tags = body.get("tags")
    if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
        errs.append("tags 必須為非空字串列表")
    if body.get("privacy") not in VALID_PRIVACY:
        errs.append(f"privacy 必須為 {sorted(VALID_PRIVACY)} 之一")
    if not str(body.get("channel", "")).strip():
        errs.append("channel 缺失")
    if video_path is not None:
        if not video_path.is_file():
            errs.append(f"影片不存在：{video_path}")
        elif str(body.get("video_file", "")) != video_path.name:
            errs.append("video_file 必須與實體檔名一致")
    return errs


def probe_video(path: Path) -> dict[str, float] | None:
    """ffprobe duration + dimensions; None when ffprobe is unavailable."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.check_output(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "json", str(path),
            ],
            timeout=40,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    try:
        payload = json.loads(out.decode("utf-8", errors="replace"))
        stream = (payload.get("streams") or [{}])[0]
        duration = float((payload.get("format") or {}).get("duration", 0.0) or 0.0)
        return {"duration": duration, "width": float(stream.get("width", 0)), "height": float(stream.get("height", 0))}
    except (ValueError, IndexError, KeyError):
        return None


def validate_video(path: Path) -> list[str]:
    """Geometry/duration checks; ffprobe missing -> warning line only."""
    info = probe_video(path)
    if info is None:
        return ["[warn] ffprobe 不可用；跳過時長/比例檢查"]
    errs: list[str] = []
    duration = info["duration"]
    width = info["width"]
    height = info["height"]
    if duration <= 0:
        errs.append("無法讀取影片時長")
    elif duration > MAX_DURATION_S:
        errs.append(f"時長 {duration:.1f}s 超過 {MAX_DURATION_S:.0f}s（須為 Shorts 容許範圍）")
    if height > 0 and width > 0:
        if height <= width:
            errs.append("非直式影片（height 必須 > width）")
        else:
            ratio = width / height
            if not (9 / 16 - ASPECT_TOLERANCE <= ratio <= 9 / 16 + ASPECT_TOLERANCE):
                errs.append(f"長寬比 {width:.0f}x{height:.0f} 偏離 9:16（w/h={ratio:.3f}）")
    return errs


def deposit(sidecar: dict[str, Any], video_path: Path, mac_root: Path, dry_run: bool) -> Path:
    """Copy video + write sidecar into Shorts_Queue/<channel>/episodes/."""
    target_dir = mac_root / "Shorts_Queue" / str(sidecar["channel"]) / "episodes"
    target_video = target_dir / video_path.name
    target_sidecar = target_dir / f"{video_path.stem}.episode.json"
    if dry_run:
        print(f"[dry-run] would deposit -> {target_video}")
        print(f"[dry-run] would write   -> {target_sidecar}")
        return target_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(video_path, target_video)
    target_sidecar.write_text(json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8")
    return target_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", help="episode mp4 path")
    parser.add_argument("--channel", default="lofi", help="target channel (lofi / light_music)")
    parser.add_argument("--title")
    parser.add_argument("--description", default="")
    parser.add_argument("--description-file", help="read description from a text file")
    parser.add_argument("--tags", default="", help="comma-separated tags")
    parser.add_argument("--privacy", default="unlisted", choices=sorted(VALID_PRIVACY))
    parser.add_argument("--slot-hint", help="preferred upload window hint (e.g. wed-sat)")
    parser.add_argument("--mac-root", help="Mac workspace root (auto-detected)")
    parser.add_argument("--skip-probe", action="store_true", help="skip ffprobe geometry checks")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate", help="validate an existing .episode.json file and exit")
    args = parser.parse_args(argv)

    if args.validate:
        sidecar_path = Path(args.validate)
        try:
            body = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[error] 無法讀取 sidecar: {exc}", file=sys.stderr)
            return 1
        video_path = sidecar_path.with_name(str(body.get("video_file", ""))) if body.get("video_file") else None
        errs = validate_sidecar(body, video_path)
        for err in errs:
            print(f"[invalid] {err}")
        print("VALID" if not errs else "INVALID")
        return 0 if not errs else 1

    if not args.video:
        parser.error("需要 --video（或使用 --validate）")
    video_path = Path(args.video)
    if not video_path.is_file():
        print(f"[error] 找不到影片：{video_path}", file=sys.stderr)
        return 1

    description = args.description
    if args.description_file:
        description = Path(args.description_file).read_text(encoding="utf-8")
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    sidecar = build_sidecar(
        video_file=video_path.name,
        channel=args.channel,
        title=args.title or video_path.stem,
        description=description,
        tags=tags,
        privacy=args.privacy,
        slot_hint=args.slot_hint,
    )

    problems = validate_sidecar(sidecar, video_path)
    if not args.skip_probe:
        probe_results = validate_video(video_path)
        problems += [p for p in probe_results if not p.startswith("[warn]")]
        for warn_line in [p for p in probe_results if p.startswith("[warn]")]:
            print(warn_line)
    if problems:
        for problem in problems:
            print(f"[invalid] {problem}", file=sys.stderr)
        print("[abort] 打包中止（fail-closed）；修正後重試", file=sys.stderr)
        return 1

    mac_root = resolve_mac_root(args.mac_root)
    target_dir = deposit(sidecar, video_path, mac_root, args.dry_run)
    print(f"BUNDLE ok channel={sidecar['channel']} privacy={sidecar['privacy']} -> {target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
