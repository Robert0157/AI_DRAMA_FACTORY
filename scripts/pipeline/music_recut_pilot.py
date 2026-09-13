#!/usr/bin/env python3
"""Healing slow-cut recut pilot: zero-cost blind comparison (CEO 2026-09-13 decision).

Same 30 s master excerpt and the SAME delivered-clip pool as the first pilot,
so the only variable is the CUT STYLE:

  fixed              - current baseline: 6 x 5.0 s straight cuts.
  mir_v1             - approved production style: beat-snapped, 1.6-3.4 s.
  ambient_cinematic  - healing candidate: 4-8 s holds, phrase-level breathing.

Planning uses the production planner (`scripts/pipeline/music_timeline.py`),
rendering reuses the first pilot's ffmpeg recipes.  No generation cost.

Deliverables (lane identity hidden in filenames):
  CEO/03_樣片與交付/盲評2_療癒慢鏡/track_*.mp4 + 評分表.md
  CEO/03_樣片與交付/盲評2_療癒慢鏡_解答.json   (open after judging)

Usage:
  venv\\Scripts\\python.exe scripts\\pipeline\\music_recut_pilot.py
"""
from __future__ import annotations

import json
import random
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from scripts.pipeline import music_pilot as pilot  # noqa: E402  (reuse ffmpeg recipes)
from scripts.pipeline.music_timeline import (  # noqa: E402
    MusicAnalysis,
    SourceSpec,
    analyze_master,
    plan_from_analysis,
    validate_plan,
)

EXCERPT_START = 81.874          # same window as the first pilot (comparability)
EXCERPT_LEN = pilot.EXCERPT_SEC
FPS = pilot.FPS
# Ambient needs 4-8 s holds, so this run cuts an 8 s pool (patched onto the
# shared extraction helpers) instead of the first pilot's 5 s pool.
SEG_SEC = 8.0
SEG_FRAMES = int(SEG_SEC * FPS)
FIXED_FRAMES = int(5.0 * FPS)    # baseline lane keeps its original 5 s cuts
OUT_DIR = WORKSPACE / "CEO" / "03_樣片與交付" / "盲評2_療癒慢鏡"
KEY_PATH = WORKSPACE / "CEO" / "03_樣片與交付" / "盲評2_療癒慢鏡_解答.json"
WORK_DIR = WORKSPACE / "logs" / "music_recut_work"
SEED = 246574                    # same pool ordering seed as the first pilot


def excerpt_view(analysis: MusicAnalysis, start: float, length: float) -> MusicAnalysis:
    """Re-base the analysis onto [start, start+length] with times starting at 0."""
    inside = lambda t: start - 1e-9 <= t <= start + length + 1e-9  # noqa: E731
    shifted = lambda ts: [round(t - start, 3) for t in ts if inside(t)]  # noqa: E731
    rms_pairs = [(round(t - start, 3), r) for t, r in zip(analysis.rms_times, analysis.rms) if inside(t)]
    return replace(
        analysis,
        duration_sec=length,
        beats=shifted(analysis.beats),
        onsets=shifted(analysis.onsets),
        rms_times=[t for t, _ in rms_pairs],
        rms=[r for _, r in rms_pairs],
        peak_t=max(0.0, analysis.peak_t - start) if inside(analysis.peak_t) else 0.0,
        calm_t=max(0.0, analysis.calm_t - start) if inside(analysis.calm_t) else 0.0,
    )


def cut_shot(src: Path, out: Path, in_offset: float, frames: int, label: str) -> Path:
    """Frame-exact cut from a pool segment at the planner's in-point (re-encode)."""
    pilot.run([
        str(pilot.FFMPEG), "-y", "-v", "error",
        "-ss", f"{in_offset:.3f}", "-i", str(src),
        "-an", "-vf", f"setpts=PTS-STARTPTS,fps={FPS}",
        "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", str(out),
    ], label)
    return out


def render_plan_lane(lane: str, plan, lane_dir: Path) -> Path:
    """Render a planner-produced lane: cut each shot, lossless concat, master mux."""
    lane_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for shot in plan.shots:
        out = lane_dir / f"shot{shot.index:02d}.mp4"
        cut_shot(Path(shot.source), out, shot.in_offset_sec, shot.frames,
                 f"{lane} shot {shot.index}")
        clips.append(out)
    return _finish_lane(lane, clips, lane_dir)


def render_fixed_lane(lane: str, segments: list[pilot.Segment], lane_dir: Path) -> Path:
    """Current baseline: six straight 5.0 s cuts in sequential pool order."""
    lane_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for idx, seg in enumerate(segments[:6]):
        out = lane_dir / f"shot{idx:02d}.mp4"
        cut_shot(seg.path, out, 0.0, FIXED_FRAMES, f"{lane} shot {idx}")
        clips.append(out)
    return _finish_lane(lane, clips, lane_dir)


def _finish_lane(lane: str, clips: list[Path], lane_dir: Path) -> Path:
    """Concat + master excerpt mux + hard QC (shared by every lane)."""
    listing = lane_dir / "concat.txt"
    listing.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
    silent = lane_dir / f"{lane}_silent.mp4"
    pilot.run([str(pilot.FFMPEG), "-y", "-v", "error", "-f", "concat", "-safe", "0",
               "-i", str(listing), "-c", "copy", str(silent)], f"{lane} concat")
    final = WORK_DIR / f"{lane}_full.mp4"
    pilot.run([str(pilot.FFMPEG), "-y", "-v", "error",
               "-i", str(silent),
               "-ss", f"{EXCERPT_START}", "-t", f"{EXCERPT_LEN}", "-i", str(pilot.MASTER),
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", str(final)],
              f"{lane} master mux")
    pilot.verify_lane(final, lane)
    return final


def write_sheet() -> None:
    """Evaluation sheet the CEO fills before opening the answer key."""
    (OUT_DIR / "評分表.md").write_text(
        "# 盲評 2：療癒慢鏡 vs 現行（30 秒）\n\n"
        "同一段母帶、同一批素材；三支影片的差別只在剪輯時間軸。先看完三支再看解答。\n\n"
        "| 面向（1-5 分） | track_1 | track_2 | track_3 |\n"
        "|---|---|---|---|\n"
        "| 療癒／沉浸感 | | | |\n"
        "| 節拍與畫面的契合 | | | |\n"
        "| 呼吸感與停留是否自然 | | | |\n"
        "| 想再看一次 | | | |\n\n"
        "看完後再打開 `CEO/03_樣片與交付/盲評2_療癒慢鏡_解答.json`。\n",
        encoding="utf-8",
    )


def main() -> int:
    if not pilot.MASTER.is_file():
        print(f"[FATAL] master not found: {pilot.MASTER}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    # Redirect the shared pool extraction dir AND switch to the 8 s pool.
    pilot.WORK_DIR = WORK_DIR
    pilot.SEGMENT_SEC = SEG_SEC
    pilot.SEGMENT_FRAMES = SEG_FRAMES

    print("[1/4] analysing master + cutting segment pool ...")
    analysis = analyze_master(pilot.MASTER)
    view = excerpt_view(analysis, EXCERPT_START, EXCERPT_LEN)
    pool = pilot.build_pool()
    sources = [SourceSpec(path=str(seg.path), duration_sec=SEG_SEC) for seg in pool]
    print(f"  pool ready: {len(pool)} segments; excerpt beats={len(view.beats)} onsets={len(view.onsets)}")

    print("[2/4] planning lanes with the production planner ...")
    plan_mir = plan_from_analysis(view, EXCERPT_LEN, sources, style="mir_v1", seed=SEED)
    plan_amb = plan_from_analysis(view, EXCERPT_LEN, sources, style="ambient_cinematic", seed=SEED)
    for lane, plan in (("mir_v1", plan_mir), ("ambient_cinematic", plan_amb)):
        errors = validate_plan(plan)
        if errors:
            print(f"[FATAL] {lane} plan invalid: {errors}", file=sys.stderr)
            return 1
        print(f"  {lane}: {len(plan.shots)} shots "
              f"(mean {plan.duration_sec / len(plan.shots):.2f}s)")

    print("[3/4] rendering lanes ...")
    lanes = {
        "fixed": render_fixed_lane("fixed", pool, WORK_DIR / "fixed"),
        "mir_v1": render_plan_lane("mir_v1", plan_mir, WORK_DIR / "mir_v1"),
        "ambient_cinematic": render_plan_lane("ambient_cinematic", plan_amb, WORK_DIR / "ambient"),
    }

    print("[4/4] blind packaging ...")
    seed = random.SystemRandom().randint(100000, 999999)
    order = sorted(lanes)
    random.Random(seed).shuffle(order)
    mapping: dict[str, str] = {}
    for i, lane in enumerate(order, start=1):
        shutil.copy2(lanes[lane], OUT_DIR / f"track_{i}.mp4")
        mapping[f"track_{i}"] = lane
    write_sheet()
    key = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seed": seed,
        "excerpt": {"start_sec": EXCERPT_START, "length_sec": EXCERPT_LEN},
        "master_sha256": pilot.MASTER_SHA256,
        "mapping": mapping,
        "plans": {
            "mir_v1": {"shots": [s.index for s in plan_mir.shots],
                       "params": plan_mir.params},
            "ambient_cinematic": {"shots": [s.index for s in plan_amb.shots],
                                  "params": plan_amb.params},
        },
        "pool_sources": [str(p) for p in pilot.POOL_SOURCES],
    }
    KEY_PATH.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  samples: {OUT_DIR}")
    print(f"  key    : {KEY_PATH} (open only after judging)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
