# -*- coding: utf-8 -*-
"""Tests for LLM JSON triple cleaning (json_clean module)."""
import pytest

from auto_drama.json_clean import clean_llm_json


def test_clean_plain_json_array():
    raw = '[{"shot_number": 1, "emotion": "suspense"}]'
    assert clean_llm_json(raw) == [{"shot_number": 1, "emotion": "suspense"}]


def test_clean_markdown_fence():
    raw = '```json\n{"episodes": []}\n```'
    assert clean_llm_json(raw) == {"episodes": []}


def test_clean_noisy_prose_before_after():
    raw = '好的，以下是分鏡結果：\n[{"a": 1}]\n希望對你有幫助。'
    assert clean_llm_json(raw) == [{"a": 1}]


def test_clean_truncated_array_repair():
    # Truncated: closing bracket missing, last object also unclosed.
    raw = '[{"shot_number": 1, "emotion": "suspense"}, {"shot_number": 2, "emotion": "sad"'
    assert clean_llm_json(raw) == [
        {"shot_number": 1, "emotion": "suspense"},
        {"shot_number": 2, "emotion": "sad"},
    ]


def test_clean_object_with_nested_string_brace():
    # A string value containing '}' must not break bracket balance.
    raw = '{"dialogue": "他說：『切勿驚慌}。』", "ok": true}'
    assert clean_llm_json(raw) == {"dialogue": "他說：『切勿驚慌}。』", "ok": True}


def test_clean_raises_when_no_json():
    with pytest.raises(ValueError):
        clean_llm_json("完全沒有 JSON 的回覆文字")
