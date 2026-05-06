#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_final_exports：通用 metadata 與同 stem 檔合併行為。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui.backend import _merge_distrokid_with_stem_metadata  # noqa: E402


class TestPublishMetadataMerge(unittest.TestCase):
    def test_stem_overrides_generic(self) -> None:
        td = Path(tempfile.mkdtemp())
        try:
            stem = "R&S_Echoes_light_music_1HrMix_20260502_171217"
            generic = {
                "album_title": "Old",
                "track_list": ["A", "B"],
                "youtube_seo_description": "wrong",
            }
            (td / f"{stem}_metadata_distrokid.json").write_text(
                json.dumps(
                    {
                        "album_title": "Serene Forest / 森之靜謐| …",
                        "track_list": ["t1", "t2"],
                        "youtube_seo_description": "🎵 OK\n\n【⏱️ TRACKLIST】\n00:00 - Whispers",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out = _merge_distrokid_with_stem_metadata(generic, td, stem)
            self.assertIn("Whispers", out["youtube_seo_description"])
            self.assertIn("森之靜謐", out["album_title"])
        finally:
            import shutil

            shutil.rmtree(td, ignore_errors=True)

    def test_no_stem_file_unchanged(self) -> None:
        td = Path(tempfile.mkdtemp())
        try:
            g = {"x": 1}
            out = _merge_distrokid_with_stem_metadata(g, td, "missing_stem")
            self.assertEqual(out, g)
        finally:
            import shutil

            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
