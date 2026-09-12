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
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
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
    """Run a media tool and fail loudly with its stderr on error."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-1500:]
        raise RuntimeError(f"{label} failed (exit {proc.returncode}): {detail}")


def probe_video(path: Path) -> dict[str, Any]:
    """Return codec/width/height/duration for a media file."""
    out = subprocess.run(
        [
            _tool("ffprobe"), "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,avg_frame_rate",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path.name}: {out.stderr.strip()[:400]}")
    data = json.loads(out.stdout)
    if not data.get("streams"):
        raise RuntimeError(f"{path.name} has no video stream")
    return data


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
    """Attach the CEO-approved master track as the only audio stream."""
    run_tool(
        [
            _tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(silent), "-i", str(master),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-shortest", str(destination),
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
        submitted = self._post(
            "/prompt", {"prompt": workflow, "client_id": str(uuid.uuid4())}
        )
        prompt_id = submitted.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI rejected workflow: {submitted}")

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
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
        destination.write_bytes(payload)
        return destination


# --------------------------------------------------------------------------
# Job maths
# --------------------------------------------------------------------------
def to_wan_frames(duration_sec: float, fps: float) -> int:
    """Wan needs 4n+1 frames; snap to the nearest legal count."""
    target = max(5, int(round(duration_sec * fps)))
    snapped = ((target - 1) // 4) * 4 + 1
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
                target.unlink()
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
        (target_dir / "status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8"
        )
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

        work = self.work_root / job_id
        (work / "units").mkdir(parents=True, exist_ok=True)
        (work / "shots").mkdir(parents=True, exist_ok=True)

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
                frames = to_wan_frames(float(unit["duration_sec"]), fps)
                seed = int(unit.get("seed", shot.get("seed", 260911)))
                target = work / "units" / f"sh{shot_no:03d}_u{unit_no:02d}.mp4"
                if target.is_file() and target.stat().st_size > 0:
                    unit_files.append(target)
                    print(f"[{job_id}] unit {target.name} reused", flush=True)
                    continue
                print(
                    f"[{job_id}] unit sh{shot_no:03d}_u{unit_no:02d} "
                    f"submitting {frames}f @ {fps}fps {width}x{height}",
                    flush=True,
                )
                record = self.comfy.generate(
                    prompt=shot["prompt"],
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
                self.comfy.download(record, target)
                probe = probe_video(target)
                stream = probe["streams"][0]
                if (int(stream["width"]), int(stream["height"])) != (width, height):
                    raise RuntimeError(
                        f"unit {target.name} rendered {stream['width']}x{stream['height']}, "
                        f"expected {width}x{height}"
                    )
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

        output_dir = self.root / "done" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        final = output_dir / job.get("output", {}).get("file", f"{job_id}.mp4")

        master = (job.get("music") or {}).get("master_track")
        # Older Windows dispatchers wrote backslash separators; POSIX needs "/".
        master_path = Path(master.replace("\\", "/")) if master else None
        if master_path and master_path.is_file():
            mux_master_track(silent, master_path, final)
            status["audio"] = {"source": str(master_path), "mode": "ceo_master_track"}
        else:
            shutil.copy2(silent, final)
            status["audio"] = {"source": None, "mode": "silent_needs_master_track"}
            status["findings"].append(
                f"master track unavailable: {master!r}; delivered silent cut"
            )

        probe = probe_video(final)
        stream = probe["streams"][0]
        status.update({
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
    never fight over the handoff queue. One-shot modes (--once / --job) stay
    exempt so manual interventions keep working.

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
    if args.watch:
        other = _other_worker_running()
        if other:
            print(
                f"[worker] another worker is already running (pid {other}); "
                "exiting so the handoff queue keeps a single owner",
                flush=True,
            )
            return 0

    root = Path(args.handoff)
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
