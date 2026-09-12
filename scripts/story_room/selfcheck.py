"""Story Room v3 self-check: one command to verify the whole creative core.

Run:
  python scripts/story_room/selfcheck.py

Covers: banks (30 hooks / 20 twists) -> variant uniqueness -> offline adversarial
loop -> critic dimensions -> Toonflow contract round-trip -> LLM channel ->
MCP facade import. Exit code 0 = all PASS. Re-run after ANY upgrade.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))


def main() -> int:
    # 1) banks
    from story_room import hooks, twists
    check("banks.hooks(30)", len(hooks.all_hooks()) == 30, f"{len(hooks.all_hooks())}")
    check("banks.twists(20)", len(twists.all_twists()) == 20, f"{len(twists.all_twists())}")

    # 2) variant uniqueness across the P3 topics
    from story_room import make_variant_plans
    from story_room.mv_strategy import MV_VALIDATION_TOPICS, validate_music_world_story
    topics = list(MV_VALIDATION_TOPICS)
    for topic in topics:
        plans = make_variant_plans(topic, n=5, seed=42)
        sigs = {p.signature() for p in plans}
        check(f"variants.unique[{topic}]", len(sigs) == 5, "5 distinct signatures")

    # 3) offline adversarial loop + dimensions
    from story_room import run_adversarial, critic_dims
    plan = make_variant_plans(topics[0], n=5, seed=42)[0]
    r = run_adversarial(topics[0], plan, offline=True)
    check("loop.offline", r["score"]["total"] > 0 and len(r["log"]) >= 1,
          f"score={r['score']['total']} rounds={len(r['log'])}")
    dims = critic_dims.review_story(r["story"])
    check("critic.dimensions", dims["score_avg"] > 0, f"avg={dims['score_avg']}")
    production = validate_music_world_story(r["story"])
    check("mv.production", production["pass"],
          f"wan={production['wan_shots']} units={production['generation_units']}")

    # 4) Toonflow contract round-trip on the pinned fixture
    from story_room.converters.toonflow_import import (
        import_toonflow_export, contract_roundtrip, CONTRACT_VERSION)
    fixture = _ROOT / "integrations" / "toonflow" / "contracts" / "fixtures" / "toonflow_export_sample.json"
    try:
        contract = import_toonflow_export(fixture)
        ok, msg = contract_roundtrip({
            "topic": contract["topic"], "logline": contract["logline"],
            "hook": contract["hook"], "theme": contract["theme"],
            "target_sec": contract["target_sec"], "acts": contract["acts"],
            "beats": contract["beats"], "characters": contract["characters"],
        })
        check("contract.roundtrip", ok and contract["contract"] == CONTRACT_VERSION,
              f"{contract['contract']} | {msg}")
    except Exception as exc:  # noqa: BLE001
        check("contract.roundtrip", False, str(exc)[:200])

    # 5) LLM text channel (availability only; no network call)
    try:
        from story_room import llm_text
        check("llm.channel", llm_text.available(), "DeepSeek key present" if llm_text.available() else "no key")
    except Exception as exc:  # noqa: BLE001
        check("llm.channel", False, str(exc)[:200])

    # 6) MCP facade module (import only; transport not started)
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "drama_factory_server", _SCRIPTS / "mcp" / "drama_factory_server.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        check("mcp.facade", hasattr(mod, "mcp"), "FastMCP instance created")
    except Exception as exc:  # noqa: BLE001
        check("mcp.facade", False, f"{type(exc).__name__}: {str(exc)[:160]}")

    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"SELFCHECK {'PASS' if failed == 0 else 'FAIL'} ({len(CHECKS) - failed}/{len(CHECKS)})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
