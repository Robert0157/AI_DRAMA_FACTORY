#!/usr/bin/env python3
"""Extract the bundled Flux VAE from a single-file checkpoint into a standalone file.

Why: the official BFL ae.safetensors download is gated (HTTP 401), while the
Comfy-Org single-file checkpoint (already byte-verified: sha256 ead42627...)
embeds the same VAE under `vae.*` keys.  Lazy safetensors reads fetch ONLY
those tensors, so extraction takes seconds and provenance is auditable.

Key detail: standalone VAE files use BARE keys (`decoder.conv_in.weight`);
ComfyUI's VAE.__init__ (comfy/sd.py) matches on those, so the checkpoint's
`vae.` prefix MUST be stripped or the loader raises "VAE is invalid: None".

Verified 2026-09-13: 244 tensors -> 335,304,060-byte ae.safetensors
(sha256 49b6f4ab...) -> the Flux GGUF stack produced 768x1344 first-frame
stills via scripts/pipeline/frame_forge.py.

Run on the Mac with the ComfyUI venv python.
"""
from pathlib import Path

from safetensors import safe_open
from safetensors.torch import save_file

BASE = Path("/Volumes/AI_Workspace/AI_Drama_Factory/integrations/comfyui/models")
SRC = BASE / "checkpoints" / "flux1-schnell-fp8.safetensors"
DST = BASE / "vae" / "ae.safetensors"

with safe_open(str(SRC), framework="pt", device="cpu") as f:
    keys = list(f.keys())
    vae_keys = [k for k in keys if k.startswith("vae.")]
    if not vae_keys:
        vae_keys = [k for k in keys if k.startswith("first_stage_model.")]
    print(f"total_keys={len(keys)} vae_keys={len(vae_keys)}")
    if not vae_keys:
        raise SystemExit(f"no VAE keys found; sample keys: {keys[:12]}")
    tensors = {}
    for k in vae_keys:
        short = k[len("vae."):] if k.startswith("vae.") else k
        if short.startswith("first_stage_model."):
            short = short[len("first_stage_model."):]
        tensors[short] = f.get_tensor(k)
    for sentinel in ("decoder.conv_in.weight", "encoder.down.2.downsample.conv.weight"):
        print(sentinel, "OK" if sentinel in tensors else "MISSING")

save_file(tensors, str(DST), metadata={
    "source": "extracted from flux1-schnell-fp8.safetensors "
              "sha256:ead426278b49030e9da5df862994f25ce94ab2ee4df38b556ddddb3db093bf72"})
print(f"WROTE {DST} tensors={len(tensors)}")
