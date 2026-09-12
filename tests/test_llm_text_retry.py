"""Offline tests for the llm_text retry/backoff logic (no network, fake OpenAI client)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.story_room import llm_text  # noqa: E402


def test_retryable_classifies_transient_failures():
    assert llm_text._retryable(RuntimeError("HTTP 429 Too Many Requests"))
    assert llm_text._retryable(RuntimeError("deepseek timeout"))
    assert llm_text._retryable(RuntimeError("DeepSeek returned empty content"))
    assert llm_text._retryable(RuntimeError("connection reset by peer"))


def test_retryable_rejects_fatal_failures():
    assert not llm_text._retryable(RuntimeError("invalid api key"))
    assert not llm_text._retryable(RuntimeError("model not found"))


class _Resp:
    def __init__(self, content):
        msg = type("M", (), {"content": content})
        self.choices = [type("C", (), {"message": msg()})()]


def _install_fake_openai(monkeypatch, script):
    """Patch openai.OpenAI with a fake replaying ``script`` (strs or Exceptions).

    The last script entry is reused once exhausted; returns a call counter.
    """
    counter = {"calls": 0}
    import openai

    class _Completions:
        def create(self, **kwargs):
            item = script[min(counter["calls"], len(script) - 1)]
            counter["calls"] += 1
            if isinstance(item, Exception):
                raise item
            return _Resp(item)

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(llm_text, "_api_key", lambda: "test-key")
    return counter


def test_deepseek_chat_retries_transient_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    counter = _install_fake_openai(monkeypatch, [RuntimeError("HTTP 429 rate limit"), "ok"])
    out = llm_text.deepseek_chat("sys", "user")
    assert out == "ok"
    assert counter["calls"] == 2
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 30


def test_deepseek_chat_fatal_error_raises_immediately(monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    counter = _install_fake_openai(monkeypatch, [RuntimeError("invalid api key")])
    with pytest.raises(RuntimeError, match="invalid api key"):
        llm_text.deepseek_chat("sys", "user")
    assert counter["calls"] == 1 and not sleeps


def test_deepseek_chat_exhausts_retries_then_raises(monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    counter = _install_fake_openai(monkeypatch, [RuntimeError("HTTP 503 overloaded")])
    with pytest.raises(RuntimeError, match="503"):
        llm_text.deepseek_chat("sys", "user")
    assert counter["calls"] == 3
    assert len(sleeps) == 2


def test_deepseek_chat_retries_empty_content(monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    counter = _install_fake_openai(monkeypatch, ["", "recovered"])
    out = llm_text.deepseek_chat("sys", "user")
    assert out == "recovered"
    assert counter["calls"] == 2
