#!/usr/bin/env python3
"""YouTube market-feedback collector (public statistics via YouTube Data API v3).

Reads the unified distribution ledger (distribution_ledger.py), fetches fresh
statistics (views / likes / comments) for every uploaded video id, and stores
timestamped snapshots in sqlite so weekly growth can be computed.

API key resolution order: --api-key > YT_DATA_API_KEY > YOUTUBE_DATA_API_KEY > GOOGLE_API_KEY
(macOS: also loads ~/Library/Application Support/AI_Drama_Factory/market_validation.env).
Without a key the collector SKIPS cleanly (exit 0) so scheduled runs stay quiet
until the CEO provisions the key.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - requests is present in both runtimes
    requests = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = REPO_ROOT / "assets" / "data" / "distribution_ledger.jsonl"
DEFAULT_DB = REPO_ROOT / "assets" / "data" / "market_feedback.db"
API_URL = "https://www.googleapis.com/youtube/v3/videos"
BATCH = 50
KEY_ENV_NAMES = ("YT_DATA_API_KEY", "YOUTUBE_DATA_API_KEY", "GOOGLE_API_KEY")
MAC_ENV_FILE = Path.home() / "Library/Application Support/AI_Drama_Factory/market_validation.env"


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE secrets (never overrides existing environment)."""
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def resolve_api_key(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for name in KEY_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def load_ledger(path: Path) -> list[dict[str, Any]]:
    """Success-only entries, de-duplicated by video_id (keeps the earliest record)."""
    if not path.is_file():
        return []
    seen: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        vid = str(obj.get("video_id", "") or "").strip()
        if not vid or obj.get("status") != "success":
            continue
        if vid not in seen:
            seen[vid] = obj
    return sorted(seen.values(), key=lambda e: str(e.get("ts", "")))


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY,
            channel TEXT, kind TEXT, title TEXT,
            published_at TEXT, first_seen_ts TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS snapshots (
            video_id TEXT, ts TEXT,
            views INTEGER, likes INTEGER, comments INTEGER
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snap_video_ts ON snapshots(video_id, ts)")
    return conn


def fetch_stats(session: Any, api_key: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    """One videos.list call for up to 50 ids; returns {video_id: stats}."""
    params = {"part": "statistics,snippet", "id": ",".join(ids), "key": api_key}
    resp = session.get(API_URL, params=params, timeout=25)
    if resp.status_code != 200:
        raise RuntimeError(f"videos.list HTTP {resp.status_code}: {resp.text[:300]}")
    payload = resp.json()
    out: dict[str, dict[str, Any]] = {}
    for item in payload.get("items", []):
        vid = str(item.get("id", ""))
        stats = item.get("statistics", {}) or {}
        snippet = item.get("snippet", {}) or {}
        out[vid] = {
            "views": int(stats.get("viewCount", 0) or 0),
            "likes": int(stats.get("likeCount", 0) or 0),
            "comments": int(stats.get("commentCount", 0) or 0),
            "title": str(snippet.get("title", "") or ""),
            "published_at": str(snippet.get("publishedAt", "") or ""),
        }
    return out


def store(conn: sqlite3.Connection, entries: list[dict[str, Any]], stats: dict[str, dict[str, Any]], ts: str) -> int:
    """Upsert video rows and append one snapshot per video."""
    updated = 0
    for entry in entries:
        vid = str(entry["video_id"])
        data = stats.get(vid)
        if not data:
            continue  # deleted/unavailable video -> keep history, no new snapshot
        conn.execute(
            """INSERT INTO videos (video_id, channel, kind, title, published_at, first_seen_ts)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                 title=excluded.title,
                 published_at=COALESCE(excluded.published_at, videos.published_at)""",
            (
                vid,
                str(entry.get("channel", "")),
                str(entry.get("kind", "")),
                data["title"] or str(entry.get("title", "")),
                data["published_at"],
                ts,
            ),
        )
        conn.execute(
            "INSERT INTO snapshots (video_id, ts, views, likes, comments) VALUES (?, ?, ?, ?, ?)",
            (vid, ts, data["views"], data["likes"], data["comments"]),
        )
        updated += 1
    conn.commit()
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", help=f"ledger jsonl (default: {DEFAULT_LEDGER})")
    parser.add_argument("--db", help=f"sqlite db (default: {DEFAULT_DB})")
    parser.add_argument("--api-key", help="YouTube Data API key (else env)")
    parser.add_argument("--limit", type=int, default=200, help="max videos per run (oldest first)")
    parser.add_argument("--dry-run", action="store_true", help="print plan only")
    args = parser.parse_args(argv)

    load_env_file(MAC_ENV_FILE)
    ledger_path = Path(args.ledger) if args.ledger else DEFAULT_LEDGER
    db_path = Path(args.db) if args.db else DEFAULT_DB
    entries = load_ledger(ledger_path)

    if not entries:
        print(f"[skip] ledger empty or missing: {ledger_path}")
        return 0

    api_key = resolve_api_key(args.api_key)
    plan_entries = entries[: max(0, args.limit)]
    if args.dry_run:
        print(f"[plan] videos={len(entries)} will_update={len(plan_entries)} batches={(len(plan_entries)+BATCH-1)//BATCH}")
        for entry in plan_entries[:5]:
            print(f"  - {entry.get('channel')} {entry.get('kind')} {entry.get('video_id')} {entry.get('title', '')[:40]}")
        return 0
    if not api_key:
        print(f"[skip] no API key ({'/'.join(KEY_ENV_NAMES)}); set market_validation.env on Mac")
        return 0
    if requests is None:
        print("[error] requests library unavailable", file=sys.stderr)
        return 1

    session = requests.Session()
    conn = open_db(db_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = 0
    failed_batches = 0
    for start in range(0, len(plan_entries), BATCH):
        batch = plan_entries[start : start + BATCH]
        ids = [str(e["video_id"]) for e in batch]
        try:
            stats = fetch_stats(session, api_key, ids)
        except Exception as exc:  # noqa: BLE001 - report, keep processing the rest
            failed_batches += 1
            print(f"[warn] batch {start // BATCH + 1} failed: {exc}", file=sys.stderr)
            continue
        updated += store(conn, batch, stats, ts)

    conn.close()
    print(f"METRICS updated={updated} total_ledger={len(entries)} failed_batches={failed_batches} db={db_path}")
    if failed_batches and updated == 0:
        return 1  # zero-silent-failure: surface total outage to scheduler/Telegram
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
