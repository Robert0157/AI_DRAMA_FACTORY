# -*- coding: utf-8 -*-
"""
Zhipu (智譜) CogView image generation client.

Endpoint: POST /api/paas/v4/images/generations (BigModel OpenAI-compatible)
Auth: Authorization: Bearer <api_key>
NOTE: free-tier output carries a watermark; paid models remove it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]


class ZhipuImageError(RuntimeError):
    """Raised on Zhipu CogView API failures (never swallowed silently)."""


class ZhipuImageClient:
    """Generate an image via Zhipu CogView and download it locally."""

    BASE = "https://open.bigmodel.cn/api/paas/v4"

    def __init__(self, api_key: str, base_url: str = BASE,
                 model: str = "cogview-3-flash") -> None:
        if requests is None:
            raise ZhipuImageError("requests package is required")
        if not api_key:
            raise ZhipuImageError("Zhipu api_key is required")
        self.base_url = (base_url or self.BASE).rstrip("/")
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, out_path: Path, aspect_ratio: str = "16:9",
                 size: str = "1024x1024") -> Path:
        """Generate one image (square for CogView-3-flash) and save it."""
        body = {"model": self.model, "prompt": prompt, "size": size}
        resp = requests.post(
            f"{self.base_url}/images/generations",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=body, timeout=240,
        )
        if resp.status_code >= 400:
            raise ZhipuImageError(
                f"Zhipu HTTP {resp.status_code}: {resp.text[:500]}"
            )
        data = resp.json()
        urls = [d.get("url") for d in (data.get("data") or []) if d.get("url")]
        if not urls:
            raise ZhipuImageError(f"Zhipu no image url in response: {str(data)[:400]}")
        dl = requests.get(urls[0], timeout=240)
        if dl.status_code >= 400:
            raise ZhipuImageError(
                f"Zhipu download HTTP {dl.status_code}: {dl.text[:300]}"
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path = out_path.with_suffix(".png")
        out_path.write_bytes(dl.content)
        return out_path
