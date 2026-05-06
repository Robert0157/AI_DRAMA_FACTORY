#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke tests for youtube_sheet / Tracklist pairing (run from repo root)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common.youtube_cheatsheet_builder import (  # noqa: E402
    generate_youtube_cheatsheet_file,
    glob_youtube_sheet_paths,
)


def _assembler_tracklist(body_lines: str) -> str:
    return (
        "【R&S Echoes 1 小時無縫混音 - Tracklist】\n"
        + "=" * 60
        + "\n"
        + body_lines
        + "=" * 60
        + "\n生成時間：2099-01-01\n"
    )


class TestYoutubeCheatSheetBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self._td = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._td, ignore_errors=True)

    def test_output_name_and_sample_aligned_sections_light_music(self) -> None:
        td = self._td
        (td / "Tracklist_20990101_1200.txt").write_text(
            _assembler_tracklist("00:00 - Alpha\n02:00 - Beta\n"),
            encoding="utf-8",
        )
        (td / "R&S_Echoes_light_music_1HrMix_20990101_1200.wav").write_bytes(b"x")
        (td / "metadata_distrokid_light_music.json").write_text(
            json.dumps({"album_title": "Album EN / 專輯"}),
            encoding="utf-8",
        )
        res = generate_youtube_cheatsheet_file(td, "light_music")
        out = res["output_path"]
        self.assertRegex(out.name, r"^youtube_sheet_\d{8}_\d{6}\.txt$")
        text = out.read_text(encoding="utf-8")
        self.assertIn("Album EN / 專輯 | 1 Hour Ambient Nature Mix", text)
        self.assertNotIn("✏️ 建議標題", text)
        self.assertNotIn("或選項 2", text)
        self.assertIn("00:00 - Alpha", text)
        self.assertIn("【⏱️ TRACKLIST】", text)
        self.assertIn("⚙️ Production:", text)
        self.assertIn("Unauthorized reproduction", text)
        self.assertFalse(res["used_default_tracklist"])
        self.assertIsNotNone(res.get("paired_master_wav"))

    def test_glob_returns_only_new_pattern_sorted_by_mtime(self) -> None:
        td = self._td
        p_old = td / "YouTube_CheatSheet_20990101_120000.txt"
        p_old.write_text("legacy", encoding="utf-8")
        p_new1 = td / "youtube_sheet_20990202_120000.txt"
        p_new1.write_text("new1", encoding="utf-8")
        p_new2 = td / "youtube_sheet_20990202_120001.txt"
        p_new2.write_text("new2", encoding="utf-8")
        paths = glob_youtube_sheet_paths(td)
        self.assertEqual([p.name for p in paths], [p_new1.name, p_new2.name])

    def test_placeholder_not_used_when_real_tracklist_exists(self) -> None:
        td = self._td
        (td / "Tracklist_20990101_0001_placeholder.txt").write_text(
            "placeholder only\n", encoding="utf-8"
        )
        (td / "Tracklist_20990101_1200.txt").write_text(
            _assembler_tracklist("00:01 - Real\n"),
            encoding="utf-8",
        )
        (td / "R&S_Echoes_1HrMix_20990101_1200.wav").write_bytes(b"w")
        (td / "metadata_distrokid_lofi.json").write_text(
            json.dumps({"album_title": "X"}), encoding="utf-8"
        )
        res = generate_youtube_cheatsheet_file(td, "lofi")
        self.assertEqual(res["tracklist_path"].name, "Tracklist_20990101_1200.txt")
        self.assertIn("00:01 - Real", res["output_path"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
