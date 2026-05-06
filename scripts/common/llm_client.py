#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common/llm_client.py
v15.10 軍規級 API 防護：三引擎大模型安全通訊網關 + 重試佇列
強制 Structured Outputs (JSON Schema)，內建重試與日誌瘦身，環境變數統一派發。

【v15.3 三引擎架構】
✅ 引擎1 zhipu  — 智譜 GLM-4（預設，省錢穩定）
✅ 引擎2 gemini — Google Gemini 2.5 Flash（視覺解構備用）
✅ 引擎3 minimax— MiniMax M2.7 230B MoE via NVIDIA NIM
             相容 OpenAI 協定，base_url = https://integrate.api.nvidia.com/v1

【v15.10 新增】
✅ LLMRetryQueue — 三引擎全失敗時的非同步重試佇列，48hr 內自動補償
✅ parse_llm_json_response() — 統一 JSON 解析入口（消除三處重複實作）
✅ 所有密鑰由 env_manager.py 統一派發，自動從 .env 讀取
✅ 全部採用 lazy import，避免未安裝套件干擾其他引擎
"""

import os
import sys
import json
import time
import random
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from collections import deque

# 【CTO 強制執行】確保腳本能找到專案根目錄並載入 common 模組
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.common.json_parser_utils import parse_llm_json_response

# 顏色碼（終端機輸出）
RED = "\033[91m"
RESET = "\033[0m"

# Gemini API 初始化旗標（lazy — 只有 provider="gemini" 時才初始化）
_gemini_configured: bool = False
_genai = None  # lazy import placeholder


# ============================================================================
# 【v15.10 新增】LLM 重試佇列 — 三引擎全失敗時的非同步補償機制
# ============================================================================

@dataclass
class FailedLLMRequest:
    """一筆失敗的 LLM 請求記錄"""
    timestamp: float = field(default_factory=time.time)
    provider: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    model: str = ""
    last_error: str = ""
    retry_count: int = 0
    max_total_retries: int = 5              # 總重試次數上限
    retention_hours: int = 48               # 超過此時間則棄置
    callback_on_success: Optional[Callable] = None  # 成功後的回呼


class LLMRetryQueue:
    """
    【v15.10】LLM 失敗請求重試佇列。
    
    當三引擎鏈（MiniMax → Zhipu → Gemini）全部失敗時，
    請求自動入隊。產線完成後或閒置時，背景執行 batch_retry()。
    48 小時內未成功則棄置並記錄最終錯誤。

    【v15.11 P2#9】SQLite 持久化：
        LLM_RETRY_PERSIST=true 時，失敗請求寫入
        assets/data/llm_retry_queue.db，重新啟動後自動恢復。

    使用方式：
        queue = LLMRetryQueue(max_queue_size=100)
        queue.enqueue(provider, sys_prompt, usr_prompt, model, error)
        # ... 產線繼續 ...
        results = queue.batch_retry()  # 背景重試
    """

    _DB_TABLE_DDL = """
        CREATE TABLE IF NOT EXISTS llm_retry_queue (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp      REAL    NOT NULL,
            provider       TEXT    NOT NULL,
            system_prompt  TEXT    NOT NULL,
            user_prompt    TEXT    NOT NULL,
            model          TEXT    NOT NULL,
            last_error     TEXT    DEFAULT '',
            retry_count    INTEGER DEFAULT 0,
            max_retries    INTEGER DEFAULT 5,
            retention_hrs  INTEGER DEFAULT 48
        )
    """

    def __init__(self, max_queue_size: int = 100, retention_hours: int = 48):
        self._queue: deque[FailedLLMRequest] = deque(maxlen=max_queue_size)
        self._lock = threading.Lock()
        self.retention_hours = retention_hours
        # v15.11 P2#9：SQLite 持久化（opt-in）
        self._persist_enabled = os.environ.get("LLM_RETRY_PERSIST", "").lower() == "true"
        self._db_path: Optional[Path] = None
        if self._persist_enabled:
            self._db_path = _PROJECT_ROOT / "assets" / "data" / "llm_retry_queue.db"
            self._init_persist_db()
            self._load_from_db()

    def _init_persist_db(self) -> None:
        """建立或遷移 SQLite 持久化資料表"""
        import sqlite3 as _sqlite3
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with _sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(self._DB_TABLE_DDL)
                conn.commit()
        except Exception as e:
            print(f"  ⚠️ [RetryQueue] 持久化 DB 初始化失敗，降級為記憶體模式: {e}")
            self._persist_enabled = False

    def _load_from_db(self) -> None:
        """啟動時從 DB 恢復未完成請求"""
        import sqlite3 as _sqlite3
        try:
            now = time.time()
            with _sqlite3.connect(str(self._db_path)) as conn:
                rows = conn.execute(
                    "SELECT timestamp, provider, system_prompt, user_prompt, model, "
                    "last_error, retry_count, max_retries, retention_hrs FROM llm_retry_queue"
                ).fetchall()
                conn.execute("DELETE FROM llm_retry_queue")
                conn.commit()
            loaded = 0
            for row in rows:
                ts, prov, sys_p, usr_p, mdl, err, rc, mr, rh = row
                if (now - ts) > (rh * 3600):
                    continue  # 過期跳過
                req = FailedLLMRequest(
                    timestamp=ts, provider=prov,
                    system_prompt=sys_p, user_prompt=usr_p,
                    model=mdl, last_error=err,
                    retry_count=rc, max_total_retries=mr, retention_hours=rh,
                )
                self._queue.append(req)
                loaded += 1
            if loaded:
                print(f"  📂 [RetryQueue] 從 DB 恢復 {loaded} 筆未完成請求")
        except Exception as e:
            print(f"  ⚠️ [RetryQueue] 從 DB 載入失敗: {e}")

    def _persist_to_db(self, req: FailedLLMRequest) -> None:
        """將單筆請求寫入 SQLite 持久化"""
        if not self._persist_enabled or self._db_path is None:
            return
        import sqlite3 as _sqlite3
        try:
            with _sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT INTO llm_retry_queue "
                    "(timestamp, provider, system_prompt, user_prompt, model, "
                    "last_error, retry_count, max_retries, retention_hrs) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (req.timestamp, req.provider, req.system_prompt, req.user_prompt,
                     req.model, req.last_error, req.retry_count,
                     req.max_total_retries, req.retention_hours),
                )
                conn.commit()
        except Exception as e:
            print(f"  ⚠️ [RetryQueue] 持久化寫入失敗: {e}")

    def enqueue(
        self,
        provider: str,
        system_prompt: str,
        user_prompt: str,
        model: str,
        error: Exception,
    ) -> None:
        """失敗請求入隊（執行緒安全）；若 LLM_RETRY_PERSIST=true 同步寫入 SQLite"""
        req = FailedLLMRequest(
            provider=provider,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            last_error=str(error)[:500],
        )
        with self._lock:
            self._queue.append(req)
        self._persist_to_db(req)  # v15.11 P2#9
        print(f"  📥 [RetryQueue] 請求已入隊 (provider={provider}, queue_size={len(self._queue)})")

    def batch_retry(self, providers: List[str] = None) -> Dict[str, Any]:
        """
        背景重試所有佇列中的請求。
        
        Args:
            providers: 重試時使用的 provider 順序（預設 ["zhipu", "minimax", "gemini"]）
        
        Returns:
            {"succeeded": N, "failed": N, "expired": N, "details": [...]}
        """
        if providers is None:
            providers = ["zhipu", "minimax", "gemini"]

        results = {"succeeded": 0, "failed": 0, "expired": 0, "details": []}
        now = time.time()

        with self._lock:
            pending = list(self._queue)
            self._queue.clear()

        for req in pending:
            # 檢查是否過期
            if (now - req.timestamp) > (req.retention_hours * 3600):
                results["expired"] += 1
                results["details"].append({
                    "status": "expired",
                    "provider": req.provider,
                    "age_hours": (now - req.timestamp) / 3600,
                    "last_error": req.last_error,
                })
                print(f"  ⏰ [RetryQueue] 請求過期丟棄 (age={(now - req.timestamp)/3600:.1f}h)")
                continue

            # 嘗試重試
            success = False
            for fallback_provider in providers:
                try:
                    result = generate_structured_json(
                        system_prompt=req.system_prompt,
                        user_prompt=req.user_prompt,
                        provider=fallback_provider,
                        model=req.model,
                        max_retries=2,
                    )
                    if result:
                        results["succeeded"] += 1
                        results["details"].append({
                            "status": "recovered",
                            "original_provider": req.provider,
                            "recovery_provider": fallback_provider,
                        })
                        print(f"  ✅ [RetryQueue] 重試成功 ({req.provider} → {fallback_provider})")
                        success = True
                        if req.callback_on_success:
                            try:
                                req.callback_on_success(result)
                            except Exception:
                                pass
                        break
                except Exception as e:
                    req.last_error = str(e)[:500]
                    continue

            if not success:
                req.retry_count += 1
                if req.retry_count < req.max_total_retries:
                    # 尚未達上限，重新入隊
                    with self._lock:
                        self._queue.append(req)
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "status": "permanent_failure",
                        "provider": req.provider,
                        "retry_count": req.retry_count,
                        "last_error": req.last_error,
                    })
                    print(f"  ❌ [RetryQueue] 最終失敗 ({req.provider}, retries={req.retry_count})")

        return results

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()


# 全局重試佇列實例（產線啟動時初始化）
_global_retry_queue: Optional[LLMRetryQueue] = None


def get_retry_queue() -> LLMRetryQueue:
    """取得全局重試佇列（延遲初始化）"""
    global _global_retry_queue
    if _global_retry_queue is None:
        _global_retry_queue = LLMRetryQueue()
    return _global_retry_queue


def _ensure_gemini_configured() -> None:
    """
    確保 Gemini API 已用 GEMINI_API_KEY 完成初始化（單次執行）。
    【v15.3 修復】將 google.generativeai import 移至此處（lazy import），
    避免 zhipu 路徑觸發廢棄套件警告，也防止套件版本不相容時崩潰影響其他功能。
    """
    global _gemini_configured, _genai
    if _gemini_configured:
        return

    try:
        import google.generativeai as genai_mod
        _genai = genai_mod
    except ImportError:
        raise ImportError(
            "❌ 缺少 google-generativeai 套件。"
            "請執行: pip install google-generativeai"
        )

    api_key = config.GEMINI_API_KEY
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY 環境變數未在 .env 中設定。\n"
            "請檢查 WORKSPACE_ROOT/.env 是否包含有效的 GEMINI_API_KEY。"
        )
    _genai.configure(api_key=api_key)
    _gemini_configured = True


def _log_fatal_slim(error_context: str, exception: Exception) -> None:
    """
    CTO 鐵律：Log Sanitization (日誌瘦身)。
    只擷取 Exception Name 與最後一行訊息，避免污染 project_learning.md。
    """
    error_type = type(exception).__name__
    last_line = str(exception).strip().split("\n")[-1][:200]
    slim_msg = f"[{error_context}] {error_type}: {last_line}"
    print(f"⚠️ LLM Client Error: {slim_msg}")



def _generate_minimax(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_retries: int,
) -> Optional[Dict[str, Any]]:
    """
    【引擎3】MiniMax M2.7 230B MoE — NVIDIA NIM (OpenAI 相容協定)
    temperature=1.0, top_p=0.95 為官方建議最佳實踐。
    """
    api_key = config.NVIDIA_API_KEY
    if not api_key or api_key.startswith("nvapi-填入"):
        raise EnvironmentError(
            "NVIDIA_API_KEY 未設定。請至 https://build.nvidia.com/ 取得金鑰"
            "並填入 .env 中的 NVIDIA_API_KEY 欄位。"
        )
    try:
        from openai import OpenAI as _OpenAI
    except ImportError:
        raise ImportError("缺少 openai 套件，請執行: pip install openai")

    # timeout=180s：NVIDIA NIM MiniMax 230B 實測 ~100s，180s 給足安全邊際
    client = _OpenAI(
        base_url=config.NVIDIA_BASE_URL,
        api_key=api_key,
        timeout=180.0,
    )
    target_model = model or "minimaxai/minimax-m2.7"
    last_exc = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=target_model,
                messages=[
                    {"role": "system", "content": system_prompt or ""},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=1.0,
                top_p=0.95,
                max_tokens=4096,  # 從 2048 提升至 4096，確保 20 首雙語曲名不截斷
            )
            raw = response.choices[0].message.content or ""
            if not raw:
                raise Exception("MiniMax API 回傳空內容")
            return parse_llm_json_response(raw, max_retries_on_decode_error=2, log_context="MiniMax")
        except ValueError as e:
            # parse_llm_json_response 最終失敗（已內部重試）
            last_exc = e
            _log_fatal_slim("MiniMax JSON Parse", e)
            if attempt < max_retries:
                backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
                print(f"  ⚠️ MiniMax JSON 解析失敗，重試 {attempt}/{max_retries}，{backoff:.1f}s 後再試")
                time.sleep(backoff)
        except Exception as e:
            last_exc = e
            _log_fatal_slim(f"MiniMax API attempt {attempt}", e)
            if attempt < max_retries:
                backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
                print(f"  ⚠️ MiniMax API 重試 {attempt}/{max_retries}：{e}，{backoff:.1f}s 後再試")
                time.sleep(backoff)
    raise Exception(f"MiniMax API 最終失敗: {last_exc}")


def generate_structured_json(
    system_prompt: str,
    user_prompt: str,
    provider: str = "minimax",
    model: str = None,
    max_retries: int = 3,
    timeout: tuple = (30, 300)
) -> Optional[Dict[str, Any]]:
    """
    三引擎 LLM JSON 生成器
    provider: "minimax"（預設，MiniMax M2.7 230B NVIDIA NIM）| "zhipu"（智譜 GLM-4）| "gemini"（Google）
    """
    if provider == "minimax":
        return _generate_minimax(system_prompt, user_prompt, model, max_retries)

    if provider == "gemini":
        _ensure_gemini_configured()   # lazy import + configure
        target_model = model or "gemini-2.5-flash"
        gemini_model = _genai.GenerativeModel(
            model_name=target_model,
            generation_config=_genai.GenerationConfig(
                temperature=0.87,
                response_mime_type="application/json",
            ),
        )
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                response = gemini_model.generate_content(
                    f"{system_prompt}\n\n{user_prompt}",
                    request_options={"timeout": 120},
                )
                raw_content = response.text
                if not raw_content:
                    raise Exception("Gemini API 回傳空內容")
                return parse_llm_json_response(raw_content, max_retries_on_decode_error=2, log_context="Gemini")
            except ValueError as e:
                _log_fatal_slim("Gemini JSON Parse", e)
                last_exc = e
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
                    print(f"  ⚠️ Gemini API JSON 解析失敗，重試 {attempt}/{max_retries}，{backoff:.1f}s 後再試")
                    time.sleep(backoff)
                    continue
                raise Exception(f"無法解析 Gemini JSON 輸出: {e}") from e
            except Exception as e:
                last_exc = e
                _log_fatal_slim(f"Gemini API attempt {attempt}", e)
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
                    print(f"  ⚠️ Gemini API 重試 {attempt}/{max_retries}：{e}，{backoff:.1f}s 後再試")
                    time.sleep(backoff)
                    continue
                raise Exception(f"Gemini API 最終失敗: {e}") from e
        if last_exc:
            raise Exception(f"Gemini API 無回應: {last_exc}")
    else:
        # 路由到 Zhipu GLM-4
        from scripts.common.llm_client_zhipu import generate_structured_json_zhipu
        prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
        target_model = model or "glm-4"
        return generate_structured_json_zhipu(prompt, model=target_model, max_retries=max_retries)


# ============================================================================
# 【v15.10 新增】三引擎全回退 + 重試佇列安全網
# ============================================================================

_FALLBACK_CHAIN = ["minimax", "zhipu", "gemini"]


def generate_with_full_fallback(
    system_prompt: str,
    user_prompt: str,
    model: str = None,
    max_retries_per_engine: int = 3,
    use_retry_queue: bool = True,
) -> Dict[str, Any]:
    """
    【v15.10】三引擎全回退 + 重試佇列安全網。
    
    嘗試鏈：MiniMax → Zhipu → Gemini → 重試佇列
    
    Args:
        system_prompt: 系統提示詞
        user_prompt: 使用者提示詞
        model: 模型名稱（None 時使用各引擎預設值）
        max_retries_per_engine: 每個引擎最大重試次數
        use_retry_queue: 全失敗時是否入隊重試佇列
    
    Returns:
        Dict[str, Any]: 解析後的 JSON
    
    Raises:
        Exception: 三引擎全失敗且重試佇列停用時
    """
    last_error = None
    
    for provider in _FALLBACK_CHAIN:
        try:
            result = generate_structured_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                provider=provider,
                model=model,
                max_retries=max_retries_per_engine,
            )
            if result:
                print(f"  ✅ [Fallback] 成功 (provider={provider})")
                return result
        except Exception as e:
            last_error = e
            print(f"  ⚠️ [Fallback] {provider} 失敗: {type(e).__name__}")
            continue

    # 三引擎全失敗 → 重試佇列
    if use_retry_queue:
        queue = get_retry_queue()
        queue.enqueue(
            provider=_FALLBACK_CHAIN[0],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model or "",
            error=last_error or Exception("Unknown"),
        )
        raise Exception(
            f"三引擎全失敗，請求已入重試佇列 (queue_size={queue.size})。"
            f"最後錯誤: {last_error}"
        )

    raise Exception(f"三引擎全失敗 (重試佇列已停用): {last_error}")