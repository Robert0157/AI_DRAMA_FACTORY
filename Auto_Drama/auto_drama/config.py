# -*- coding: utf-8 -*-
"""
Central settings loader for Auto_Drama.

Rules:
- No API keys in YAML; keys come exclusively from environment variables.
- Paths are resolved with pathlib (never hardcoded drive letters).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override dict into base dict (override wins)."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    """Typed accessor over the merged settings tree."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Fetch nested value by dotted key, e.g. 'lmd.base_url'."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def raw(self) -> Dict[str, Any]:
        return self._data


def load_settings(project_root: Path | None = None) -> Settings:
    """Load config/settings.yaml with optional env-driven overrides."""
    root = Path(project_root or _PROJECT_ROOT)
    cfg_path = root / "config" / "settings.yaml"
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    # Env overrides (never persisted into the yaml file).
    env_map = {
        "LMD_BASE_URL": "lmd.base_url",
        "AUTO_DRAMA_OUTPUT_ROOT": "output.root",
    }
    for env_key, dotted in env_map.items():
        val = os.environ.get(env_key)
        if val:
            node = data
            parts = dotted.split(".")
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = val
    return Settings(data)
