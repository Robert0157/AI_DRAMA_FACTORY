# -*- coding: utf-8 -*-
"""
BytePlus ModelArk — Dreamina-Seedance-2.5 video generation client (CEO 唯一合法引擎).

Reference (official curl example, 2026-09-09):
  POST https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks
  model: dreamina-seedance-2-5-260628
  content: [ {text}, {image_url role=reference_image}... {video_url}... {audio_url}... ]
  generate_audio / ratio / duration / watermark
Submit returns a task id; poll GET .../contents/generations/tasks/{id} until
status == successed, then download the produced video.

Retry policy (CEO §3.2): 429 / 5xx 走指數退避，最多重試 3 次，禁止無限/靜默重試。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SeedanceError(RuntimeError):
    """Raised on BytePlus Seedance failures (never swallowed silently)."""


class BytePlusSeedanceClient:
    """Minimal client for Dreamina-Seedance-2.5 via BytePlus ModelArk."""

    DEFAULT_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"
    DEFAULT_MODEL = "dreamina-seedance-2-5-260628"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE,
                 model: str = DEFAULT_MODEL, timeout_sec: int = 120) -> None:
        if requests is None:
            raise SeedanceError("requests package is required")
        if not api_key:
            raise SeedanceError("BytePlus api_key is required")
        self.base_url = (base_url or self.DEFAULT_BASE).rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec

    def _headers(self) -> dict:
        return {"Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key}

    def _should_retry(self, status: int) -> bool:
        # CEO §3.2：僅 429 / 5xx 需要退避重試；4xx（參數/權限錯誤）直接 loud raise
        return status in _RETRYABLE_STATUS

    def _sleep_backoff(self, attempt: int) -> None:
        # 指數退避：1s -> 2s -> 4s（attempt 從 0 起算）
        time.sleep(min(1.0 * (2 ** attempt), 8.0))

    # ------------------------------------------------------------------ submit
    def submit(self, prompt: str, reference_images: Optional[List[str]] = None,
               reference_videos: Optional[List[str]] = None,
               reference_audios: Optional[List[str]] = None,
               duration: int = 5, ratio: str = "16:9",
               generate_audio: bool = False, watermark: bool = False) -> str:
        """Create a generation task; returns the task id.

        Retries on 429/5xx with exponential backoff (max 3 attempts).
        """
        content: List[dict] = [{"type": "text", "text": prompt}]
        for url in (reference_images or []):
            content.append({"type": "image_url",
                            "image_url": {"url": url},
                            "role": "reference_image"})
        for url in (reference_videos or []):
            content.append({"type": "video_url",
                            "video_url": {"url": url},
                            "role": "reference_video"})
        for url in (reference_audios or []):
            content.append({"type": "audio_url",
                            "audio_url": {"url": url},
                            "role": "reference_audio"})
        body = {
            "model": self.model,
            "content": content,
            "generate_audio": generate_audio,
            "ratio": ratio,
            "duration": duration,
            "watermark": watermark,
        }
        max_attempts = 3
        last_err: Optional[SeedanceError] = None
        for attempt in range(max_attempts):
            resp = requests.post(f"{self.base_url}/contents/generations/tasks",
                                 json=body, headers=self._headers(),
                                 timeout=self.timeout_sec)
            if resp.status_code < 400:
                data = resp.json()
                payload = data.get("data") if isinstance(data, dict) else data
                task_id = (payload or {}).get("id") or (data or {}).get("id")
                if not task_id:
                    raise SeedanceError(f"Seedance no task id: {str(data)[:600]}")
                return str(task_id)
            err = SeedanceError(
                f"Seedance submit HTTP {resp.status_code}: {resp.text[:800]}"
            )
            if not self._should_retry(resp.status_code) or attempt == max_attempts - 1:
                raise err
            last_err = err
            self._sleep_backoff(attempt)
        raise last_err or SeedanceError("Seedance submit failed unexpectedly")

    # ------------------------------------------------------------------- poll
    def wait(self, task_id: str, timeout_sec: int = 1800,
             poll_interval: float = 8.0) -> Dict:
        """Poll until terminal state; returns {status, url, raw}.

        429/5xx 以指數退避重試（最多 3 次），連續超過即 loud raise，禁止無窮靜默輪詢。
        """
        deadline = time.time() + timeout_sec
        last: Dict = {}
        consecutive_errors = 0
        while time.time() < deadline:
            try:
                r = requests.get(
                    f"{self.base_url}/contents/generations/tasks/{task_id}",
                    headers=self._headers(), timeout=self.timeout_sec,
                )
            except requests.RequestException as exc:  # type: ignore[union-attr]
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    raise SeedanceError(
                        f"Seedance poll 連續失敗 {consecutive_errors} 次 (task {task_id}): {exc}"
                    ) from exc
                self._sleep_backoff(consecutive_errors - 1)
                continue
            if r.status_code >= 400:
                consecutive_errors += 1
                if not self._should_retry(r.status_code) or consecutive_errors >= 3:
                    raise SeedanceError(
                        f"Seedance poll HTTP {r.status_code} (task {task_id}): {r.text[:800]}"
                    )
                self._sleep_backoff(consecutive_errors - 1)
                continue
            consecutive_errors = 0
            data = r.json()
            payload = data.get("data") if isinstance(data, dict) else data
            status = str((payload or {}).get("status") or (data or {}).get("status") or "")
            last = {"status": status, "payload": payload or data, "raw": r.text[:1000]}
            if status in ("successed", "succeeded", "success", "done"):
                url = self._extract_url(payload or data)
                return {"status": "successed", "url": url, **last}
            if status in ("failed", "error", "cancelled", "canceled"):
                raise SeedanceError(
                    f"Seedance task {task_id} status={status}: "
                    f"{r.text[:800]}"
                )
            time.sleep(poll_interval)
        raise SeedanceError(f"Seedance task {task_id} timed out after {timeout_sec}s")

    @staticmethod
    def _extract_url(payload: dict) -> Optional[str]:
        """Pull the produced video/image URL out of a success payload.

        BytePlus succeeded payload shape:
          {"content": {"video_url": "<tos signed url>", "audio_url": ...}, ...}
        (content may also be a list of typed parts in other models).
        """
        content = payload.get("content")
        if isinstance(content, dict):
            for key in ("video_url", "image_url", "audio_url"):
                v = content.get(key)
                if isinstance(v, str) and v:
                    return v
                if isinstance(v, dict) and v.get("url"):
                    return v["url"]
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                for key in ("video_url", "image_url", "audio_url"):
                    v = item.get(key)
                    if isinstance(v, str) and v:
                        return v
                    if isinstance(v, dict) and v.get("url"):
                        return v["url"]
                if item.get("type") == "video_url":
                    u = (item.get("video_url") or {}).get("url")
                    if u:
                        return u
        for key in ("video_url", "image_url"):
            v = payload.get(key)
            if isinstance(v, dict) and v.get("url"):
                return v["url"]
            if isinstance(v, str):
                return v
        return None

    # ---------------------------------------------------------------- download
    def download(self, url: str, out_path: Path) -> Path:
        r = requests.get(url, timeout=300)
        if r.status_code >= 400:
            raise SeedanceError(f"Seedance download HTTP {r.status_code}: {r.text[:300]}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(r.content)
        return out_path
