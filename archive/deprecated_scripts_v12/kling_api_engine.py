#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kling 正式引擎
Phase 3: JWT 動態簽章 + 首幀繼承 + 影片下載
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config

MAX_RETRIES = 5
BACKOFF_BASE = 2.0
BACKOFF_CAP = 30.0
POLL_INTERVAL_SEC = 5
POLL_TIMEOUT_SEC = 7200  # 120 分鐘（增加至 2 小時以容納多軌渲染）
CATBOX_UPLOAD_URL = "https://catbox.moe/user/api.php"
CATBOX_TIMEOUT_CONNECT_SEC = 30
CATBOX_TIMEOUT_READ_SEC = 300


def fatal_log(exc: Exception | str, *, label: str = "kling_api_engine") -> None:
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


def build_bearer_token() -> str:
    """
    依 Kling 常見 AK/SK JWT 規範建立短效 token：
    - iss: Access Key
    - exp: 過期時間
    - nbf: 生效時間（略早於現在，避免時鐘漂移）
    """
    now = datetime.now(timezone.utc)
    payload = {
        "iss": config.kling_ak,
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "nbf": int((now - timedelta(seconds=5)).timestamp()),
    }
    token = jwt.encode(payload, config.kling_sk, algorithm="HS256")
    return f"Bearer {token}"


def _request_with_backoff(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        headers = {"Authorization": build_bearer_token(), "Content-Type": "application/json"}
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=timeout,
            )
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


def _extract_task_id(payload: dict[str, Any]) -> str:
    for key in ("id", "taskId", "task_id", "result"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("id", "taskId", "task_id"):
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
        # Kling 實際回應格式：data.task_status
        for key in ("task_status", "status", "state"):
            val = data.get(key)
            if isinstance(val, str):
                return val.upper()
    return "UNKNOWN"


def _extract_video_url(payload: dict[str, Any]) -> str:
    keys = ("videoUrl", "video_url", "url", "result")
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
        # Kling 實際回應格式：data.task_result.videos[0].url
        task_result = data.get("task_result")
        if isinstance(task_result, dict):
            videos = task_result.get("videos")
            if isinstance(videos, list) and videos:
                url = videos[0].get("url", "")
                if isinstance(url, str) and url.startswith("http"):
                    return url
    return ""


def _kling_base_url() -> str:
    return os.getenv("KLING_BASE_URL", "https://api.klingai.com").rstrip("/")


def _upload_file_to_catbox(file_path: Path, *, label: str) -> str:
    """將本地媒體上傳至 Catbox，回傳可公開存取的直連 URL。"""
    if not file_path.exists():
        raise RuntimeError(f"{label} file not found: {file_path}")

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(file_path, "rb") as fh:
                resp = requests.post(
                    CATBOX_UPLOAD_URL,
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": fh},
                    timeout=(CATBOX_TIMEOUT_CONNECT_SEC, CATBOX_TIMEOUT_READ_SEC),
                )
            resp.raise_for_status()
            upload_url = resp.text.strip()
            if not upload_url.startswith("http"):
                raise RuntimeError(f"catbox invalid response: {upload_url[:200]}")
            return upload_url
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < MAX_RETRIES:
                _sleep_backoff(attempt)
                continue
            raise RuntimeError(f"catbox upload failed: {label} {file_path} | {exc}") from exc
    raise RuntimeError(f"catbox upload failed with unknown error: {last_exc}")


def _assert_single_subject_reference(reference_video_path: Path, reference_subject_hint: str | None) -> None:
    """以最低成本做動作參考檢核：只接受明確宣告或檔名可辨識的單人素材。"""
    hint = (reference_subject_hint or "").strip().lower()
    if hint in {"single", "single_subject", "solo", "one_person"}:
        return

    name = reference_video_path.name.lower()
    allow_tokens = ("single", "solo", "skeleton_constrained", "shot_")
    if any(token in name for token in allow_tokens) and "reference_dance" not in name:
        return

    raise RuntimeError(
        "motion reference must be single-subject; "
        f"got={reference_video_path.name}. "
        "Please use a solo clip or set shot.reference_subject='single'."
    )


def submit_video_to_video(
    reference_video_path: Path,
    anchor_image_path: Path,
    prompt: str,
    duration_sec: int,
    *,
    reference_subject_hint: str | None = None,
) -> str:
    """
    v8.5 Motion Control (動作控制) 升級：Kling v3 原生支援多模態參考
    - reference_video_path: 真人動作影片作為骨架/動作控制
    - anchor_image_path: 目標角色圖片作為外觀參考
    - 端點：POST https://api-singapore.klingai.com/v1/videos/motion-control
    - 絕對不降級至 I2V（CEO 鐵律）
    """
    if not reference_video_path.exists():
        raise RuntimeError(f"reference video not found: {reference_video_path}")
    if not anchor_image_path.exists():
        raise RuntimeError(f"anchor image not found: {anchor_image_path}")

    _assert_single_subject_reference(reference_video_path, reference_subject_hint)

    # Motion Control 最穩定策略：先上傳公網 URL，再走 snake_case payload
    image_url = _upload_file_to_catbox(anchor_image_path, label="anchor image")
    video_url = _upload_file_to_catbox(reference_video_path, label="reference video")

    # 🚀 Motion Control 端點（Kling v3 官方正式端點）
    url = os.getenv("KLING_MOTION_CONTROL_URL", "https://api-singapore.klingai.com/v1/videos/motion-control")
    
    # Motion Control Payload 規格：支援多模態參考（video + image）
    payload = {
        "model_name": "kling-v3",  # 👉 Kling v3 模型
        "image_url": image_url,
        "video_url": video_url,
        "prompt": prompt,
        "duration": duration_sec,
        "mode": "pro",  # 專業模式
        "character_orientation": "image",  # 角色朝向以圖片為准
    }
    
    print(
        f"[KLING-MC] 🚀 Motion Control（動作控制）強制執行："
    )
    print(
        f"  • Model: kling-v3 | Mode: pro | Orientation: image"
    )
    print(
        f"  • Ref Video: {reference_video_path.name} | Anchor Image: {anchor_image_path.name}"
    )
    print(f"  • Ref URL: {video_url[:72]}...")
    
    resp = _request_with_backoff("POST", url, json_body=payload, timeout=180)
    if int(resp.get("code", 0)) != 0:
        raise RuntimeError(f"Kling Motion Control API error: {resp}")
    task_id = _extract_task_id(resp)
    if not task_id:
        raise RuntimeError(f"Kling Motion Control response missing task id: {resp}")
    print(f"[KLING-MC] ✅ Motion Control 提交成功！Task ID: {task_id}")
    return task_id


def submit_image_to_video(image_path: Path, prompt: str, duration_sec: int) -> str:
    if not image_path.exists():
        raise RuntimeError(f"image prompt not found: {image_path}")

    # CTO 鐵律：放棄 multipart，改用 Base64 純 JSON 送出，避免 code=1200 不穩定
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")

    url = f"{_kling_base_url()}/v1/videos/image2video"
    
    # 🛡️ v9.5 靜止相機鎖定鐵律：強制禁止運鏡
    payload = {
        "model": "kling-v1",
        "image": image_b64,
        "prompt": prompt,
        "duration": str(duration_sec),
        # 【關鍵】靜止相機硬編碼 - 絕對禁止任何 Pan/Zoom/Tilt
        "camera_control": {
            "type": "static",
            "motion_intensity": 0,
        }
    }
    print(f"[KLING] submit image2video (JSON/base64, STATIC CAMERA): image={image_path} duration={duration_sec}s")
    resp = _request_with_backoff("POST", url, json_body=payload, timeout=180)

    task_id = _extract_task_id(resp)
    if not task_id:
        raise RuntimeError(f"kling submit response missing task id: {resp}")
    print(f"[KLING] submitted task_id={task_id} [STATIC CAMERA ENFORCED]")
    return task_id


def poll_task(task_id: str, *, timeout_sec: int = POLL_TIMEOUT_SEC) -> dict[str, Any]:
    base = _kling_base_url()
    # 候選路徑：找到有效回應後即記錄，後續只用該 URL，避免反覆重試 404 路徑浪費時間
    candidates = [
        f"{base}/v1/videos/image2video/{task_id}",
        f"{base}/v1/videos/{task_id}",
        f"{base}/v1/videos/tasks/{task_id}",
    ]
    confirmed_url: str | None = None
    started = time.time()
    last_payload: dict[str, Any] = {}
    attempt = 0
    last_status = None

    while time.time() - started < timeout_sec:
        attempt += 1
        # 一旦確認有效 URL，只掃該路徑，跳過已知 404 candidates
        poll_urls = [confirmed_url] if confirmed_url else candidates
        for url in poll_urls:
            try:
                payload = _request_with_backoff("GET", url, timeout=30)
            except Exception as e:
                # 連接失敗時打印更多診斷訊息
                elapsed = int(time.time() - started)
                print(f"[KLING] poll attempt={attempt} elapsed={elapsed}s error={type(e).__name__}")
                continue
            # 首次成功後記錄有效路徑
            if confirmed_url is None:
                confirmed_url = url
                print(f"[KLING] confirmed poll url: {url}")
            last_payload = payload
            status = _extract_status(payload)
            
            # 只在狀態變化時打印（避免日誌洪流）
            if status != last_status:
                elapsed = int(time.time() - started)
                print(f"[KLING] poll task={task_id} attempt={attempt} elapsed={elapsed}s status={status}")
                last_status = status
            
            if status in {"SUCCESS", "DONE", "COMPLETED", "SUCCEED"}:
                print(f"[KLING] ✅ COMPLETED! task_id={task_id}")
                return payload
            if status in {"FAILURE", "FAILED", "ERROR"}:
                raise RuntimeError(f"kling task failed: {payload}")
            break  # 已取得有效回應，不繼續試其他 candidates
        time.sleep(POLL_INTERVAL_SEC)

    # 超時時更詳細的診斷
    remaining_time = int(timeout_sec - (time.time() - started))
    error_msg = f"kling polling timeout: task_id={task_id}, last_status={last_status}, timeout_sec={timeout_sec}"
    print(f"[KLING] ⚠️  {error_msg}")
    raise TimeoutError(error_msg)


def extract_last_frame(video_path: Path, output_frame: Path) -> Path:
    """複雜流程前置註解：先用 ffprobe 取時長，再抽最後 0.1 秒，避免 EOF 空幀。"""
    if not video_path.exists():
        raise RuntimeError(f"previous shot video missing: {video_path}")

    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    duration_raw = subprocess.check_output(probe_cmd, text=True, timeout=30).strip()
    duration = float(duration_raw)
    seek_time = max(0.0, duration - 0.1)

    output_frame.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_cmd = [
        "ffmpeg",
        "-loglevel", "error",  # 抑制診斷資訊，僅顯示實際錯誤
        "-y",
        "-ss",
        f"{seek_time:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-update",
        "1",
        "-q:v",
        "2",
        str(output_frame),
    ]
    print(f"[KLING] extracting last frame: src={video_path} dst={output_frame}")
    subprocess.run(ffmpeg_cmd, check=True, timeout=60, capture_output=True)
    if not output_frame.exists() or output_frame.stat().st_size == 0:
        raise RuntimeError(f"extract last frame failed: {output_frame}")
    return output_frame


def download_video(video_url: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[KLING] downloading shot video -> {output_path}")
    with requests.get(video_url, timeout=240, stream=True) as resp:
        resp.raise_for_status()
        with open(output_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"video download failed: {output_path}")
    return output_path


def run_job(
    job_id: str,
    shots_file: Path,
    *,
    start_shot: int = 1,
    seed_prev_video: Path | None = None,
) -> list[Path]:
    if not config.kling_ak or not config.kling_sk:
        raise RuntimeError("KLING_AK / KLING_SK is required in .env")

    with open(shots_file, "r", encoding="utf-8") as fh:
        shots = json.load(fh)
    if not isinstance(shots, list) or not shots:
        raise RuntimeError(f"shots file invalid: {shots_file}")

    workspace = Path(config.workspace_root)
    anchor_path = workspace / "assets" / "image_anchors" / job_id / "anchor_01.jpg"
    shots_dir = workspace / "assets" / "video_clips" / job_id / "shots"
    frames_dir = workspace / "assets" / "video_clips" / job_id / "frames"

    if start_shot < 1:
        raise RuntimeError(f"start_shot must be >= 1, got {start_shot}")

    generated: list[Path] = []
    prev_video: Path | None = None
    if start_shot > 1:
        if seed_prev_video is None:
            raise RuntimeError("seed_prev_video is required when start_shot > 1")
        if not seed_prev_video.exists():
            raise RuntimeError(f"seed_prev_video missing: {seed_prev_video}")
        prev_video = seed_prev_video

    for idx, shot in enumerate(shots, start=1):
        if idx < start_shot:
            continue

        shot_name = f"shot_{idx:02d}"
        prompt = str(shot.get("prompt", ""))
        duration = int(shot.get("duration", 5))

        # 首鏡必吃 anchor_01；後續鏡頭必吃上一鏡 last frame
        if idx == 1 and prev_video is None:
            image_prompt = anchor_path
            if not image_prompt.exists():
                raise RuntimeError(f"anchor image missing: {anchor_path}")
            print(f"[KLING] {shot_name} uses anchor frame: {image_prompt}")
        else:
            assert prev_video is not None
            image_prompt = extract_last_frame(
                prev_video,
                frames_dir / f"{shot_name}_from_prev_last_frame.jpg",
            )
            print(f"[KLING] {shot_name} uses previous last frame: {image_prompt}")

        # v8.5 Motion Control 邏輯：若 shot 包含 reference_video_path，走動作控制正式流程
        reference_video = shot.get("reference_video_path")
        try:
            if reference_video:
                ref_video_path = Path(reference_video)
                if not ref_video_path.is_absolute():
                    ref_video_path = workspace / reference_video
                if ref_video_path.exists():
                    subject_hint = str(shot.get("reference_subject", ""))
                    task_id = submit_video_to_video(
                        ref_video_path,
                        image_prompt,
                        prompt,
                        duration,
                        reference_subject_hint=subject_hint,
                    )
                    print(f"[KLING] {shot_name} using Motion Control (image anchor + ref video)")
                else:
                    task_id = submit_image_to_video(image_prompt, prompt, duration)
            else:
                task_id = submit_image_to_video(image_prompt, prompt, duration)
            final_payload = poll_task(task_id)
            video_url = _extract_video_url(final_payload)
            if not video_url:
                raise RuntimeError(f"kling success but missing video url: {final_payload}")

            shot_path = download_video(video_url, shots_dir / f"{shot_name}.mp4")
            generated.append(shot_path)
            prev_video = shot_path
        except KeyboardInterrupt:
            print(f"[KLING] ⚠️  使用者在 {shot_name} 處中斷。已生成 {len(generated)} 個分鏡。")
            raise

    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="Kling JWT 正式引擎")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--shots-file", required=True, help="JSON list: [{prompt,duration}, ...]")
    parser.add_argument("--start-shot", type=int, default=1, help="start from this shot index (1-based)")
    parser.add_argument("--seed-prev-video", default="", help="required when --start-shot > 1")
    args = parser.parse_args()

    try:
        seed_prev_video = Path(args.seed_prev_video) if args.seed_prev_video else None
        outputs = run_job(
            args.job_id,
            Path(args.shots_file),
            start_shot=args.start_shot,
            seed_prev_video=seed_prev_video,
        )
        print(json.dumps({"status": "success", "shots": [str(p) for p in outputs]}, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        # 使用者中斷 - 記錄但不視為致命錯誤
        print("[KLING] ⚠️  使用者中斷（Ctrl+C）。進程可在背景繼續。")
        raise SystemExit(0)  # 正常結束，讓進程可在背景繼續
    except Exception as exc:  # noqa: BLE001
        fatal_log(exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
