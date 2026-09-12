"""Offline tests for the CEO console mirror tool (no network)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import ceo_console as cc  # noqa: E402


def _make_sources(tmp_path: Path) -> Path:
    """Build a fake share tree with forge run, CP-D pack and one sample."""
    share = tmp_path / "share"
    forge = share / "Auto_Drama" / "output" / "script_forge" / "s1"
    forge.mkdir(parents=True)
    (forge / "run_meta.json").write_text(
        json.dumps({"series_id": "s1", "status": "running", "iterations": 2,
                    "min_iters": 15, "max_iters": 20}), encoding="utf-8")
    (forge / "iteration_log.md").write_text("# log\n| 1 | 4.8 |\n", encoding="utf-8")
    (forge / "iter_02.json").write_text(json.dumps(
        {"iteration": 2, "final": {"final_total": 5.1, "min_domain": 5.5, "domains": {}}}),
        encoding="utf-8")
    (forge / "best_package.json").write_text(json.dumps({
        "schema": "series_contract.v1",
        "title": "測試劇",
        "logline": "一句話故事。",
        "episode_outline": [{"ep": 1, "arc": 1, "title": "第一集",
                             "hook": "鉤子", "summary": "大綱摘要", "cliffhanger": "收束"}],
    }, ensure_ascii=False), encoding="utf-8")
    (forge / "best_meta.json").write_text(json.dumps(
        {"score": 8.4, "iteration": 2, "official_total": 5.0,
         "domains": {"concept": 8.4, "structure": 8.2}, "findings": []},
        ensure_ascii=False), encoding="utf-8")

    cp_d = share / "assets" / "reference_intake" / "cp_d" / "W-TEST"
    cp_d.mkdir(parents=True)
    (cp_d / "review.html").write_text("<html>ok</html>", encoding="utf-8")
    (cp_d / "proposal.md").write_text("# proposal", encoding="utf-8")
    (cp_d / "sheet_lofi_3types.jpg").write_bytes(b"jpg")

    inbox = share / "assets" / "reference_intake" / "inbox" / "W-TEST"
    inbox.mkdir(parents=True)
    (inbox / "pexels_1.jpg").write_bytes(b"jpg")
    (inbox / "manifest.json").write_text("{}", encoding="utf-8")

    handoff = share / "Auto_Drama" / "output" / "handoff" / "done" / "job1"
    handoff.mkdir(parents=True)
    (handoff / "status.json").write_text(json.dumps(
        {"pass": True, "duration_sec": 29.1, "size": "480x848", "output": "/x/v01.mp4"}),
        encoding="utf-8")
    return share


def test_sync_mirrors_and_indexes(tmp_path, monkeypatch):
    share = _make_sources(tmp_path)
    monkeypatch.setenv("CEO_CONSOLE_ROOT", str(tmp_path / "CEO"))
    monkeypatch.setenv("CEO_SOURCE_ROOT", str(share))
    forge_dst = tmp_path / "CEO" / "01_劇本鑄造" / "s1"
    forge_dst.mkdir(parents=True, exist_ok=True)
    (forge_dst / "state_latest.json").write_text("{}", encoding="utf-8")  # stale JSON from old syncs
    rc = cc.main(["--sync", "--forge-series", "s1", "--week", "W-TEST"])
    assert rc == 0
    ceo = tmp_path / "CEO"
    assert (forge_dst / "iteration_log.md").is_file()
    assert not (forge_dst / "iter_02.json").exists()        # machine JSON stays offline
    assert not (forge_dst / "state_latest.json").exists()   # stale JSON is purged
    novel = forge_dst / "劇本小說版.md"
    assert novel.is_file() and "測試劇" in novel.read_text(encoding="utf-8")
    summary = (forge_dst / "進度摘要.md").read_text(encoding="utf-8")
    assert "迭代次數：2" in summary
    assert "μ **8.4**" in summary           # champion focus, not the last-iter net score
    assert "距閘門" in summary
    assert (ceo / "02_素材與CP-D" / "W-TEST" / "review.html").is_file()
    assert (ceo / "02_素材與CP-D" / "W-TEST" / "pexels_1.jpg").is_file()
    assert (ceo / "03_樣片與交付" / "樣片清單.md").is_file()
    index = (ceo / "README.md").read_text(encoding="utf-8")
    assert "W-TEST" in index and "01_劇本鑄造" in index


def test_sync_reports_missing_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("CEO_CONSOLE_ROOT", str(tmp_path / "CEO2"))
    monkeypatch.setenv("CEO_SOURCE_ROOT", str(tmp_path / "none"))
    rc = cc.main(["--sync"])
    assert rc == 0
    assert (tmp_path / "CEO2" / "README.md").is_file()
