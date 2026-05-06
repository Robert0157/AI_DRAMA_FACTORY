#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Template lock test for DistroKid_Sheet output."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.gear1_prod.music_metadata_engine import (  # noqa: E402
    MetadataRecord,
    _build_distrokid_sheet_content,
)


def _normalize_lines(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.replace("\r\n", "\n").splitlines()]


class TestDistroKidSheetTemplate(unittest.TestCase):
    def test_key_sections_match_sample(self) -> None:
        sample_path = (
            ROOT / "assets" / "final_exports" / "light_music" / "DistroKid_sheet_sample.txt"
        )
        sample = sample_path.read_text(encoding="utf-8")

        record = MetadataRecord(
            album_title="Ethereal Horizons / 縈繞的天際",
            track_list=[],
            spotify_subgenre="Ambient",
            youtube_seo_description="",
            generated_at="2026-04-30T11:05:20",
            youtube_copyright="© 2026 R&S Echoes. All rights reserved.",
        )
        rendered = _build_distrokid_sheet_content(record, "light_music")

        sample_lines = _normalize_lines(sample)
        rendered_lines = _normalize_lines(rendered)

        # 關鍵段落鎖定：避免後續模板跑版
        expected_block = [
            "==================================================",
            "【R&S Echoes 雙語發行企劃書 (DistroKid / Spotify)】",
            "生成時間: 2026-04-30T11:05:20",
            "頻道戰區: LIGHT_MUSIC",
            "==================================================",
            "",
            "🎧 [Album Title / 專輯名稱]",
            "Ethereal Horizons / 縈繞的天際",
            "",
            "🏷️ [Primary Genre / 主要曲風]",
            "Electronic / Ambient",
            "",
            "🏷️ [Secondary Genre / 次要曲風 (Spotify)]",
            "Ambient",
        ]

        self.assertEqual(rendered_lines[: len(expected_block)], expected_block)
        self.assertEqual(sample_lines[: len(expected_block)], expected_block)


if __name__ == "__main__":
    unittest.main()

