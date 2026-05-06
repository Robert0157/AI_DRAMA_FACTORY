#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mac watcher for shorts audio sidecar signals.

Default watch roots:
- /Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/light_music/.signal.json
- /Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/lofi/.signal.json

Behavior:
- Poll signal files every N seconds
- Deduplicate by (channel, batch_id)
- Execute a placeholder handler when there are effective changes
- Write .ack.json after handling each batch
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

DEFAULT_BASE = Path("/Volumes/AI_Workspace/AI_Drama_Factory/Short_audio")
DEFAULT_CHANNELS = ("light_music", "lofi")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: Path) -> Dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"[{_now()}] [WARN] JSON parse failed: {path} :: {e}")
        return None


def _save_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _load_state(path: Path) -> Dict[str, str]:
    data = _load_json(path)
    if not isinstance(data, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out


def _write_ack(channel_dir: Path, signal: Dict[str, Any], status: str, detail: str) -> None:
    ack_path = channel_dir / ".ack.json"
    payload = {
        "schema_version": "shorts-ack-v1",
        "batch_id": str(signal.get("batch_id", "")),
        "channel": str(signal.get("channel", channel_dir.name)),
        "handled_at": _now(),
        "status": status,
        "detail": detail,
        "signal_timestamp": str(signal.get("timestamp", "")),
    }
    _save_json_atomic(ack_path, payload)


def _has_effective_changes(signal: Dict[str, Any]) -> bool:
    stats = signal.get("stats", {}) if isinstance(signal.get("stats"), dict) else {}
    moved = int(stats.get("moved", 0) or 0)
    deleted = int(stats.get("deleted", 0) or 0)
    missing = int(stats.get("missing", 0) or 0)
    return (moved + deleted + missing) > 0


def _handle_batch(channel: str, signal: Dict[str, Any], dry_run: bool) -> str:
    """
    Placeholder for Mac side business logic.
    Replace this with upload/sync/indexing logic as needed.
    """
    stats = signal.get("stats", {})
    msg = (
        f"channel={channel}, batch_id={signal.get('batch_id')}, "
        f"moved={stats.get('moved', 0)}, deleted={stats.get('deleted', 0)}, "
        f"missing={stats.get('missing', 0)}"
    )
    if dry_run:
        print(f"[{_now()}] [DRYRUN] handle_batch: {msg}")
    else:
        print(f"[{_now()}] [EXEC] handle_batch: {msg}")
        # TODO: integrate real Mac workflow here.
    return msg


def process_signals_once(
    *,
    base_dir: Path,
    channels: tuple[str, ...],
    state_path: Path,
    dry_run: bool,
) -> int:
    state = _load_state(state_path)
    processed = 0

    for channel in channels:
        channel_dir = base_dir / channel
        signal_path = channel_dir / ".signal.json"

        signal = _load_json(signal_path)
        if not signal:
            continue

        batch_id = str(signal.get("batch_id", "")).strip()
        if not batch_id:
            print(f"[{_now()}] [WARN] Missing batch_id: {signal_path}")
            continue

        key = f"{channel}:last_batch_id"
        if state.get(key) == batch_id:
            continue

        if not _has_effective_changes(signal):
            _write_ack(channel_dir, signal, "skipped", "No effective changes in stats.")
            state[key] = batch_id
            processed += 1
            continue

        try:
            detail = _handle_batch(channel, signal, dry_run=dry_run)
            _write_ack(channel_dir, signal, "ok", detail)
            state[key] = batch_id
            processed += 1
        except Exception as e:
            _write_ack(channel_dir, signal, "error", str(e))
            print(f"[{_now()}] [ERROR] Handling failed: channel={channel}, batch_id={batch_id}, err={e}")

    _save_json_atomic(state_path, state)
    return processed


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch shorts audio sidecar signals on Mac mini.")
    parser.add_argument(
        "--base-dir",
        default=str(DEFAULT_BASE),
        help="Base dir of mounted shorts audio root.",
    )
    parser.add_argument(
        "--channels",
        default="light_music,lofi",
        help="Comma-separated channels to watch.",
    )
    parser.add_argument(
        "--interval-sec",
        type=int,
        default=15,
        help="Polling interval in seconds.",
    )
    parser.add_argument(
        "--state-path",
        default=str(DEFAULT_BASE / ".watcher_state.json"),
        help="Path to watcher dedupe state file.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scan only, then exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not execute real side effects in handler.",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    channels = tuple(c.strip() for c in args.channels.split(",") if c.strip())
    state_path = Path(args.state_path)
    interval_sec = max(3, int(args.interval_sec))

    if not channels:
        print("No channels specified.")
        return 2

    print(f"[{_now()}] Start watcher. base_dir={base_dir}, channels={channels}, interval={interval_sec}s")

    if args.once:
        n = process_signals_once(
            base_dir=base_dir,
            channels=channels,
            state_path=state_path,
            dry_run=args.dry_run,
        )
        print(f"[{_now()}] One-shot done. processed={n}")
        return 0

    while True:
        n = process_signals_once(
            base_dir=base_dir,
            channels=channels,
            state_path=state_path,
            dry_run=args.dry_run,
        )
        if n > 0:
            print(f"[{_now()}] Processed batches: {n}")
        time.sleep(interval_sec)


if __name__ == "__main__":
    sys.exit(main())
