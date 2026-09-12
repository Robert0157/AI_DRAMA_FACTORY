"""P1 critic dimension library: foreshadow ledger / canon / pacing curve.

Concept borrowed from OpenWrite's six-domain review + review DAG, promoted to
checkable data structures so findings are evidence-based, not vibes.
"""
from __future__ import annotations

import statistics


def _score_from(findings: list[dict]) -> float:
    errors = sum(1 for f in findings if f["level"] == "error")
    warns = sum(1 for f in findings if f["level"] == "warn")
    return max(1.0, 9.0 - 3.0 * errors - 1.5 * warns)


def foreshadow_ledger(story: dict) -> dict:
    """Every setup must have a payoff; fewer than 2 items is a suspense warning."""
    items = story.get("foreshadows") or []
    findings: list[dict] = []
    resolved = 0
    for i, item in enumerate(items, 1):
        setup = str(item.get("setup", "")).strip()
        payoff = str(item.get("payoff", "")).strip()
        if setup and payoff:
            resolved += 1
        else:
            findings.append({"domain": "foreshadow", "level": "error",
                             "msg": f"伏筆#{i} 缺 setup 或 payoff"})
    if len(items) < 2:
        findings.append({"domain": "foreshadow", "level": "warn",
                         "msg": f"伏筆數 {len(items)} < 2（懸疑偏薄）"})
    return {"score": _score_from(findings), "findings": findings,
            "resolved": resolved, "total": len(items)}


def canon_check(story: dict, canon: dict | None = None) -> dict:
    """Character/canon consistency (names unique, cast present, canon respected)."""
    findings: list[dict] = []
    chars = story.get("characters") or []
    names = [c if isinstance(c, str) else str(c.get("name", "")) for c in chars]
    if not names and story.get("production_mode") != "music_world_mv":
        findings.append({"domain": "feasibility", "level": "warn", "msg": "未定義角色"})
    if len(names) != len(set(names)):
        findings.append({"domain": "logic", "level": "error", "msg": "角色重名"})
    if canon:
        for c in canon.get("characters", []):
            if c not in names:
                findings.append({"domain": "logic", "level": "warn",
                                 "msg": f"canon 角色 {c} 未出現"})
    return {"score": _score_from(findings), "findings": findings}


def pacing_curve(story: dict, target_sec: float = 175.0) -> dict:
    """Shot-duration curve: flag flat pacing and total-duration drift."""
    findings: list[dict] = []
    shots = story.get("shots") or []
    durs = [float(s.get("duration_sec", 0)) for s in shots if s.get("duration_sec")]
    cv = 0.0
    if not durs:
        findings.append({"domain": "pacing", "level": "warn", "msg": "無鏡長資料，無法評估節奏曲線"})
    else:
        if len(durs) >= 2 and statistics.mean(durs) > 0:
            cv = statistics.pstdev(durs) / statistics.mean(durs)
            if cv < 0.10:
                findings.append({"domain": "pacing", "level": "warn",
                                 "msg": f"節奏曲線過平（CV={cv:.2f}）"})
        total = sum(durs)
        if abs(total - target_sec) > 1.0:
            findings.append({"domain": "pacing", "level": "warn",
                             "msg": f"總長 {total:.1f}s 與目標 {target_sec:.0f}s 偏差 > 1s"})
    if not str(story.get("hook", "")).strip():
        findings.append({"domain": "hook", "level": "error", "msg": "缺開場鉤子"})
    return {"score": _score_from(findings), "findings": findings, "cv": round(cv, 3)}


def review_story(story: dict, target_sec: float = 175.0) -> dict:
    """Aggregate the three dimension reports into one finding list."""
    parts = [foreshadow_ledger(story), canon_check(story), pacing_curve(story, target_sec)]
    findings = [f for p in parts for f in p["findings"]]
    return {
        "domain_scores": [round(p["score"], 1) for p in parts],
        "score_avg": round(sum(p["score"] for p in parts) / len(parts), 1),
        "findings": findings,
    }
