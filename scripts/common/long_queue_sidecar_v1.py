#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Long_Queue sidecar — schema `long-upload-v1`（Mac 端介接）+ preflight 驗證。

與工程規格一致：寫入 .json 前必須通過 validate，失敗則不應產生觸發訊號（fail-closed）。
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

SCHEMA_VERSION = "long-upload-v1"
VALID_PRIVACY = frozenset({"public", "unlisted", "private"})
DEFAULT_SOURCE_SYSTEM = "AI_DRAMA_FACTORY_WINDOWS"


def _created_at_iso() -> str:
    """發行當下 Asia/Taipei 時間 + 16 小時，ISO8601（邊車 `created_at`）。"""
    try:
        from zoneinfo import ZoneInfo

        dt = datetime.now(ZoneInfo("Asia/Taipei")) + timedelta(hours=16)
        return dt.isoformat()
    except Exception:
        # 無 zoneinfo 時以固定 UTC+8 代表台北，再 +16h
        tz_tpe = timezone(timedelta(hours=8))
        dt = datetime.now(tz_tpe) + timedelta(hours=16)
        return dt.isoformat()


def build_long_upload_sidecar_v1(
    *,
    mp4_filename: str,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    category_id: str = "10",
    mode_auto: bool = True,
    contains_synthetic_media: bool = True,
    self_declared_made_for_kids: bool = False,
    playlist_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    source_system: str = DEFAULT_SOURCE_SYSTEM,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    組出 long-upload-v1 邊車本體。

    R&S 政策（YouTube）：
    - `containsSyntheticMedia`：變造／合成內容申報為「是」→ 固定為 True。
    - `selfDeclaredMadeForKids`：本頻道非兒童導向 → 固定為 False。

    額外保留 `privacyStatus` / `auto_publish_enabled` 供舊版 Mac 讀者過渡（與 privacy 同步語意）。
    """
    if created_at is None:
        created_at = _created_at_iso()
    if not idempotency_key:
        idempotency_key = f"winjob-{uuid.uuid4().hex[:16]}"

    out: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "video_file": mp4_filename,
        "title": (title or "").strip(),
        "description": description if isinstance(description, str) else "",
        "privacy": privacy,
        "categoryId": str(category_id),
        "tags": list(tags),
        "notifySubscribers": bool(mode_auto),
        "idempotency_key": idempotency_key,
        "source_system": source_system,
        "created_at": created_at,
        # 過渡／內部旗標 + YouTube 合規（合成內容／兒童導向）
        "auto_publish_enabled": bool(mode_auto),
        "containsSyntheticMedia": bool(contains_synthetic_media),
        "selfDeclaredMadeForKids": bool(self_declared_made_for_kids),
        "privacyStatus": privacy,
    }
    if playlist_id and str(playlist_id).strip():
        out["playlistId"] = str(playlist_id).strip()
    return out


def validate_long_upload_v1(body: Any, mp4_basename: str) -> Tuple[bool, str]:
    """
    通過回傳 (True, "")；失敗回傳 (False, 原因短碼訊息)。
    """
    if not isinstance(body, dict):
        return False, "payload 必須為 JSON object"

    if body.get("schema_version") != SCHEMA_VERSION:
        return False, f"schema_version 必須為 {SCHEMA_VERSION!r}"

    vf = body.get("video_file")
    if not isinstance(vf, str) or vf != mp4_basename:
        return False, f"video_file 必須與實體 MP4 檔名一致（期望 {mp4_basename!r}，實際 {vf!r}）"

    for key in ("title", "description", "privacy", "categoryId"):
        v = body.get(key)
        if not isinstance(v, str) or not v.strip():
            return False, f"必填欄位缺漏或空字串: {key}"

    if body["privacy"] not in VALID_PRIVACY:
        return False, "privacy 僅能為 public | unlisted | private"

    cid_raw = body.get("categoryId", "")
    if not isinstance(cid_raw, str) or not re.fullmatch(r"\d+", cid_raw.strip()):
        return False, "categoryId 必須為字串數字（如 10）"

    tags = body.get("tags")
    if tags is not None:
        if not isinstance(tags, list):
            return False, "tags 若提供必須為陣列"
        for t in tags:
            if not isinstance(t, str):
                return False, "tags 內每項必須為字串"

    n = body.get("notifySubscribers")
    if n is not None and not isinstance(n, bool):
        return False, "notifySubscribers 若提供必須為布林"

    pl = body.get("playlistId")
    if pl is not None and (not isinstance(pl, str) or not pl.strip()):
        return False, "playlistId 若提供必須為非空字串"

    syn = body.get("containsSyntheticMedia")
    if syn is not True:
        return False, "containsSyntheticMedia 必須為 true（變造／合成內容須申報為是）"

    kids = body.get("selfDeclaredMadeForKids")
    if kids is not False:
        return False, "selfDeclaredMadeForKids 必須為 false（非兒童導向影片）"

    return True, ""
