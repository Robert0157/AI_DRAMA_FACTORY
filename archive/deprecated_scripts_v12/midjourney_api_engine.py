#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTAPI (Midjourney) 正式引擎
Phase 2: imagine -> poll -> U1 upscale -> poll -> download
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

MAX_RETRIES = 5
BACKOFF_BASE = 2.0
BACKOFF_CAP = 30.0
POLL_INTERVAL_SEC = 5
POLL_TIMEOUT_SEC = 900


def fatal_log(exc: Exception | str, *, label: str = "midjourney_api_engine") -> None:
    """Fatal log 瘦身：僅保留例外名稱與最後一行訊息。"""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    exc_name = type(exc).__name__ if isinstance(exc, Exception) else "FatalError"
    last_line = str(exc).strip().splitlines()[-1] if str(exc).strip() else str(exc)
    entry = (
        f"\n---\n"
        f"### ❌ [{ts}] {label}\n"
        f"- **ExceptionType** : `{exc_name}`\n"
        f"- **KeyError**      : {last_line}\n"
    )
    with open(Path(config.workspace_root) / "project_learning.md", "a", encoding="utf-8") as fh:
        fh.write(entry)


def _sleep_backoff(attempt: int) -> None:
    wait = min(BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1), BACKOFF_CAP)
    time.sleep(wait)


def _request_with_backoff(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
            if not resp.text.strip():
                return {}
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < MAX_RETRIES:
                _sleep_backoff(attempt)
                continue
            raise RuntimeError(f"request failed: {method} {url} | {exc}") from exc
    raise RuntimeError(f"request failed with unknown error: {last_exc}")


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _extract_task_id(payload: dict[str, Any]) -> str:
    for key in ("result", "id", "taskId", "task_id", "jobId", "job_id"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("id", "taskId", "task_id", "jobId", "job_id"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _extract_status(payload: dict[str, Any]) -> str:
    for key in ("status", "state"):
        val = payload.get(key)
        if isinstance(val, str):
            return val.upper()
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("status", "state"):
            val = data.get(key)
            if isinstance(val, str):
                return val.upper()
    return "UNKNOWN"


def _extract_image_url(payload: dict[str, Any]) -> str:
    keys = ("imageUrl", "image_url", "result", "url", "cdnImage", "discordImage")
    for key in keys:
        val = payload.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    data = payload.get("data")
    if isinstance(data, dict):
        for key in keys:
            val = data.get(key)
            if isinstance(val, str) and val.startswith("http"):
                return val
        images = data.get("images")
        if isinstance(images, list):
            for item in images:
                if isinstance(item, str) and item.startswith("http"):
                    return item
    return ""


def submit_imagine(prompt: str) -> str:
    base = _normalize_base_url(config.mj_base_url)
    urls = [
        f"{base}/midjourney/v1/imagine",
        f"{base}/mj/submit/imagine",
    ]
    headers = {
        "tt-api-key": config.mj_api_key,
        "TT-API-KEY": config.mj_api_key,
        "Content-Type": "application/json",
    }
    payload = {"prompt": prompt, "mode": "fast"}

    last_err: Exception | None = None
    for url in urls:
        try:
            resp = _request_with_backoff("POST", url, headers=headers, json_body=payload)
            task_id = _extract_task_id(resp)
            if not task_id:
                raise RuntimeError(f"imagine response missing task id: {resp}")
            print(f"[MJ] imagine submitted: task_id={task_id}")
            return task_id
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue

    raise RuntimeError(f"imagine submit failed on all endpoints: {last_err}")


def poll_task(task_id: str, *, timeout_sec: int = POLL_TIMEOUT_SEC) -> dict[str, Any]:
    base = _normalize_base_url(config.mj_base_url)
    headers = {"tt-api-key": config.mj_api_key, "TT-API-KEY": config.mj_api_key}
    candidates = [
        f"{base}/midjourney/v1/fetch?jobId={task_id}",
        f"{base}/mj/task/{task_id}/fetch",
        f"{base}/mj/task/{task_id}",
    ]
    started = time.time()
    last_payload: dict[str, Any] = {}
    attempt = 0

    while time.time() - started < timeout_sec:
        attempt += 1
        for url in candidates:
            try:
                payload = _request_with_backoff("GET", url, headers=headers, timeout=60)
            except Exception:
                continue
            last_payload = payload
            status = _extract_status(payload)
            print(f"[MJ] poll task={task_id} attempt={attempt} status={status}")
            if status in {"SUCCESS", "DONE", "COMPLETED"}:
                return payload
            if status in {"FAILURE", "FAILED", "ERROR"}:
                raise RuntimeError(f"task failed: {payload}")
        time.sleep(POLL_INTERVAL_SEC)

    raise TimeoutError(f"task polling timeout: task_id={task_id}, last={last_payload}")


def submit_upscale_u1(task_id: str) -> str:
    base = _normalize_base_url(config.mj_base_url)
    urls = [
        f"{base}/midjourney/v1/action",
        f"{base}/mj/submit/action",
    ]
    headers = {
        "tt-api-key": config.mj_api_key,
        "TT-API-KEY": config.mj_api_key,
        "Content-Type": "application/json",
    }

    # 不同 TTAPI 兼容 payload 逐一嘗試
    candidates = [
        {"jobId": task_id, "action": "upsample1"},
        {"jobId": task_id, "action": "U1"},
        {"taskId": task_id, "action": "UPSCALE_1"},
        {"taskId": task_id, "action": "U1"},
        {"taskId": task_id, "customId": f"MJ::JOB::upsample::1::{task_id}"},
    ]

    last_resp: dict[str, Any] = {}
    for url in urls:
        for body in candidates:
            try:
                resp = _request_with_backoff("POST", url, headers=headers, json_body=body)
                last_resp = resp
                new_task_id = _extract_task_id(resp)
                if new_task_id:
                    print(f"[MJ] upscale U1 submitted: parent={task_id} task_id={new_task_id}")
                    return new_task_id
            except Exception:
                continue

    raise RuntimeError(f"upscale action failed for task={task_id}, last_resp={last_resp}")


def download_image(image_url: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[MJ] downloading anchor image -> {output_path}")
    with requests.get(image_url, timeout=120, stream=True) as resp:
        resp.raise_for_status()
        with open(output_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"download failed: {output_path}")
    return output_path


def generate_anchor(job_id: str, prompt: str) -> Path:
    if not config.mj_api_key or not config.mj_base_url:
        raise RuntimeError("MJ_API_KEY / MJ_BASE_URL is required in .env")

    task_id = submit_imagine(prompt)
    _ = poll_task(task_id)
    u1_task_id = submit_upscale_u1(task_id)
    u1_payload = poll_task(u1_task_id)
    image_url = _extract_image_url(u1_payload)
    if not image_url:
        raise RuntimeError(f"upscale success but image url missing: {u1_payload}")

    out = Path(config.workspace_root) / "assets" / "image_anchors" / job_id / "anchor_01.jpg"
    return download_image(image_url, out)


def main() -> None:
    parser = argparse.ArgumentParser(description="TTAPI Midjourney 正式引擎")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args()

    try:
        out = generate_anchor(job_id=args.job_id, prompt=args.prompt)
        print(json.dumps({"status": "success", "anchor_path": str(out)}, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001
        fatal_log(exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
