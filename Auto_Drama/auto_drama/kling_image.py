# -*- coding: utf-8 -*-
"""
Kling AI official image generation client (direct, no middleman).

Official auth requires a HS256 JWT signed with (access_key, secret_key):
  header {"alg":"HS256","typ":"JWT"}
  payload {"iss": access_key, "exp": now+1800, "nbf": now-5}
Flow: POST /v1/images/generations -> poll GET /v1/images/generations/{task_id}
until task_status == 'succeed', then download the produced image.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]


class KlingError(RuntimeError):
    """Raised on Kling API failures (never swallowed silently)."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_kling_jwt(access_key: str, secret_key: str, ttl_sec: int = 1800) -> str:
    """Mint a Kling official bearer JWT from AK/SK (HS256)."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"iss": access_key, "exp": now + ttl_sec, "nbf": now - 5}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")) + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    )
    sig = hmac.new(secret_key.encode("utf-8"), signing_input.encode("ascii"),
                   hashlib.sha256).digest()
    return signing_input + "." + _b64url(sig)


class KlingImageClient:
    """Generate and download images from Kling official image API."""

    BASE = "https://api.klingai.com"

    def __init__(self, access_key: str, secret_key: str,
                 base_url: str = BASE, timeout_sec: int = 60) -> None:
        if requests is None:
            raise KlingError("requests package is required")
        if not access_key or not secret_key:
            raise KlingError("Kling access/secret keys are required")
        self.base_url = (base_url or self.BASE).rstrip("/")
        self._ak = access_key
        self._sk = secret_key
        self.timeout_sec = timeout_sec

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + make_kling_jwt(self._ak, self._sk),
        }

    def generate(self, prompt: str, out_path: Path, model: str = "kling-image",
                 aspect_ratio: str = "16:9", reference_urls: Optional[List[str]] = None,
                 poll_attempts: int = 90, poll_interval_sec: float = 4.0) -> Path:
        """Generate one image, poll to completion, download it, save PNG/JPG."""
        body: dict = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "aspect_ratio": aspect_ratio,
            "callback_url": "",
        }
        refs = [u for u in (reference_urls or []) if u]
        if refs:
            # Kling subject/face reference (official field names).
            body["image_reference"] = [{"type": "subject", "url": refs[0]}]
            body["image_fidelity"] = 0.5

        submit = requests.post(f"{self.base_url}/v1/images/generations",
                               json=body, headers=self._headers(),
                               timeout=self.timeout_sec)
        if submit.status_code >= 400:
            raise KlingError(
                f"Kling submit HTTP {submit.status_code}: {submit.text[:500]}"
            )
        data = submit.json()
        if data.get("code") not in (None, 0):
            raise KlingError(f"Kling submit error {data.get('code')}: "
                             f"{data.get('message') or data}")
        task_id = (data.get("data") or {}).get("task_id")
        if not task_id:
            raise KlingError(f"Kling no task_id in submit response: {data}")

        # Poll until succeed/failed.
        for attempt in range(poll_attempts):
            time.sleep(poll_interval_sec)
            q = requests.get(
                f"{self.base_url}/v1/images/generations/{task_id}",
                headers=self._headers(), timeout=self.timeout_sec,
            )
            if q.status_code >= 400:
                continue
            qd = q.json()
            status = ((qd.get("data") or {}).get("task_status") or "")
            if status == "succeed":
                images = ((qd.get("data") or {}).get("task_result") or {}).get("images") or []
                if not images or not images[0].get("url"):
                    raise KlingError(f"Kling succeed but no image url: {qd}")
                return self._download(images[0]["url"], out_path)
            if status == "failed":
                msg = ((qd.get("data") or {}).get("task_status_msg") or "unknown")
                raise KlingError(f"Kling task failed: {msg}")
        raise KlingError(f"Kling image task {task_id} timed out after "
                         f"{poll_attempts * poll_interval_sec:.0f}s")

    @staticmethod
    def _download(url: str, out_path: Path) -> Path:
        r = requests.get(url, timeout=180)
        if r.status_code >= 400:
            raise KlingError(f"Kling download HTTP {r.status_code}: {r.text[:300]}")
        low = url.split("?")[0].lower()
        ext = ".png" if low.endswith(".png") else ".jpg"
        out_path = out_path.with_suffix(ext)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(r.content)
        return out_path
