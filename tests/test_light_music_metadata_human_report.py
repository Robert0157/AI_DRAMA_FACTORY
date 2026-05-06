#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.gear1_prod.music_metadata_engine import (  # noqa: E402
    LIGHT_MUSIC_ALBUM_TITLE_SUFFIX,
    MetadataRecord,
    compose_light_music_youtube_seo,
    print_light_music_human_readable_report,
    validate_light_music_metadata_record,
)


class TestLightMusicMetadataHuman(unittest.TestCase):
    def test_validate_ok_minimal(self) -> None:
        creative = "Test Album / 測試"
        at = creative + LIGHT_MUSIC_ALBUM_TITLE_SUFFIX
        tl = [f"Track {i}" for i in range(1, 6)]
        seo = compose_light_music_youtube_seo(at, tl)
        rec = MetadataRecord(
            album_title=at,
            track_list=tl,
            spotify_subgenre="ambient",
            youtube_seo_description=seo,
            generated_at="2026-05-02T12:00:00",
            youtube_copyright="© 2026 R&S Echoes. All rights reserved.",
        )
        errs = validate_light_music_metadata_record(rec, expected_tracks=5)
        self.assertEqual(errs, [])

    def test_validate_fails_bad_suffix(self) -> None:
        rec = MetadataRecord(
            album_title="bad title no suffix",
            track_list=["a"],
            spotify_subgenre="ambient",
            youtube_seo_description="🎵 x\nPerfect for:\n【⏱️ TRACKLIST】\n",
            generated_at="x",
            youtube_copyright="y",
        )
        errs = validate_light_music_metadata_record(rec, expected_tracks=1)
        self.assertTrue(any("固定尾段" in e for e in errs))

    def test_human_report_prints(self) -> None:
        creative = "X / Y"
        at = creative + LIGHT_MUSIC_ALBUM_TITLE_SUFFIX
        tl = [f"T{i}" for i in range(1, 6)]
        seo = compose_light_music_youtube_seo(at, tl)
        rec = MetadataRecord(
            album_title=at,
            track_list=tl,
            spotify_subgenre="ambient",
            youtube_seo_description=seo,
            generated_at="2026-05-02T12:00:00",
            youtube_copyright="© 2026 R&S Echoes. All rights reserved.",
        )
        buf = io.StringIO()
        old = sys.stdout
        try:
            sys.stdout = buf
            print_light_music_human_readable_report(
                rec,
                json_path="Z:/fake/metadata_distrokid_light_music.json",
                distrokid_sheet_path="Z:/fake/DistroKid_Sheet.txt",
                expected_tracks=5,
            )
        finally:
            sys.stdout = old
        out = buf.getvalue()
        self.assertIn("人類可讀摘要", out)
        self.assertIn("驗證通過", out)
        self.assertIn("【曲目】", out)


if __name__ == "__main__":
    unittest.main()
