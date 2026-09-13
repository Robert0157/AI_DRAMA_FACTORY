#!/usr/bin/env python3
"""Mac mini render worker: handoff job -> Wan 2.1 480p -> assembled episode.

Self-contained on purpose: the Mac workspace is a SEPARATE git repo and does not
carry the Windows-side modules, so this file must run with stdlib + requests only.

Runs on the Mac mini (ComfyUI must be listening on --comfy-url).

Usage (on Mac):
  export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH
  python3 mac_wan_worker.py --once
  python3 mac_wan_worker.py --watch --interval 30
  python3 mac_wan_worker.py --job <job_id>

Job lifecycle (all under the handoff root, shared with the PC over SMB):
  inbox/<job_id>.json      written by the PC dispatcher (tmp+rename)
  processing/<job_id>.json claimed by this worker
  done/<job_id>/           final episode + status.json
  failed/<job_id>/         status.json with the error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from fractions import Fraction
from typing import Any

DEFAULT_COMFY = "http://127.0.0.1:8188"
DEFAULT_HANDOFF = "/Volumes/AI_Workspace/AI_Drama_Factory/Auto_Drama/output/handoff"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"

WAN_UNET = "wan2.1_t2v_1.3B_fp16.safetensors"
WAN_CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WAN_VAE = "wan_2.1_vae.safetensors"

DEFAULT_NEGATIVE = (
    "people, person, human, character, face, body, dialogue, speech, text, "
    "subtitle, logo, watermark, low quality, distorted"
)


# --------------------------------------------------------------------------
# ffmpeg / ffprobe helpers
# --------------------------------------------------------------------------
def _tool(name: str) -> str:
    """Resolve ffmpeg/ffprobe, tolerating a minimal SSH PATH."""
    candidate = Path(name)
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    fallback = Path("/opt/homebrew/bin") / name
    if fallback.is_file():
        return str(fallback)
    raise RuntimeError(f"{name} not found; install it or fix PATH")


def run_tool(cmd: list[str], label: str) -> None:
    """Run a media tool and fail loudly with its stderr on error or timeout."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{label} timed out after 1800s; child killed") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-1500:]
        raise RuntimeError(f"{label} failed (exit {proc.returncode}): {detail}")


def _is_tcc_volume(path: Path) -> bool:
    """True for paths on the external volume that macOS TCC blocks under launchd.

    Verified 2026-09-13 with a launchd contract probe: a Homebrew ffprobe or
    ffmpeg child calling open() on /Volumes/* hangs forever because the consent
    prompt can never be shown to the user, while the same paths work fine when
    spawned from an interactive shell. Apple-signed python3 reads and writes the
    same files without any prompt, so all tool I/O runs on TMPDIR and Python
    performs the volume-side copies.
    """
    return os.name != "nt" and str(path).startswith("/Volumes/")


def _stage_input(path: Path) -> Path:
    """Return a locally readable copy of a volume file for ffmpeg/ffprobe."""
    if not _is_tcc_volume(path):
        return path
    stage = Path(tempfile.gettempdir()) / "aidrama_stage"
    stage.mkdir(parents=True, exist_ok=True)
    staged = stage / f"{file_sha256(path)[:16]}_{path.name}"
    if not staged.is_file() or staged.stat().st_size != path.stat().st_size:
        shutil.copy2(path, staged)
        print(f"[worker] staged {path.name} -> TMPDIR (macOS TCC gate)", flush=True)
    return staged


def _work_stage(job_id: str) -> Path:
    """Per-job scratch space on TMPDIR so every ffmpeg path stays off /Volumes."""
    work = Path(tempfile.gettempdir()) / "aidrama_work" / job_id
    (work / "units").mkdir(parents=True, exist_ok=True)
    (work / "shots").mkdir(parents=True, exist_ok=True)
    return work


def probe_video(path: Path) -> dict[str, Any]:
    """Return codec/width/height/duration for a media file (TCC-safe staging)."""
    probe_path = _stage_input(path)
    try:
        out = subprocess.run(
            [
                _tool("ffprobe"), "-v", "error",
                "-show_streams", "-show_format",
                "-of", "json", str(probe_path),
            ],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ffprobe timed out on {path.name}; TCC or I/O stall") from exc
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path.name}: {out.stderr.strip()[:400]}")
    data = json.loads(out.stdout)
    if not data.get("streams"):
        raise RuntimeError(f"{path.name} has no media stream")
    return data


def file_sha256(path: Path) -> str:
    """Hash media incrementally without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict) -> None:
    """Publish a complete record or preserve the previous record on failure."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def exclusive_worker(root: Path):
    """Hold an OS-backed lock across recovery and every worker execution mode."""
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / ".worker.lock").open("a+b")
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        yield
    finally:
        if acquired:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def validate_master_track(music: dict, duration: float) -> Path:
    """Reject missing, changed, or short master audio before costly generation."""
    source = music.get("master_track")
    master = Path(str(source).replace("\\", "/")) if source else None
    if master is None or not master.is_file():
        raise ValueError("CEO master track is required")
    if file_sha256(master) != music.get("sha256"):
        raise ValueError("CEO master track sha256 mismatch")
    info = probe_video(master)
    audio = next((stream for stream in info["streams"] if stream.get("codec_type") == "audio"), None)
    if audio is None or float(info["format"]["duration"]) + 0.001 < duration:
        raise ValueError("CEO master track has no audio or is shorter than the timeline")
    return master


def verify_delivery(path: Path, width: int, height: int, fps: float, frames: int) -> dict:
    """Validate technical delivery; this does not authorize publication."""
    info = probe_video(path)
    video = next((stream for stream in info["streams"] if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in info["streams"] if stream.get("codec_type") == "audio"), None)
    if video is None or video.get("codec_name") != "h264":
        raise ValueError("delivery must contain H.264 video")
    if (video.get("width"), video.get("height")) != (width, height):
        raise ValueError("delivery dimensions mismatch")
    if abs(float(Fraction(video.get("avg_frame_rate", "0"))) - fps) > 0.001:
        raise ValueError("delivery fps mismatch")
    if int(video.get("nb_frames", 0)) != frames:
        raise ValueError("delivery frame count mismatch")
    if audio is None or audio.get("codec_name") != "aac" or int(audio.get("sample_rate", 0)) != 48000:
        raise ValueError("delivery must contain AAC at 48000 Hz")
    duration = frames / fps
    if abs(float(audio.get("duration", 0)) - duration) > 1 / fps + 0.025:
        raise ValueError("delivery audio duration mismatch")
    run_tool([_tool("ffmpeg"), "-v", "error", "-xerror", "-i", str(path),
              "-f", "null", "-"], "full delivery decode")
    return info


def normalize_unit(source: Path, destination: Path, fps: float, frames: int) -> None:
    """Trim surplus model frames in Stage 1; never pad missing motion."""
    info = probe_video(source)
    video = next(stream for stream in info["streams"] if stream.get("codec_type") == "video")
    if float(video.get("duration", info["format"]["duration"])) + 0.001 < frames / fps:
        raise ValueError("generated unit is shorter than its target timeline")
    run_tool([_tool("ffmpeg"), "-y", "-v", "error", "-i", str(source),
              "-vf", f"setpts=PTS-STARTPTS,fps={fps},trim=end_frame={frames}",
              "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "23",
              "-pix_fmt", "yuv420p", "-flags", "+cgop", "-g", "48",
              "-keyint_min", "48", "-sc_threshold", "0", str(destination)],
             "normalize MV unit")


def concat_clips(clips: list[Path], destination: Path) -> None:
    """Losslessly join clips with the concat demuxer (no re-encode)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    listing = destination.parent / f".{destination.stem}.concat.txt"
    listing.write_text(
        "".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8"
    )
    try:
        run_tool(
            [
                _tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(listing),
                "-c", "copy", str(destination),
            ],
            f"concat -> {destination.name}",
        )
    finally:
        listing.unlink(missing_ok=True)


def mux_master_track(silent: Path, master: Path, destination: Path) -> None:
    """Attach the CEO-approved master track as the only audio stream (TCC-safe)."""
    duration = float(probe_video(silent)["format"]["duration"])
    silent_local = _stage_input(silent)
    master_local = _stage_input(master)
    run_tool(
        [
            _tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(silent_local), "-i", str(master_local),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-af", f"atrim=duration={duration},asetpts=PTS-STARTPTS", str(destination),
        ],
        "mux master track",
    )


# --------------------------------------------------------------------------
# ComfyUI client (local Wan 2.1)
# --------------------------------------------------------------------------
class ComfyClient:
    """Minimal ComfyUI HTTP client for the local Wan 2.1 text-to-video graph."""

    def __init__(self, base_url: str, timeout: int = 60):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.task_path: Path | None = None

    def _get(self, path: str) -> Any:
        with urllib.request.urlopen(f"{self.base}{path}", timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, payload: dict) -> Any:
        request = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def precondition(self, width: int, height: int) -> None:
        """Verify the server exposes every node/model this graph needs."""
        registry = self._get("/object_info")
        required = {
            "UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode",
            "EmptyHunyuanLatentVideo", "ModelSamplingSD3", "KSampler",
            "VAEDecode", "CreateVideo", "SaveVideo",
        }
        missing = sorted(required.difference(registry))
        if missing:
            raise RuntimeError(f"ComfyUI missing nodes: {missing}")
        for node, field, filename in (
            ("UNETLoader", "unet_name", WAN_UNET),
            ("CLIPLoader", "clip_name", WAN_CLIP),
            ("VAELoader", "vae_name", WAN_VAE),
        ):
            options = registry[node]["input"]["required"][field][0]
            if filename not in options:
                raise RuntimeError(f"ComfyUI missing model {filename} for {node}")
        _ = (width, height)

    def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        frames: int,
        fps: float,
        steps: int,
        cfg: float,
        seed: int,
        filename_prefix: str,
        timeout_sec: int,
    ) -> dict[str, str]:
        """Submit one Wan job, wait for it, and return the output file record."""
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {
                "unet_name": WAN_UNET, "weight_dtype": "default"}},
            "2": {"class_type": "ModelSamplingSD3", "inputs": {
                "model": ["1", 0], "shift": 8.0}},
            "3": {"class_type": "CLIPLoader", "inputs": {
                "clip_name": WAN_CLIP, "type": "wan", "device": "default"}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {
                "text": prompt, "clip": ["3", 0]}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {
                "text": negative_prompt, "clip": ["3", 0]}},
            "6": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {
                "width": width, "height": height, "length": frames,
                "batch_size": 1}},
            "7": {"class_type": "KSampler", "inputs": {
                "model": ["2", 0], "seed": seed, "steps": steps, "cfg": cfg,
                "sampler_name": "euler", "scheduler": "simple",
                "positive": ["4", 0], "negative": ["5", 0],
                "latent_image": ["6", 0], "denoise": 1.0}},
            "8": {"class_type": "VAELoader", "inputs": {"vae_name": WAN_VAE}},
            "9": {"class_type": "VAEDecode", "inputs": {
                "samples": ["7", 0], "vae": ["8", 0]}},
            "10": {"class_type": "CreateVideo", "inputs": {
                "images": ["9", 0], "fps": fps}},
            "11": {"class_type": "SaveVideo", "inputs": {
                "video": ["10", 0], "filename_prefix": filename_prefix,
                "format": "mp4"}},
        }
        request_hash = hashlib.sha256(json.dumps(workflow, sort_keys=True).encode("utf-8")).hexdigest()
        journal = {}
        if self.task_path and self.task_path.is_file():
            journal = json.loads(self.task_path.read_text(encoding="utf-8"))
            if journal.get("request_sha256") != request_hash:
                raise ValueError("task journal belongs to different generation inputs")
            if not journal.get("prompt_id"):
                raise RuntimeError("submission outcome unknown; reconcile ComfyUI before retrying")
        if not journal:
            journal = {"request_sha256": request_hash, "phase": "submitting", "updated_epoch": time.time()}
            if self.task_path:
                write_json_atomic(self.task_path, journal)
            submitted = self._post(
                "/prompt", {"prompt": workflow, "client_id": str(uuid.uuid4())}
            )
            prompt_id = submitted.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI rejected workflow: {submitted}")
            journal.update({"prompt_id": prompt_id, "phase": "submitted"})
            if self.task_path:
                write_json_atomic(self.task_path, journal)
        prompt_id = journal["prompt_id"]
        if journal.get("phase") == "completed" and journal.get("output"):
            return journal["output"]

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            journal["updated_epoch"] = time.time()
            if self.task_path:
                write_json_atomic(self.task_path, journal)
            history = self._get(f"/history/{prompt_id}").get(prompt_id)
            if history:
                status = history.get("status") or {}
                for message in status.get("messages") or []:
                    if message and message[0] == "execution_error":
                        raise RuntimeError(f"Wan execution error: {message[1]}")
                for node_output in (history.get("outputs") or {}).values():
                    for key in ("videos", "gifs", "images"):
                        files = node_output.get(key) or []
                        if files:
                            journal.update({"phase": "completed", "output": files[0]})
                            if self.task_path:
                                write_json_atomic(self.task_path, journal)
                            return files[0]
            time.sleep(5)
        raise TimeoutError(f"Wan generation timed out after {timeout_sec}s")

    def download(self, record: dict[str, str], destination: Path) -> Path:
        """Download a generated file from the ComfyUI output store."""
        query = urllib.parse.urlencode({
            "filename": record["filename"],
            "subfolder": record.get("subfolder", ""),
            "type": record.get("type", "output"),
        })
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(
            f"{self.base}/view?{query}", timeout=max(self.timeout, 300)
        ) as resp:
            payload = resp.read()
        if not payload:
            raise RuntimeError(f"empty download for {record['filename']}")
        temporary = destination.with_suffix(destination.suffix + ".part")
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
        return destination


# --------------------------------------------------------------------------
# Job maths
# --------------------------------------------------------------------------
def to_wan_frames(duration_sec: float, fps: float) -> int:
    """Round up to legal 4n+1 frames so Stage 1 can trim without padding."""
    if not math.isfinite(duration_sec) or not math.isfinite(fps) or duration_sec <= 0 or fps <= 0:
        raise ValueError("duration and fps must be finite and positive")
    target = max(5, math.ceil(duration_sec * fps - 1e-9))
    snapped = math.ceil((target - 1) / 4) * 4 + 1
    return max(5, snapped)


def frame_size(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    """Translate resolution + aspect ratio into 16-multiple dimensions."""
    long_edge = {"480p": 848, "720p": 1280, "1080p": 1920}.get(resolution)
    if not long_edge:
        raise ValueError(f"unsupported resolution {resolution!r}")
    if aspect_ratio == "9:16":
        short_edge = {"480p": 480, "720p": 720, "1080p": 1080}[resolution]
        return short_edge, long_edge
    if aspect_ratio == "16:9":
        short_edge = {"480p": 480, "720p": 720, "1080p": 1080}[resolution]
        return long_edge, short_edge
    raise ValueError(f"unsupported aspect ratio {aspect_ratio!r}")


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------
class RenderWorker:
    """Claims handoff jobs and renders them to finished episodes."""

    def __init__(self, handoff_root: Path, comfy_url: str, work_root: Path):
        self.root = handoff_root
        self.work_root = work_root
        self.comfy = ComfyClient(comfy_url)
        for name in ("inbox", "processing", "done", "failed", "work"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self._recover_stale()

    def _recover_stale(self) -> None:
        """Return jobs stranded in processing/ to the inbox.

        A unit that already finished on disk is reused on the retry, so
        re-claiming a partially rendered job costs only the unfinished units.
        Safe because a single worker owns this handoff root.
        """
        for stranded in sorted((self.root / "processing").glob("*.json")):
            target = self.root / "inbox" / stranded.name
            if target.exists():
                raise RuntimeError(f"recovery conflict: {stranded.name}; both jobs preserved")
            os.replace(stranded, target)
            print(f"[worker] recovered stalled job -> {target.name}", flush=True)

    # -- job discovery ----------------------------------------------------
    def claim(self) -> Path | None:
        """Atomically move the oldest inbox job into processing."""
        pending = sorted((self.root / "inbox").glob("*.json"), key=lambda p: p.stat().st_mtime)
        for candidate in pending:
            claimed = self.root / "processing" / candidate.name
            try:
                os.replace(candidate, claimed)
            except OSError:
                continue  # another worker took it
            return claimed
        return None

    def _finish(self, job_file: Path, bucket: str, status: dict) -> None:
        target_dir = self.root / bucket / job_file.stem
        target_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(target_dir / "status.json", status)
        job_file.unlink(missing_ok=True)

    # -- rendering --------------------------------------------------------
    def render(self, job_file: Path, timeout_sec: int) -> dict:
        """Render one job: units -> shots -> episode -> master track."""
        job = json.loads(job_file.read_text(encoding="utf-8"))
        job_id = job.get("job_id") or job_file.stem
        production = job["production"]
        resolution = production.get("resolution", "480p")
        aspect = production.get("aspect_ratio", "9:16")
        fps = float(production.get("fps", 20))
        steps = int(production.get("steps", 20))
        cfg = float(production.get("cfg", 6.0))
        width, height = frame_size(resolution, aspect)
        if resolution != "480p" or fps != 20 or (steps < 20 and job.get("purpose") != "engineering_smoke"):
            raise ValueError("job violates the 480p/20fps/20-step production policy")
        if Path(job_id).name != job_id or "/" in job_id or "\\" in job_id or job_id in (".", ".."):
            raise ValueError("invalid job identifier")
        output_name = job.get("output", {}).get("file", f"{job_id}.mp4")
        if Path(output_name).name != output_name or "/" in output_name or "\\" in output_name:
            raise ValueError("output must be a filename")
        total_frames = 0
        shot_numbers = set()
        for shot in job["shots"]:
            shot_number = int(shot["shot_number"])
            if shot_number <= 0 or shot_number in shot_numbers:
                raise ValueError("duplicate or invalid shot number")
            shot_numbers.add(shot_number)
            unit_numbers = set()
            for unit in shot.get("units") or [{"duration_sec": shot["duration_sec"]}]:
                unit_number = int(unit.get("index", 1))
                if unit_number <= 0 or unit_number in unit_numbers:
                    raise ValueError("duplicate or invalid unit number")
                unit_numbers.add(unit_number)
                duration = float(unit["duration_sec"])
                frames = int(unit.get("target_frames") or round(duration * fps))
                if not math.isfinite(duration) or duration <= 0 or frames <= 0 or abs(frames - duration * fps) > 1:
                    raise ValueError("invalid unit timeline")
                total_frames += frames
        if total_frames <= 0:
            raise ValueError("empty timeline")
        if job.get("target_frames", total_frames) != total_frames:
            raise ValueError("declared timeline frame count mismatch")
        master_path = validate_master_track(job.get("music") or {}, total_frames / fps)

        # All intermediate media lives on TMPDIR: launchd cannot grant ffmpeg
        # access to /Volumes (TCC), while Python copies to /Volumes are allowed.
        # Consequence: per-unit caches reset when TMPDIR is cleared.
        work = _work_stage(job_id)

        self.comfy.precondition(width, height)
        started = time.time()
        status: dict[str, Any] = {
            "job_id": job_id,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "resolution": f"{width}x{height}",
            "fps": fps,
            "shots": [],
            "findings": [],
        }

        shot_files: list[Path] = []
        for shot in job["shots"]:
            shot_no = int(shot["shot_number"])
            units = shot.get("units") or [{"index": 1, "duration_sec": shot["duration_sec"]}]
            unit_files: list[Path] = []
            for unit in units:
                unit_no = int(unit["index"])
                target_frames = int(unit.get("target_frames") or round(float(unit["duration_sec"]) * fps))
                frames = to_wan_frames(target_frames / fps, fps)
                seed = int(unit.get("seed", shot.get("seed", 260911)))
                target = work / "units" / f"sh{shot_no:03d}_u{unit_no:02d}.mp4"
                cache_path = target.with_suffix(".json")
                inputs = {"production": production, "shot": shot, "unit": unit,
                          "models": [WAN_UNET, WAN_CLIP, WAN_VAE], "worker_sha256": file_sha256(Path(__file__))}
                input_hash = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode("utf-8")).hexdigest()
                if target.is_file() and target.stat().st_size > 0:
                    cached = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
                    if cached.get("input_sha256") != input_hash or cached.get("media_sha256") != file_sha256(target):
                        raise ValueError(f"unverified or stale cache: {target.name}; explicit regeneration required")
                    probe_video(target)
                    unit_files.append(target)
                    print(f"[{job_id}] unit {target.name} reused", flush=True)
                    continue
                print(
                    f"[{job_id}] unit sh{shot_no:03d}_u{unit_no:02d} "
                    f"submitting {frames}f @ {fps}fps {width}x{height}",
                    flush=True,
                )
                self.comfy.task_path = target.with_suffix(".task.json")
                record = self.comfy.generate(
                    prompt=unit.get("prompt") or shot["prompt"],
                    negative_prompt=shot.get("negative_prompt") or DEFAULT_NEGATIVE,
                    width=width,
                    height=height,
                    frames=frames,
                    fps=fps,
                    steps=steps,
                    cfg=cfg,
                    seed=seed,
                    filename_prefix=f"handoff/{job_id}/sh{shot_no:03d}_u{unit_no:02d}",
                    timeout_sec=timeout_sec,
                )
                raw = target.with_name(target.stem + "_raw.mp4")
                self.comfy.download(record, raw)
                probe = probe_video(raw)
                stream = probe["streams"][0]
                if (int(stream["width"]), int(stream["height"])) != (width, height):
                    raise RuntimeError(
                        f"unit {target.name} rendered {stream['width']}x{stream['height']}, "
                        f"expected {width}x{height}"
                    )
                normalize_unit(raw, target, fps, target_frames)
                write_json_atomic(cache_path, {"input_sha256": input_hash, "media_sha256": file_sha256(target)})
                unit_files.append(target)

            shot_file = work / "shots" / f"sh{shot_no:03d}.mp4"
            concat_clips(unit_files, shot_file)
            shot_files.append(shot_file)
            status["shots"].append({
                "shot_number": shot_no,
                "units": len(unit_files),
                "file": str(shot_file),
                "duration_sec": float(probe_video(shot_file)["format"]["duration"]),
            })
            print(
                f"[{job_id}] shot {shot_no} done "
                f"({len(unit_files)} units, {time.time() - started:.0f}s elapsed)",
                flush=True,
            )

        silent = work / "episode_silent.mp4"
        concat_clips(shot_files, silent)

        validate_master_track(job["music"], total_frames / fps)
        staged = work / "delivery.mp4"
        mux_master_track(silent, master_path, staged)
        probe = verify_delivery(staged, width, height, fps, total_frames)
        output_dir = self.root / "done" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        final = output_dir / output_name
        shutil.copy2(staged, final.with_suffix(".mp4.part"))
        os.replace(final.with_suffix(".mp4.part"), final)
        status["audio"] = {"source": str(master_path), "mode": "ceo_master_track", "sha256": job["music"]["sha256"]}
        stream = next(stream for stream in probe["streams"] if stream.get("codec_type") == "video")
        status.update({
            "state": "technical_qc_passed",
            "publish_eligible": False,
            "pending_reviews": ["visual_content", "watermark", "variation_policy", "ceo_approval"],
            "target_frames": total_frames,
            "output_sha256": file_sha256(final),
            "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_sec": round(time.time() - started, 1),
            "output": str(final),
            "codec": stream["codec_name"],
            "size": f"{stream['width']}x{stream['height']}",
            "duration_sec": float(probe["format"]["duration"]),
            "pass": not status["findings"],
        })
        return status

    # -- entry point ------------------------------------------------------
    def run_job(self, job_file: Path, timeout_sec: int) -> dict:
        """Render a claimed job and file it under done/ or failed/."""
        try:
            status = self.render(job_file, timeout_sec)
            if not status.get("pass"):
                raise ValueError(f"delivery rejected: {status.get('findings')}")
            self._finish(job_file, "done", status)
            print(f"[{job_file.stem}] DONE -> {status['output']}", flush=True)
            return status
        except Exception as exc:  # noqa: BLE001 - worker must keep serving
            status = {
                "job_id": job_file.stem,
                "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
                "pass": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            self._finish(job_file, "failed", status)
            print(f"[{job_file.stem}] FAILED: {exc}", file=sys.stderr, flush=True)
            return status

    def loop(self, interval: int, timeout_sec: int) -> None:
        """Poll the inbox forever."""
        print(f"[worker] watching {self.root / 'inbox'}", flush=True)
        while True:
            job_file = self.claim()
            if job_file:
                self.run_job(job_file, timeout_sec)
            else:
                time.sleep(interval)


# --------------------------------------------------------------------------
# Single-instance guard (LaunchAgent <-> manual start)
# --------------------------------------------------------------------------
def _other_worker_running() -> int:
    """Return the PID of another live mac_wan_worker.py, or 0 when alone.

    The persistent --watch daemon must have exactly one owner: the LaunchAgent
    copy (auto-revived after a Mac reboot) and a manually started copy must
    never fight over the handoff queue. All CLI modes check legacy workers
    before acquiring the OS-backed handoff lock and recovering stranded jobs.

    Only Python processes actually running the worker script count. A bare
    `pgrep -f` match is not enough: shell wrappers, editors, log tails or ssh
    scripts that merely mention the script name would otherwise be mistaken
    for a live worker and turn the LaunchAgent into an exit loop.
    """
    try:
        found = subprocess.run(
            ["pgrep", "-f", "mac_wan_worker.py"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0  # no pgrep on this host: fail open, the queue still works
    for token in found.split():
        try:
            pid = int(token)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        # Ask ps for the real command line and require a Python interpreter.
        try:
            command = subprocess.run(
                ["ps", "-o", "command=", "-p", str(pid)],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        parts = command.split()
        if not parts:
            continue
        if "python" in parts[0].lower() and "mac_wan_worker.py" in command:
            return pid
    return 0


def main() -> int:
    # Flush progress immediately even when stdout is redirected to a log file.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", default=os.getenv("HANDOFF_ROOT", DEFAULT_HANDOFF))
    parser.add_argument("--comfy-url", default=os.getenv("COMFY_URL", DEFAULT_COMFY))
    parser.add_argument("--work-root", default=None)
    parser.add_argument("--once", action="store_true", help="process the oldest job and exit")
    parser.add_argument("--watch", action="store_true", help="poll the inbox forever")
    parser.add_argument("--job", help="job_id already sitting in inbox/")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument(
        "--timeout",
        type=int,
        default=21600,
        help="per-unit generation budget in seconds for a 480p unit on M4 (default: 21600 = 6h)",
    )
    args = parser.parse_args()

    # The single-owner check must run BEFORE the worker object is built: its
    # constructor recovers stalled jobs, which would otherwise shuffle the job
    # a live worker is still rendering in ComfyUI.
    other = _other_worker_running()
    if other:
        print(f"[worker] another worker is already running (pid {other}); refusing recovery",
              file=sys.stderr, flush=True)
        return 1

    root = Path(args.handoff)
    try:
        with exclusive_worker(root):
            return _run_locked_worker(args, root)
    except (OSError, RuntimeError) as exc:
        print(f"[worker] startup failed: {exc}", file=sys.stderr, flush=True)
        return 1


def _run_locked_worker(args: argparse.Namespace, root: Path) -> int:
    """Recover and execute only while the CLI holds the exclusive root lock."""
    work_root = Path(args.work_root) if args.work_root else root / "work"
    worker = RenderWorker(root, args.comfy_url, work_root)

    if args.job:
        source = root / "inbox" / f"{args.job}.json"
        if not source.is_file():
            print(f"[FATAL] no such job in inbox: {source}", file=sys.stderr)
            return 1
        claimed = root / "processing" / source.name
        os.replace(source, claimed)
        status = worker.run_job(claimed, args.timeout)
        return 0 if status.get("pass") else 1

    if args.watch:
        worker.loop(args.interval, args.timeout)
        return 0

    job_file = worker.claim()
    if not job_file:
        print("[worker] inbox empty")
        return 0
    status = worker.run_job(job_file, args.timeout)
    return 0 if status.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
