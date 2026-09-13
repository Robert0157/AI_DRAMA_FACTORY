# -*- coding: utf-8 -*-
"""
Music-drama (MV) pipeline core — draft v2 -> validation -> LMD normalization -> mix.

CEO policy (approved 2026-09-10, MV exception §10b):
  - The CEO-approved song (assets/audio/ceo_approved_beats/...) is the ONLY master track.
  - Seedance audio survives only as an extremely light ambient bed (default -27 dB).
  - Zero dialogue: shots carry no dialogue; lyrics/section cues drive the visuals.
  - Draft is fingerprinted (sha256) and duration-checked before anything is generated.

This module is deterministic and loud: validation problems raise/aggregate; ffmpeg
failures raise FfmpegError-style MusicDramaError with stderr tails. No silent retries.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .logging_util import get_logger

log = get_logger()

# Seedance 2.x single-generation window (LMD clamps to this range as well).
SEEDANCE_MIN_SEC = 4.0
# Seedance 2.5 supports up to 30s per generation (CEO-authorized Option A,
# 2026-09-10; live-verified: 30s OK for 9:16 & 16:9, 35s rejected HTTP400).
# The LMD clamp normalizeVolcengineDuration was patched 15 -> 30 (2.5 only).
SEEDANCE_MAX_SEC = 30.0
# §10b default: keep Seedance track as a whisper under the song.
DEFAULT_AMBIENT_GAIN_DB = -27.0

# Workspace root = F:\AI_DRAMA_FACTORY (Auto_Drama/auto_drama/ -> parents[2]).
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class MusicDramaError(RuntimeError):
    """Raised on any music-drama pipeline failure (never swallowed)."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _sanitize(name: str) -> str:
    """Filesystem-safe token for names inside paths."""
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", str(name or "").strip()).strip("_") or "item"


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    """Return the lowercase hex sha256 of a file (streamed)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _probe_duration_sec(media_path: Path) -> float:
    """ffprobe duration; raises if ffprobe is unavailable or output is malformed."""
    if shutil.which("ffprobe") is None:
        raise MusicDramaError("ffprobe not found on PATH")
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise MusicDramaError(f"ffprobe failed on {media_path}: {proc.stderr[-400:]}")
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise MusicDramaError(f"ffprobe non-numeric duration: {proc.stdout!r}") from exc


def gain_db_to_linear(db: float) -> float:
    """dB -> linear amplitude multiplier."""
    return 10.0 ** (float(db) / 20.0)


# ---------------------------------------------------------------------------
# draft loading & validation
# ---------------------------------------------------------------------------
def load_draft(path: Path) -> Dict[str, Any]:
    """Parse a music_drama draft JSON file (UTF-8)."""
    p = Path(path)
    if not p.is_file():
        raise MusicDramaError(f"draft not found: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MusicDramaError(f"draft JSON invalid: {exc}") from exc


def resolve_audio_path(draft: Dict[str, Any],
                       workspace_root: Path = WORKSPACE_ROOT) -> Path:
    """Resolve draft.audio.file (workspace-relative or absolute) to an existing file."""
    raw = str((draft.get("audio") or {}).get("file") or "").strip()
    if not raw:
        raise MusicDramaError("draft.audio.file is empty")
    p = Path(raw)
    if not p.is_absolute():
        p = workspace_root / raw
    if not p.is_file():
        raise MusicDramaError(f"audio file missing: {p}")
    return p


def validate_draft(draft: Dict[str, Any],
                   workspace_root: Path = WORKSPACE_ROOT) -> Dict[str, Any]:
    """
    Strict validation of a draft v2. Returns:
      {"errors": [...], "warnings": [...], "audio_path": Path, "segment": (start, end)}
    Errors are fatal (caller aborts); warnings are advisory.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if draft.get("schema_version") != "music_drama.v2":
        errors.append(f"schema_version must be 'music_drama.v2', got {draft.get('schema_version')!r}")

    # ---- audio binding: file exists + fingerprint match (CEO fingerprint rule) ----
    audio: Dict[str, Any] = draft.get("audio") or {}
    audio_path: Optional[Path] = None
    try:
        audio_path = resolve_audio_path(draft, workspace_root)
    except MusicDramaError as exc:
        errors.append(str(exc))

    seg = audio.get("segment") or {}
    try:
        seg_start = float(seg.get("start_sec", 0.0))
        seg_end = float(seg.get("end_sec", 0.0))
    except (TypeError, ValueError):
        seg_start, seg_end = 0.0, 0.0
        errors.append("audio.segment start/end must be numeric")
    if seg_end - seg_start < SEEDANCE_MIN_SEC:
        errors.append(f"audio.segment too short: {seg_end - seg_start:.2f}s")

    if audio_path is not None:
        actual_sha = sha256_file(audio_path)
        declared_sha = str(audio.get("sha256") or "").strip().lower()
        if not declared_sha:
            errors.append("audio.sha256 missing (fingerprint required)")
        elif declared_sha != actual_sha:
            errors.append(
                f"audio.sha256 mismatch: declared {declared_sha[:12]}… != actual {actual_sha[:12]}…"
            )
        actual_dur = _probe_duration_sec(audio_path)
        declared_dur = float(audio.get("duration_sec") or 0.0)
        if declared_dur and abs(actual_dur - declared_dur) > 1.5:
            warnings.append(
                f"audio.duration_sec drift: declared {declared_dur:.3f}s vs actual {actual_dur:.3f}s"
            )
        if seg_end > actual_dur + 0.5:
            errors.append(
                f"audio.segment end {seg_end:.2f}s exceeds file duration {actual_dur:.2f}s"
            )

    # ---- visual style ----
    vs = draft.get("visual_style") or {}
    if str(vs.get("aspect_ratio") or "") != "9:16":
        warnings.append(f"aspect_ratio is {vs.get('aspect_ratio')!r} (Shorts format is 9:16)")

    # ---- cast / scenes ----
    cast_keys = {str(c.get("key")) for c in (draft.get("cast") or [])}
    if not cast_keys:
        errors.append("cast is empty (at least one character required)")
    for c in draft.get("cast") or []:
        if not str(c.get("portrait_prompt") or "").strip():
            warnings.append(f"cast[{c.get('name')}] has no portrait_prompt (no ref image will be created)")
    scene_ids = {int(s.get("scene_id") or 0) for s in (draft.get("scenes") or [])}

    # ---- shots ----
    shots = draft.get("shots") or []
    if not shots:
        errors.append("shots is empty")
    cursor = seg_start
    total = 0.0
    for i, shot in enumerate(shots):
        tag = f"shots[{i}] (sh{shot.get('shot_number')})"
        try:
            s_start = float(shot["start_sec"])
            s_end = float(shot["end_sec"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{tag}: start_sec/end_sec missing or non-numeric")
            continue
        dur = float(shot.get("duration_sec") or (s_end - s_start))
        total += dur
        if abs((s_end - s_start) - dur) > 0.51:
            warnings.append(f"{tag}: duration_sec {dur:.2f} != end-start {s_end - s_start:.2f}")
        if dur < SEEDANCE_MIN_SEC - 0.01 or dur > SEEDANCE_MAX_SEC + 0.01:
            errors.append(
                f"{tag}: duration {dur:.2f}s outside Seedance window "
                f"[{SEEDANCE_MIN_SEC:.0f}, {SEEDANCE_MAX_SEC:.0f}]s"
            )
        if abs(s_start - cursor) > 0.6:
            errors.append(f"{tag}: not contiguous (starts {s_start:.2f}s, previous ended {cursor:.2f}s)")
        cursor = s_end
        if int(shot.get("scene_id") or 0) not in scene_ids:
            errors.append(f"{tag}: scene_id {shot.get('scene_id')} not declared in scenes[]")
        for key in shot.get("characters") or []:
            if str(key) not in cast_keys:
                errors.append(f"{tag}: character key {key!r} not in cast[]")
        text = str(shot.get("universal_segment_text") or "")
        if not text:
            errors.append(f"{tag}: universal_segment_text missing")
        elif "@图片" not in text:
            warnings.append(f"{tag}: universal_segment_text has no @图片N slot")
        if draft.get("episode", {}).get("zero_dialogue") and str(shot.get("dialogue") or "").strip():
            errors.append(f"{tag}: zero_dialogue is true but shot carries dialogue")

    if shots:
        expected = seg_end - seg_start
        if abs(total - expected) > 1.0:
            errors.append(
                f"shots total {total:.2f}s != segment length {expected:.2f}s (±1.0s tolerance)"
            )

    return {
        "errors": errors,
        "warnings": warnings,
        "audio_path": audio_path,
        "segment": (seg_start, seg_end),
    }


# ---------------------------------------------------------------------------
# draft -> LMD normalization
# ---------------------------------------------------------------------------
def normalize_storyboards(draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Map draft shots onto LMD storyboard payloads.

    Returns a list of specs:
      {payload: {...}, universal_segment_text: str, character_names: [str],
       start_sec, end_sec, audio_cue}
    `payload` matches POST /storyboards fields (episode_id is added by the caller).
    """
    scenes = {int(s.get("scene_id") or 0): s for s in (draft.get("scenes") or [])}
    cast = {str(c.get("key")): c for c in (draft.get("cast") or [])}

    specs: List[Dict[str, Any]] = []
    for shot in draft.get("shots") or []:
        scene = scenes.get(int(shot.get("scene_id") or 0), {})
        char_names = [
            str(cast[k]["name"]) for k in (shot.get("characters") or []) if str(k) in cast
        ]
        duration = float(shot.get("duration_sec") or (float(shot["end_sec"]) - float(shot["start_sec"])))
        payload = {
            "storyboard_number": int(shot["shot_number"]),
            "title": str(shot.get("title") or f"shot {shot['shot_number']}"),
            "description": str(shot.get("description") or ""),
            "location": str(scene.get("location") or ""),
            "time": str(scene.get("time") or ""),
            "duration": duration,
            "dialogue": "",  # §10b zero-dialogue policy
            "action": str(shot.get("action") or ""),
            "atmosphere": str(shot.get("atmosphere") or shot.get("lighting") or ""),
            "image_prompt": str(shot.get("image_prompt") or ""),
            "video_prompt": str(shot.get("universal_segment_text") or ""),
        }
        specs.append({
            "payload": payload,
            "universal_segment_text": str(shot.get("universal_segment_text") or ""),
            "character_names": char_names,
            "start_sec": float(shot["start_sec"]),
            "end_sec": float(shot["end_sec"]),
            "audio_cue": str(shot.get("audio_cue") or ""),
        })
    return specs


# ---------------------------------------------------------------------------
# LMD authoring (drama / episode / cast / portraits / storyboards)
# ---------------------------------------------------------------------------
def prepare_lmd_episode(
    lmd: Any,
    draft: Dict[str, Any],
    storyboards: List[Dict[str, Any]],
    *,
    portrait_client: Any = None,
    portraits_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Create the whole LMD side for one MV episode:
      drama -> episode -> cast (upsert) -> portrait upload -> storyboards (+@图片N text, char bindings).

    `lmd` is an auto_drama.lmd_client.LocalMiniDramaClient (duck-typed).
    `portrait_client` is a ZhipuImageClient (or None to skip portraits).
    Returns {drama_id, episode_id, character_ids: {name: id}, storyboard_ids, portraits_dir}.
    """
    ep = draft.get("episode") or {}
    ep_title = str(ep.get("title") or "mv_episode")
    cast_specs = draft.get("cast") or []
    if not cast_specs:
        raise MusicDramaError("draft.cast is empty — at least one character is required")

    if portraits_dir is None:
        portraits_dir = (Path(__file__).resolve().parents[1] / "output" / "sandbox"
                         / _sanitize(ep_title) / "cast")
    portraits_dir = Path(portraits_dir)
    portraits_dir.mkdir(parents=True, exist_ok=True)

    total_dur = int(round(sum(s["payload"]["duration"] for s in storyboards)))

    drama = lmd.create_drama(title=f"[MV] {ep_title}", style="music_drama", genre="mv")
    drama_id = int(drama.get("id") or 0)
    if not drama_id:
        raise MusicDramaError(f"create_drama returned no id: {drama}")

    lmd.save_episodes(drama_id, [{
        "episode_number": 1, "title": ep_title, "duration": total_dur,
        "description": str(ep.get("episode_id") or ""),
    }])
    detail = lmd.get_drama(drama_id)
    episodes = detail.get("episodes") or []
    if not episodes:
        raise MusicDramaError(f"episode creation failed on drama {drama_id}")
    episode_id = int(episodes[0].get("id"))

    lmd.save_characters(drama_id, [{
        "name": str(c.get("name")),
        "role": str(c.get("role") or "main"),
        "description": str(c.get("description") or ""),
        "appearance": str(c.get("appearance") or ""),
    } for c in cast_specs])
    detail = lmd.get_drama(drama_id)
    char_ids = {str(c.get("name")): int(c.get("id")) for c in (detail.get("characters") or [])}

    # ---- portraits: single clean portrait per cast member -> LMD ref image ----
    for c in cast_specs:
        cid = char_ids.get(str(c.get("name")))
        prompt = str(c.get("portrait_prompt") or "").strip()
        if not cid or not prompt:
            continue
        out_png = portraits_dir / f"char_{cid}_{_sanitize(str(c.get('name')))}.png"
        # Cross-episode consistency: reuse an existing portrait file verbatim
        # (draft `cast[].portrait_source`, workspace-relative path) instead of
        # re-generating a new face for the same character.
        source = str(c.get("portrait_source") or "").strip()
        if source and not out_png.is_file():
            src_path = Path(source)
            if not src_path.is_absolute():
                src_path = WORKSPACE_ROOT / source
            if src_path.is_file():
                out_png.parent.mkdir(parents=True, exist_ok=True)
                out_png.write_bytes(src_path.read_bytes())
                log.info("portrait reused from %s -> %s", src_path, out_png.name)
            else:
                log.warning("portrait_source not found: %s (will generate)", src_path)
        if not out_png.is_file():
            if portrait_client is None:
                log.warning("portrait skipped for %s (no image client)", c.get("name"))
                continue
            try:
                out_png = portrait_client.generate(prompt, out_png, size="768x1024")
            except Exception as exc:  # size rejected -> fall back to square
                log.warning("portrait 768x1024 failed (%s); retry 1024x1024", exc)
                out_png = portrait_client.generate(prompt, out_png, size="1024x1024")
        lmd.upload_character_image(cid, out_png)
        log.info("portrait uploaded: %s -> char %s", out_png.name, cid)

    # ---- storyboards: create + attach @图片N text + character bindings ----
    sb_ids: List[int] = []
    for spec in storyboards:
        fields = dict(spec["payload"])
        fields["episode_id"] = episode_id
        row = lmd.create_storyboard(fields)
        sid = int(row.get("id"))
        update: Dict[str, Any] = {"universal_segment_text": spec["universal_segment_text"]}
        ids = [char_ids[n] for n in spec["character_names"] if n in char_ids]
        if ids:
            update["character_ids"] = ids
        lmd.update_storyboard(sid, update)
        sb_ids.append(sid)
        log.info("storyboard created: id=%s sh=%s duration=%ss",
                 sid, fields["storyboard_number"], fields["duration"])

    return {
        "drama_id": drama_id,
        "episode_id": episode_id,
        "character_ids": char_ids,
        "storyboard_ids": sb_ids,
        "portraits_dir": str(portraits_dir),
    }


# ---------------------------------------------------------------------------
# assembly: song-as-master mux + contact sheet
# ---------------------------------------------------------------------------
def mux_music_master(
    video_path: Path,
    music_path: Path,
    output_path: Path,
    *,
    music_start_sec: float = 0.0,
    ambient_gain_db: float = DEFAULT_AMBIENT_GAIN_DB,
) -> Path:
    """
    §10b mix: the song is the ONLY master track; the Seedance track is kept as an
    extremely light ambient bed so the mix never fully strips the original audio.

    Falls back to a full music-only replace (logged loudly) when the video carries
    no audio stream at all.
    """
    if shutil.which("ffmpeg") is None:
        raise MusicDramaError("ffmpeg not found on PATH")
    video_path, music_path = Path(video_path), Path(music_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Bound the output to the VIDEO length: the music file usually runs far
    # longer than the episode segment, and an unbounded mux would produce a
    # silent-video tail with the music continuing (regression fixed 2026-09-10).
    video_dur = _probe_duration_sec(video_path)

    amb = f"{gain_db_to_linear(ambient_gain_db):.5f}"
    filter_complex = (
        f"[0:a]volume={amb}[amb];"
        f"[1:a]volume=1.0[mus];"
        f"[mus][amb]amix=inputs=2:duration=longest:dropout_transition=2[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-ss", f"{float(music_start_sec):.3f}", "-i", str(music_path),
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{video_dur:.3f}",
        "-movflags", "+faststart",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Fallback: video without any audio stream -> replace with music only.
        log.warning("amix mux failed (%s); retrying music-only replace", proc.stderr[-300:])
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-ss", f"{float(music_start_sec):.3f}", "-i", str(music_path),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-t", f"{video_dur:.3f}",
            "-movflags", "+faststart",
            str(output_path),
        ]
        proc2 = subprocess.run(cmd_fallback, capture_output=True, text=True)
        if proc2.returncode != 0:
            raise MusicDramaError(f"mv mux failed: {proc2.stderr[-700:]}")
    log.info("MV master muxed (song=master, ambient %sdB) -> %s", ambient_gain_db, output_path.name)
    return output_path


def make_contact_sheet(
    video_path: Path,
    output_path: Path,
    sample_times: List[float],
    *,
    tile_height: int = 640,
) -> Path:
    """Row contact sheet: one frame per sample time, horizontally stacked."""
    if shutil.which("ffmpeg") is None:
        raise MusicDramaError("ffmpeg not found on PATH")
    if not sample_times:
        raise MusicDramaError("contact sheet needs at least one sample time")
    inputs: List[str] = []
    for t in sample_times:
        inputs += ["-ss", f"{float(t):.2f}", "-i", str(video_path)]
    n = len(sample_times)
    parts = "".join(f"[{i}:v]scale=-2:{int(tile_height)}[v{i}];" for i in range(n))
    stack = "".join(f"[v{i}]" for i in range(n)) + f"hstack=inputs={n}[out]"
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", parts + stack,
        "-map", "[out]", "-frames:v", "1",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MusicDramaError(f"contact sheet failed: {proc.stderr[-500:]}")
    log.info("contact sheet -> %s", output_path.name)
    return Path(output_path)
