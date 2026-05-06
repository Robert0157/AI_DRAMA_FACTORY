#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common.youtube_longform_tags import (  # noqa: E402
    LIGHT_MUSIC_LONGFORM_TAGS_FIXED,
    merge_longform_tags,
)


class TestYoutubeLongformTags(unittest.TestCase):
    def test_light_music_fixed_count(self) -> None:
        self.assertEqual(len(LIGHT_MUSIC_LONGFORM_TAGS_FIXED), 21)

    def test_light_music_merge_keeps_fixed_first_and_dedupes(self) -> None:
        merged = merge_longform_tags(
            "light_music",
            ["AmbientMusic", "ExtraTag", "#NatureSounds"],
        )
        self.assertEqual(merged[0], "AmbientMusic")
        self.assertIn("ExtraTag", merged)
        # NatureSounds only once (duplicate removed)
        self.assertEqual(merged.count("NatureSounds"), 1)


if __name__ == "__main__":
    unittest.main()
