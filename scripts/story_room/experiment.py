"""P3 comparison experiment: topics x n structural variants through the loop.

Outputs per-variant story JSON + results.json under
Auto_Drama/output/sandbox/story_room/p3_experiment/ (artifacts, not reports).

Usage:
  python -m story_room.experiment --topics 貓與老麵包店 雲端列車 石像山神 --n 5 --offline
  python -m story_room.experiment --topics 燈塔守夜人 --n 5 --llm   (DeepSeek text only)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if __package__ in (None, ""):  # allow direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from story_room.agents import run_adversarial  # type: ignore
    from story_room.diversity import make_variant_plans  # type: ignore
else:
    from .agents import run_adversarial
    from .diversity import make_variant_plans
    from .mv_strategy import MV_VALIDATION_TOPICS, validate_music_world_story

if __package__ in (None, ""):
    from story_room.mv_strategy import MV_VALIDATION_TOPICS, validate_music_world_story  # type: ignore


def _out_root() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "Auto_Drama" / "output" / "sandbox" / "story_room" / "p3_experiment"


def run(topics: list[str], n: int = 5, offline: bool = True, seed: int = 42,
        golden_snippet: str | None = None, model: str | None = None,
        force: bool = False) -> dict:
    out_root = _out_root()
    out_root.mkdir(parents=True, exist_ok=True)
    results: dict = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "offline" if offline else "llm",
        "n_per_topic": n,
        "topics": {},
    }
    for topic in topics:
        plans = make_variant_plans(topic, n=n, seed=seed)
        tdir = out_root / topic
        tdir.mkdir(parents=True, exist_ok=True)
        entries = []
        for plan in plans:
            variant_path = tdir / f"v{plan.variant}.json"
            if variant_path.exists() and not force:
                prev = json.loads(variant_path.read_text(encoding="utf-8"))
                production = prev.get("production_validation") or {}
                if production.get("pass"):
                    entries.append({"variant": plan.variant, "signature": plan.signature(),
                                    "world_signature": production.get("world_signature"),
                                    "score": prev.get("score", {}).get("total", 0.0),
                                    "pass": bool(prev.get("pass")), "file": str(variant_path),
                                    "resumed": True})
                    print(f"[{topic}] v{plan.variant} resume-skip")
                    continue
                print(f"[{topic}] v{plan.variant} legacy artifact; rebuilding")
            try:
                r = run_adversarial(topic, plan, golden_snippet=golden_snippet,
                                    offline=offline, model=model)
            except Exception as exc:  # noqa: BLE001 - keep the batch running
                print(f"[{topic}] v{plan.variant} ERROR: {exc}")
                entries.append({"variant": plan.variant, "signature": plan.signature(),
                                "score": 0.0, "pass": False, "error": str(exc)[:300]})
                continue
            variant_path = tdir / f"v{plan.variant}.json"
            production = validate_music_world_story(r["story"])
            passed = bool(r["pass"] and production["pass"])
            variant_path.write_text(json.dumps(
                {"story": r["story"], "score": r["score"], "log": r["log"],
                 "production_validation": production,
                 "pass": passed, "mode": r["mode"]},
                ensure_ascii=False, indent=1), encoding="utf-8")
            entries.append({"variant": plan.variant, "signature": plan.signature(),
                            "world_signature": production["world_signature"],
                            "score": r["score"]["total"], "pass": passed,
                            "wan_shots": production["wan_shots"],
                            "generation_units": production["generation_units"],
                            "file": str(variant_path)})
            print(f"[{topic}] v{plan.variant} {plan.signature()} "
                  f"score={r['score']['total']} pass={passed} "
                  f"wan={production['wan_shots']} units={production['generation_units']}")
        results["topics"][topic] = entries
    (out_root / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"RESULTS -> {out_root / 'results.json'}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="P3 story diversity experiment")
    ap.add_argument("--topics", nargs="+", default=list(MV_VALIDATION_TOPICS))
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--llm", action="store_true", help="use DeepSeek writer (text only)")
    ap.add_argument("--force", action="store_true", help="re-run variants even if vN.json exists")
    args = ap.parse_args()
    run(args.topics, n=args.n, offline=not args.llm, seed=args.seed, force=args.force)


if __name__ == "__main__":
    main()
