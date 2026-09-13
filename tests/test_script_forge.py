"""Offline tests for the Script Forge gate loop (no network, no LLM)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.story_room import script_forge as sf  # noqa: E402


def test_offline_seed_passes_rule_dims():
    pkg = sf.offline_seed_package()
    findings = sf.rule_findings(pkg)
    assert not [f for f in findings if f["level"] == "error"], findings


def test_rule_dims_flag_missing_episodes():
    pkg = sf.offline_seed_package()
    pkg["episode_outline"] = pkg["episode_outline"][:40]
    findings = sf.rule_findings(pkg)
    assert any(f["level"] == "error" for f in findings)


def test_forge_runs_full_floor_before_lock(tmp_path):
    result = sf.run_forge("brief", "t-floor", tmp_path, min_iters=15, max_iters=30, offline=True)
    assert result["status"] == "locked_ready"
    # Converges immediately offline, but the CEO floor forces 15 logged iterations.
    assert result["iterations"] == 15
    run = tmp_path / "t-floor"
    assert (run / "lock_ready.json").is_file()
    assert len(list(run.glob("iter_*.json"))) == 15
    assert len(list((run / "l1_workbench").glob("iter_*.json"))) == 15
    md = (run / "iteration_log.md").read_text(encoding="utf-8")
    assert "| 15 |" in md
    gate = sf.gate_check(run)
    assert gate["eligible"] is False
    assert gate["evidence_valid"] is True
    # Champion tracking: the best package snapshot is persisted for resume
    assert (run / "best_package.json").is_file()
    best_meta = json.loads((run / "best_meta.json").read_text(encoding="utf-8"))
    assert best_meta["score"] >= 9.0


def test_capped_run_is_not_eligible(tmp_path):
    result = sf.run_forge("brief", "t-broken", tmp_path, min_iters=15, max_iters=16,
                          offline=True, broken=True)
    assert result["status"] == "capped"
    assert result["iterations"] == 16
    run = tmp_path / "t-broken"
    assert not (run / "lock_ready.json").exists()
    assert sf.gate_check(run)["eligible"] is False


@pytest.mark.parametrize("payload", [
    {"cp_d_eligible": True, "iterations": 15, "final_total": 1.0, "min_domain": 1.0},
    {"eligible": True, "cp_d_eligible": False, "iterations": 15},
    {"cp_d_eligible": True, "iterations": 15, "mode": "offline"},
])
def test_gate_rejects_unverified_lock(tmp_path, payload):
    """A lock file alone must never grant production eligibility."""
    (tmp_path / "lock_ready.json").write_text(json.dumps(payload), encoding="utf-8")
    assert sf.gate_check(tmp_path)["eligible"] is False


def test_gate_rejects_malformed_lock(tmp_path):
    """Corrupt evidence must return a visible rejection, not approval."""
    (tmp_path / "lock_ready.json").write_text("{", encoding="utf-8")
    result = sf.gate_check(tmp_path)
    assert result["eligible"] is False
    assert result["reason"]


def _reviewed_test_run(tmp_path):
    """Build simulated production evidence without any network calls."""
    sf.run_forge("brief", "verified", tmp_path, offline=True)
    run = tmp_path / "verified"
    for path in [run / "run_meta.json", run / "lock_ready.json", *run.glob("iter_*.json")]:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["mode"] = "llm"
        if path.name == "lock_ready.json":
            data["cp_d_eligible"] = True
        path.write_text(json.dumps(data), encoding="utf-8")
    return run


def test_gate_accepts_complete_consistent_evidence(tmp_path):
    assert sf.gate_check(_reviewed_test_run(tmp_path))["eligible"] is True


@pytest.mark.parametrize("filename,field,value", [
    ("state_latest.json", "title", "changed after review"),
    ("best_package.json", "title", "changed after review"),
    ("iter_01.json", "degraded", True),
    ("iter_01.json", "errors", 1),
    ("run_meta.json", "mode", "offline"),
    ("lock_ready.json", "final_total", float("nan")),
    ("lock_ready.json", "final_total", 1.0),
])
def test_gate_rejects_changed_evidence(tmp_path, filename, field, value):
    run = _reviewed_test_run(tmp_path)
    path = run / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    assert sf.gate_check(run)["eligible"] is False


def test_gate_rejects_missing_iteration(tmp_path):
    run = _reviewed_test_run(tmp_path)
    (run / "iter_05.json").unlink()
    assert sf.gate_check(run)["eligible"] is False


def test_resume_continues_and_locks(tmp_path):
    first = sf.run_forge("brief", "t-resume", tmp_path, min_iters=15, max_iters=16,
                         offline=True, broken=True)
    assert first["status"] == "capped"
    second = sf.run_forge("brief", "t-resume", tmp_path, min_iters=15, max_iters=30,
                          offline=True, resume=True)
    assert second["status"] == "locked_ready"
    assert second["iterations"] == 17
    assert len(list((tmp_path / "t-resume").glob("iter_*.json"))) == 17


def test_existing_run_requires_resume_or_force(tmp_path):
    sf.run_forge("brief", "t-guard", tmp_path, min_iters=15, max_iters=15, offline=True)
    with pytest.raises(SystemExit):
        sf.run_forge("brief", "t-guard", tmp_path, min_iters=15, max_iters=15, offline=True)


def test_min_iters_below_ceo_floor_rejected(tmp_path):
    with pytest.raises(SystemExit):
        sf.run_forge("brief", "t-floor-guard", tmp_path, min_iters=14, max_iters=20, offline=True)


def test_apply_patch_merges_episode_patches():
    pkg = sf.offline_seed_package()
    patched = sf._apply_patch(pkg, {"episode_patches": [{"ep": 3, "hook": "新鉤子"}], "theme": "新主題"})
    assert patched["theme"] == "新主題"
    ep3 = [e for e in patched["episode_outline"] if e["ep"] == 3][0]
    assert ep3["hook"] == "新鉤子"
    assert pkg["theme"] != "新主題"  # original package untouched


def test_salvage_json_recovers_truncated_seed():
    truncated = '{"title": "測試", "arcs": [{"arc": 1, "summary": "弧一"}], "episode_outline": [{"ep": 1, "hook": "鉤子"}, {"ep": 2, "hook\n'
    salvaged = sf._salvage_json(truncated)
    assert salvaged is not None
    assert salvaged["title"] == "測試"
    assert salvaged["episode_outline"][0]["ep"] == 1


def test_salvage_json_returns_none_for_garbage():
    assert sf._salvage_json("no json here") is None


def test_apply_patch_upserts_missing_episodes_and_guards_empties():
    pkg = sf.offline_seed_package()
    pkg["episode_outline"] = [e for e in pkg["episode_outline"] if e["ep"] <= 54]
    patched = sf._apply_patch(pkg, {
        "bible": {"locations": []},
        "episode_patches": [
            {"ep": 55, "arc": 4, "title": "t55", "hook": "h55", "summary": "s55", "cliffhanger": "c55"},
            {"ep": 56, "arc": 4, "title": "t56", "hook": "h56", "summary": "s56", "cliffhanger": "c56"},
        ],
    })
    assert len(patched["bible"]["locations"]) >= 6  # empty list must not wipe content
    assert [e["ep"] for e in patched["episode_outline"]] == list(range(1, 57))


def test_restore_missing_recovers_seed_fields():
    ref = sf.offline_seed_package()
    damaged = json.loads(json.dumps(ref))
    damaged["bible"]["locations"] = []
    damaged["arcs"] = []
    restored, names = sf._restore_missing(damaged, ref)
    assert "bible.locations" in names and restored["bible"]["locations"]
    assert "arcs" in names and restored["arcs"]


def test_apply_patch_merges_pilot_excerpt_without_touching_samples():
    pkg = sf.offline_seed_package()
    patched = sf._apply_patch(pkg, {"pilot": {"ep1": {"script_excerpt": "X" * 700}}})
    assert patched["pilot"]["ep1"]["script_excerpt"].startswith("X")
    assert patched["pilot"]["ep1"]["dialogue_sample"]  # existing content untouched


# ---------------------------------------------------------------------------
# v3 multi-agent review panel (offline: mocked LLM channel)
# ---------------------------------------------------------------------------
def _director_payload(score: float = 8.2) -> dict:
    return {
        "domains": {k: score for k in sf.RUBRIC_WEIGHTS},
        "top_fixes": ["fix-1", "fix-2"],
        "verdict": "緊湊可行",
        "findings": [{"domain": "dialogue", "level": "warn", "msg": "director-note"}],
    }


def _rubric_payload(score: float = 7.7) -> dict:
    return {"domains": {k: score for k in sf.RUBRIC_WEIGHTS},
            "top_fixes": ["rubric-fix"], "verdict": "單評審"}


def _install_panel_mock(monkeypatch, *, critic_score=8.0, director=None,
                        fail_critics=(), fail_director=False):
    """Route fake replies by system prompt so the real merge logic is exercised."""
    from scripts.story_room import llm_text as lt

    def fake_chat(system, user, **kwargs):
        if system == sf._DIRECTOR_SYS:
            if fail_director:
                raise RuntimeError("503 director down")
            return json.dumps(director if director is not None else _director_payload(),
                              ensure_ascii=False)
        if system == sf._RUBRIC_SYS:
            return json.dumps(_rubric_payload(), ensure_ascii=False)
        for name, spec in sf._CRITIC_PANEL.items():
            if system == spec["sys"]:
                if name in fail_critics:
                    raise RuntimeError(f"{name} down")
                return json.dumps({
                    "domains": {d: critic_score for d in spec["domains"]},
                    "report": f"{name} 簡評",
                    "findings": [{"domain": spec["domains"][0], "level": "warn",
                                  "msg": f"{name}-finding"}],
                }, ensure_ascii=False)
        raise AssertionError(f"unexpected system prompt: {system[:60]}")

    monkeypatch.setattr(lt, "deepseek_chat", fake_chat)


def test_review_panel_merges_critics_and_director(monkeypatch):
    _install_panel_mock(monkeypatch, critic_score=8.0, director=_director_payload(8.2))
    result, findings, degraded = sf._review_panel(sf.offline_seed_package(), None)
    assert degraded is False
    assert all(abs(result["domains"][k] - 8.2) < 1e-9 for k in sf.RUBRIC_WEIGHTS)
    assert result["verdict"] == "緊湊可行"
    msgs = [f["msg"] for f in findings]
    assert "director-note" in msgs
    assert "structure-finding" in msgs and "feasibility-finding" in msgs


def test_review_panel_critic_failure_marks_degraded(monkeypatch):
    _install_panel_mock(monkeypatch, critic_score=7.8, director=_director_payload(8.0),
                        fail_critics=("feasibility",))
    result, _findings, degraded = sf._review_panel(sf.offline_seed_package(), None)
    assert degraded is True
    assert result["domains"]["feasibility"] == 8.0  # filled by the director


def test_review_panel_director_failure_uses_critic_anchor(monkeypatch):
    _install_panel_mock(monkeypatch, critic_score=7.6, fail_director=True)
    result, _findings, degraded = sf._review_panel(sf.offline_seed_package(), None)
    assert degraded is True
    assert all(abs(result["domains"][k] - 7.6) < 1e-9 for k in sf.RUBRIC_WEIGHTS)
    assert result["verdict"].startswith("panel degraded")


def test_review_panel_total_failure_falls_back_to_single_judge(monkeypatch):
    _install_panel_mock(monkeypatch, fail_critics=tuple(sf._CRITIC_PANEL))
    result, _findings, degraded = sf._review_panel(sf.offline_seed_package(), None)
    assert degraded is True
    assert all(abs(result["domains"][k] - 7.7) < 1e-9 for k in sf.RUBRIC_WEIGHTS)


def test_md_row_marks_degraded_rounds():
    entry = {
        "iteration": 3, "ts": "12:00:00", "action": "revise", "best": False, "degraded": True,
        "errors": 0, "warns": 2,
        "final": {"final_total": 7.0, "min_domain": 6.0, "llm_total": 7.5,
                  "domains": {k: 7.0 for k in sf.RUBRIC_WEIGHTS}},
    }
    row = sf._md_row(entry)
    assert "⚠" in row and "★" not in row


def test_campaign_cap_is_industry_1000():
    # CEO 2026-09-12 (rev): 150 was too low -> industry-standard 10^3 budget.
    assert sf.DEFAULT_MAX_ITERATIONS == 1000


def test_plateau_warning_alerts_after_idle_streak():
    assert sf._plateau_warning(101, 1) is not None   # gap = 100 -> alert
    assert sf._plateau_warning(151, 1) is not None   # gap = 150 -> alert
    assert sf._plateau_warning(100, 1) is None       # gap = 99 -> too early
    assert sf._plateau_warning(126, 1) is None       # gap = 125 -> not a boundary
    assert sf._plateau_warning(90, None) is None     # no champion yet


def test_ceo_notes_reader(tmp_path):
    assert sf._read_ceo_notes(tmp_path) == ""
    (tmp_path / "ceo_notes.md").write_text("Ep1 修訂：隧道太假", encoding="utf-8")
    assert "隧道太假" in sf._read_ceo_notes(tmp_path)


def test_excerpt_rotation_keeps_ep1_off_colliding_index():
    # index % 5 == 0 collides with the it % 10 == 0 production-plan branch,
    # so that episode would never be refreshed.
    idx = sf._EXCERPT_ROTATION.index(1)
    assert idx % 5 != 0


def test_locked_episode_enforcement_roundtrip(tmp_path):
    (tmp_path / "ceo_locked").mkdir()
    payload = {"ep": 1, "script_excerpt": "COLD OPEN ... frozen text"}
    (tmp_path / "ceo_locked" / "ep01_ceo_approved.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "ceo_locked.json").write_text(
        json.dumps({"episodes": [1]}), encoding="utf-8")
    locked = sf._load_locked_episodes(tmp_path)
    assert locked[1]["script_excerpt"].startswith("COLD OPEN")
    pkg = {"pilot": {"ep1": {"scenes": ["x"], "script_excerpt": "wiped"}}}
    assert sf._enforce_locked(pkg, locked) == [1]
    assert pkg["pilot"]["ep1"]["script_excerpt"] == payload["script_excerpt"]
    assert pkg["pilot"]["ep1"]["scenes"] == ["x"]   # non-frozen fields survive
    assert sf._enforce_locked(pkg, locked) == []      # idempotent


def test_rotation_skips_locked_episode():
    assert sf._pick_rotated_episode(118, {}) == 1     # slot 9 -> Ep1
    assert sf._pick_rotated_episode(118, {1}) == 14   # steps to the next slot


def test_append_text_retries_on_smb_lock(tmp_path, monkeypatch):
    log = tmp_path / "iteration_log.md"
    calls = {"n": 0}
    real_open = Path.open

    def flaky_open(self, *a, **kw):
        if self == log:
            calls["n"] += 1
            if calls["n"] <= 2:          # first two attempts hit the SMB lock
                raise PermissionError("locked")
        return real_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", flaky_open)
    monkeypatch.setattr(sf.time, "sleep", lambda s: None)
    sf._append_text(log, "row1\n")
    assert log.read_text(encoding="utf-8") == "row1\n"
    assert calls["n"] >= 3   # two locked attempts + the successful append


# ---------------------------------------------------------------------------
# B+ pilot-arc gate (CEO 2026-09-13): Ep1-4 unlocks CP-D before the full lock
# ---------------------------------------------------------------------------
def _pilot_arc_payload(run: Path, **overrides) -> dict:
    package = json.loads((run / "best_package.json").read_text(encoding="utf-8"))
    payload = {
        "schema": sf.PILOT_ARC_SCHEMA,
        "series_id": "verified",
        "arc": sf.PILOT_ARC_ID,
        "iterations": 15,
        "arc_score": 8.9,
        "min_domain": 8.2,
        "errors": 0,
        "bible_complete": True,
        "canon_complete": True,
        "bible_ref": "bible.md",
        "canon_ref": "canon.md",
        "package_sha256": sf._package_sha256(package),
    }
    payload.update(overrides)
    return payload


def _pilot_ready_run(tmp_path, **overrides):
    run = _reviewed_test_run(tmp_path)
    (run / "bible.md").write_text("bible", encoding="utf-8")
    (run / "canon.md").write_text("canon", encoding="utf-8")
    (run / sf.PILOT_ARC_EVIDENCE).write_text(
        json.dumps(_pilot_arc_payload(run, **overrides)), encoding="utf-8")
    return run


def test_pilot_gate_accepts_valid_arc_and_writes_lock(tmp_path):
    run = _pilot_ready_run(tmp_path)
    report = sf.pilot_gate_check(run)
    assert report["eligible"] is True
    lock = json.loads((run / sf.PILOT_ARC_LOCK).read_text(encoding="utf-8"))
    assert lock["schema"] == sf.PILOT_ARC_LOCK_SCHEMA
    assert lock["arc"] == "ep01-ep04"
    assert lock["cp_d_eligible"] is True
    # Idempotent: re-checking the same evidence stays green.
    assert sf.pilot_gate_check(run)["eligible"] is True


def test_pilot_gate_requires_review_evidence(tmp_path):
    run = _reviewed_test_run(tmp_path)
    report = sf.pilot_gate_check(run)
    assert report["eligible"] is False
    assert "pilot_arc.json missing" in report["reason"]


def test_pilot_gate_goes_stale_when_package_changes(tmp_path):
    run = _pilot_ready_run(tmp_path)
    package = json.loads((run / "best_package.json").read_text(encoding="utf-8"))
    package["title"] = "changed after the arc review"
    (run / "best_package.json").write_text(json.dumps(package), encoding="utf-8")
    report = sf.pilot_gate_check(run)
    assert report["eligible"] is False
    assert "stale" in report["reason"]


def test_pilot_gate_offline_run_cannot_authorize(tmp_path):
    sf.run_forge("brief", "pilot-offline", tmp_path, offline=True)
    run = tmp_path / "pilot-offline"
    (run / "bible.md").write_text("bible", encoding="utf-8")
    (run / "canon.md").write_text("canon", encoding="utf-8")
    (run / sf.PILOT_ARC_EVIDENCE).write_text(
        json.dumps(_pilot_arc_payload(run, series_id="pilot-offline")), encoding="utf-8")
    report = sf.pilot_gate_check(run)
    assert report["eligible"] is False
    assert report["evidence_valid"] is True
    assert not (run / sf.PILOT_ARC_LOCK).exists()


def test_pilot_gate_cli_dispatch(tmp_path):
    run = _pilot_ready_run(tmp_path)
    code = sf.main(["--series-id", "verified", "--out", str(tmp_path),
                    "--gate-check", "--pilot"])
    assert code == 0
    assert (run / sf.PILOT_ARC_LOCK).is_file()


@pytest.mark.parametrize("overrides", [
    {"schema": "forge.pilot_arc.v0"},
    {"arc": "ep01-ep03"},
    {"iterations": 14},
    {"arc_score": 8.7},
    {"min_domain": 7.9},
    {"errors": 1},
    {"bible_complete": False},
    {"canon_complete": False},
    {"bible_ref": ""},
    {"bible_ref": "no_such_artifact.md"},
    {"bible_ref": "../escape.md"},
    {"package_sha256": "0" * 64},
])
def test_pilot_gate_rejects_bad_arc_evidence(tmp_path, overrides):
    run = _pilot_ready_run(tmp_path, **overrides)
    report = sf.pilot_gate_check(run)
    assert report["eligible"] is False
    assert not (run / sf.PILOT_ARC_LOCK).exists()
