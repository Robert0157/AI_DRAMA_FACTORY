"""Toonflow export -> story_contract.v1 adapter (version-pinned, tolerant).

Pinned target: Toonflow-app v1.1.8 (see integrations/toonflow/VERSION.lock).
Toonflow export shapes drift between releases; this adapter reads a JSON export
and tries known key paths, then fails loudly with an actionable message.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONTRACT_VERSION = "story_contract.v1"
ADAPTER_VERSION = "0.1.0"


def _first(*vals):
    return next((v for v in vals if v not in (None, "", [], {})), None)


def toonflow_to_contract(raw: dict) -> dict:
    """Map a Toonflow-style export dict into the story contract."""
    story = raw.get("story") or {}
    topic = _first(raw.get("projectName"), raw.get("project_name"),
                   raw.get("title"), raw.get("name"))
    logline = _first(raw.get("logline"), story.get("logline"),
                     raw.get("synopsis"), raw.get("description"))
    if not topic or not logline:
        raise ValueError(
            "Toonflow export missing topic/logline — shape may have changed; "
            f"refresh adapter {ADAPTER_VERSION} for the pinned Toonflow version"
        )
    acts_raw = _first(raw.get("acts"), (raw.get("outline") or {}).get("acts"), story.get("acts"))
    beats_raw = _first(raw.get("beats"), story.get("beats"), raw.get("scenes"), raw.get("shots"))

    acts: list[dict] = []
    for i, a in enumerate((acts_raw or [])[:3], 1):
        acts.append({
            "index": i,
            "title": _first(a.get("title"), a.get("name"), f"第{i}幕"),
            "synopsis": _first(a.get("synopsis"), a.get("summary"), a.get("desc"), ""),
        })
    while len(acts) < 3:
        acts.append({"index": len(acts) + 1, "title": f"第{len(acts) + 1}幕", "synopsis": ""})

    beats: list[dict] = []
    for i, b in enumerate((beats_raw or [])[:12], 1):
        default_act = 1 if i <= 4 else (2 if i <= 8 else 3)
        beats.append({
            "index": i,
            "act": int(_first(b.get("act"), default_act)),
            "name": _first(b.get("name"), b.get("title"), f"節拍{i}"),
            "intent": _first(b.get("intent"), b.get("desc"), b.get("action"), ""),
        })
    if not beats:
        raise ValueError("Toonflow export has no beats/scenes/shots to map")

    chars = raw.get("characters") or story.get("characters") or []
    characters = [
        (c if isinstance(c, str) else _first(c.get("name"), c.get("key"), "character"))
        for c in chars
    ] or ["lead"]

    return {
        "contract": CONTRACT_VERSION,
        "topic": topic,
        "logline": logline,
        "hook": _first(raw.get("hook"), story.get("hook"), ""),
        "theme": _first(raw.get("theme"), story.get("theme"), ""),
        "target_sec": float(_first(raw.get("target_sec"), raw.get("duration_sec"), 175.0)),
        "acts": acts,
        "beats": beats,
        "characters": characters,
        "source": "toonflow",
    }


def export_to_contract(sheet_like: dict) -> dict:
    """Reverse direction: our BeatSheet/dict -> story contract (for round-trips)."""
    topic = _first(sheet_like.get("topic"), sheet_like.get("title"))
    if not topic:
        raise ValueError("cannot export without topic/title")
    beats_src = sheet_like.get("beats") or []
    return {
        "contract": CONTRACT_VERSION,
        "topic": topic,
        "logline": _first(sheet_like.get("logline"), ""),
        "hook": _first(sheet_like.get("hook"), ""),
        "theme": _first(sheet_like.get("theme"), ""),
        "target_sec": float(_first(sheet_like.get("target_sec"), 175.0)),
        "acts": [{"index": a.get("index", i + 1), "title": a.get("title", ""),
                  "synopsis": a.get("synopsis", "")}
                 for i, a in enumerate(sheet_like.get("acts", [])[:3])],
        "beats": [{"index": b.get("index", i + 1), "act": b.get("act", 1),
                   "name": b.get("name", ""), "intent": b.get("intent", "")}
                  for i, b in enumerate(beats_src[:12])],
        "characters": sheet_like.get("characters", ["lead"]),
        "source": "local",
    }


def load_export(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"export must be a JSON object: {path}")
    return data


def import_toonflow_export(path: Path) -> dict:
    """File-level entry used by the pipeline and MCP façade."""
    return toonflow_to_contract(load_export(path))


def contract_roundtrip(sheet_like: dict) -> tuple[bool, str]:
    """Fixture round-trip: local -> contract -> re-import -> compare key fields."""
    contract = export_to_contract(sheet_like)
    reimport = toonflow_to_contract({"projectName": contract["topic"],
                                     "logline": contract["logline"],
                                     "hook": contract["hook"],
                                     "theme": contract["theme"],
                                     "acts": contract["acts"],
                                     "beats": contract["beats"],
                                     "characters": contract["characters"]})
    ok = (reimport["topic"] == contract["topic"]
          and reimport["logline"] == contract["logline"]
          and len(reimport["beats"]) == len(contract["beats"]))
    return ok, f"roundtrip topic={reimport['topic']} beats={len(reimport['beats'])} ok={ok}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Toonflow export -> story contract")
    ap.add_argument("--src", required=True, help="Toonflow export JSON path")
    ap.add_argument("--out", default=None, help="write contract JSON here")
    args = ap.parse_args()
    contract = import_toonflow_export(Path(args.src))
    print(json.dumps(contract, ensure_ascii=False, indent=1)[:1200])
    if args.out:
        Path(args.out).write_text(json.dumps(contract, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(f"WROTE {args.out}")


if __name__ == "__main__":
    sys.exit(main())
