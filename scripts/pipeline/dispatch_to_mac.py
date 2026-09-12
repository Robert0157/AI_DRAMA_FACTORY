#!/usr/bin/env python3
"""PC dispatcher: validated storyboard -> Mac render inbox (via the SMB share).

This is the PC half of the two-machine pipeline. It never renders anything.

  PC (control plane)   : story / storyboard generation + validation + dispatch
  Mac (execution plane): Toonflow review surface + Wan 2.1 480p render + assembly

The handoff root is the SAME directory on both hosts:
  PC  : Y:\\AI_Drama_Factory\\Auto_Drama\\output\\handoff   (Y: = \\\\192.168.2.200\\AI_Workspace)
  Mac : /Volumes/AI_Workspace/AI_Drama_Factory/Auto_Drama/output/handoff

Usage:
  python scripts/pipeline/dispatch_to_mac.py --topic 昭和101年空中都市 --variant 1
  python scripts/pipeline/dispatch_to_mac.py --topic 昭和101年空中都市 --variant 1 \
      --master-track "assets/audio/ceo_approved_beats/lofi/track.mp3" --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path, PurePosixPath

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from scripts.story_room.mv_strategy import validate_music_world_story  # noqa: E402

EXPERIMENT_ROOT = WORKSPACE / "Auto_Drama" / "output" / "sandbox" / "story_room" / "p3_experiment"

# Y: is the Mac's AI_Workspace share; fall back to an explicit env override.
SMB_ROOT = Path("Y:/AI_Drama_Factory")
# PurePosixPath keeps forward slashes even when this dispatcher runs on Windows.
# A plain Path rewrites "/Volumes/..." into "\Volumes\...", the Mac worker can
# not find such a file, and the job silently loses its master track (2026-09-12).
MAC_ROOT = PurePosixPath("/Volumes/AI_Workspace/AI_Drama_Factory")
DEFAULT_HANDOFF = SMB_ROOT / "Auto_Drama" / "output" / "handoff"


def to_mac_path(local: Path) -> str:
    """Translate a Y:\\ share path into the Mac-visible absolute POSIX path."""
    resolved = local.resolve()
    try:
        relative = resolved.relative_to(SMB_ROOT.resolve())
    except ValueError as exc:
        raise SystemExit(
            f"[FATAL] {resolved} is not under the Mac share {SMB_ROOT}. "
            "Assets referenced by a job must live on the shared volume."
        ) from exc
    return str(MAC_ROOT / relative.as_posix())


def enforce_steps_policy(steps: int | None, smoke_test: bool) -> None:
    """Reject sub-20 steps unless the run is explicitly marked as a smoke test.

    CEO decision 2026-09-12: every sample shown to the CEO and all production
    renders use the 20-step quality standard; 8-step style runs are for
    engineering plumbing tests only.
    """
    if steps is not None and steps < 20 and not smoke_test:
        raise SystemExit(
            f"[FATAL] steps={steps} is below the CEO quality standard (20). "
            "Add --smoke-test for a technical-only run."
        )


def handoff_root(override: str | None) -> Path:
    """Resolve the handoff directory on the PC side."""
    if override:
        return Path(override)
    root = DEFAULT_HANDOFF
    if not root.parent.parent.parent.parent.exists():  # Y: not mounted
        raise SystemExit(
            f"[FATAL] Mac share not mounted at {SMB_ROOT}. "
            "Map \\\\192.168.2.200\\AI_Workspace to Y: (or pass --handoff)."
        )
    return root


def sha256_of(path: Path) -> str:
    """Fingerprint a file for the manifest (master-track integrity)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_variant(topic: str, variant: int) -> dict:
    """Read one validated variant artifact from the P3 experiment."""
    path = EXPERIMENT_ROOT / topic / f"v{variant}.json"
    if not path.is_file():
        raise SystemExit(f"[FATAL] variant artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    story = payload.get("story") or {}
    validation = payload.get("production_validation") or {}
    if not payload.get("pass") or not validation.get("pass"):
        raise SystemExit(
            f"[FATAL] {path.name} did not pass the world-first contract: "
            f"{validation.get('findings')}"
        )
    return story


def build_job(story: dict, master_track: Path | None, limits: dict) -> dict:
    """Turn a validated story into a handoff.job.v1 manifest."""
    shots = story.get("shots") or []
    if limits.get("shots"):
        shots = shots[: limits["shots"]]

    job_shots = []
    for position, shot in enumerate(shots, 1):
        route = shot.get("generation_route") or {}
        plan = shot.get("generation_plan") or {}
        # Story Room emits `no`; storyboards promoted downstream use `shot_number`.
        shot_number = int(shot.get("shot_number") or shot.get("no") or position)
        unit_count = max(1, int(plan.get("unit_count", 1)))
        unit_duration = float(plan.get("unit_duration_sec", shot["duration_sec"]))
        if limits.get("units"):
            unit_count = min(unit_count, limits["units"])
        job_shots.append({
            "shot_number": shot_number,
            "duration_sec": float(shot["duration_sec"]),
            "prompt": shot["prompt"],
            "negative_prompt": shot.get("negative_prompt"),
            "seed": int(shot.get("seed", 260911)) + shot_number,
            "visual_anchor": shot.get("visual_anchor"),
            "route": route,
            "units": [
                {"index": index, "duration_sec": unit_duration}
                for index in range(1, unit_count + 1)
            ],
        })

    music: dict = {"master_track": None, "sha256": None}
    if master_track:
        music = {
            "master_track": to_mac_path(master_track),
            "sha256": sha256_of(master_track),
        }

    channel = (story.get("world_bible") or {}).get("channel", "lofi")
    episode_id = story.get("episode_id") or f"v{story.get('variant', 1):02d}"
    job_id = f"{time.strftime('%Y%m%dT%H%M%S')}_{story.get('title', 'untitled')[:24]}"
    job_id = "".join(ch for ch in job_id if ch not in '\\/:*?"<>|').replace(" ", "_")

    return {
        "schema": "handoff.job.v1",
        "job_id": job_id,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dispatched_by": "scripts/pipeline/dispatch_to_mac.py",
        "episode": {
            "series": "mv",
            "episode_id": episode_id,
            "channel": channel,
            "title": story.get("title"),
            "world_signature": (
                f"{(story.get('world_bible') or {}).get('treatment_id')}|"
                f"{(story.get('world_bible') or {}).get('palette')}"
            ),
        },
        "production": {
            "engine": "wan21_local",
            "resolution": "480p",
            "aspect_ratio": "9:16",
            "fps": 20,
            "steps": int(limits.get("steps") or 20),
            "cfg": 6.0,
            "assembly": "sequential_concat",
        },
        "music": music,
        "output": {"file": f"{episode_id}.mp4"},
        "shots": job_shots,
    }


def dispatch(job: dict, root: Path, dry_run: bool) -> Path:
    """Write the manifest into the Mac inbox with an atomic rename."""
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / f"{job['job_id']}.json"
    payload = json.dumps(job, ensure_ascii=False, indent=1)
    if dry_run:
        preview = root / f"{job['job_id']}.dryrun.json"
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_text(payload, encoding="utf-8")
        return preview
    staging = inbox / f".{job['job_id']}.tmp"
    staging.write_text(payload, encoding="utf-8")
    staging.replace(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--variant", type=int, required=True)
    parser.add_argument("--master-track", help="CEO-approved master track (Y:\\ share path)")
    parser.add_argument("--handoff", help="override the handoff root")
    parser.add_argument("--limit-shots", type=int, help="smoke test: first N shots only")
    parser.add_argument("--limit-units", type=int, help="smoke test: first N units per shot")
    parser.add_argument(
        "--steps", type=int,
        help="sampler steps override; production default is 20 (CEO quality standard)",
    )
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="acknowledge sub-20 steps for technical smoke tests only (never CEO samples)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    enforce_steps_policy(args.steps, args.smoke_test)

    story = load_variant(args.topic, args.variant)
    story.setdefault("variant", args.variant)

    validation = validate_music_world_story(story)
    if not validation["pass"]:
        raise SystemExit(f"[FATAL] world-first contract failed: {validation['findings']}")

    master = Path(args.master_track) if args.master_track else None
    if master and not master.is_file():
        raise SystemExit(f"[FATAL] master track not found: {master}")

    limits = {"shots": args.limit_shots, "units": args.limit_units, "steps": args.steps}
    job = build_job(story, master, limits)
    target = dispatch(job, handoff_root(args.handoff), args.dry_run)

    total_units = sum(len(shot["units"]) for shot in job["shots"])
    print(
        f"DISPATCHED {job['job_id']} shots={len(job['shots'])} units={total_units} "
        f"resolution={job['production']['resolution']} -> {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
