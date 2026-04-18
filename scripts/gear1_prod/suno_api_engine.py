# -*- coding: utf-8 -*-
"""
suno_api_engine.py  —  v8.3 Docker Microservice Edition
==========================================================
Project  : The Marionette's Requiem (v8.3 Golden Triangle API)
Upstream : gcui-art/suno-api  @  http://localhost:3000
Managed  : Docker Compose  →  services/suno-api/

Changelog (v8.3):
  - REMOVED : All legacy Mock / official Suno API direct-call logic
  - ADDED   : Full local-proxy integration via http://localhost:3000
  - ADDED   : /api/custom_generate  with  make_instrumental=True
  - ADDED   : /api/get  polling until status in {streaming, complete}
  - ADDED   : Exponential Backoff retry (max 5 rounds, base 2 s, cap 60 s)
  - ADDED   : Fatal Log hook → project_learning.md  on Exit Code 1

Changelog (v8.3.1 — Epic Extension):
  - ADDED   : extend_audio()  →  POST /api/extend_audio  (previous-segment chaining)
  - ADDED   : concat_clips()  →  POST /api/concat        (multi-segment stitching)
  - ADDED   : _get_track_duration()  helper (reads metadata.duration)
  - ADDED   : generate_epic()  →  high-level 5-10 min epic loop
               (custom_generate → loop extend → concat → music_epic.mp3)

Author    : $$OpenClaw Manager Agent
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 【v12.17】引入 requests 庫進行帶 User-Agent 的下載
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# 跨平台路徑統一由 env_manager 提供，禁止硬編碼磁碟機代號
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/
from common.env_manager import config  # noqa: E402

# ──────────────────────────────────────────────────────────────────────
# 0. PATHS & CONSTANTS
# ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = config.workspace_root
AUDIO_DIR    = PROJECT_ROOT / "assets" / "audio" / "raw_tracks"
LEARNING_LOG = PROJECT_ROOT / "project_learning.md"

# 【CTO v12.0 Master Key Mode】TTAPI 官方 API 配置
TT_BASE_URL        = os.getenv("TT_BASE_URL", "https://api.ttapi.io")
TTAPI_KEY          = os.getenv("TTAPI_KEY", "")
# 向後兼容：仍支持本地代理（若 TT_BASE_URL 設為 localhost）
SUNO_BASE          = TT_BASE_URL  # 統一使用 TTAPI Base URL

POLL_INTERVAL_SEC  = int(os.getenv("SUNO_POLL_INTERVAL", "5"))
MAX_POLL_ATTEMPTS  = int(os.getenv("SUNO_MAX_POLL",      "72"))   # 6 min max
MAX_RETRIES        = int(os.getenv("SUNO_MAX_RETRIES",   "5"))
BACKOFF_BASE_SEC   = float(os.getenv("SUNO_BACKOFF_BASE","2.0"))
BACKOFF_CAP_SEC    = float(os.getenv("SUNO_BACKOFF_CAP", "60.0"))

# 【v12.8 動態彈性輪詢】廢除硬編碼等待，啟用即時輪詢機制
DEFAULT_WAIT_SEC   = 180          # 【v12.18 時長超時寬限】預熱期改為 180 秒（對應 7 分鐘時長基準）
DYNAMIC_POLL_INTERVAL_SEC = 30    # 輪詢期：每隔 30 秒呼叫一次 get_task_status
MAX_WAIT_SEC       = 900          # 超時機制：最多等待 900 秒（15 分鐘）
DYNAMIC_POLL_MAX_ATTEMPTS = (MAX_WAIT_SEC - DEFAULT_WAIT_SEC) // DYNAMIC_POLL_INTERVAL_SEC  # 【v12.18】計算最大輪詢次數 = (900-180)/30 = 24

TERMINAL_STATUSES  = {"streaming", "complete", "error"}

# 【CTO 終極指令】TTAPI Job Status Mapping
TTAPI_JOB_SUCCESS_STATUS = {"success", "completed", "done"}
TTAPI_JOB_PENDING_STATUS = {"pending", "processing", "generating"}
TTAPI_JOB_FAILED_STATUS  = {"failed", "error"}

AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────
# 1. LOGGING
# ──────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SUNO-ENGINE] %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("suno_engine")


# ──────────────────────────────────────────────────────────────────────
# 2. FATAL LOG HOOK  →  project_learning.md
# ──────────────────────────────────────────────────────────────────────
def fatal_log(exc: Exception | str, *, label: str = "suno_api_engine") -> None:
    """
    精簡版 Fatal Log：只寫 ExceptionType + 最後一行關鍵錯誤，防止 log 膨脹。
    遵循 v8.3 規範：append 至 project_learning.md。
    """
    timestamp  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    # 取得 exception 類型名稱與最後一行訊息
    exc_type   = type(exc).__name__ if isinstance(exc, Exception) else "FatalError"
    last_line  = str(exc).strip().splitlines()[-1] if str(exc).strip() else str(exc)

    entry = (
        f"\n---\n"
        f"### ❌ [{timestamp}] {label}\n"
        f"- **ExceptionType** : `{exc_type}`\n"
        f"- **KeyError**      : {last_line}\n"
    )
    try:
        with open(LEARNING_LOG, "a", encoding="utf-8") as fh:
            fh.write(entry)
        log.warning("Fatal error appended to project_learning.md")
    except OSError as e:
        log.error("Could not write to project_learning.md: %s", e)


# ──────────────────────────────────────────────────────────────────────
# 3. HTTP HELPERS  (stdlib only — no external deps for the engine core)
# ──────────────────────────────────────────────────────────────────────
def _normalize_endpoint(endpoint: str) -> str:
    """
    【CTO v12.0 Master Key Mode】
    將本地代理端點轉換為 TTAPI Suno 官方端點。
    支持多個可能的端點路由（故障轉移）。
    
    本地代理: /api/custom_generate  →  TTAPI: /suno/v1/music
    本地代理: /api/get?ids=...  →  TTAPI: /suno/v1/music?ids=...
    本地代理: /api/extend_audio  →  TTAPI: /suno/v1/music/extend
    本地代理: /api/concat  →  TTAPI: /suno/v1/music/concat
    
    若基礎 URL 仍為 localhost:3000，則保持原端點（向後兼容本地測試）。
    """
    # 檢查是否為本地測試模式
    if "localhost" in SUNO_BASE or "127.0.0.1" in SUNO_BASE:
        return endpoint  # 保持原端點
    
    # TTAPI 官方模式：轉換端點
    mapping = {
        "/api/custom_generate": "/suno/v1/music",
        "/api/get": "/suno/v1/music",
        "/api/extend_audio": "/suno/v1/music/extend",
        "/api/concat": "/suno/v1/music/concat",
    }
    
    # 提取基礎端點（去除查詢字串）
    base_endpoint = endpoint.split("?")[0]
    query_string = "?" + endpoint.split("?")[1] if "?" in endpoint else ""
    
    converted = mapping.get(base_endpoint, endpoint)
    return converted + query_string


def _http_post(endpoint: str, payload: dict) -> dict:
    """POST JSON to the TTAPI Suno endpoint with Master Key authentication."""
    endpoint = _normalize_endpoint(endpoint)
    url = f"{SUNO_BASE}{endpoint}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    
    # 【CTO 終極指令】TTAPI 官方規格 - 大寫的 TT-API-KEY
    # 【CTO Cloudflare WAF 繞過】添加 Chrome User-Agent 偽裝
    headers = {
        "Content-Type": "application/json",
        "TT-API-KEY": TTAPI_KEY,  # 必須大寫，無 Accept 欄位
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )
    
    # 【CTO 終極指令 診斷日誌】
    log.info(f"[TTAPI-POST] URL: {url}")
    log.info(f"[TTAPI-POST] TT-API-KEY: {TTAPI_KEY[:20]}..." if TTAPI_KEY else "[TTAPI-POST] TT-API-KEY: NOT SET")
    # 【v12.18 強制 JSON 結構驗證】全量打印 payload，保留轉義符號（不截斷）
    payload_debug = json.dumps(payload, ensure_ascii=False, indent=2)
    log.info(f"【v12.18 Payload-Full-Debug】\n{payload_debug}")
    log.info(f"【v12.18 Payload-Check】提示詞結尾驗證 (應見 \\n...\\n):")
    if "prompt" in payload:
        prompt_content = payload["prompt"]
        last_50_chars = repr(prompt_content[-50:]) if len(prompt_content) > 50 else repr(prompt_content)
        log.info(f"  最後 50 字元 (repr): {last_50_chars}")
    
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as http_err:
        # 【診斷】記錄 403 響應的詳細信息
        log.error(f"[TTAPI-POST] HTTP Error {http_err.code}: {http_err.reason}")
        try:
            error_body = http_err.read().decode("utf-8")
            log.error(f"[TTAPI-POST] Error Response: {error_body[:300]}")
            # 【TTAPI 水位防線】捕捉餘額不足訊息
            if "insufficient balance" in error_body or "餘額不足" in error_body:
                print("\033[91m\n🚨 【TTAPI 緊急停機】餘額不足，請總指揮官儲值！\033[0m")
                import sys
                sys.exit(1)
        except Exception as e:
            pass
        raise


def _http_get(endpoint: str, params: dict | None = None) -> dict | list:
    """GET from the TTAPI Suno endpoint with Master Key authentication."""
    endpoint = _normalize_endpoint(endpoint)
    url = f"{SUNO_BASE}{endpoint}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    
    # 【CTO 終極指令】TTAPI 官方規格 - 大寫的 TT-API-KEY
    # 【CTO Cloudflare WAF 繞過】添加 Chrome User-Agent 偽裝
    headers = {
        "TT-API-KEY": TTAPI_KEY,  # 必須大寫
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    req = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )
    
    log.debug(f"GET {url}")
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


# ──────────────────────────────────────────────────────────────────────
# 4. EXPONENTIAL BACKOFF WRAPPER
# ──────────────────────────────────────────────────────────────────────
def _with_backoff(fn, *args, label: str = "operation", **kwargs) -> Any:
    """
    Call fn(*args, **kwargs) with exponential backoff.
    Raises the last exception (and writes Fatal Log) after MAX_RETRIES fail.
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            wait = min(BACKOFF_BASE_SEC * (2 ** (attempt - 1)), BACKOFF_CAP_SEC)
            log.warning(
                "[%s] Attempt %d/%d failed: %s — retrying in %.0f s",
                label, attempt, MAX_RETRIES, exc, wait,
            )
            if attempt < MAX_RETRIES:
                time.sleep(wait)

    # All retries exhausted → Fatal Log + exit
    err_msg = f"[{label}] All {MAX_RETRIES} retries exhausted. Last error: {last_exc}"
    log.error(err_msg)
    fatal_log(err_msg, label=label)
    raise RuntimeError(err_msg) from last_exc


# ──────────────────────────────────────────────────────────────────────
# 5. CORE API CALLS
# ──────────────────────────────────────────────────────────────────────
def custom_generate(
    prompt: str,
    style: str = "",
    title: str = "Untitled",
    make_instrumental: bool = True,
    model: str = "chirp-v5",
    wait_audio: bool = False,
) -> dict:
    """
    【CTO Custom Mode v16.0 - TTAPI 官方修復】Suno API - 自訂模式 (Custom Mode)
    POST /suno/v1/music
    
    【HTTP 400 修復】根據 TTAPI 官方最新規格，payload 結構修正
    使用結構化時間膨脹 Prompt ([Intro], [Verse], [Chorus])
    """
    # 【v12.17 模型參數化】使用傳入的 model 參數，取代硬編碼
    log.info(f"【v12.17 模型校準】當前使用：{model}")
    
    # 【修正的 Payload 格式】- TTAPI 官方標準
    payload: dict[str, Any] = {
        "custom": True,                    # 自訂模式
        "instrumental": True,              # 純音樂
        "title": title,                    # 曲目名稱
        "prompt": prompt,                  # 結構化 Prompt（支援 [Intro], [Verse] 等）
        "tags": style,                     # 曲風標籤
        "model_name": model,               # 【v12.17 參數化】使用傳入的模型，廢除硬編碼
    }
    
    log.info(f"[TTAPI Suno Official v16.0] POST /suno/v1/music")
    log.info(f"  title={title!r}, style={style!r}")
    log.info(f"  prompt_len={len(prompt)}, model={model}")

    def _do_post() -> dict:
        result = _http_post("/suno/v1/music", payload)
        # TTAPI 官方 API 回傳: {'status': 'success', 'data': {'status': 'SUCCESS', 'data': {'jobId': '...'}}}
        log.info(f"[TTAPI-RESPONSE] {result}")
        
        if isinstance(result, dict):
            # 【CTO 修正】檢查多層次的 status 欄位
            outer_status = result.get("status", "").lower()
            inner_data = result.get("data", {})
            
            if isinstance(inner_data, dict):
                inner_status = inner_data.get("status", "").upper()
                
                # 情況1：outer_status=success 或 inner_status=SUCCESS
                if outer_status == "success" or inner_status == "SUCCESS":
                    # 嘗試多個位置的 jobId
                    nested_data = inner_data.get("data", {})
                    job_id = (
                        inner_data.get("jobId") or
                        inner_data.get("job_id") or
                        (nested_data.get("jobId") if isinstance(nested_data, dict) else None)
                    )
                    
                    if job_id:
                        log.info(f"[TTAPI-SUCCESS] Job accepted: job_id={job_id}")
                        return {"status": "success", "job_id": job_id, "data": result}
            
            # 【診斷】記錄非預期的回應結構
            log.error(f"[TTAPI-ERROR] Unexpected response structure: {result}")
        raise ValueError(f"Unexpected response: {result!r}")

    return _with_backoff(_do_post, label="custom_generate")


# ──────────────────────────────────────────────────────────────────────
# 5.1 TTAPI 異步輪詢 (Job Status Polling)
# ──────────────────────────────────────────────────────────────────────
def _poll_ttapi_job(
    job_id: str,
    poll_interval: int = DYNAMIC_POLL_INTERVAL_SEC,
    max_attempts: int = DYNAMIC_POLL_MAX_ATTEMPTS,
) -> dict:
    """
    【v12.15 緊急邏輯修正】TTAPI 非同步輪詢機制
    
    輪詢策略（嚴禁提前退出）：
    ✅ 預熱期（DEFAULT_WAIT = 120s）：等待初始處理
    ✅ 輪詢期：每隔 30 秒呼叫一次 get_task_status API
    ✅ 嚴禁在 processing/queued 狀態退出
    ✅ 超時機制：最多等待 900 秒（15 分鐘）
    ✅ 只有狀態明確變為 failed 或達到 MAX_WAIT_SEC 時才允許返回錯誤
    
    Args:
        job_id: TTAPI 回傳的任務 ID
        poll_interval: 輪詢間隔秒數（預設 30s）
        max_attempts: 最大輪詢次數（預設 26 次）
    
    Returns:
        job_data dict 包含 status, audio_url 等資訊
    
    Raises:
        TimeoutError: 超過 MAX_WAIT_SEC（900s）無法完成
        RuntimeError: 任務失敗或其他錯誤
    """
    import time
    log.info(f"【v12.18 時長超時寬限】開始監控 job_id={job_id}")
    log.info(f"  預熱期：{DEFAULT_WAIT_SEC}s (v12.18 改為 180s) | 輪詢間隔：{poll_interval}s | 最大等待：{MAX_WAIT_SEC}s")
    
    # 【預熱期】首先等待 DEFAULT_WAIT_SEC 秒，給 TTAPI 足夠的初始處理時間
    log.info(f"⏱️  預熱期：等待 {DEFAULT_WAIT_SEC} 秒讓 TTAPI 初始化 (允許長時長歌曲膨脹時間)...")
    time.sleep(DEFAULT_WAIT_SEC)
    
    # 【輪詢期】一旦預熱完成，開始動態輪詢（嚴禁提前退出）
    for attempt in range(1, max_attempts + 1):
        elapsed_sec = DEFAULT_WAIT_SEC + ((attempt - 1) * poll_interval)
        
        # 【第一優先級】檢查總超時時間
        if elapsed_sec >= MAX_WAIT_SEC:
            err_detail = f"輪詢在 {MAX_WAIT_SEC}s 超時未完成（已達最大等待時限）"
            log.error(f"【v12.15 超時決斷】{err_detail}")
            fatal_log(err_detail, label="_poll_ttapi_job")
            raise TimeoutError(err_detail)
        
        try:
            # 【即時查詢】GET /suno/v1/fetch?jobId=<job_id>
            resp = _http_get("/suno/v1/fetch", params={"jobId": job_id})
            
            # 解析 TTAPI 官方回應格式
            if isinstance(resp, dict):
                status = resp.get("status", "unknown")
                data = resp.get("data", {})
                musics = data.get("musics", []) or []
                
                music_count = len(musics) if musics else 0
                log.info(f"【輪詢 {attempt}/{max_attempts}】[{elapsed_sec}s] status={status}, musics={music_count}")
                
                # 【第二優先級】只有在狀態為 SUCCESS 且有音樂時，才立即返回
                if status in {"SUCCESS", "COMPLETED", "completed", "success"}:
                    if musics and isinstance(musics, list) and len(musics) > 0:
                        log.info(f"【✓ 任務完成 (狀態成功)】耗時 {elapsed_sec}s，共 {len(musics)} 首音樂")
                        # 【v12.8 雙軌全量下載】返回所有 musics（通常為 2 首）
                        return {"status": "success", "musics": musics, "data": {"musics": musics}}
                
                # 【第三優先級】檢查失敗狀態（FAILED = 永久失敗）
                if status == "FAILED":
                    error_msg = "未知錯誤"
                    if musics and isinstance(musics, list) and len(musics) > 0:
                        error_msg = musics[0].get('error_message', '未知錯誤')
                    err_detail = f"TTAPI 任務永久失敗: {error_msg}"
                    log.error(err_detail)
                    fatal_log(err_detail, label="_poll_ttapi_job")
                    raise RuntimeError(err_detail)
                
                # 【第四優先級】所有其他狀態（processing, queued, pending 等）→ 繼續輪詢
                # 嚴禁在 processing/queued 狀態時退出！
                log.info(f"  狀態 [{status}] 未見完成，繼續輪詢...")
                if attempt < max_attempts:
                    next_wait = poll_interval
                    log.debug(f"  待機 {next_wait}s 後進行第 {attempt+1} 次查詢...")
                    time.sleep(next_wait)
                    continue
                else:
                    # 已達最大輪詢次數但尚未超時，應該觸發超時錯誤
                    elapsed_sec_updated = DEFAULT_WAIT_SEC + ((attempt - 1) * poll_interval)
                    err_detail = f"已達最大輪詢次數 ({max_attempts}) 但未超時。狀態: {status}"
                    log.error(f"【v12.15 最大輪詢迴圈結束】{err_detail}")
                    fatal_log(err_detail, label="_poll_ttapi_job")
                    raise TimeoutError(err_detail)
            
            else:
                raise ValueError(f"非預期的 TTAPI 回應結構: {resp!r}")
                
        except urllib.error.HTTPError as http_err:
            log.warning(f"【輪詢 {attempt}/{max_attempts}】HTTP Error {http_err.code}: {http_err.reason}")
            
            # 【v12.11 詳細報錯】捕獲具體 HTTP 狀態碼與錯誤訊息
            error_body = ""
            try:
                error_body = http_err.read().decode("utf-8")
                log.error(f"【v12.11 HTTP 診斷】HTTP {http_err.code} 詳細訊息: {error_body[:300]}")
            except Exception:
                pass
            
            # 【v12.11 容錯升級】HTTP 錯誤時的容錯邏輯
            # - 判斷是否是臨時性錯誤 (5xx 類視為暫時可重試)
            # - 若已接近超時，則拋出異常
            # - 否則繼續重試
            if http_err.code >= 500:
                # 服務器錯誤，允許重試
                log.warning(f"【v12.11 容錯】偵測到服務器暫時故障 (HTTP {http_err.code})，將重試...")
                if elapsed_sec >= MAX_WAIT_SEC:
                    err_detail = f"TTAPI 在 {elapsed_sec}s 後因服務器故障持續失敗 (HTTP {http_err.code}): {error_body[:200]}"
                    log.error(f"【v12.11 最終失敗】{err_detail}")
                    fatal_log(err_detail, label="_poll_ttapi_job")
                    raise TimeoutError(err_detail) from http_err
                log.debug(f"  待機 {poll_interval}s 後進行第 {attempt+1} 次查詢...")
                time.sleep(poll_interval)
                continue
            else:
                # 客戶端錯誤或其他，可能是真實錯誤
                err_detail = f"TTAPI 輪詢失敗 (HTTP {http_err.code}): {error_body[:200]}"
                log.error(f"【v12.11 不可恢復的錯誤】{err_detail}")
                fatal_log(err_detail, label="_poll_ttapi_job")
                raise RuntimeError(err_detail) from http_err
        
        except Exception as exc:
            # 【v12.11 詳細報錯】所有例外都要記錄完整的異常訊息
            log.warning(f"【輪詢 {attempt}/{max_attempts}】異常: {type(exc).__name__}: {str(exc)[:150]}")
            
            if elapsed_sec >= MAX_WAIT_SEC:
                err_detail = f"TTAPI 輪詢在 {elapsed_sec}s 後失敗。最後錯誤: {type(exc).__name__}: {str(exc)[:200]}"
                log.error(f"【v12.11 最終失敗】{err_detail}")
                fatal_log(err_detail, label="_poll_ttapi_job")
                raise RuntimeError(err_detail) from exc
            log.debug(f"  待機 {poll_interval}s 後進行第 {attempt+1} 次查詢...")
            time.sleep(poll_interval)
            continue
    
    # 【輪詢迴圈結束】理論上應該不會執行到此處（已在迴圈內處理所有出口）
    raise TimeoutError(f"任務 {job_id} 輪詢迴圈異常終止")


def poll_until_done(
    track_ids: list[str],
    poll_interval: int = POLL_INTERVAL_SEC,
    max_attempts: int  = MAX_POLL_ATTEMPTS,
) -> list[dict]:
    """
    GET /api/get?ids=<comma-separated>
    Polls until ALL requested tracks reach a terminal status
    (streaming | complete | error).

    Returns the final list of track objects.
    """
    ids_str = ",".join(track_ids)
    log.info("Polling /api/get?ids=%s  (max %d attempts × %ds)",
             ids_str, max_attempts, poll_interval)

    for attempt in range(1, max_attempts + 1):
        def _do_get() -> list[dict]:
            resp = _http_get("/api/get", params={"ids": ids_str})
            if isinstance(resp, list):
                return resp
            if isinstance(resp, dict):
                return [resp]
            raise ValueError(f"Unexpected /api/get response: {resp!r}")

        tracks = _with_backoff(_do_get, label=f"poll/get attempt {attempt}")

        statuses = {t.get("status", "unknown") for t in tracks}
        log.info("  [%d/%d] Statuses: %s", attempt, max_attempts, statuses)

        if statuses.issubset(TERMINAL_STATUSES):
            # Check for errors
            errors = [t for t in tracks if t.get("status") == "error"]
            if errors:
                err_detail = json.dumps(errors, ensure_ascii=False, indent=2)
                msg = f"Suno returned error status for {len(errors)} track(s)"
                fatal_log(msg, label="poll_until_done")
                raise RuntimeError(msg + "\n" + err_detail)
            log.info("All tracks reached terminal status.")
            return tracks

        time.sleep(poll_interval)

    # Timeout
    msg = (f"Polling timed out after {max_attempts * poll_interval}s. "
           f"Last statuses: {statuses}")
    fatal_log(msg, label="poll_until_done")
    raise TimeoutError(msg)


# ──────────────────────────────────────────────────────────────────────
# 5.5  EXTEND + CONCAT  (v8.3.1 史詩長片邏輯)
# ──────────────────────────────────────────────────────────────────────
def extend_audio(
    audio_id: str,
    prompt: str,
    style: str = "",
    model: str = "chirp-crow",
) -> list[dict]:
    """
    POST /api/extend_audio — 接續前段 ID 向後延伸，生成下一片段。
    回傳新片段的 track 物件清單。
    """
    payload: dict[str, Any] = {
        "audio_id":         audio_id,
        "prompt":           prompt,
        "tags":             style,
        "make_instrumental": True,
        "model":            model,
    }
    log.info("POST /api/extend_audio  audio_id=%s", audio_id)

    def _do_post() -> list[dict]:
        result = _http_post("/api/extend_audio", payload)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "id" in result:
            return [result]
        raise ValueError(f"Unexpected extend_audio response: {result!r}")

    return _with_backoff(_do_post, label="extend_audio")


def concat_clips(last_clip_id: str) -> dict:
    """
    POST /api/concat — 傳入 extend 鏈的最後一段 ID，
    Suno 後端會自動把整條 extend 鏈縫合成完整音軌。
    """
    payload = {"clip_id": last_clip_id}
    log.info("POST /api/concat  clip_id=%s", last_clip_id)

    def _do_post() -> dict:
        result = _http_post("/api/concat", payload)
        if isinstance(result, dict):
            return result
        if isinstance(result, list) and result:
            return result[0]
        raise ValueError(f"Unexpected concat response: {result!r}")

    return _with_backoff(_do_post, label="concat_clips")


def _get_track_duration(track: dict) -> float:
    """
    從 track 物件取得秒數。
    Suno 在 streaming 階段 metadata.duration 尚未填寫，
    改從頂層 duration / audio_duration 欄位取值；全部為空時回傳預設 120s（單段約 2 分鐘）。
    """
    try:
        # 優先：頂層直接欄位（complete 狀態）
        for key in ("duration", "audio_duration"):
            v = track.get(key)
            if v:
                return float(v)
        # 次要：metadata.duration
        v = track.get("metadata", {}).get("duration")
        if v:
            return float(v)
    except (TypeError, ValueError):
        pass
    # streaming 狀態尚無 metadata：預設每段 ~120s 讓 total_sec 累積正常
    if track.get("status") == "streaming":
        return 120.0
    return 0.0


# ──────────────────────────────────────────────────────────────────────
# 6. AUDIO DOWNLOAD HELPER
# ──────────────────────────────────────────────────────────────────────
# 【v12.17】帶 User-Agent + 重試機制的下載函數
def _download_with_retry(
    url: str,
    dest: Path,
    max_retries: int = 3,
    retry_interval_sec: int = 5,
) -> bool:
    """
    【v12.17 防彈下載引擎】透過 requests 庫進行下載，帶 User-Agent 與重試機制
    
    Args:
        url: 下載 URL
        dest: 目標檔案路徑
        max_retries: 最大重試次數（預設 3）
        retry_interval_sec: 重試間隔秒數（預設 5）
    
    Returns:
        True 如果成功，False 如果失敗
    """
    # 模擬瀏覽器 User-Agent
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for attempt in range(1, max_retries + 1):
        try:
            if HAS_REQUESTS:
                # 【優先】使用 requests 庫
                log.info(f"  【下載嘗試 {attempt}/{max_retries}】透過 requests 下載: {url[:80]}...")
                resp = requests.get(url, headers=headers, timeout=60, allow_redirects=True)
                resp.raise_for_status()
                
                with open(dest, "wb") as f:
                    f.write(resp.content)
                
                log.info(f"    ✅ 下載成功（{len(resp.content) / 1024 / 1024:.2f} MB）")
                return True
            else:
                # 【備援】使用 urllib，但帶 User-Agent
                log.info(f"  【下載嘗試 {attempt}/{max_retries}】透過 urllib 下載: {url[:80]}...")
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    with open(dest, "wb") as f:
                        f.write(resp.read())
                log.info(f"    ✅ 下載成功")
                return True
        
        except Exception as exc:
            log.warning(f"    ⚠️  嘗試 {attempt} 失敗: {type(exc).__name__}: {str(exc)[:100]}")
            
            if attempt < max_retries:
                log.info(f"    ⏱️  等待 {retry_interval_sec} 秒後重試...")
                time.sleep(retry_interval_sec)
            else:
                log.error(f"  【❌ 下載最終失敗】已嘗試 {max_retries} 次，放棄")
                return False
    
    return False


def get_unique_filename(
    base_title: str,
    dest_dir: Path = AUDIO_DIR,
    extension: str = ".mp3",
    batch_index: int = 0,  # 【v12.17】批次索引（用於預判命名）
) -> str:
    """
    【v12.17 預判命名演算法】生成唯一的檔名，避免批次內衝突。

    演算法流程：
      1. 若 batch_index > 0，預設 [base_title] Vol. 2.mp3、Vol. 3…（空格 + Vol. n，沿用既有規則）
      2. 否則檢查 [base_title].mp3 是否已存在
      3. 若存在，嘗試 [base_title] Vol. 2.mp3, Vol. 3, ... 直到找到第一個可用的檔名
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 【v12.17 預判 + 防覆蓋】若非第一首，預設加上 Vol. 標記，但需檢查磁碟碰撞
    if batch_index > 0:
        vol_start = batch_index + 1
        candidate = f"{base_title} Vol. {vol_start}{extension}"
        if not (dest_dir / candidate).exists():
            log.info(f"【v12.17 預判命名】批次第 {batch_index + 1} 首，預設命名: {candidate}")
            return candidate
        vol_ver = vol_start + 1
        while vol_ver <= 100:
            candidate = f"{base_title} Vol. {vol_ver}{extension}"
            if not (dest_dir / candidate).exists():
                log.info(f"【預判防覆蓋】Vol. {vol_start} 已存在，遞增至: {candidate}")
                return candidate
            vol_ver += 1
        raise RuntimeError(f"無法為 {base_title} 找到唯一檔名（Vol. {vol_start}~100 皆被佔用）")

    # 【默認】首先嘗試基礎檔名
    candidate = f"{base_title}{extension}"
    candidate_path = dest_dir / candidate

    if not candidate_path.exists():
        log.info(f"【Unique Filename】可用檔名: {candidate}")
        return candidate

    vol_version = 2
    max_attempts = 100
    while vol_version <= max_attempts:
        # 格式：[Title] Vol. 2.mp3（空格必須保留）
        candidate = f"{base_title} Vol. {vol_version}{extension}"
        candidate_path = dest_dir / candidate

        if not candidate_path.exists():
            log.info(f"【Unique Filename】已存在重複，遞增至: {candidate}")
            return candidate

        vol_version += 1

    raise RuntimeError(f"無法為 {base_title} 找到唯一檔名（已嘗試 {max_attempts} 個版本）")


def download_audio(track: dict, dest_dir: Path = AUDIO_DIR) -> Path:
    """
    Download the audio_url from a completed track object and save as MP3.
    【v12.8】使用遞增命名演算法避免檔名衝突。
    Returns the local Path of the saved file.
    """
    audio_url = track.get("audio_url") or track.get("stream_audio_url", "")
    if not audio_url:
        raise ValueError(f"No audio_url in track: {track.get('id')}")

    track_id = track.get("id", "unknown")
    title    = track.get("title", "untitled").replace(" ", "_").replace("/", "-")
    
    # 【v12.8】使用遞增命名演算法
    filename = get_unique_filename(title, dest_dir)
    dest     = dest_dir / filename

    log.info("Downloading audio → %s", dest)

    def _do_download() -> Path:
        urllib.request.urlretrieve(audio_url, str(dest))  # noqa: S310
        return dest

    return _with_backoff(_do_download, label="download_audio")


# ──────────────────────────────────────────────────────────────────────
# 7. HIGH-LEVEL PUBLIC INTERFACE
# ──────────────────────────────────────────────────────────────────────
def generate_instrumental(
    prompt:  str,
    style:   str  = "",
    title:   str  = "BGM",
    model:   str  = "chirp-crow",
    download: bool = True,
    output_dir: Path | str | None = None,
) -> dict:
    """
    【CTO 終極指令】End-to-end TTAPI pipeline:
      1. POST /suno/v1/music  (custom_generate, custom=True, mv=chirp-v5)
      2. Poll /suno/v1/music?ids=job_id  until complete
      3. 【v12.8】Download ALL MP3s from task["clips"] to assets/audio/  (雙軌全量下載)

    【v12.8 物理隔離】支援 --output-dir 參數指定下載目錄（通常為頻道子目錄）
    
    Returns a result dict:
      {
        "status":           "success" | "error",
        "job_id":           "...",
        "downloaded_files": [Path1, Path2, ...],  # 【v12.8】所有下載的檔案清單
        "duration_sec":     float | None
      }
    """
    dest_dir = Path(output_dir) if output_dir else AUDIO_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    log.info("=== [TTAPI v12.17] generate_instrumental START ===")
    log.info("  title=%r  style=%r  model=%r  download=%s  output_dir=%s", title, style, model, download, dest_dir)
    log.info("【v12.17 模型校準】當前使用模型: %s", model)

    try:
        # Step 1 — Submit generation job via TTAPI
        result = custom_generate(
            prompt=prompt,
            style=style,
            title=title,
            make_instrumental=True,
            model=model,  # 【v12.17】直接傳遞 model 參數，不再硬編碼
            wait_audio=False,
        )
        
        if not result or result.get("status") != "success":
            raise ValueError(f"custom_generate failed: {result}")
        
        job_id = result.get("job_id")
        if not job_id:
            raise ValueError(f"custom_generate returned no job_id: {result}")
        log.info(f"【TTAPI】Job submitted: job_id={job_id}")
        
        # Step 2 — Poll until complete
        job_data = _poll_ttapi_job(job_id)
        
        # Step 3 — 【v12.17 防彈下載】遍歷所有 clips/musics 並下載（帶 User-Agent + 重試）
        downloaded_files = []
        if download:
            musics = job_data.get("musics", [])
            
            if not musics:
                log.warning("⚠️  warning: TTAPI 回應未包含 musics/clips")
            else:
                log.info(f"【v12.17 防彈下載】檢測到 {len(musics)} 首音樂，開始遍歷下載...")
                
                for idx, music_track in enumerate(musics, start=1):
                    try:
                        audio_url = music_track.get("audioUrl") or music_track.get("audio_url")
                        track_title = music_track.get("title") or f"Track_{idx}"  # 【v14.2 命名權歸還】Only fallback if Suno truly returned no title
                        track_id = music_track.get("id", f"unknown_{idx}")
                        
                        if not audio_url:
                            log.warning(f"  【音軌 {idx}】⚠️  無 audioUrl，跳過")
                            continue
                        
                        # 【v12.17 預判命名】批次內第 2、3 首自動加 Vol. 標記
                        batch_index = idx - 1  # 0-indexed
                        filename = get_unique_filename(track_title, dest_dir, batch_index=batch_index)
                        dest = dest_dir / filename
                        
                        log.info(f"  【音軌 {idx}/{len(musics)}】下載: {filename}")
                        
                        # 【v12.17 防彈下載】使用帶 User-Agent 和重試的下載函數
                        if _download_with_retry(audio_url, dest, max_retries=3, retry_interval_sec=5):
                            downloaded_files.append(dest)
                            log.info(f"    ✅ 成功: {dest}")
                        else:
                            log.warning(f"  【音軌 {idx}】❌ 下載最終失敗（3 次重試後仍失敗）")
                            continue
                        
                    except Exception as track_err:
                        log.warning(f"  【音軌 {idx}】❌ 下載異常: {track_err}")
                        continue
                
                if downloaded_files:
                    log.info(f"【✓ v12.17 防彈下載完成】共下載 {len(downloaded_files)} 首")
                else:
                    log.warning("⚠️ 無法下載任何音軌")

        # 【v15.9】審計用：下載數量 + 每首檔名（產線 log / 對帳）
        if download:
            if downloaded_files:
                log.info("【TTAPI_DOWNLOAD_SUMMARY】本次成功下載 %d 首", len(downloaded_files))
                for _i, _p in enumerate(downloaded_files, start=1):
                    log.info("  [%d] %s", _i, _p.name)
                log.info(
                    "【TTAPI_DOWNLOAD_SUMMARY】路徑: %s",
                    downloaded_files[0].parent,
                )
            elif job_data.get("musics"):
                log.warning(
                    "【TTAPI_DOWNLOAD_SUMMARY】API 回傳 %d 首但本地下載 0 首，請檢查 URL / 網路",
                    len(job_data.get("musics", [])),
                )
        
        log.info("=== [TTAPI v12.8] generate_instrumental SUCCESS ===")
        return {
            "status":           "success",
            "job_id":           job_id,
            "downloaded_files": downloaded_files,
            "duration_sec":     job_data.get("duration"),
        }
    
    except Exception as exc:
        err_msg = f"generate_instrumental failed: {exc}"
        log.error(err_msg)
        fatal_log(err_msg, label="generate_instrumental")
        raise RuntimeError(err_msg) from exc


# ──────────────────────────────────────────────────────────────────────
# 6.5 FFmpeg CROSSFADE CONCAT (CTO v16.0 - Multi-Shot Stitching)
# ──────────────────────────────────────────────────────────────────────
def _concat_with_crossfade(
    part1_path: Path,
    part2_path: Path,
    output_path: Path,
    crossfade_sec: float = 5.0,
) -> bool:
    """
    【CTO v16.0】FFmpeg 交叉淡化縫合 (Crossfade Concat)
    
    使用 FFmpeg 的 acrossfade 濾鏡將兩個音檔無縫拼接。
    
    Args:
        part1_path: 第一首音檔路徑
        part2_path: 第二首音檔路徑
        output_path: 輸出檔案路徑
        crossfade_sec: 交叉淡化時長 (秒)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        log.info(f"【FFmpeg Crossfade】 part1={part1_path.name}, part2={part2_path.name}, crossfade={crossfade_sec}s")
        
        # 【FFmpeg 交叉淡化命令】
        # -i part1.mp3 -i part2.mp3 -filter_complex 
        # "[0:a][1:a]acrossfade=d=5:c1=tri:c2=tri[aout]" -map "[aout]" output.mp3
        cmd = [
            "ffmpeg",
            "-i", str(part1_path),
            "-i", str(part2_path),
            "-filter_complex",
            f"[0:a][1:a]acrossfade=d={crossfade_sec}:c1=tri:c2=tri[aout]",
            "-map", "[aout]",
            "-y",  # 覆蓋輸出檔案（無提示）
            str(output_path),
        ]
        
        log.info(f"[FFmpeg Command] {' '.join(cmd)}")
        
        # 執行 FFmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 分鐘超時
        )
        
        if result.returncode == 0:
            output_size_mb = output_path.stat().st_size / (1024 * 1024)
            log.info(f"【✓ FFmpeg Crossfade SUCCESS】 {output_path.name} ({output_size_mb:.2f} MB)")
            return True
        else:
            log.error(f"[FFmpeg Error] Return code: {result.returncode}")
            log.error(f"[FFmpeg Stderr] {result.stderr}")
            return False
    
    except subprocess.TimeoutExpired:
        log.error(f"[FFmpeg Timeout] Crossfade took longer than 300s")
        return False
    except FileNotFoundError:
        log.error(f"[FFmpeg NotFound] Is FFmpeg installed? Check PATH")
        return False
    except Exception as exc:
        log.error(f"[FFmpeg Error] {exc}")
        return False




def generate_epic(
    prompt: str,
    style: str = "",
    title: str = "BGM_Epic",
    model: str = "chirp-v5",
    target_sec: float = 150.0,
    dest_filename: str = "music_epic.mp3",
) -> dict:
    """
    【CTO v16.0 - 多次獨立生成 + FFmpeg 交叉淡化】
    
    放棄 Extend API （因為 continue_at 參數無法正確解析），改用多次獨立生成策略：
    
    流程：
      1. 迴圈 2 次，各呼叫 custom_generate (使用相同 Prompt 和 Style)
      2. 下載 part1 和 part2
      3. 使用 FFmpeg acrossfade 濾鏡進行 5 秒交叉淡化縫合
      4. 驗證輸出長度 (>2.5MB ≈ 100 秒)
      5. 垃圾回收 — 刪除所有 temp_ 碎片
    
    Args:
        prompt: 結構化時間膨脹 Prompt ([Intro], [Verse], [Chorus] ...)
        style: 曲風標籤
        title: 曲名
        model: Suno 模型 (chirp-v5 / chirp-v5.5)
        target_sec: 目標長度 (參考值，實際由 FFmpeg 決定)
        dest_filename: 輸出檔案名稱

    Returns:
        result dict with keys: status, job_ids, local_path, final_size_mb
    """
    log.info(f"[TTAPI Epic v16.0 - Multi-Shot] START target={target_sec}s title={title!r} model={model}")
    
    temp_parts = []  # 追蹤所有臨時檔案以便清理
    job_ids = []
    
    try:
        # ═════════════════════════════════════════════════════════════
        # 【STEP 1】多次獨立生成
        # ═════════════════════════════════════════════════════════════
        log.info("【Step 1】多次獨立生成 - 迴圈呼叫 custom_generate 2 次")
        
        for shot_idx in range(1, 3):  # 生成 part1 和 part2
            log.info(f"[Multi-Shot] Shot {shot_idx}/2 generating...")
            
            try:
                # 呼叫 custom_generate
                result = custom_generate(
                    prompt=prompt,
                    style=style,
                    title=f"{title}_part{shot_idx}",
                    make_instrumental=True,
                    model=model,
                    wait_audio=False,
                )
                
                if not result or result.get("status") != "success":
                    raise ValueError(f"custom_generate shot {shot_idx} failed: {result}")
                
                job_id = result.get("job_id")
                if not job_id:
                    raise ValueError(f"No job_id returned from shot {shot_idx}: {result}")
                
                job_ids.append(job_id)
                log.info(f"[Multi-Shot] Shot {shot_idx} job_id={job_id}")
                
                # 輪詢至完成
                log.info(f"[Multi-Shot] Shot {shot_idx} polling...")
                job_data = _poll_ttapi_job(job_id)
                
                # 下載音檔
                audio_url = job_data.get("audio_url")
                if not audio_url:
                    raise ValueError(f"No audio_url from shot {shot_idx}: {job_data}")
                
                # 儲存為臨時檔案
                temp_filename = f"temp_{job_id}_part{shot_idx}.mp3"
                temp_path = AUDIO_DIR / temp_filename
                
                log.info(f"[Multi-Shot] Shot {shot_idx} downloading to {temp_filename}...")
                urllib.request.urlretrieve(audio_url, str(temp_path))  # noqa: S310
                
                temp_size_mb = temp_path.stat().st_size / (1024 * 1024)
                temp_parts.append(temp_path)
                log.info(f"【✓ Part {shot_idx} Downloaded】{temp_filename} ({temp_size_mb:.2f} MB)")
                
            except Exception as shot_err:
                log.error(f"[Multi-Shot] Shot {shot_idx} failed: {shot_err}")
                # 清理已下載的臨時檔案
                for temp_file in temp_parts:
                    try:
                        os.remove(temp_file)
                        log.info(f"[GC] Deleted {temp_file.name}")
                    except OSError:
                        pass
                raise RuntimeError(f"Shot {shot_idx} generation failed") from shot_err
        
        # 確保有 2 個部分
        if len(temp_parts) < 2:
            raise RuntimeError(f"Expected 2 parts, got {len(temp_parts)}")
        
        part1_path = temp_parts[0]
        part2_path = temp_parts[1]
        
        # ═════════════════════════════════════════════════════════════
        # 【STEP 2】FFmpeg 交叉淡化縫合
        # ═════════════════════════════════════════════════════════════
        log.info("【Step 2】FFmpeg 交叉淡化縫合 (Crossfade Concat)")
        
        # 使用臨時目標檔案，暫時儲存縫合結果
        temp_output_path = AUDIO_DIR / f"temp_crossfade_{job_ids[0]}.mp3"
        
        success = _concat_with_crossfade(
            part1_path=part1_path,
            part2_path=part2_path,
            output_path=temp_output_path,
            crossfade_sec=5.0,  # CTO 指定 5 秒交叉淡化
        )
        
        if not success:
            # 清理所有臨時檔案
            for temp_file in temp_parts + [temp_output_path]:
                try:
                    if temp_file.exists():
                        os.remove(temp_file)
                        log.info(f"[GC] Deleted {temp_file.name}")
                except OSError:
                    pass
            raise RuntimeError("FFmpeg crossfade failed")
        
        # ═════════════════════════════════════════════════════════════
        # 【STEP 3】長度驗證 (Validation & Fallback)
        # ═════════════════════════════════════════════════════════════
        log.info("【Step 3】長度驗證")
        
        final_size_mb = temp_output_path.stat().st_size / (1024 * 1024)
        log.info(f"[Validation] Concatenated size: {final_size_mb:.2f} MB")
        
        # CTO 要求：只要合併後的檔案大於 2.5MB (約 100 秒)，就視為及格
        MIN_SIZE_MB = 2.5
        if final_size_mb < MIN_SIZE_MB:
            log.error(f"[Validation FAIL] Size {final_size_mb:.2f} MB < {MIN_SIZE_MB} MB")
            # 清理所有臨時檔案
            for temp_file in temp_parts + [temp_output_path]:
                try:
                    if temp_file.exists():
                        os.remove(temp_file)
                        log.info(f"[GC] Deleted {temp_file.name}")
                except OSError:
                    pass
            raise RuntimeError(f"Output too small: {final_size_mb:.2f} MB < {MIN_SIZE_MB} MB")
        
        log.info(f"【✓ Validation PASS】Size {final_size_mb:.2f} MB ≥ {MIN_SIZE_MB} MB")
        
        # ═════════════════════════════════════════════════════════════
        # 【STEP 4】移動至最終目標位置
        # ═════════════════════════════════════════════════════════════
        log.info("【Step 4】移動至最終目標位置")
        
        final_path = AUDIO_DIR / dest_filename
        # 如果目標檔案已存在，覆蓋它
        if final_path.exists():
            os.remove(final_path)
            log.info(f"[Overwrite] Removed existing {dest_filename}")
        
        # 將臨時輸出移動到最終位置
        shutil.move(str(temp_output_path), str(final_path))
        log.info(f"【✓ Final Output】{final_path.name}")
        
        # ═════════════════════════════════════════════════════════════
        # 【STEP 5】垃圾回收 (Garbage Collection)
        # ═════════════════════════════════════════════════════════════
        log.info("【Step 5】垃圾回收 - 刪除所有臨時檔案")
        
        for temp_file in temp_parts:
            try:
                if temp_file.exists():
                    os.remove(temp_file)
                    log.info(f"[GC] Deleted {temp_file.name}")
            except OSError as gc_err:
                log.warning(f"[GC] Failed to delete {temp_file.name}: {gc_err}")
        
        # 確保臨時輸出檔案也被刪除（若尚未移動）
        if temp_output_path.exists():
            try:
                os.remove(temp_output_path)
                log.info(f"[GC] Deleted {temp_output_path.name}")
            except OSError:
                pass
        
        # ═════════════════════════════════════════════════════════════
        # 【完成】返回成功結果
        # ═════════════════════════════════════════════════════════════
        log.info(f"[TTAPI Epic v16.0] SUCCESS: {final_path}")
        
        return {
            "status":       "success",
            "job_ids":      job_ids,
            "audio_urls":   [],
            "local_path":   final_path,
            "final_size_mb": final_size_mb,
        }
    
    except Exception as exc:
        err_msg = f"generate_epic v16.0 failed: {exc}"
        log.error(err_msg)
        fatal_log(err_msg, label="generate_epic")
        
        # 確保清理所有臨時檔案
        for temp_file in temp_parts:
            try:
                if temp_file.exists():
                    os.remove(temp_file)
                    log.info(f"[GC] Emergency cleanup: {temp_file.name}")
            except OSError:
                pass
        
        raise RuntimeError(err_msg) from exc



# ──────────────────────────────────────────────────────────────────────
# 8. HEALTH CHECK
# ──────────────────────────────────────────────────────────────────────
def health_check() -> bool:
    """
    Ping the suno-api proxy to verify it is reachable.
    Returns True if the service is up.
    """
    try:
        resp = _http_get("/api/get_limit")
        log.info("Health check OK — proxy is reachable: %s", resp)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("Health check FAILED — is Docker running? Error: %s", exc)
        log.error(
            "  Start the service with:  cd services/suno-api && docker compose up -d"
        )
        return False


# ──────────────────────────────────────────────────────────────────────
# 9. MAIN (smoke test / CLI usage)
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    """
    【CTO 終極指令】CLI 單曲生成模式  
    允許 pipeline_runner.py 透過 subprocess 直接呼叫此腳本進行單曲生成。
    
    使用方式：
      python suno_api_engine.py --prompt "..." --tags "lofi,chill"
      python suno_api_engine.py --recipe-file daily_prompts_*.txt --line 0
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Suno API Engine - CLI Single Track Generation v8.3.1 (CTO Edition)"
    )
    
    # 模式 A：直接傳入 prompt
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="直接傳入 Prompt 文本"
    )
    
    parser.add_argument(
        "--tags",
        type=str,
        default="lofi,chill",
        help="風格標籤（逗號分隔）"
    )
    
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="曲目標題（若不指定則自動生成）"
    )
    
    # 模式 B：從配方檔讀取
    parser.add_argument(
        "--recipe-file",
        type=str,
        default=None,
        help="配方檔路徑（JSON）"
    )
    
    parser.add_argument(
        "--line",
        type=int,
        default=0,
        help="配方檔中第幾行（0-based）"
    )
    
    # 輸出目錄（覆蓋預設值）
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="輸出目錄（預設：assets/audio/ceo_approved_beats/）"
    )
    
    # 【v12.17】模型參數化
    parser.add_argument(
        "--model",
        type=str,
        default="chirp-v5",
        help="使用的 Suno 模型 (預設: chirp-v5，可選: chirp-crow, chirp-v3-5)"
    )
    
    # 【v12.27 頻道參數穿透協議】強制頻道標簽（用於審計與監控）
    parser.add_argument(
        "--channel",
        type=str,
        default="lofi",
        choices=["lofi", "light_music"],
        help="視覺通道：lofi（預設）或 light_music"
    )
    
    args = parser.parse_args()
    
    # 【v12.17 路徑優先級驗證】CLI 參數 > 配置預設值
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        # 【CTO 強制】下載到 ceo_approved_beats/，而非 raw_tracks/
        out_dir = PROJECT_ROOT / "assets" / "audio" / "ceo_approved_beats"
    
    # 【v12.17 模型參數驗證】
    model_choice = args.model
    log.info(f"【v12.17 CLI 參數校準】selected_model={model_choice}")
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 取得 Prompt
    if args.recipe_file:
        # 模式 B：從配方檔讀取
        recipe_path = Path(args.recipe_file)
        try:
            with open(recipe_path, "r", encoding="utf-8") as f:
                recipes = json.load(f)
            
            if not isinstance(recipes, list):
                recipes = [recipes]
            
            if args.line >= len(recipes):
                log.error("❌ 行號超出範圍")
                sys.exit(1)
            
            recipe = recipes[args.line]
            prompt = recipe.get("prompt")
            tags = recipe.get("tags", args.tags)
            title = recipe.get("title", args.title or f"Track_{args.line:03d}")
            
        except Exception as e:
            log.error(f"❌ 讀取配方檔失敗: {e}")
            sys.exit(1)
    
    elif args.prompt:
        # 模式 A：直接傳入
        prompt = args.prompt
        tags = args.tags
        title = args.title if args.title is not None else ""  # 【v14.2 命名權歸還】支持真正的空字串，禁止偷塞 Generated_Track
    
    else:
        log.error("❌ 必須提供 --prompt 或 --recipe-file")
        parser.print_help()
        sys.exit(1)
    
    # 【關鍵】驗證 TTAPI 環境
    if not TTAPI_KEY:
        log.error("❌ TTAPI_KEY 未設定，無法進行生成")
        sys.exit(1)
    
    log.info("=" * 80)
    log.info("【CLI 單曲生成模式】")
    log.info(f"  Title: {title}")
    log.info(f"  Tags: {tags}")
    log.info(f"  Prompt: {prompt[:100]}...")
    log.info(f"  Output: {out_dir}")
    log.info("=" * 80)
    
    # 【v12.17 真實呼叫】執行生成 + 下載（帶模型參數化）
    result = generate_instrumental(
        prompt=prompt,
        style=tags,
        title=title,
        model=model_choice,  # 【v12.17】使用 CLI 指定的模型
        download=True,
        output_dir=str(out_dir)  # 【v12.17 路徑優先級】明確指定輸出目錄
    )
    
    if result.get("status") != "success":
        log.error(f"❌ 生成失敗: {result}")
        sys.exit(1)
    
    # 【v12.17 完成報告】（檔名清單已由 generate_instrumental 內 【TTAPI_DOWNLOAD_SUMMARY】輸出）
    downloaded_files = result.get("downloaded_files", [])
    if downloaded_files:
        log.info(f"✅ 成功下載 {len(downloaded_files)} 首音樂到: {out_dir}")
        log.info(f"   Job ID: {result.get('job_id')}")
        log.info(f"   Duration: {result.get('duration_sec', 'N/A')} sec")
    else:
        log.error(f"❌ 下載檔案不存在")
        sys.exit(1)
    
    log.info("=" * 80)
    log.info("✅ CLI 單曲生成完成")
    log.info("=" * 80)