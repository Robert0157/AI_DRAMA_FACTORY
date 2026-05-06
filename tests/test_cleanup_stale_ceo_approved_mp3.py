#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.maintenance.cleanup_stale_ceo_approved_mp3 import (  # noqa: E402
    mac_synced_path,
    resolve_mastered_wav,
)


class TestCleanupStaleCeo(unittest.TestCase):
    def test_resolve_mastered_wav(self) -> None:
        td = Path(tempfile.mkdtemp())
        try:
            wr = td / "assets" / "audio" / "mastered_tracks" / "lofi"
            wr.mkdir(parents=True)
            mp3 = td / "assets" / "audio" / "ceo_approved_beats" / "lofi" / "My_Track.mp3"
            mp3.parent.mkdir(parents=True, exist_ok=True)
            mp3.write_bytes(b"x")
            m = wr / "My_Track_YT_-16.0LUFS.wav"
            m.write_bytes(b"w")
            got = resolve_mastered_wav(mp3, td, "lofi")
            self.assertIsNotNone(got)
            assert got is not None
            self.assertEqual(got.name, m.name)
        finally:
            import shutil

            shutil.rmtree(td, ignore_errors=True)

    def test_mac_synced_path(self) -> None:
        p = mac_synced_path(Path("Foo_YT_-16.0LUFS.wav"), "light_music")
        self.assertIn("Shorts_audio", str(p).replace("\\", "/"))
        self.assertIn("light_music", str(p))


if __name__ == "__main__":
    unittest.main()
