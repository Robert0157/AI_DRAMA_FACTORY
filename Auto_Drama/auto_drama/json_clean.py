# -*- coding: utf-8 -*-
"""
LLM JSON triple-cleaning utilities (mirrors llm_client._clean_json_response()).

Pipeline rule: never call json.loads() directly on raw LLM output. Always run
through clean_llm_json() first.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional


def strip_markdown_fences(raw: str) -> str:
    """Remove ```json ... ``` fences and surrounding prose."""
    s = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, flags=re.S | re.I)
    if fence:
        return fence.group(1).strip()
    # Some models only prepend a language tag line.
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _extract_json_candidate(raw: str) -> Optional[str]:
    """Find the outermost JSON array or object inside noisy text."""
    s = raw.strip()
    # Prefer balanced scanning from first structural character.
    start = None
    for i, ch in enumerate(s):
        if ch in "[{":
            start = i
            break
    if start is None:
        return None
    opener = s[start]
    closer = "]" if opener == "[" else "}"
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    # Never closed: return the unbalanced tail so repair_truncated_array can fix it.
    return s[start:]


def repair_truncated_array(raw: str) -> str:
    """Best-effort repair of a truncated JSON array by closing open objects."""
    s = raw.rstrip()
    # Drop a trailing unclosed object/array.
    # Close all open string values first (rare) then balance brackets.
    depth_obj = 0
    depth_arr = 0
    in_str = False
    escape = False
    out = []
    for ch in s:
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth_obj += 1
        elif ch == "}":
            depth_obj = max(0, depth_obj - 1)
        elif ch == "[":
            depth_arr += 1
        elif ch == "]":
            depth_arr = max(0, depth_arr - 1)
        out.append(ch)
    # Close inner-most constructs first: object braces, then the array bracket.
    tail = "}" * depth_obj + "]" * depth_arr
    return "".join(out) + tail


def clean_llm_json(raw: str) -> Any:
    """
    Triple cleaning pipeline:
      1. Strip markdown fences / prose.
      2. Extract the outermost JSON candidate.
      3. On parse failure, repair a truncated array and retry once.
    Raises ValueError when no valid JSON can be recovered.
    """
    if raw is None:
        raise ValueError("clean_llm_json: input is None")
    step1 = strip_markdown_fences(raw)
    candidate = _extract_json_candidate(step1)
    if candidate is None:
        raise ValueError("clean_llm_json: no JSON array/object found in response")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = repair_truncated_array(candidate)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise ValueError(f"clean_llm_json: unrecoverable JSON after repair: {exc}") from exc
