from __future__ import annotations

import base64
import json
import mimetypes
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from PIL import Image
from zhipuai import ZhipuAI

# 讓腳本可直接以檔案路徑執行（python scripts/gear1_prod/xxx.py）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


API_BASE = "https://open.bigmodel.cn/api/paas/v4"
GENERATION_URL = f"{API_BASE}/videos/generations"
POLL_INTERVAL_SEC = 10
POLL_TIMEOUT_SEC = 1800
REQUEST_TIMEOUT_SEC = 180
MAX_RETRIES = 3
CATBOX_UPLOAD_URL = "https://catbox.moe/user/api.php"
CATBOX_TIMEOUT_CONNECT_SEC = 20
CATBOX_TIMEOUT_READ_SEC = 120
MAX_INPUT_IMAGE_SIDE = 1280
MAX_INPUT_IMAGE_BYTES = 4 * 1024 * 1024

PROMPT = (
    "畫面保持極度靜謐的 Lo-Fi 氛圍。"
    "女孩保持發呆的姿勢不變，胸口有著極其輕微、平緩的呼吸起伏。"
    "窗外左側的紅楓葉被微風輕輕吹拂，微微搖曳。"
    "窗外遠處的雲層有極其緩慢的流動。"
    "不要有任何大動作，不要改變人物長相，保持唯美、寧靜、治癒的微動態感，電影級光影。"
    # 🛡️ v9.5 靜止相機鐵律 - 強制注入於 Prompt 末端
    ", static camera, absolute still frame, NO camera movement whatsoever, "
    "fixed angle, no pan, no zoom, no tilt, no dolly shot, frozen perspective, "
    "absolute motionless viewpoint."
)


def _append_fatal_learning(context: str, exc: Exception) -> None:
    project_learning = Path(config.workspace_root) / "project_learning.md"
    project_learning.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detail = str(exc).strip()
    entry = (
        "\n\n"
        f"## [{stamp}] Fatal: {context}\n"
        f"- 錯誤類型: {type(exc).__name__}\n"
        f"- 錯誤訊息: {detail}\n"
        "- 處置: 已中斷執行，需人工檢查後重啟。\n"
    )
    with project_learning.open("a", encoding="utf-8") as fh:
        fh.write(entry)


def _request_with_backoff(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    timeout: int = REQUEST_TIMEOUT_SEC,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=json_body,
                timeout=timeout,
            )
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}: {resp.text[:600]}")
            resp.raise_for_status()
            if not resp.text.strip():
                return {}
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"request failed: {method} {url} | {exc}") from exc
    raise RuntimeError(f"request failed with unknown error: {last_exc}")


def _upload_file_to_catbox(file_path: Path, label: str) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"catbox upload source not found: {file_path}")

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with file_path.open("rb") as fh:
                resp = requests.post(
                    CATBOX_UPLOAD_URL,
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": (file_path.name, fh)},
                    timeout=(CATBOX_TIMEOUT_CONNECT_SEC, CATBOX_TIMEOUT_READ_SEC),
                )
            resp.raise_for_status()
            upload_url = resp.text.strip()
            if not upload_url.startswith("http"):
                raise RuntimeError(f"catbox invalid response: {upload_url[:200]}")
            print(f"[ZHIPU] catbox uploaded {label}: {upload_url}", flush=True)
            return upload_url
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"catbox upload failed: {label} {file_path} | {exc}") from exc
    raise RuntimeError(f"catbox upload failed with unknown error: {last_exc}")


def _iter_values(node: Any):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from _iter_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_values(item)


def _extract_task_id(payload: dict[str, Any]) -> str | None:
    direct_candidates = [
        payload.get("id"),
        payload.get("task_id"),
        payload.get("request_id"),
    ]
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    direct_candidates.extend([data.get("id"), data.get("task_id"), data.get("request_id")])
    for candidate in direct_candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    for key, value in _iter_values(payload):
        if key in {"id", "task_id", "request_id"} and isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_status(payload: dict[str, Any]) -> str:
    status_keys = ("task_status", "status", "state", "job_status")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    for key in status_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    for key in status_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()

    code = payload.get("code")
    message = payload.get("message")
    if isinstance(code, int) and code != 0:
        return "FAILED"
    if isinstance(message, str) and message.strip().upper() in {"SUCCESS", "SUCCEED"}:
        return "SUCCEED"
    return "UNKNOWN"


def _extract_video_url(payload: dict[str, Any]) -> str | None:
    candidate_keys = {
        "url",
        "video_url",
        "videoUrl",
        "result_url",
        "output_url",
        "download_url",
    }

    for key, value in _iter_values(payload):
        if key in candidate_keys and isinstance(value, str) and value.startswith("http"):
            if ".mp4" in value or "video" in key.lower():
                return value

    for _, value in _iter_values(payload):
        if isinstance(value, str) and value.startswith("http") and ".mp4" in value:
            return value
    return None


def _build_data_uri(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(image_path.name)
    if not mime_type:
        mime_type = "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _prepare_input_image(image_path: Path) -> Path:
    size_bytes = image_path.stat().st_size
    if size_bytes <= MAX_INPUT_IMAGE_BYTES:
        print(f"[ZHIPU] input image size ok: {size_bytes} bytes", flush=True)
        return image_path

    optimized_path = image_path.with_name("RS_lofi_gril_i2v_input.jpg")
    print(
        f"[ZHIPU] optimizing image: {image_path.name} ({size_bytes} bytes) -> {optimized_path.name}",
        flush=True,
    )

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        width, height = img.size
        longest = max(width, height)
        if longest > MAX_INPUT_IMAGE_SIDE:
            scale = MAX_INPUT_IMAGE_SIDE / float(longest)
            img = img.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
        img.save(optimized_path, format="JPEG", quality=88, optimize=True)

    print(f"[ZHIPU] optimized size: {optimized_path.stat().st_size} bytes", flush=True)
    return optimized_path


def _normalize_sdk_payload(resp: Any) -> dict[str, Any]:
    if isinstance(resp, dict):
        return resp
    if hasattr(resp, "model_dump"):
        return resp.model_dump()
    if hasattr(resp, "dict"):
        return resp.dict()
    return json.loads(str(resp))


def _submit_i2v_job(
    client: ZhipuAI,
    image_url: str,
    image_data_uri: str,
) -> tuple[str | None, str | None, dict[str, Any]]:
    model_candidates = ["cogvideox", "cogvideox", "cogvideox-2"]
    payload_variants = [
        {"prompt": PROMPT, "image_url": image_url, "duration": 5},
        {"prompt": PROMPT, "image_url": image_data_uri, "duration": 5},
        {"prompt": PROMPT, "image_url": image_data_uri},
        {"prompt": PROMPT, "image": image_data_uri, "duration": 5},
    ]

    last_error: Exception | None = None
    for model in model_candidates:
        for variant in payload_variants:
            payload = {"model": model, **variant}
            try:
                print(f"[ZHIPU] submit I2V: model={model} keys={sorted(payload.keys())}", flush=True)
                response_raw = client.videos.generations(
                    model=model,
                    prompt=payload.get("prompt"),
                    image_url=payload.get("image_url") or payload.get("image"),
                    duration=payload.get("duration"),
                    timeout=120,
                )
                response = _normalize_sdk_payload(response_raw)
                if int(response.get("code", 0)) != 0:
                    raise RuntimeError(f"zhipu api error: {json.dumps(response, ensure_ascii=False)[:1200]}")
                task_id = _extract_task_id(response)
                video_url = _extract_video_url(response)
                return task_id, video_url, response
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(f"[ZHIPU] submit variant failed: {exc}", flush=True)
                continue

    raise RuntimeError(f"all submit variants failed: {last_error}")


def _poll_until_done(client: ZhipuAI, task_id: str) -> tuple[str, dict[str, Any]]:
    success_status = {"SUCCESS", "SUCCEED", "SUCCEEDED", "DONE", "COMPLETED", "FINISHED"}
    failed_status = {"FAIL", "FAILED", "ERROR", "CANCELED", "CANCELLED", "REJECTED"}

    started = time.time()
    last_status = "UNKNOWN"
    last_payload: dict[str, Any] = {}

    while time.time() - started < POLL_TIMEOUT_SEC:
        response_raw = client.videos.retrieve_videos_result(id=task_id, timeout=40)
        payload = _normalize_sdk_payload(response_raw)

        last_payload = payload
        status = _extract_status(payload)
        if status != last_status:
            elapsed = int(time.time() - started)
            print(f"[ZHIPU] poll task={task_id} elapsed={elapsed}s status={status}", flush=True)
            last_status = status

        if status in success_status:
            video_url = _extract_video_url(payload)
            if video_url:
                return video_url, payload
        if status in failed_status:
            raise RuntimeError(f"zhipu task failed: {json.dumps(payload, ensure_ascii=False)}")

        time.sleep(POLL_INTERVAL_SEC)

    raise TimeoutError(
        f"zhipu polling timeout: task_id={task_id}, last_status={last_status}, last_payload={json.dumps(last_payload, ensure_ascii=False)[:800]}"
    )


def _download_video(video_url: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[ZHIPU] downloading video -> {output_path}")
    with requests.get(video_url, stream=True, timeout=240) as resp:
        resp.raise_for_status()
        with output_path.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"downloaded file is empty: {output_path}")
    return output_path


def main() -> int:
    api_key = config.ZHIPUAI_API_KEY
    if not api_key:
        raise EnvironmentError("Missing ZHIPUAI_API_KEY in config")

    workspace_root = Path(config.workspace_root)
    image_path = workspace_root / "assets" / "video_clips" / "RS_lofi_gril.png"
    output_path = workspace_root / "assets" / "video_clips" / "lofi_girl_5s_base.mp4"

    if not image_path.exists():
        raise FileNotFoundError(f"image not found: {image_path}")

    prepared_image_path = _prepare_input_image(image_path)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    client = ZhipuAI(api_key=api_key)

    image_data_uri = _build_data_uri(prepared_image_path)
    print("[ZHIPU] uploading anchor image to Catbox...", flush=True)
    image_url = _upload_file_to_catbox(prepared_image_path, label="lofi image")
    task_id, direct_video_url, submit_payload = _submit_i2v_job(client, image_url, image_data_uri)
    print(f"[ZHIPU] submit response: {json.dumps(submit_payload, ensure_ascii=False)[:1000]}", flush=True)

    if direct_video_url:
        final_url = direct_video_url
        final_payload = submit_payload
    else:
        if not task_id:
            raise RuntimeError(f"submit succeeded but no task_id: {json.dumps(submit_payload, ensure_ascii=False)}")
        print(f"[ZHIPU] polling task_id={task_id}, interval={POLL_INTERVAL_SEC}s", flush=True)
        final_url, final_payload = _poll_until_done(client, task_id)

    output_file = _download_video(final_url, output_path)
    print(
        json.dumps(
            {
                "status": "success",
                "output": str(output_file),
                "size_bytes": output_file.stat().st_size,
                "task_id": task_id,
                "video_url": final_url,
                "final_payload_preview": json.dumps(final_payload, ensure_ascii=False)[:500],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _append_fatal_learning("Zhipu CogVideoX I2V Launcher", exc)
        print(f"❌ Fatal: {exc}")
        sys.exit(1)