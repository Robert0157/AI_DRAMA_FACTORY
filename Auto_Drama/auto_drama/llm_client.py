# -*- coding: utf-8 -*-
"""
DeepSeek-R1 direct LLM client (OpenAI-compatible /chat/completions).

Used by Stage 1 for: classical Chinese -> vernacular 3-act drama -> storyboard
JSON. Responses MUST go through json_clean.clean_llm_json (triple cleaning).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

from .json_clean import clean_llm_json


class LlmError(RuntimeError):
    """Raised when the text model fails."""


class DeepSeekClient:
    """Minimal OpenAI-compatible chat client for DeepSeek-R1."""

    DEFAULT_BASE = "https://api.deepseek.com"
    DEFAULT_MODEL = "deepseek-reasoner"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE,
                 model: str = DEFAULT_MODEL, temperature: float = 0.7) -> None:
        if requests is None:
            raise LlmError("requests package is required for live mode")
        if not api_key:
            raise LlmError("DeepSeekClient: DEEPSEEK_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature

    def chat(self, system: str, user: str, temperature: Optional[float] = None,
             max_tokens: int = 16384) -> str:
        """Single-shot chat call; returns assistant text content."""
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(
            url, json=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=300,
        )
        if resp.status_code >= 400:
            raise LlmError(f"DeepSeek HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError(f"DeepSeek unexpected payload: {str(data)[:500]}") from exc

    def chat_json(self, system: str, user: str, temperature: Optional[float] = None) -> Any:
        """Chat then triple-clean the response into a JSON object/array."""
        text = self.chat(system, user, temperature=temperature)
        return clean_llm_json(text)
