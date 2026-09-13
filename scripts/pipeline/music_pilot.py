#!/usr/bin/env python3
"""Music timeline pilot: one 30 s excerpt, three cut strategies, blind package.

The CEO pilot question: does a MIR-driven (beat/onset/energy) timeline make the
footage feel "chosen" instead of merely "delivered"?  Three lanes are rendered
from the SAME segment pool and the SAME 30 s master excerpt so the only
variable is EDIT LOGIC:

  Lane A - current baseline: fixed 5.0 s straight cuts, sequential pool order.
  Lane B - light MIR timeline: cut boundaries snapped to detected beats; shot
           lengths track the music; pool cycle shifted.
  Lane C - B + editorial extras: onset-driven boundaries, one speed-ramp shot
           at the peak, one slow-motion breather, one reversed shot, and a
           slow push-in crop on every second shot.

The three deliverables are written WITHOUT lane identity in their filenames
(track_1.mp4 .. track_3.mp4, assignment shuffled with a recorded seed).  The
answer key is a separate file the CEO opens only after judging.

Usage:
  venv\\Scripts\\python.exe scripts\\pipeline\\music_pilot.py
  venv\\Scripts\\python.exe scripts\\pipeline\\music_pilot.py --excerpt-start 42.0

Requires: librosa + soundfile in the venv, ffmpeg/ffprobe console binaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]

FFMPEG = Path("C:/ffmpeg/bin/ffmpeg.exe")
FFPROBE = Path("C:/ffmpeg/bin/ffprobe.exe")
SMB_ROOT = Path("Y:/AI_Drama_Factory")

MASTER = SMB_ROOT / "assets/audio/ceo_approved_beats/lofi/CinematicAnthem_FallingStars.mp3"
MASTER_SHA256 = "69d6131763421e58f5ff6a28e8f7a08cd8e154c73e921365d7800addd2f768bc"

# All delivered episodes of the same show family -> coherent visual pool.
# Smoke episodes are only ~29 s long, so offsets are planned per source
# against the measured duration instead of hard-coded timestamps.
POOL_SOURCES = [
    SMB_ROOT / "Auto_Drama/output/handoff/done/20260912T115959_伸展台之夢｜微縮日常/v01.mp4",
    SMB_ROOT / "Auto_Drama/output/handoff/done/20260911T212309_伸展台之夢｜微縮日常/v01.mp4",
    SMB_ROOT / "Auto_Drama/output/handoff/done/20260911T201957_湖光微火｜微縮日常/v01.mp4",
    SMB_ROOT / "Auto_Drama/output/handoff/done/20260911T202014_湖光微火｜微縮日常/v01.mp4",
]

OUT_DIR = WORKSPACE / "CEO" / "03_樣片與交付" / "音樂時間軸盲評"
KEY_PATH = WORKSPACE / "CEO" / "03_樣片與交付" / "音樂時間軸盲評_解答.json"
SHEET_PATH = OUT_DIR / "評分表.md"
WORK_DIR = WORKSPACE / "logs" / "music_pilot_work"

FPS = 20
WIDTH, HEIGHT = 480, 848
EXCERPT_SEC = 30.0
SEGMENT_SEC = 5.0
SEGMENT_FRAMES = int(SEGMENT_SEC * FPS)

# Segment extraction is planned per source against its measured duration.
MIN_SEGMENT_SOURCE_SEC = 8.0


@dataclass
class Segment:
    """One pre-cut pool item: known duration, uniform encoder settings."""
    name: str
    path: Path
    frames: int = SEGMENT_FRAMES


@dataclass
class Lane:
    """Rendered lane metadata for the answer key."""
    lane: str
    cuts: list[float] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)
    notes: str = ""


# --------------------------------------------------------------------------
# Process helpers (fail loudly; this is a production artifact)
# --------------------------------------------------------------------------
def run(cmd: list[str], label: str) -> str:
    """Run a media tool; raise with its stderr when it fails or times out."""
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {proc.returncode}): {proc.stderr.strip()[-800:]}")
    return proc.stdout


def probe(path: Path) -> dict:
    """Return ffprobe JSON for a local file."""
    out = run([str(FFPROBE), "-v", "error", "-show_streams", "-show_format",
               "-of", "json", str(path)], f"probe {path.name}")
    data = json.loads(out)
    if not data.get("streams"):
        raise RuntimeError(f"{path.name} has no media streams")
    return data


def sha256_of(path: Path) -> str:
    """Hash a file incrementally."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Step 1 - music analysis (librosa)
# --------------------------------------------------------------------------
def analyse_master(excerpt_start: float | None) -> dict:
    """Pick the excerpt window and return beat/onset/energy landmarks."""
    import librosa  # imported here so --help stays instant
    import numpy as np

    if sha256_of(MASTER) != MASTER_SHA256:
        raise RuntimeError("master track sha256 mismatch; refusing to build a pilot on drifted audio")

    y, sr = librosa.load(str(MASTER), sr=22050, mono=True)
    duration = len(y) / sr
    if excerpt_start is None:
        # Highest sustained RMS 30 s window inside the first 70% of the track.
        hop = 512
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
        frames_per_sec = sr / hop
        win = int(EXCERPT_SEC * frames_per_sec)
        best_score, best_idx = -1.0, 0
        limit = int(0.7 * len(rms) - win)
        for start in range(0, max(limit, 1), int(2 * frames_per_sec)):
            score = float(rms[start:start + win].mean())
            if score > best_score:
                best_score, best_idx = score, start
        excerpt_start = best_idx / frames_per_sec

    start_sample = int(excerpt_start * sr)
    end_sample = start_sample + int(EXCERPT_SEC * sr)
    y_ex = y[start_sample:end_sample]

    tempo, beat_frames = librosa.beat.beat_track(y=y_ex, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    onset_env = librosa.onset.onset_strength(y=y_ex, sr=sr)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units="frames")
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    onset_strength = librosa.util.normalize(onset_env)
    rms = librosa.feature.rms(y=y_ex, frame_length=2048, hop_length=512)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)

    peak_i = int(np.argmax(rms))
    calm_slice = rms[: len(rms) // 2] if len(rms) > 4 else rms
    calm_i = int(np.argmin(calm_slice))
    strongest_onset_i = int(np.argmax(onset_strength))

    return {
        "source_duration_sec": round(duration, 3),
        "excerpt_start_sec": round(float(excerpt_start), 3),
        "excerpt_sec": EXCERPT_SEC,
        "tempo_bpm": float(np.atleast_1d(tempo)[0]),
        "beats": [round(float(t), 3) for t in beat_times],
        "onsets": [round(float(t), 3) for t in onset_times],
        "peak_rms_t": round(float(rms_times[peak_i]), 3),
        "calm_rms_t": round(float(rms_times[calm_i]), 3),
        "strongest_onset_t": round(float(rms_times[min(strongest_onset_i, len(rms_times) - 1)]), 3),
        "library_version": librosa.__version__,
    }


def snap_to_grid(target: float, grid: list[float], min_gap: float, previous: float) -> float | None:
    """Snap a target time to the nearest grid point, keeping cuts strictly ordered."""
    best, best_delta = None, None
    for point in grid:
        if point <= previous + min_gap or point >= EXCERPT_SEC - 0.4:
            continue
        delta = abs(point - target)
        if best_delta is None or delta < best_delta:
            best, best_delta = point, delta
    return best


def boundaries_from_grid(grid: list[float], count: int, min_gap: float) -> list[float]:
    """Build evenly targeted boundaries snapped onto the given grid."""
    boundaries = [0.0]
    step = EXCERPT_SEC / float(count)
    for k in range(1, count):
        snapped = snap_to_grid(k * step, grid, min_gap, boundaries[-1])
        if snapped is not None:
            boundaries.append(round(snapped, 3))
    boundaries.append(EXCERPT_SEC)
    return boundaries


# --------------------------------------------------------------------------
# Step 2 - segment pool
# --------------------------------------------------------------------------
def plan_offsets(duration: float) -> list[float]:
    """Evenly spread 5 s takes inside one source episode (needs >= 8 s)."""
    usable_start, usable_end = 2.5, duration - (SEGMENT_SEC + 0.5)
    if usable_end - usable_start < MIN_SEGMENT_SOURCE_SEC - SEGMENT_SEC - 0.5:
        return []
    span = usable_end - usable_start
    count = max(2, min(10, int(span / 2.4) + 1))
    if count == 1:
        return [round(usable_start, 2)]
    step = span / (count - 1)
    return [round(usable_start + i * step, 2) for i in range(count)]


def build_pool() -> list[Segment]:
    """Cut the deterministic 5 s pool from the delivered episodes."""
    pool_dir = WORK_DIR / "pool"
    pool_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Segment] = []
    index = 0
    for src in POOL_SOURCES:
        if not src.is_file():
            print(f"  skip missing source: {src}")
            continue
        src_info = probe(src)
        src_duration = float(src_info["format"]["duration"])
        offsets = plan_offsets(src_duration)
        if not offsets:
            print(f"  skip too-short source ({src_duration:.1f}s): {src.name}")
            continue
        print(f"  {src.parent.name}: {src_duration:.1f}s -> {len(offsets)} takes")
        for offset in offsets:
            name = f"seg{index:02d}"
            target = pool_dir / f"{name}.mp4"

            def extract() -> None:
                """Hybrid seek (fast input seek + 1 s refinement) for frame-exact takes.

                The delivered episodes come from lossless concat and can carry
                timestamp gaps, so a plain input seek may return fewer frames
                than requested (seen 2026-09-13: seg02 -> 62/100 frames).  One
                second of margin plus -frames:v guarantees the exact budget.
                """
                run([
                    str(FFMPEG), "-y", "-v", "error",
                    "-ss", str(max(offset - 1.0, 0.0)), "-i", str(src),
                    "-ss", "1.0", "-t", str(SEGMENT_SEC + 1.0), "-an",
                    "-vf", f"setpts=PTS-STARTPTS,fps={FPS},scale={WIDTH}:{HEIGHT}",
                    "-frames:v", str(SEGMENT_FRAMES),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", str(target),
                ], f"extract {name}")

            if not target.is_file():
                extract()
            info = probe(target)
            frames = int(next(s for s in info["streams"] if s["codec_type"] == "video").get("nb_frames", 0))
            if frames < SEGMENT_FRAMES:
                print(f"  re-extracting {name}: stale take has {frames} frames")
                target.unlink(missing_ok=True)
                extract()
                info = probe(target)
                frames = int(next(s for s in info["streams"] if s["codec_type"] == "video").get("nb_frames", 0))
            if frames < SEGMENT_FRAMES:
                raise RuntimeError(f"{name} only has {frames} of {SEGMENT_FRAMES} frames")
            segments.append(Segment(name=name, path=target))
            index += 1
    if len(segments) < 12:
        raise RuntimeError(f"pool too small for a meaningful pilot: {len(segments)} segments")
    return segments


# --------------------------------------------------------------------------
# Step 3 - lane rendering
# --------------------------------------------------------------------------
def cut_segment(segment: Segment, out: Path, frames: int, effect: str, lane: str, idx: int,
                lane_meta: Lane) -> Path:
    """Re-encode one pool segment to an exact frame budget with an optional effect."""
    duration = frames / FPS
    filters: list[str] = []
    if effect == "push":
        # 1.05x slow push-in via upscale + slowly panning crop (smooth, cheap).
        sc_w, sc_h = int(WIDTH * 1.05) // 2 * 2, int(HEIGHT * 1.05) // 2 * 2
        filters = [
            f"scale={sc_w}:{sc_h}",
            f"crop={WIDTH}:{HEIGHT}:x='(iw-{WIDTH})*min(1,t/{max(duration, 0.1):.3f})':y='(ih-{HEIGHT})/2'",
        ]
    elif effect == "speedup":
        filters = ["setpts=PTS/1.35", f"fps={FPS}"]
    elif effect == "slowmo":
        filters = ["setpts=PTS/0.85", f"fps={FPS}"]
    elif effect == "reverse":
        filters = ["reverse", "setpts=PTS-STARTPTS"]
    filters.append("setpts=PTS-STARTPTS")
    run([
        str(FFMPEG), "-y", "-v", "error", "-i", str(segment.path),
        "-an", "-vf", ",".join(filters), "-frames:v", str(frames),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", str(out),
    ], f"{lane} shot {idx}")
    lane_meta.effects.append(f"shot{idx}:{effect or 'plain'}:{frames}f")
    return out


def render_lane(lane: str, pool: list[Segment], boundaries: list[float], order_start: int,
                effects: dict[int, str], meta: Lane) -> Path:
    """Render one lane: per-shot re-encode, lossless concat, master mux."""
    lane_dir = WORK_DIR / lane
    lane_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for idx, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        frames = max(2, round((end - start) * FPS))
        segment = pool[(order_start + idx) % len(pool)]
        effect = effects.get(idx, "")
        out = lane_dir / f"shot{idx:02d}_{segment.name}.mp4"
        cut_segment(segment, out, frames, effect, lane, idx, meta)
        clips.append(out)

    listing = lane_dir / "concat.txt"
    listing.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
    silent = lane_dir / f"{lane}_silent.mp4"
    run([str(FFMPEG), "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(silent)], f"{lane} concat")

    final = OUT_DIR / f"{lane}_full.mp4"
    run([str(FFMPEG), "-y", "-v", "error",
         "-i", str(silent),
         "-ss", f"{MUSIC['excerpt_start_sec']}", "-t", f"{EXCERPT_SEC}", "-i", str(MASTER),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", str(final)],
        f"{lane} master mux")
    meta.cuts = boundaries
    verify_lane(final, lane)
    return final


def verify_lane(path: Path, lane: str) -> None:
    """Hard technical QC; any deviation aborts the pilot build."""
    info = probe(path)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    duration = float(info["format"]["duration"])
    problems = []
    if video["codec_name"] != "h264":
        problems.append(f"codec {video['codec_name']}")
    if (int(video["width"]), int(video["height"])) != (WIDTH, HEIGHT):
        problems.append(f"size {video['width']}x{video['height']}")
    fps_ok = True
    try:
        num, den = video.get("avg_frame_rate", "0/0").split("/")
        fps_ok = float(den) > 0 and abs(float(num) / float(den) - FPS) <= 0.01
    except (ValueError, ZeroDivisionError):
        fps_ok = False
    if not fps_ok:
        problems.append(f"fps {video.get('avg_frame_rate')}")
    if abs(duration - EXCERPT_SEC) > 0.25:
        problems.append(f"duration {duration:.3f}s")
    if audio is None or audio["codec_name"] != "aac" or int(audio["sample_rate"]) != 48000:
        problems.append("audio stream not AAC 48k")
    if problems:
        raise RuntimeError(f"{lane} failed QC: {', '.join(problems)}")
    print(f"  [{lane}] QC ok: {duration:.3f}s {video['width']}x{video['height']} @ {video['avg_frame_rate']}")


# --------------------------------------------------------------------------
# Step 4 - blind packaging
# --------------------------------------------------------------------------
def write_sheet(track_count: int) -> None:
    """Evaluation sheet the CEO fills before opening the answer key."""
    SHEET_PATH.write_text(
        "# 音樂時間軸盲評（30 秒）\n\n"
        "同一段母帶、同一批素材，三種剪輯時間軸。請先看完三支再看解答。\n\n"
        "| 面向（1-5 分） | track_1 | track_2 | track_3 |\n"
        "|---|---|---|---|\n"
        "| 節拍與畫面動作的契合 | | | |\n"
        "| 情緒曲線（堆疊/舒緩） | | | |\n"
        "| 鏡頭節奏的呼吸感 | | | |\n"
        "| 整體專業完成度 | | | |\n"
        "| 「想再看一次」 | | | |\n\n"
        "看完三支後，再打開 `CEO/03_樣片與交付/音樂時間軸盲評_解答.json`。\n",
        encoding="utf-8",
    )


def package_blind(lanes: dict[str, Path], seed: int) -> dict:
    """Shuffle lanes into track_1..N names; key file maps back afterwards."""
    rng = random.Random(seed)
    names = list(lanes.keys())
    rng.shuffle(names)
    mapping: dict[str, str] = {}
    for i, lane in enumerate(names, start=1):
        target = OUT_DIR / f"track_{i}.mp4"
        shutil.copy2(lanes[lane], target)
        mapping[f"track_{i}"] = lane
    return mapping


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
MUSIC: dict = {}


def main() -> int:
    global MUSIC
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--excerpt-start", type=float, default=None,
                        help="force the 30 s window start (default: auto-pick)")
    parser.add_argument("--seed", type=int, default=None, help="blind shuffle seed")
    args = parser.parse_args()

    for tool in (FFMPEG, FFPROBE):
        if not tool.is_file():
            print(f"[FATAL] missing tool: {tool}", file=sys.stderr)
            return 1
    if not MASTER.is_file():
        print(f"[FATAL] master track not found: {MASTER}", file=sys.stderr)
        return 1

    seed = args.seed if args.seed is not None else random.SystemRandom().randint(100000, 999999)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/5] analysing master track + excerpt window ...")
    MUSIC = analyse_master(args.excerpt_start)
    print(f"  window start {MUSIC['excerpt_start_sec']}s  bpm {MUSIC['tempo_bpm']:.1f}  "
          f"beats {len(MUSIC['beats'])}  onsets {len(MUSIC['onsets'])}")

    print("[2/5] cutting the 5 s segment pool from delivered episodes ...")
    pool = build_pool()
    print(f"  pool ready: {len(pool)} segments")

    print("[3/5] rendering lanes ...")
    meta: dict[str, Lane] = {}

    # Lane A - current baseline: fixed 5.0 s straight cuts, sequential pool.
    lane_a_meta = Lane(lane="A", notes="現行基準：固定 5.0 秒直切、素材順序播放")
    boundaries_a = [round(i * 5.0, 3) for i in range(7)]
    render_lane("A", pool, boundaries_a, 0, {}, lane_a_meta)

    # Lane B - light MIR timeline: beat-snapped boundaries, ~2.7 s per shot.
    lane_b_meta = Lane(lane="B", notes="輕量 MIR：切點對齊偵測節拍、鏡頭長度隨樂句變化")
    boundaries_b = boundaries_from_grid(MUSIC["beats"], 11, min_gap=1.6)
    render_lane("B", pool, boundaries_b, 6, {}, lane_b_meta)

    # Lane C - B + editorial extras on an onset-driven grid.
    lane_c_meta = Lane(lane="C", notes="MIR＋加料：onset 切點＋推鏡/變速/倒放")
    grid_c = sorted(set(MUSIC["onsets"]) | set(MUSIC["beats"]))
    boundaries_c = boundaries_from_grid(grid_c, 13, min_gap=1.2)
    effects_c: dict[int, str] = {}
    shots = list(zip(boundaries_c[:-1], boundaries_c[1:]))
    for idx, (start, end) in enumerate(shots):
        if start <= MUSIC["peak_rms_t"] < end:
            effects_c[idx] = "speedup"
        elif start <= MUSIC["calm_rms_t"] < end:
            effects_c[idx] = "slowmo"
        elif idx % 2 == 1 and "reverse" not in effects_c.values():
            effects_c[idx] = "reverse"
        else:
            effects_c[idx] = "push"
    render_lane("C", pool, boundaries_c, 12, effects_c, lane_c_meta)

    meta.update({"A": lane_a_meta, "B": lane_b_meta, "C": lane_c_meta})

    print("[4/5] blind packaging ...")
    lanes = {lane: OUT_DIR / f"{lane}_full.mp4" for lane in ("A", "B", "C")}
    mapping = package_blind(lanes, seed)
    write_sheet(3)
    for lane_file in lanes.values():
        lane_file.unlink(missing_ok=True)  # keep the folder blind

    key = {
        "created": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "seed": seed,
        "excerpt": {"start_sec": MUSIC["excerpt_start_sec"], "length_sec": EXCERPT_SEC},
        "master": {"path": str(MASTER), "sha256": MASTER_SHA256},
        "music_analysis": MUSIC,
        "mapping": mapping,
        "lanes": {
            lane: {"notes": meta[lane].notes, "cuts_sec": meta[lane].cuts,
                   "effects": meta[lane].effects}
            for lane in ("A", "B", "C")
        },
        "pool_sources": [str(p) for p in POOL_SOURCES],
    }
    KEY_PATH.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")

    print("[5/5] done.")
    print(f"  samples : {OUT_DIR}")
    print(f"  key     : {KEY_PATH}  (open only after judging)")
    print(f"  mapping : seed={seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
