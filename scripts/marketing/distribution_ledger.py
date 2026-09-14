#!/usr/bin/env python3
"""Unified distribution ledger for the AI video/audio factory.

Two upload systems currently write history in different shapes:
  - Shorts: Shorts_Queue/{channel}/upload_history.jsonl   (ts, status, video_id, file, title, ...)
  - Long:   Long_Queue/{channel}/long_upload_history.jsonl (ts, status, sha256, video_id, file, title, mode)

This tool merges both into ONE ledger (JSONL) and runs a cadence check
(expected uploads vs. actual, staleness) against configs/market_validation_policy.json.
Runs on PC (reads the Y: share) or on Mac (reads /Volumes/... directly).
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = REPO_ROOT / "configs" / "market_validation_policy.json"
DEFAULT_LEDGER = REPO_ROOT / "assets" / "data" / "distribution_ledger.jsonl"


def resolve_mac_root(explicit: str | None = None) -> Path:
    """Locate the Mac workspace tree (Y:/AI_Drama_Factory from Windows, /Volumes/... on macOS)."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("AI_DRAMA_MAC_ROOT")
    if env:
        candidates.append(Path(env))
    candidates.append(Path("/Volumes/AI_Workspace/AI_Drama_Factory"))
    candidates.append(Path("Y:/AI_Drama_Factory"))
    for cand in candidates:
        try:
            if cand.is_dir() and (cand / "Shorts_Queue").is_dir():
                return cand
        except OSError:
            continue
    for cand in candidates:
        try:
            if cand.is_dir():
                return cand
        except OSError:
            continue
    return candidates[-1]


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read a JSONL file; return (records, bad_line_count). Missing file -> ([], 0)."""
    records: list[dict[str, Any]] = []
    bad = 0
    if not path.is_file():
        return records, bad
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return records, bad
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(obj, dict):
            records.append(obj)
        else:
            bad += 1
    return records, bad


def _entry(channel: str, kind: str, source: str, rec: dict[str, Any]) -> dict[str, Any]:
    """Normalize one history record into a ledger entry."""
    return {
        "channel": channel,
        "kind": kind,
        "source": source,
        "ts": str(rec.get("ts", "")),
        "status": str(rec.get("status", "")),
        "video_id": str(rec.get("video_id", "") or ""),
        "file": str(rec.get("file", "") or ""),
        "title": str(rec.get("title", "") or ""),
    }


def collect_entries(mac_root: Path, channels: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Merge shorts + long histories from the Mac tree into one entry list."""
    entries: list[dict[str, Any]] = []
    bad_lines = {"shorts": 0, "long": 0}
    shorts_root = mac_root / "Shorts_Queue"
    long_root = mac_root / "Long_Queue"
    # Discover channels from disk; caller-provided list is merged in as well.
    found: set[str] = set(channels or [])
    try:
        for sub in shorts_root.iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                found.add(sub.name)
    except OSError:
        pass
    try:
        for sub in long_root.iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                found.add(sub.name)
    except OSError:
        pass

    for channel in sorted(found):
        recs, bad = _read_jsonl(shorts_root / channel / "upload_history.jsonl")
        bad_lines["shorts"] += bad
        entries.extend(_entry(channel, "short", "shorts_queue", r) for r in recs)
        recs, bad = _read_jsonl(long_root / channel / "long_upload_history.jsonl")
        bad_lines["long"] += bad
        entries.extend(_entry(channel, "long", "long_queue", r) for r in recs)

    entries.sort(key=lambda e: e.get("ts", ""))
    return entries, bad_lines


def _parse_ts(raw: str) -> datetime | None:
    """Best-effort ISO8601 parser (handles +0800 and Z)."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19] + (text[19:] if "%z" in fmt else ""), fmt)
            except ValueError:
                continue
    return None


def cadence_report(
    entries: list[dict[str, Any]], policy: dict[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    """Expected-vs-actual upload cadence per channel + staleness alerts."""
    now = now or datetime.now(timezone.utc)
    cadence_cfg = policy.get("cadence", {})
    lookback_days = int(cadence_cfg.get("lookback_days", 14))
    stale_hours = float(cadence_cfg.get("stale_after_hours", 48))
    ratio = float(cadence_cfg.get("under_cadence_ratio", 0.6))
    channels_cfg: dict[str, Any] = cadence_cfg.get("channels", {})

    window_start = now - timedelta(days=lookback_days)
    per_channel: dict[str, Any] = {}
    alerts: list[str] = []

    known = set(channels_cfg.keys()) | {e["channel"] for e in entries}
    for channel in sorted(known):
        cfg = channels_cfg.get(channel, {})
        if cfg.get("enabled") is False and channel not in {e["channel"] for e in entries}:
            per_channel[channel] = {"enabled": False, "note": cfg.get("note", "")}
            continue
        ch_entries = [e for e in entries if e["channel"] == channel and e.get("status") == "success"]
        recent = 0
        last_ts: datetime | None = None
        for e in ch_entries:
            dt = _parse_ts(str(e.get("ts", "")))
            if dt is None:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= window_start:
                recent += 1
            if last_ts is None or dt > last_ts:
                last_ts = dt
        age_hours = None if last_ts is None else (now - last_ts).total_seconds() / 3600.0
        expected = float(cfg.get("expected_per_day", 0.0) or 0.0) * lookback_days
        info = {
            "kind": cfg.get("kind", "short"),
            "enabled": cfg.get("enabled", True),
            "expected_14d": round(expected, 1),
            "actual_14d": recent,
            "last_ts": "" if last_ts is None else last_ts.isoformat(),
            "age_hours": None if age_hours is None else round(age_hours, 1),
            "alerts": [],
        }
        if info["enabled"]:
            if age_hours is None:
                info["alerts"].append("no-successful-uploads")
                alerts.append(f"{channel}: no successful uploads on record")
            elif age_hours > stale_hours:
                info["alerts"].append("stale")
                alerts.append(f"{channel}: last upload {info['age_hours']}h ago (> {stale_hours:g}h)")
            if expected > 0 and recent < expected * ratio:
                info["alerts"].append("under-cadence")
                alerts.append(f"{channel}: {recent}/{round(expected,1)} uploads in {lookback_days}d (under cadence)")
        per_channel[channel] = info
    return {"generated": now.isoformat(), "lookback_days": lookback_days, "channels": per_channel, "alerts": alerts}


def write_ledger(path: Path, entries: list[dict[str, Any]]) -> None:
    """Atomic JSONL write (temp file + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Mac workspace root (auto-detected when omitted)")
    parser.add_argument("--out", help=f"ledger output path (default: {DEFAULT_LEDGER})")
    parser.add_argument("--policy", help=f"policy file (default: {DEFAULT_POLICY})")
    parser.add_argument("--check", action="store_true", help="print cadence report")
    args = parser.parse_args(argv)

    mac_root = resolve_mac_root(args.root)
    entries, bad = collect_entries(mac_root)
    out_path = Path(args.out) if args.out else DEFAULT_LEDGER
    write_ledger(out_path, entries)

    ok = sum(1 for e in entries if e.get("status") == "success")
    print(f"LEDGER entries={len(entries)} success={ok} bad_lines={bad} -> {out_path}")
    by_source: dict[str, int] = {}
    for e in entries:
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
    print(f"BY_SOURCE {by_source}")

    if args.check:
        policy_path = Path(args.policy) if args.policy else DEFAULT_POLICY
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        report = cadence_report(entries, policy)
        for channel, info in report["channels"].items():
            if not info.get("enabled", True):
                print(f"[{channel}] disabled ({info.get('note', '')})")
                continue
            print(
                f"[{channel}] actual_14d={info['actual_14d']} expected={info['expected_14d']} "
                f"last={info['last_ts'] or 'never'} age_h={info['age_hours']}"
            )
        if report["alerts"]:
            print("ALERTS:")
            for alert in report["alerts"]:
                print(f"  ! {alert}")
        else:
            print("ALERTS: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
