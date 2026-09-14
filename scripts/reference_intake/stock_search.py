#!/usr/bin/env python3
"""Stock-material intake for the reference library (Pexels / Pixabay / Unsplash).

2026-09-14: runs DAILY into ONE FIXED folder (assets/reference_intake/inbox);
cross-day duplicates are suppressed via the seen-assets registry under
reference_intake/_state/. See daily_intake.py for the scheduled runner.

Contract (架構說明書 v16.1 §3.4 / §4.7):
  - Pexels is the primary provider, Pixabay the fallback, Unsplash an aesthetic
    supplement. Providers without a key are skipped with a loud warning.
  - Downloads only (hotlinking is forbidden); every item gets a provenance
    record (provider / id / page / author / sha256) in the weekly manifest.
  - Queries come from configs/stock_search_queries.json and rotate
    deterministically by ISO week number, so every week proposes new material.

Usage:
  python scripts/reference_intake/stock_search.py --dry-run
  python scripts/reference_intake/stock_search.py --limit 4
  python scripts/reference_intake/stock_search.py --world 伸展台之夢 --limit 6
  python scripts/reference_intake/stock_search.py --query "fashion runway"
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

import requests  # noqa: E402

# PC writes to the Mac share so both hosts see the same intake queue (v16.1 §2.3).
SMB_INTAKE = Path("Y:/AI_Drama_Factory/assets/reference_intake/inbox")
LOCAL_INTAKE = WORKSPACE / "assets" / "reference_intake" / "inbox"
QUERY_CONFIG = WORKSPACE / "configs" / "stock_search_queries.json"

TIMEOUT = 30
THROTTLE_SEC = 0.5  # conservative pacing; exact quotas follow each provider's docs
PROVIDER_ORDER = ("pexels", "pixabay", "unsplash")


# --------------------------------------------------------------------------
# Query planning (offline, deterministic)
# --------------------------------------------------------------------------
def load_query_config(path: Path = QUERY_CONFIG) -> dict[str, Any]:
    """Load the query catalogue; a missing file is a configuration error."""
    if not path.is_file():
        raise SystemExit(f"[FATAL] query config missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _group_generic(generic: dict[str, list[str]]) -> dict[str, list[str]]:
    """Group generic labels by channel prefix ('lofi.*' / 'light_music.*')."""
    groups: dict[str, list[str]] = {}
    for name in generic:
        prefix = name.split(".", 1)[0] if "." in name else ""
        groups.setdefault(prefix, []).append(name)
    return {key: sorted(names) for key, names in groups.items()}


def build_query_plan(
    config: dict[str, Any],
    week: int | None = None,
    world: str | None = None,
    type_label: str | None = None,
    extra: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Return [(label, query)] for this week - deterministic per ISO week."""
    if week is None:
        week = dt.date.today().isocalendar().week
    plan: list[tuple[str, str]] = []

    worlds: dict[str, list[str]] = config.get("worlds") or {}
    generic: dict[str, list[str]] = config.get("generic") or {}

    if type_label:
        if type_label not in generic:
            raise SystemExit(f"[FATAL] unknown type in query config: {type_label}")
        plan.extend((type_label, q) for q in generic[type_label])
        for query in extra or []:
            plan.append(("custom", query))
        return plan

    if world:
        if world not in worlds:
            raise SystemExit(f"[FATAL] unknown world in query config: {world}")
        labels = [world]
    else:
        labels = [sorted(worlds)[week % len(sorted(worlds))]] if worlds else []
    for label in labels:
        plan.extend((label, q) for q in worlds[label])

    for names in _group_generic(generic).values():
        picked = names[week % len(names)]
        plan.extend((picked, q) for q in generic[picked])

    for query in extra or []:
        plan.append(("custom", query))
    return plan


def map_orientation(provider: str, orientation: str) -> str:
    """Canonical portrait/landscape/square -> provider-specific value."""
    table = {
        "portrait": {"pexels": "portrait", "pixabay": "vertical", "unsplash": "portrait"},
        "landscape": {"pexels": "landscape", "pixabay": "horizontal", "unsplash": "landscape"},
        "square": {"pexels": "square", "pixabay": "all", "unsplash": "squarish"},
    }
    return table.get(orientation, table["portrait"])[provider]


# --------------------------------------------------------------------------
# Provider adapters
# --------------------------------------------------------------------------
def resolve_keys() -> dict[str, str]:
    """Provider keys via secrets_manager first, then plain environment variables."""
    names = ("PEXELS_API_KEY", "PIXABAY_API_KEY", "UNSPLASH_ACCESS_KEY")
    keys: dict[str, str] = {}
    try:
        from scripts.common.secrets_manager import get_secrets

        secrets = get_secrets()
        if hasattr(secrets, "items"):  # mapping-style backend
            keys.update({str(k): str(v) for k, v in secrets.items() if v})
        else:  # SecretsManager exposes per-key lookups instead of a mapping
            for name in names:
                value = secrets.get(name) if hasattr(secrets, "get") else None
                if value:
                    keys[name] = str(value)
    except Exception as exc:  # noqa: BLE001 - env fallback is the documented path
        print(f"[warn] secrets_manager unavailable ({exc}); using environment only", file=sys.stderr)
    for name in names:
        if not keys.get(name) and os.getenv(name):
            keys[name] = os.environ[name]
    return keys


def _search_pexels(session: requests.Session, query: str, orientation: str, limit: int, key: str) -> list[dict[str, Any]]:
    resp = session.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "orientation": orientation, "per_page": limit},
        headers={"Authorization": key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    items = []
    for photo in (resp.json().get("photos") or [])[:limit]:
        src = photo.get("src") or {}
        items.append({
            "provider": "pexels",
            "id": photo.get("id"),
            "page_url": photo.get("url"),
            "download_url": src.get("large2x") or src.get("original"),
            "author": photo.get("photographer"),
        })
    return items


def _search_pixabay(session: requests.Session, query: str, orientation: str, limit: int, key: str) -> list[dict[str, Any]]:
    resp = session.get(
        "https://pixabay.com/api/",
        params={
            "key": key,
            "q": query,
            "image_type": "photo",
            "orientation": orientation,
            "per_page": max(3, limit),  # Pixabay requires per_page >= 3
            "safesearch": "true",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    items = []
    for hit in (resp.json().get("hits") or [])[:limit]:
        items.append({
            "provider": "pixabay",
            "id": hit.get("id"),
            "page_url": hit.get("pageURL"),
            "download_url": hit.get("largeImageURL"),
            "author": hit.get("user"),
        })
    return items


def _search_unsplash(session: requests.Session, query: str, orientation: str, limit: int, key: str) -> list[dict[str, Any]]:
    resp = session.get(
        "https://api.unsplash.com/search/photos",
        params={"query": query, "orientation": orientation, "per_page": limit},
        headers={"Authorization": f"Client-ID {key}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    items = []
    for photo in (resp.json().get("results") or [])[:limit]:
        items.append({
            "provider": "unsplash",
            "id": photo.get("id"),
            "page_url": (photo.get("links") or {}).get("html"),
            "download_url": (photo.get("urls") or {}).get("regular"),
            "author": (photo.get("user") or {}).get("name"),
        })
    return items


PROVIDERS = {
    "pexels": ("PEXELS_API_KEY", _search_pexels),
    "pixabay": ("PIXABAY_API_KEY", _search_pixabay),
    "unsplash": ("UNSPLASH_ACCESS_KEY", _search_unsplash),
}


def load_seen(state_path: Path) -> dict[str, set[str]]:
    """Previously downloaded provider ids (cross-day duplicate suppression)."""
    if not state_path.is_file():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {key: {str(x) for x in values} for key, values in (payload.get("seen") or {}).items()}


def save_seen(state_path: Path, seen: dict[str, set[str]]) -> None:
    """Persist the seen registry atomically (survives daily inbox purges)."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "reference_intake.seen.v1",
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
        "seen": {key: sorted(values) for key, values in seen.items()},
    }
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, state_path)


def download_item(session: requests.Session, item: dict[str, Any], target_dir: Path) -> dict[str, Any]:
    """Download one provider item; the provenance record feeds the manifest."""
    url = item.get("download_url")
    if not url:
        raise RuntimeError(f"{item.get('provider')}#{item.get('id')} has no download url")
    resp = session.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    filename = f"{item['provider']}_{item['id']}.jpg"  # photo endpoints all serve JPEG
    (target_dir / filename).write_bytes(resp.content)
    return {
        "provider": item.get("provider"),
        "id": item.get("id"),
        "page_url": item.get("page_url"),
        "author": item.get("author"),
        "file": filename,
        "sha256": hashlib.sha256(resp.content).hexdigest(),
        "bytes": len(resp.content),
        "license": "provider license: free for commercial use, attribution not required (kept for audit)",
    }


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", default=[], help="extra query (repeatable)")
    parser.add_argument("--world", help="restrict to one world key from the query config")
    parser.add_argument(
        "--type",
        dest="type_label",
        help="restrict to one generic type label (e.g. lofi.dream_objects / light_music.water_light)",
    )
    parser.add_argument("--week", type=int, help="ISO week override for the rotation")
    parser.add_argument("--provider", choices=[*PROVIDER_ORDER, "auto"], default="auto")
    parser.add_argument("--orientation", choices=["portrait", "landscape", "square"], default="portrait")
    parser.add_argument("--limit", type=int, default=4, help="items per query per provider")
    parser.add_argument("--out", help="output root (defaults to the Y: share, then local intake)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; no network calls")
    args = parser.parse_args()

    config = load_query_config()
    plan = build_query_plan(
        config, week=args.week, world=args.world, type_label=args.type_label, extra=args.query
    )
    if not plan:
        print("[FATAL] nothing to search: query plan is empty", file=sys.stderr)
        return 1

    keys = resolve_keys()
    if args.provider == "auto":
        order = [p for p in PROVIDER_ORDER if keys.get(PROVIDERS[p][0])]
    else:
        order = [args.provider] if keys.get(PROVIDERS[args.provider][0]) else []

    if args.dry_run:
        print(f"[plan] {len(plan)} queries; provider chain: {', '.join(order) or 'NONE (missing keys)'}")
        for label, query in plan:
            print(f"  - {label}: {query}")
        missing = [p for p in PROVIDER_ORDER if not keys.get(PROVIDERS[p][0])]
        if missing:
            print(f"[plan] skipped (no key): {', '.join(missing)}")
        return 0

    if not order:
        print(
            "[FATAL] no provider key found. Set PEXELS_API_KEY / PIXABAY_API_KEY / "
            "UNSPLASH_ACCESS_KEY via secrets_manager or .env.",
            file=sys.stderr,
        )
        return 2

    intake_root = Path(args.out) if args.out else (
        SMB_INTAKE if SMB_INTAKE.parent.parent.exists() else LOCAL_INTAKE
    )
    # 2026-09-14: ONE fixed folder — files go straight into the inbox root.
    target_dir = intake_root
    target_dir.mkdir(parents=True, exist_ok=True)
    state_path = target_dir.parent / "_state" / "seen_assets.json"
    seen = load_seen(state_path)

    session = requests.Session()
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    for label, query in plan:
        got = 0
        for provider in order:
            key_name, search = PROVIDERS[provider]
            try:
                items = search(
                    session, query, map_orientation(provider, args.orientation), args.limit, keys[key_name]
                )
            except Exception as exc:  # noqa: BLE001 - provider outage -> try the next provider
                print(f"[warn] {provider} failed for '{query}': {exc}", file=sys.stderr)
                continue
            for item in items:
                if str(item.get("id")) in seen.get(provider, set()):
                    print(f"[skip] {provider}#{item.get('id')} already in seen registry", flush=True)
                    continue
                try:
                    record = download_item(session, item, target_dir)
                except Exception as exc:  # noqa: BLE001 - one bad item must not kill the run
                    print(f"[warn] download failed ({provider}#{item.get('id')}): {exc}", file=sys.stderr)
                    continue
                record["label"] = label
                record["query"] = query
                records.append(record)
                seen.setdefault(provider, set()).add(str(record["id"]))
                got += 1
                time.sleep(THROTTLE_SEC)
            if got:
                break  # first provider with usable results wins the chain
        if not got:
            failures.append(f"{label}:{query}")

    save_seen(state_path, seen)
    manifest_path = target_dir / "manifest.json"
    existing: list[dict[str, Any]] = []
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8")).get("items") or []
    payload = {
        "schema": "reference_intake.v1",
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "run_date": dt.date.today().isoformat(),
        "orientation": args.orientation,
        "providers": order,
        "items": existing + records,
        "failures": failures,
    }
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, manifest_path)

    print(f"[intake] {len(records)} items -> {target_dir}")
    if failures:
        print(f"[intake] failed queries: {', '.join(failures)}", file=sys.stderr)
    if not records:
        print("[FATAL] no material downloaded at all", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
