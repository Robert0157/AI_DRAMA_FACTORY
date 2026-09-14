"""Tests for the market-validation toolchain (ledger, policy grading, episode bundles)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.marketing.distribution_ledger import cadence_report, collect_entries  # noqa: E402
from scripts.marketing.episode_bundle import build_sidecar, validate_sidecar  # noqa: E402
from scripts.marketing.market_validation_report import grade_for, iso_week_label  # noqa: E402

POLICY = {
    "short": {
        "grade_rules": [
            {"grade": "scale", "min_views_7d": 800, "min_like_rate_pct": 3.0},
            {"grade": "iterate", "min_views_7d": 200, "min_like_rate_pct": 0.0},
            {"grade": "retire", "min_views_7d": 0, "min_like_rate_pct": 0.0},
        ]
    },
    "cadence": {
        "lookback_days": 14,
        "stale_after_hours": 48,
        "under_cadence_ratio": 0.6,
        "channels": {"lofi": {"kind": "short", "expected_per_day": 2.0, "enabled": True}},
    },
}


class TestGrading(unittest.TestCase):
    def test_scale_requires_both_thresholds(self) -> None:
        self.assertEqual(grade_for("short", 900, 4.0, POLICY), "scale")
        self.assertEqual(grade_for("short", 900, 1.0, POLICY), "iterate")  # views ok, likes low

    def test_mid_and_low_bands(self) -> None:
        self.assertEqual(grade_for("short", 200, 0.0, POLICY), "iterate")
        self.assertEqual(grade_for("short", 199, 5.0, POLICY), "retire")

    def test_iso_week_label(self) -> None:
        when = datetime(2026, 9, 14, tzinfo=timezone.utc)
        self.assertEqual(iso_week_label(when), "2026-W38")


class TestLedger(unittest.TestCase):
    def test_collect_and_cadence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shorts = root / "Shorts_Queue" / "lofi"
            shorts.mkdir(parents=True)
            rows = [
                {"ts": "2026-09-13T14:00:00+0800", "status": "success", "video_id": "AAA111", "file": "a.mp4", "title": "t1"},
                {"ts": "2026-09-13T22:00:00+0800", "status": "success", "video_id": "BBB222", "file": "b.mp4", "title": "t2"},
                {"ts": "2026-09-12T14:00:00+0800", "status": "failed", "video_id": "", "file": "c.mp4", "title": "t3"},
            ]
            body = "\n".join(json.dumps(r) for r in rows) + "\n{broken json\n"
            (shorts / "upload_history.jsonl").write_text(body, encoding="utf-8")
            long_dir = root / "Long_Queue" / "lofi"
            long_dir.mkdir(parents=True)
            (long_dir / "long_upload_history.jsonl").write_text(
                json.dumps({"ts": "2026-05-12T17:13:31+0800", "status": "success", "video_id": "CCC333", "file": "d.mp4", "title": "t4"}) + "\n",
                encoding="utf-8",
            )

            entries, bad = collect_entries(root)
            self.assertEqual(len(entries), 4)
            self.assertEqual(bad["shorts"], 1)

            now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
            report = cadence_report(entries, POLICY, now=now)
            info = report["channels"]["lofi"]
            self.assertEqual(info["actual_14d"], 2)  # only success entries count
            self.assertEqual(info["expected_14d"], 28.0)
            self.assertIn("under-cadence", info["alerts"])
            self.assertTrue(any("lofi" in alert for alert in report["alerts"]))


class TestEpisodeBundle(unittest.TestCase):
    def test_build_and_validate_ok(self) -> None:
        sidecar = build_sidecar(
            video_file="ep01.mp4",
            channel="lofi",
            title="測試標題",
            description="desc",
            tags=["a", "b"],
            privacy="unlisted",
        )
        self.assertEqual(validate_sidecar(sidecar), [])

    def test_validate_rejects_bad_fields(self) -> None:
        sidecar = build_sidecar(
            video_file="ep01.mp4",
            channel="lofi",
            title="ok",
            description="d",
            tags=["a"],
            privacy="unlisted",
        )
        # Tamper with the payload the way a hand-edited sidecar could be.
        sidecar["title"] = ""
        sidecar["channel"] = ""
        sidecar["tags"] = "not-a-list"
        sidecar["privacy"] = "friends-only"
        errs = validate_sidecar(sidecar)
        self.assertTrue(any("title" in e for e in errs))
        self.assertTrue(any("tags" in e for e in errs))
        self.assertTrue(any("privacy" in e for e in errs))
        self.assertTrue(any("channel" in e for e in errs))

    def test_build_coerces_comma_string_tags(self) -> None:
        sidecar = build_sidecar(
            video_file="ep01.mp4",
            channel="lofi",
            title="t",
            description="d",
            tags="alpha, beta ,gamma",  # type: ignore[arg-type]
            privacy="unlisted",
        )
        self.assertEqual(sidecar["tags"], ["alpha", "beta", "gamma"])
        self.assertEqual(validate_sidecar(sidecar), [])


if __name__ == "__main__":
    unittest.main()
