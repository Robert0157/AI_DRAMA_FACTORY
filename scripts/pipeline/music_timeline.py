#!/usr/bin/env python3
"""Music timeline planner (mir_v1): master track -> beat-aligned shot plan.

The blind pilot (2026-09-13, CEO scoring) chose lane B: boundaries snapped to
the music's beats with shot lengths breathing along the energy curve; editorial
extras (speed ramps, reversal, push-ins) added nothing.

CEO decisions carried in this module:
  D1  A repetition counts only when the SAME (source, in_offset, out_offset)
      triple replays; unique non-overlapping segments are native use, and all
      usage counts are written into the plan/manifest for auditability.
  D2  Minimum shot length is 1.6 s globally.
  D3  Production rollout is per-episode opt-in (enforced by callers, not here).

Layering (design draft v1, P1):
  analyze_master()      -> MusicAnalysis        (audio -> landmarks; needs librosa)
  plan_from_analysis()  -> TimelinePlan         (pure planning; offline-testable)
  validate_plan()       -> list[str]            (empty list == pass)
  save_plan()/load_plan()                       (JSON round-trip for dispatch)

CLI:
  venv\\Scripts\\python.exe scripts\\pipeline\\music_timeline.py ^
    --master <mp3> --duration 175 --done-dir <episode-dir> --seed 7 ^
    --out plan.json
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
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

PLANNER_VERSION = "music_timeline.mir_v1"

DEFAULT_PARAMS: dict[str, float] = {
    "min_shot_sec": 1.6,      # D2: global floor
    "max_shot_sec": 3.4,      # ceiling for energy-driven targets
    "hard_shot_sec": 4.5,     # absolute cap after snapping / tail merge
    "beat_tolerance_sec": 0.18,
    "onset_tolerance_sec": 0.25,
}

# Style presets (CEO 2026-09-13 decisions: D1-D3 rules unchanged; ambient is a
# parallel candidate for the healing/light_music direction, 4-8 s holds).
STYLE_PRESETS: dict[str, dict[str, float]] = {
    "mir_v1": dict(DEFAULT_PARAMS),
    "ambient_cinematic": {
        "min_shot_sec": 4.0,
        "max_shot_sec": 8.0,
        "hard_shot_sec": 9.0,
        "beat_tolerance_sec": 0.35,
        "onset_tolerance_sec": 0.50,
    },
}


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MusicAnalysis:
    """Landmarks extracted from the master track (whole file or excerpt)."""
    sha256: str
    duration_sec: float
    bpm: float
    beats: list[float]
    onsets: list[float]
    rms_times: list[float]
    rms: list[float]
    peak_t: float
    calm_t: float

    def energy_at(self, t_sec: float) -> float:
        """Normalized [0,1] RMS at a point in time (linear interpolation)."""
        import numpy as np  # local import keeps module import cheap

        if not self.rms_times or not self.rms:
            return 0.5
        values = np.asarray(self.rms, dtype=float)
        span = float(values.max() - values.min())
        normalized = (values - values.min()) / span if span > 1e-9 else np.zeros_like(values)
        return float(np.interp(t_sec, np.asarray(self.rms_times, dtype=float), normalized))


@dataclass(frozen=True)
class SourceSpec:
    """A generation unit available to the timeline (long take or delivered clip)."""
    path: str
    duration_sec: float


@dataclass(frozen=True)
class ShotSpec:
    """One timeline shot: a frame-exact segment cut from a source unit."""
    index: int
    start_sec: float
    end_sec: float
    frames: int
    source: str
    in_offset_sec: float
    out_offset_sec: float


@dataclass(frozen=True)
class TimelinePlan:
    """The auditable artifact consumed by dispatch and the Mac assembler."""
    version: str
    master_sha256: str
    duration_sec: float
    fps: float
    boundaries: list[float]
    shots: list[ShotSpec]
    params: dict[str, float]
    seed: int
    source_use_count: dict[str, int]
    created_utc: str
    style: str = "mir_v1"
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_json_dict(cls, data: dict) -> "TimelinePlan":
        shots = [ShotSpec(**shot) for shot in data["shots"]]
        payload = dict(data)
        payload["shots"] = shots
        return cls(**payload)


# --------------------------------------------------------------------------
# IO helpers
# --------------------------------------------------------------------------
def sha256_of(path: Path) -> str:
    """Hash a file incrementally."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_plan(plan: TimelinePlan, path: Path) -> None:
    """Write the plan as UTF-8 JSON (stable key order for diffing)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.to_json_dict(), ensure_ascii=False, indent=1),
                    encoding="utf-8")


def load_plan(path: Path) -> TimelinePlan:
    """Load a plan written by save_plan()."""
    return TimelinePlan.from_json_dict(json.loads(path.read_text(encoding="utf-8")))


def _ffprobe() -> str:
    """Resolve ffprobe for source duration probing (PC path, then PATH)."""
    candidate = Path("C:/ffmpeg/bin/ffprobe.exe")
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("ffprobe")
    if found:
        return found
    raise RuntimeError("ffprobe not found; install it or fix PATH")


def probe_duration(path: Path) -> float:
    """Media duration in seconds via a single ffprobe call."""
    proc = subprocess.run(
        [_ffprobe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {proc.stderr.strip()[:300]}")
    return float(proc.stdout.strip())


# --------------------------------------------------------------------------
# Audio analysis (librosa)
# --------------------------------------------------------------------------
def analyze_master(path: Path, *, sr: int = 22050) -> MusicAnalysis:
    """Extract beats / onsets / energy landmarks from a master track."""
    import librosa  # heavy import kept out of the module import path
    import numpy as np

    digest = sha256_of(path)
    y, sample_rate = librosa.load(str(path), sr=sr, mono=True)
    duration = len(y) / sample_rate

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sample_rate, units="frames")
    beats = librosa.frames_to_time(beat_frames, sr=sample_rate)
    onset_env = librosa.onset.onset_strength(y=y, sr=sample_rate)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sample_rate, units="frames")
    onsets = librosa.frames_to_time(onset_frames, sr=sample_rate)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sample_rate, hop_length=512)

    peak_i = int(np.argmax(rms))
    calm_i = int(np.argmin(rms))
    return MusicAnalysis(
        sha256=digest,
        duration_sec=round(float(duration), 3),
        bpm=float(np.atleast_1d(tempo)[0]),
        beats=[round(float(t), 3) for t in beats],
        onsets=[round(float(t), 3) for t in onsets],
        rms_times=[round(float(t), 3) for t in rms_times],
        rms=[round(float(v), 6) for v in rms],
        peak_t=round(float(rms_times[peak_i]), 3),
        calm_t=round(float(rms_times[calm_i]), 3),
    )


# --------------------------------------------------------------------------
# Planning core (pure; offline-testable)
# --------------------------------------------------------------------------
def _snap(candidate: float, beats: list[float], onsets: list[float],
          beat_tol: float, onset_tol: float) -> float:
    """Snap a boundary to the nearest beat, else onset, else leave as-is."""
    best: float | None = None
    best_delta = beat_tol
    for beat in beats:
        delta = abs(beat - candidate)
        if delta < best_delta:
            best, best_delta = beat, delta
    if best is not None:
        return best
    best_delta = onset_tol
    for onset in onsets:
        delta = abs(onset - candidate)
        if delta < best_delta:
            best, best_delta = onset, delta
    return candidate if best is None else best


def plan_from_analysis(analysis: MusicAnalysis, duration: float,
                       sources: list[SourceSpec], *, style: str = "mir_v1",
                       seed: int = 7,
                       fps: float = 20.0,
                       params: dict[str, float] | None = None) -> TimelinePlan:
    """Build the shot plan for the chosen style (D1/D2 semantics).

    Sources are consumed as sequential cursors: the first shot takes the head
    of a source, the next takes what follows, so every shot is a unique
    (source, in, out) triple - zero replays by construction (D1 strictest
    reading).  Adjacent shots never share a source while alternatives exist.
    Style presets supply the shot-length envelope and snapping tolerances;
    explicit ``params`` override them.
    """
    if style not in STYLE_PRESETS:
        raise ValueError(f"unknown style {style!r}; choose from {sorted(STYLE_PRESETS)}")
    active = {**DEFAULT_PARAMS, **STYLE_PRESETS[style], **(params or {})}
    min_shot = active["min_shot_sec"]
    max_shot = active["max_shot_sec"]
    hard_shot = active["hard_shot_sec"]

    if duration <= 0 or not math.isfinite(duration):
        raise ValueError("duration must be a positive number")
    usable = [s for s in sources if s.duration_sec > 0]
    if not usable:
        raise ValueError("at least one source with positive duration is required")
    if sum(s.duration_sec for s in usable) < duration:
        raise RuntimeError(
            f"source pool too small: {sum(s.duration_sec for s in usable):.1f}s < {duration:.1f}s timeline")

    rng = random.Random(seed)
    order = list(range(len(usable)))
    rng.shuffle(order)
    cursor = {i: 0.0 for i in order}
    counts = {usable[i].path: 0 for i in order}

    boundaries = [0.0]
    shots: list[ShotSpec] = []
    t = 0.0
    last_source: int | None = None

    while duration - t > 1e-6:
        remaining = duration - t
        if remaining <= hard_shot + 1e-9:
            # The tail is already within one legal shot: absorb it entirely.
            candidate = duration
        else:
            # D2-driven target: strong music -> short shots, calm -> longer shots.
            target = max(min_shot, min(max_shot, max_shot - 1.0 * analysis.energy_at(t)))
            candidate = _snap(t + target, analysis.beats, analysis.onsets,
                              active["beat_tolerance_sec"], active["onset_tolerance_sec"])
            candidate = min(candidate, t + hard_shot)
            candidate = max(candidate, t + min_shot)
            candidate = min(candidate, duration)
            tail = duration - candidate
            if 1e-6 < tail < min_shot:
                # Never leave a stub below the floor. Either push the boundary
                # back so the final shot is exactly min_shot, or absorb the
                # tail here (length stays <= 2*min_shot <= hard by the branch
                # condition, so both outcomes respect the legal range).
                if (candidate - t) >= (min_shot + (min_shot - tail)):
                    candidate = duration - min_shot
                else:
                    candidate = duration
        shot_len = candidate - t
        # Pick a source that still has un-consumed footage of this length.
        picked: int | None = None
        for step in range(len(order)):
            idx = order[(order.index(last_source) + 1 + step) % len(order)] if last_source is not None else order[step]
            if cursor[idx] + shot_len <= usable[idx].duration_sec + 1e-6:
                picked = idx
                break
        if picked is None:
            raise RuntimeError(
                f"insufficient unique footage for shot {len(shots)} ({shot_len:.2f}s); "
                "add sources or shorten the timeline")

        in_offset = cursor[picked]
        out_offset = in_offset + shot_len
        cursor[picked] = out_offset
        counts[usable[picked].path] += 1
        boundaries.append(round(candidate, 3))
        shots.append(ShotSpec(
            index=len(shots),
            start_sec=round(t, 3),
            end_sec=round(candidate, 3),
            frames=0,  # frame-exact values assigned after cumulative rounding
            source=usable[picked].path,
            in_offset_sec=round(in_offset, 3),
            out_offset_sec=round(out_offset, 3),
        ))
        last_source = picked
        t = candidate

    # Frame budget: cumulative rounding so sum(frames) == round(duration*fps).
    total_frames = round(duration * fps)
    fixed_shots: list[ShotSpec] = []
    prev_frame = 0
    for i, shot in enumerate(shots):
        end_frame = round(shot.end_sec * fps)
        if i == len(shots) - 1:
            end_frame = total_frames
        fixed_shots.append(ShotSpec(
            index=shot.index, start_sec=shot.start_sec, end_sec=shot.end_sec,
            frames=max(1, end_frame - prev_frame), source=shot.source,
            in_offset_sec=shot.in_offset_sec, out_offset_sec=shot.out_offset_sec,
        ))
        prev_frame = end_frame

    warnings: list[str] = []
    if not analysis.beats:
        warnings.append("no beats detected; boundaries fell back to onsets/raw targets")
    return TimelinePlan(
        version=PLANNER_VERSION,
        master_sha256=analysis.sha256,
        duration_sec=round(duration, 3),
        fps=fps,
        boundaries=[round(b, 3) for b in boundaries],
        shots=fixed_shots,
        params=active,
        seed=seed,
        source_use_count=counts,
        created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        style=style,
        warnings=warnings,
    )


def plan_timeline(master: Path, duration: float, sources: list[SourceSpec], *,
                  style: str = "mir_v1", seed: int = 7, fps: float = 20.0,
                  params: dict[str, float] | None = None) -> TimelinePlan:
    """Convenience wrapper: analyse the master then plan."""
    analysis = analyze_master(master)
    return plan_from_analysis(analysis, duration, sources, style=style,
                              seed=seed, fps=fps, params=params)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_plan(plan: TimelinePlan, *, min_shot_sec: float | None = None,
                  max_shot_sec: float | None = None, max_source_repeats: int = 3) -> list[str]:
    """Return a list of violations (empty list == pass).

    Bounds come from the plan's own params (style preset) unless overridden
    explicitly, so mir_v1 and ambient_cinematic are each judged by their own
    envelope.
    """
    params = plan.params or {}
    if min_shot_sec is None:
        min_shot_sec = float(params.get("min_shot_sec", 1.6))
    if max_shot_sec is None:
        max_shot_sec = float(params.get("hard_shot_sec", 4.5))
    errors: list[str] = []
    if not plan.shots:
        return ["plan has no shots"]
    if abs(plan.boundaries[0]) > 1e-6:
        errors.append("first boundary must be 0")
    if abs(plan.boundaries[-1] - plan.duration_sec) > 0.01:
        errors.append("last boundary must equal the timeline duration")
    triples: dict[tuple[str, float, float], int] = {}
    previous_source: str | None = None
    for i, shot in enumerate(plan.shots):
        length = shot.end_sec - shot.start_sec
        if length < min_shot_sec - 1e-6:
            errors.append(f"shot {i} shorter than {min_shot_sec}s ({length:.3f}s)")
        if length > max_shot_sec + 1e-6:
            errors.append(f"shot {i} longer than {max_shot_sec}s ({length:.3f}s)")
        if i > 0 and abs(plan.shots[i - 1].end_sec - shot.start_sec) > 1e-6:
            errors.append(f"shot {i} is not contiguous with shot {i - 1}")
        if i > 0 and shot.source == previous_source and len(plan.source_use_count) > 1:
            errors.append(f"shot {i} repeats the adjacent source {shot.source}")
        triple = (shot.source, shot.in_offset_sec, shot.out_offset_sec)
        triples[triple] = triples.get(triple, 0) + 1
        previous_source = shot.source
    for triple, count in triples.items():
        if count > max_source_repeats:
            errors.append(f"triple {triple} replays {count} times (> {max_source_repeats})")
    if sum(shot.frames for shot in plan.shots) != round(plan.duration_sec * plan.fps):
        errors.append("shot frame budget does not add up to the timeline frame count")
    return errors


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _collect_sources(args: argparse.Namespace) -> list[SourceSpec]:
    """Turn CLI inputs into duration-probed source specs."""
    paths: list[Path] = [Path(p) for p in (args.sources or [])]
    if args.done_dir:
        done_dir = Path(args.done_dir)
        # Accept both a flat folder of mp4s and the handoff/done/<job>/v01.mp4 layout.
        found = sorted(set(done_dir.glob("*.mp4")) | set(done_dir.glob("*/*.mp4")))
        if not found:
            raise SystemExit(f"[FATAL] no mp4 found under {done_dir}")
        paths.extend(found)
    specs: list[SourceSpec] = []
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"[FATAL] source missing: {path}")
        specs.append(SourceSpec(path=str(path), duration_sec=probe_duration(path)))
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", required=True, help="master track (mp3)")
    parser.add_argument("--duration", type=float, required=True, help="timeline seconds")
    parser.add_argument("--sources", nargs="*", help="source media files")
    parser.add_argument("--done-dir", help="directory whose *.mp4 become sources")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--style", default="mir_v1", choices=sorted(STYLE_PRESETS),
                        help="shot-length envelope preset")
    parser.add_argument("--out", required=True, help="plan JSON output path")
    args = parser.parse_args()

    master = Path(args.master)
    if not master.is_file():
        print(f"[FATAL] master not found: {master}", file=sys.stderr)
        return 1
    try:
        sources = _collect_sources(args)
        plan = plan_timeline(master, args.duration, sources, style=args.style,
                             seed=args.seed, fps=args.fps)
    except (RuntimeError, ValueError) as exc:
        print(f"[FATAL] planning failed: {exc}", file=sys.stderr)
        return 1

    errors = validate_plan(plan)
    if errors:
        print("[FATAL] plan validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    out = Path(args.out)
    save_plan(plan, out)
    print(f"PLAN_OK style={plan.style} shots={len(plan.shots)} boundaries={len(plan.boundaries)} "
          f"total_frames={round(plan.duration_sec * plan.fps)}")
    print(f"  sources used: {plan.source_use_count}")
    print(f"  written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
