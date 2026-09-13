# -*- coding: utf-8 -*-
"""
Suno music client with a dual-backend strategy (TTAPI is retired):

  backend="official"  -> Suno official API (studio-api.suno.ai) Bearer token
  backend="docker"    -> local gcui-art/suno-api container (localhost:3000)
                         [existing original scaffold at services/suno-api/]

Only `generate` / `fetch` are required by Auto_Drama's music bridge. Polling
uses exponential backoff with a hard cap (never remove per CEO rule).
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]


class SunoError(RuntimeError):
    """Raised on any Suno backend failure."""


class SunoClient:
    """Generate and fetch Suno tracks through the configured backend."""

    OFFICIAL_BASE = "https://studio-api.suno.ai"
    DOCKER_BASE = "http://localhost:3000"

    def __init__(self, backend: str = "official", api_key: str = "",
                 docker_base: str = "", max_retries: int = 5,
                 backoff_base: float = 2.0, backoff_cap: float = 60.0) -> None:
        if requests is None:
            raise SunoError("requests package is required for live mode")
        self.backend = backend
        self.api_key = api_key
        self.base = docker_base or self.DOCKER_BASE if backend == "docker" else self.OFFICIAL_BASE
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        if backend == "official" and not api_key:
            raise SunoError("SunoClient: SUNO_API_KEY is required for official backend")

    # ---------- auth header ----------
    def _headers(self) -> Dict[str, str]:
        if self.backend == "official":
            return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        # Docker backend uses its own cookie-based session; no bearer header.
        return {"Content-Type": "application/json"}

    # ---------- generation ----------
    def generate(self, prompt: str, title: str = "", tags: str = "",
                 instrumental: bool = True, duration: int = 120,
                 is_custom: bool = True, mv: str = "chirp-v5-5") -> Dict[str, Any]:
        """
        Generate one track.
        Returns backend payload containing the job/song id to poll.
        """
        if self.backend == "official":
            payload: Dict[str, Any] = {
                "mv": mv,
                "prompt": prompt,          # custom lyrics/gpt description prompt
                "title": title or "auto_drama_track",
                "tags": tags,
                "make_instrumental": instrumental,
                "continue_clip_id": None,
                "continue_at": None,
            }
            path = "/api/generate"
        else:
            payload = {
                "prompt": prompt,
                "tags": tags,
                "title": title or "auto_drama_track",
                "make_instrumental": instrumental,
                "is_custom": is_custom,
                "mv": mv,
                "gpt_description_prompt": prompt,
            }
            path = "/api/custom_generate"
        return self._post_with_backoff(path, payload)

    def extend(self, music_id: str, prompt: str, tags: str = "",
               duration: int = 120) -> Dict[str, Any]:
        """Extend an existing track for emotional continuity between segments."""
        if self.backend == "official":
            payload = {
                "mv": "chirp-v5-5",
                "prompt": prompt,
                "continue_clip_id": music_id,
                "continue_at": 90,
                "make_instrumental": True,
                "tags": tags,
            }
            path = "/api/generate"
        else:
            payload = {"music_id": music_id, "prompt": prompt, "tags": tags, "duration": duration}
            path = "/api/extend_audio"
        return self._post_with_backoff(path, payload)

    # ---------- fetch ----------
    def fetch(self, job_id: str) -> Dict[str, Any]:
        path = "/api/get" if self.backend == "official" else "/api/get"
        params = {"ids": job_id}
        resp = requests.get(f"{self.base}{path}", params=params,
                            headers=self._headers(), timeout=60)
        if resp.status_code >= 400:
            raise SunoError(f"Suno fetch HTTP {resp.status_code}: {resp.text[:400]}")
        return resp.json()

    # ---------- internal ----------
    def _post_with_backoff(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base}{path}"
        attempt = 0
        while True:
            try:
                resp = requests.post(url, json=payload, headers=self._headers(), timeout=120)
                # 429 / 5xx -> retry with exponential backoff (CEO rule).
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    attempt += 1
                    delay = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
                    time.sleep(delay)
                    continue
                if resp.status_code >= 400:
                    raise SunoError(f"Suno POST {path} HTTP {resp.status_code}: {resp.text[:400]}")
                return resp.json()
            except requests.RequestException as exc:
                if attempt < self.max_retries:
                    attempt += 1
                    delay = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
                    time.sleep(delay)
                    continue
                raise SunoError(f"Suno POST {path} network failure: {exc}") from exc
