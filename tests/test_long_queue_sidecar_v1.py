#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common.long_queue_sidecar_v1 import (  # noqa: E402
    build_long_upload_sidecar_v1,
    validate_long_upload_v1,
)


class TestLongQueueSidecarV1(unittest.TestCase):
    def test_build_and_validate_ok(self) -> None:
        mp4 = "R&S_Echoes_light_music_1HrMix_20260501_210000.mp4"
        body = build_long_upload_sidecar_v1(
            mp4_filename=mp4,
            title="Test Title",
            description="Desc line",
            tags=["a", "b"],
            privacy="public",
            mode_auto=True,
        )
        ok, err = validate_long_upload_v1(body, mp4)
        self.assertTrue(ok, err)
        self.assertEqual(err, "")
        self.assertIs(body.get("containsSyntheticMedia"), True)
        self.assertIs(body.get("selfDeclaredMadeForKids"), False)

    def test_video_file_mismatch_fails(self) -> None:
        body = build_long_upload_sidecar_v1(
            mp4_filename="a.mp4",
            title="t",
            description="d",
            tags=[],
            privacy="public",
            mode_auto=True,
        )
        ok, err = validate_long_upload_v1(body, "b.mp4")
        self.assertFalse(ok)
        self.assertIn("video_file", err)

    def test_privacy_illegal(self) -> None:
        mp4 = "x.mp4"
        body = build_long_upload_sidecar_v1(
            mp4_filename=mp4,
            title="t",
            description="d",
            tags=[],
            privacy="public",
            mode_auto=True,
        )
        body["privacy"] = "friends"
        ok, err = validate_long_upload_v1(body, mp4)
        self.assertFalse(ok)
        self.assertIn("privacy", err)

    def test_synthetic_must_be_true(self) -> None:
        mp4 = "a.mp4"
        body = build_long_upload_sidecar_v1(
            mp4_filename=mp4,
            title="t",
            description="d",
            tags=[],
            privacy="public",
            mode_auto=True,
        )
        body["containsSyntheticMedia"] = False
        ok, err = validate_long_upload_v1(body, mp4)
        self.assertFalse(ok)
        self.assertIn("containsSyntheticMedia", err)

    def test_not_made_for_kids_must_be_false(self) -> None:
        mp4 = "a.mp4"
        body = build_long_upload_sidecar_v1(
            mp4_filename=mp4,
            title="t",
            description="d",
            tags=[],
            privacy="public",
            mode_auto=True,
        )
        body["selfDeclaredMadeForKids"] = True
        ok, err = validate_long_upload_v1(body, mp4)
        self.assertFalse(ok)
        self.assertIn("selfDeclaredMadeForKids", err)


if __name__ == "__main__":
    unittest.main()
