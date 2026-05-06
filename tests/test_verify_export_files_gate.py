#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression: verify_export_files requires DistroKid_Sheet_*.txt."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui.backend import UIBackend  # noqa: E402


class TestVerifyExportFilesGate(unittest.TestCase):
    def setUp(self) -> None:
        self._td = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self._td, ignore_errors=True)

    def _touch_four_core(self, exp: Path, *, with_distrokid: bool) -> None:
        exp.mkdir(parents=True, exist_ok=True)
        (exp / "metadata_distrokid_light_music.json").write_text(
            json.dumps({"album_title": "X"}), encoding="utf-8"
        )
        (exp / "youtube_sheet_20260101_120000.txt").write_text("專輯：X\n", encoding="utf-8")
        (exp / "mix.mp4").write_bytes(b"fake")
        if with_distrokid:
            (exp / "DistroKid_Sheet_20260101_120000.txt").write_text("sheet", encoding="utf-8")

    def test_fails_without_distrokid_sheet(self) -> None:
        exp = self._td / "final_exports" / "light_music"
        self._touch_four_core(exp, with_distrokid=False)

        backend = UIBackend()
        with patch.object(backend, "_export_dir_for_channel", lambda self, channel=None: exp):
            r = backend.verify_export_files("light_music")

        self.assertFalse(r["all_passed"])
        self.assertIn("DistroKid_Sheet_*.txt", r["status"]["missing_list"])

    def test_passes_with_all_four(self) -> None:
        exp = self._td / "final_exports" / "light_music"
        self._touch_four_core(exp, with_distrokid=True)

        backend = UIBackend()
        with patch.object(backend, "_export_dir_for_channel", lambda self, channel=None: exp):
            r = backend.verify_export_files("light_music")

        self.assertTrue(r["all_passed"])
        self.assertEqual(r["status"]["missing_list"], [])


if __name__ == "__main__":
    unittest.main()
