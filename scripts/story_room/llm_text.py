"""Free-text LLM channel for the Story Room (DeepSeek official API).

Kept separate from scripts/common/llm_client.py because that client is
JSON-only; the writer/critic loop needs prose + JSON both.

Rules:
- Never hardcode drive letters: the workspace root is derived from __file__
  and the .env is loaded from there.
- Fail loudly with actionable messages (ZERO SILENT FAILURES).
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_ENV_LOADED = False


def _load_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(_WORKSPACE_ROOT / ".env")
    except Exception:
        pass  # env may already be provided by the caller
    _ENV_LOADED = True


def _api_key() -> str:
    _load_env()
    # New name first, legacy name second (see copilot-instructions env list).
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DeepSeek_API") or ""


def available() -> bool:
    """True when a DeepSeek key is present (no network call performed)."""
    return bool(_api_key())


_RETRY_MARKERS = ("429", "500", "502", "503", "504", "timeout", "timed out",
                  "empty content", "connection", "rate limit")


def _retryable(exc: Exception) -> bool:
    """Transient failures worth a backoff-retry (rate limits / 5xx / timeout / empty)."""
    text = (str(exc) + " " + type(exc).__name__).lower()
    return any(m in text for m in _RETRY_MARKERS)


def deepseek_chat(
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 1.0,
    timeout: float = 240.0,
    thinking: bool = False,
) -> str:
    """One chat completion with exponential backoff (transient-only).

    Retries <=3 times on 429/5xx/timeout/empty-content, sleeping 2^n + jitter
    capped at 30s. Raises on fatal errors or after retries are exhausted.
    """
    key = _api_key()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY / DeepSeek_API not found in .env")
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("openai package missing: pip install openai") from exc

    base = os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    client = OpenAI(base_url=base, api_key=key, timeout=timeout)
    payload = dict(
        model=model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-v4-flash",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        top_p=0.95,
        max_tokens=max_tokens,
        extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}},  # JSON/prose straight out
    )
    retries = max(1, int(os.environ.get("DEEPSEEK_RETRIES", "3")))
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(**payload)
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise RuntimeError("DeepSeek returned empty content")
            return text
        except Exception as exc:  # noqa: BLE001 - retry transient, raise fatal immediately
            last_exc = exc
            if attempt >= retries - 1 or not _retryable(exc):
                raise
            delay = min(2.0 ** attempt + random.uniform(0, 1), 30.0)
            print(f"[warn] deepseek_chat retry {attempt + 1}/{retries} in {delay:.1f}s: {str(exc)[:120]}",
                  file=sys.stderr, flush=True)
            time.sleep(delay)
    raise last_exc if last_exc else RuntimeError("DeepSeek chat failed")


def extract_json(text: str) -> dict:
    """Best-effort JSON extraction from an LLM reply (fences + prose tolerant)."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Find the first balanced {...} block.
    start = cleaned.find("{")
    if start >= 0:
        depth = 0
        for i, ch in enumerate(cleaned[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"no valid JSON object found in reply (head: {text[:120]!r})")
