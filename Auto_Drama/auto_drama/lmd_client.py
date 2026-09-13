# -*- coding: utf-8 -*-
"""
LocalMiniDrama REST client (in-place reference via HTTP, never modifies source).

Verified endpoints (backend-node/src/routes/index.js, root /api/v1):
  GET  /health
  POST /dramas                          create a drama project
  POST /dramas/import-novel             multipart file OR body.text chapter import
  POST /generation/story                body {drama_id,...} -> async task (task_id)
  POST /generation/characters           body {drama_id} -> async task
  POST /episodes/{episode_id}/storyboards   generate storyboards (async)
  GET  /episodes/{episode_id}/storyboards   list generated storyboards
  GET  /tasks/{task_id}                 task status polling
  POST /videos/image/{image_gen_id}     generate video from an image
  POST /videos/episode/{episode_id}/batch   batch video generation
  POST /video-merges                    create a concat merge task
  GET  /video-merges/{merge_id}         merge status/result
  POST /audio/extract                   audio-related extraction

Each method returns parsed JSON; API errors raise LmdApiError.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - live mode requires requests
    requests = None  # type: ignore[assignment]


class LmdApiError(RuntimeError):
    """Raised when LocalMiniDrama backend returns an error."""


class LocalMiniDramaClient:
    """Thin HTTP wrapper over the LocalMiniDrama backend."""

    def __init__(self, base_url: str, api_prefix: str = "/api/v1", timeout_sec: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix
        self.timeout_sec = timeout_sec
        if requests is None:
            raise LmdApiError("requests package is required for live mode")

    # ---------- low-level ----------
    def _url(self, path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}{self.api_prefix}{p}"

    def _request(self, method: str, path: str, json: Optional[dict] = None,
                 files: Optional[dict] = None, data: Optional[dict] = None,
                 timeout_sec: Optional[int] = None) -> Dict[str, Any]:
        """HTTP 呼叫並 unwrap {success, data} envelope；非 2xx / success=false 一律 loud raise."""
        url = self._url(path)
        try:
            resp = requests.request(method, url, json=json, files=files, data=data,
                                    timeout=timeout_sec or self.timeout_sec)
        except Exception as exc:  # network errors must surface loudly
            raise LmdApiError(f"LMD request failed {method} {url}: {exc}") from exc
        try:
            body = resp.json()
        except Exception as exc:
            raise LmdApiError(
                f"LMD non-JSON response from {url} (HTTP {resp.status_code}): {resp.text[:300]}"
            ) from exc
        if resp.status_code >= 400:
            msg = ""
            if isinstance(body, dict):
                err = body.get("error") or {}
                msg = err.get("message") if isinstance(err, dict) else ""
            raise LmdApiError(
                f"LMD HTTP {resp.status_code} on {method} {url}: {msg or resp.text[:500]}"
            )
        if isinstance(body, dict) and "success" in body:
            if not body.get("success"):
                err = body.get("error") or {}
                msg = err.get("message") if isinstance(err, dict) else body
                raise LmdApiError(f"LMD error on {method} {url}: {msg}")
            return body.get("data")
        return body

    # ---------- health ----------
    def health(self) -> Dict[str, Any]:
        try:
            return requests.get(f"{self.base_url}/health", timeout=10).json()
        except Exception as exc:
            raise LmdApiError(f"LMD health check failed: {exc}") from exc

    # ---------- dramas / novel import ----------
    def create_drama(self, title: str, style: str = "", genre: str = "") -> Dict[str, Any]:
        return self._request("POST", "/dramas", json={
            "title": title, "style": style, "genre": genre,
        })
    def get_drama(self, drama_id: int) -> Dict[str, Any]:
        """完整 drama 物件（含 episodes/characters/scenes/props/storyboards）。"""
        return self._request("GET", f"/dramas/{int(drama_id)}")
    def import_novel_text(self, text: str, title: str = "", max_chapters: int = 20,
                          ai_summarize: bool = False) -> Dict[str, Any]:
        """Chapter import straight from text (no file upload)."""
        return self._request("POST", "/dramas/import-novel", data={
            "text": text, "title": title, "max_chapters": str(max_chapters),
            "ai_summarize": "true" if ai_summarize else "false",
        })

    # ---------- generation ----------
    def start_story_generation(self, drama_id: int, premise: str = "",
                               episode_count: int = 1) -> Dict[str, Any]:
        """Async story expansion bound to an existing drama -> {task_id}."""
        return self._request("POST", "/generation/story", json={
            "drama_id": drama_id, "premise": premise, "episode_count": episode_count,
        })

    def start_character_generation(self, drama_id: int) -> Dict[str, Any]:
        return self._request("POST", "/generation/characters", json={"drama_id": drama_id})

    def generate_storyboards(self, episode_id: int, **params) -> Dict[str, Any]:
        return self._request("POST", f"/episodes/{episode_id}/storyboards", json=params)

    # ---------- manual authoring (music-drama / MV pipeline) ----------
    def save_characters(self, drama_id: int, characters: List[dict]) -> Dict[str, Any]:
        """PUT /dramas/:id/characters — upsert cast (matched by id or name)."""
        return self._request("PUT", f"/dramas/{int(drama_id)}/characters",
                             json={"characters": characters})

    def save_episodes(self, drama_id: int, episodes: List[dict]) -> Dict[str, Any]:
        """PUT /dramas/:id/episodes — upsert episodes by episode_number."""
        return self._request("PUT", f"/dramas/{int(drama_id)}/episodes",
                             json={"episodes": episodes})

    def create_storyboard(self, fields: dict) -> Dict[str, Any]:
        """POST /storyboards — create one storyboard row; returns the full row."""
        return self._request("POST", "/storyboards", json=fields)

    def upload_character_image(self, character_id: int, image_path) -> Dict[str, Any]:
        """POST /characters/:id/upload-image — multipart portrait upload (sets image refs)."""
        p = Path(image_path)
        with open(p, "rb") as fh:
            files = {"file": (p.name, fh, "image/png")}
            return self._request("POST", f"/characters/{int(character_id)}/upload-image",
                                 files=files, timeout_sec=300)

    def list_storyboards(self, episode_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/episodes/{episode_id}/storyboards")

    # ---------- tasks ----------
    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/tasks/{task_id}")

    def wait_task(self, task_id: str, timeout_sec: int = 1800, poll_sec: int = 10) -> Dict[str, Any]:
        """Poll a task to terminal state; returns final task payload."""
        deadline = time.time() + timeout_sec
        last: Dict[str, Any] = {}
        while time.time() < deadline:
            last = self.get_task(task_id)
            status = str(last.get("status", "")).lower()
            if status in ("completed", "success", "failed", "error"):
                if status in ("failed", "error"):
                    raise LmdApiError(f"LMD task {task_id} failed: {last}")
                return last
            time.sleep(poll_sec)
        raise LmdApiError(f"LMD task {task_id} timed out after {timeout_sec}s")

    # ---------- storyboards (per-shot video chain) ----------
    def get_storyboard(self, storyboard_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/storyboards/{int(storyboard_id)}")

    def update_storyboard(self, storyboard_id: int, fields: dict) -> Dict[str, Any]:
        """更新分鏡（支援 character_ids 陣列、universal_segment_text 等欄位）。"""
        return self._request("PUT", f"/storyboards/{int(storyboard_id)}", json=fields)

    def get_omni_reference_plan(self, storyboard_id: int) -> Dict[str, Any]:
        """權威 @圖片N 槽位 + 參考圖 URL 計畫（CEO 視覺一致性契約）。"""
        return self._request("GET", f"/storyboards/{int(storyboard_id)}/omni-reference-plan")

    def generate_universal_segment(self, storyboard_id: int,
                                   body: Optional[dict] = None) -> str:
        """同步產生含 @圖片N 的全能片段提示詞並寫回分鏡；回傳文本。"""
        data = self._request(
            "POST", f"/storyboards/{int(storyboard_id)}/universal-segment-prompt",
            json=body or {}, timeout_sec=300,
        )
        return str((data or {}).get("universal_segment_text") or "").strip()

    def preflight_reference_assets(self, episode_id: int) -> Dict[str, Any]:
        """整集角色參考資產 preflight；data.can_proceed 決定是否放行。"""
        return self._request("GET", f"/videos/episode/{int(episode_id)}/preflight-reference-assets")

    # ---------- video / merge ----------
    def generate_video_from_image(self, image_gen_id: int, **params) -> Dict[str, Any]:
        return self._request("POST", f"/videos/image/{image_gen_id}", json=params)

    def generate_video(self, payload: dict) -> Dict[str, Any]:
        """逐鏡 POST /videos（storyboard_id + reference_image_urls + @圖片N prompt）。"""
        return self._request("POST", "/videos", json=payload, timeout_sec=300)

    def get_video(self, video_gen_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/videos/{int(video_gen_id)}")

    def wait_video_gen(self, video_gen_id: int, timeout_sec: int = 2400,
                       poll_sec: float = 10.0) -> Dict[str, Any]:
        """輪詢單筆 video_generation 至 completed；failed/timeout 一律 loud raise。"""
        deadline = time.time() + timeout_sec
        last: Dict[str, Any] = {}
        while time.time() < deadline:
            last = self.get_video(video_gen_id)
            status = str(last.get("status") or "").lower()
            if status == "completed":
                return last
            if status in ("failed", "error"):
                raise LmdApiError(
                    f"LMD video_generation {video_gen_id} failed: "
                    f"{last.get('error_msg') or last}"
                )
            time.sleep(poll_sec)
        raise LmdApiError(f"LMD video_generation {video_gen_id} timed out after {timeout_sec}s")

    def batch_generate_episode_videos(self, episode_id: int, **params) -> Dict[str, Any]:
        return self._request("POST", f"/videos/episode/{episode_id}/batch", json=params)

    def create_video_merge(self, episode_id: int, title: str = "", scenes=None) -> Dict[str, Any]:
        return self._request("POST", "/video-merges", json={
            "episode_id": episode_id, "title": title, "scenes": scenes or [],
        })

    def get_video_merge(self, merge_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/video-merges/{merge_id}")

    # ---------- prompt overrides (custom classical-Chinese expansion prompt) ----------
    def put_prompt_override(self, key: str, content: str) -> Dict[str, Any]:
        """Install a custom system/user prompt override (key like story_generation)."""
        return self._request("PUT", f"/settings/prompts/{key}", json={"content": content})
