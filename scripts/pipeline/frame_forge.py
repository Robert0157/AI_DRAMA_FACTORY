#!/usr/bin/env python3
"""Frame forge: first-frame image generation on the Mac ComfyUI (Flux.1-schnell).

G1 of the A-line upgrade: every expensive video step is gated by an approved
FIRST FRAME.  This tool turns an approved-style prompt into 9:16 stills via
the ComfyUI-GGUF route (fp8 checkpoints cannot sample on Apple MPS: PyTorch
raises "Undefined type Float8_e4m3fn").  Graph:

  UnetLoaderGGUF(flux1-schnell-Q6_K) + DualCLIPLoaderGGUF(t5 Q6_K + clip_l)
  -> CLIPTextEncode x2 -> EmptyLatentImage
  -> KSampler(4 steps, cfg 1.0, euler/simple) -> VAEDecode(ae) -> SaveImage

Licensing: FLUX.1-schnell is Apache-2.0 (commercial use OK); ComfyUI-GGUF is
Apache-2.0.  Model files are pinned in integrations/comfyui/VERSION.lock with
sha256 fingerprints (pin-once-validated).

Usage (PC, talking to the Mac over LAN):
  venv\\Scripts\\python.exe scripts\\pipeline\\frame_forge.py ^
    --prompt "empty moonlit conservatory ..." --width 768 --height 1344 ^
    --seed 7 --out "CEO/02_素材與CP-D/first_frames"

Exit codes: 0 = image written; 1 = failure (zero silent failures).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DEFAULT_COMFY = "http://192.168.2.200:8188"
UNET_GGUF = "flux1-schnell-Q6_K.gguf"
T5_GGUF = "t5-v1_1-xxl-encoder-Q6_K.gguf"
CLIP_L = "clip_l.safetensors"
VAE_FILE = "ae.safetensors"


def _post(base: str, path: str, payload: dict, timeout: int = 120) -> dict:
    request = urllib.request.Request(
        f"{base}{path}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(base: str, path: str, timeout: int = 60) -> dict:
    with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_graph(prompt: str, negative: str, width: int, height: int,
                steps: int, cfg: float, seed: int) -> dict:
    """GGUF first-frame graph (fp8 checkpoints are unsupported on MPS)."""
    return {
        "1": {"class_type": "UnetLoaderGGUF",
              "inputs": {"unet_name": UNET_GGUF}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["8", 0]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["8", 0]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "seed": seed, "steps": steps,
                         "cfg": cfg, "sampler_name": "euler",
                         "scheduler": "simple",
                         "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "denoise": 1.0}},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["9", 0]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"images": ["6", 0], "filename_prefix": "firstframe"}},
        "8": {"class_type": "DualCLIPLoaderGGUF",
              "inputs": {"clip_name1": T5_GGUF, "clip_name2": CLIP_L,
                         "type": "flux"}},
        "9": {"class_type": "VAELoader",
              "inputs": {"vae_name": VAE_FILE}},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="")
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=1344)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--cfg", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--comfy", default=DEFAULT_COMFY)
    parser.add_argument("--out", default=".")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="generation budget in seconds")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else int(time.time()) % 1_000_000
    base = args.comfy.rstrip("/")

    # Refresh the server's file lists so a just-downloaded checkpoint is seen.
    for refresh_path in ("/api/refresh", "/refresh"):
        try:
            _post(base, refresh_path, {})
            break
        except Exception:  # noqa: BLE001 - best effort; submit will fail loudly
            continue

    try:
        submitted = _post(base, "/prompt",
                          {"prompt": build_graph(args.prompt, args.negative,
                                                 args.width, args.height,
                                                 args.steps, args.cfg, seed),
                           "client_id": str(uuid.uuid4())})
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] submit failed: {exc}", file=sys.stderr)
        return 1
    prompt_id = submitted.get("prompt_id")
    if not prompt_id:
        print(f"[FATAL] rejected: {submitted}", file=sys.stderr)
        return 1
    print(f"submitted prompt_id={prompt_id} seed={seed} {args.width}x{args.height} "
          f"steps={args.steps} cfg={args.cfg}")

    deadline = time.monotonic() + args.timeout
    record = None
    while time.monotonic() < deadline:
        history = _get(base, f"/history/{prompt_id}").get(prompt_id)
        if history:
            status = history.get("status") or {}
            for message in status.get("messages") or []:
                if message and message[0] == "execution_error":
                    print(f"[FATAL] execution error: {message[1]}", file=sys.stderr)
                    return 1
            for node_output in (history.get("outputs") or {}).values():
                files = node_output.get("images") or []
                if files:
                    record = files[0]
                    break
            if record:
                break
        time.sleep(3)
    if not record:
        print("[FATAL] generation timed out", file=sys.stderr)
        return 1

    query = urllib.parse.urlencode({"filename": record["filename"],
                                    "subfolder": record.get("subfolder", ""),
                                    "type": record.get("type", "output")})
    with urllib.request.urlopen(f"{base}/view?{query}", timeout=300) as resp:
        payload = resp.read()
    if not payload:
        print("[FATAL] empty download", file=sys.stderr)
        return 1

    stamp = time.strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"firstframe_{stamp}_s{seed}.png"
    target.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    print(f"IMAGE_OK {target} ({len(payload)//1024}KB) sha256={digest[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
