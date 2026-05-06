#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common.tracklist_pick import pick_tracklist_txt_for_mp4  # noqa: E402


class TestTracklistPick(unittest.TestCase):
    def test_prefers_stem_match_over_mtime_when_multiple_mp4(self) -> None:
        """目錄內有較新 MP4 時，仍以 stem 對應正確 Tracklist，不依賴僅 mtime。"""
        td = Path(tempfile.mkdtemp())
        try:
            # 舊 run：151011 對應 Tracklist_1510
            (td / "Tracklist_20260502_1510.txt").write_text(
                "【x】\n" + "=" * 60 + "\n00:00 - Alpha\n" + "=" * 60 + "\n",
                encoding="utf-8",
            )
            # 較新 run
            (td / "Tracklist_20260502_1712.txt").write_text(
                "【x】\n" + "=" * 60 + "\n00:00 - Beta\n" + "=" * 60 + "\n",
                encoding="utf-8",
            )
            old_mp4 = td / "R&S_Echoes_light_music_1HrMix_20260502_151011.mp4"
            new_mp4 = td / "R&S_Echoes_light_music_1HrMix_20260502_171217.mp4"
            old_mp4.write_bytes(b"a")
            new_mp4.write_bytes(b"b")
            # 讓「較新」MP4 的 mtime 嚴格較晚（跨 tick）
            import os
            import time

            st_o = old_mp4.stat()
            os.utime(new_mp4, (st_o.st_mtime + 100, st_o.st_mtime + 100))
            time.sleep(0.05)
            os.utime(old_mp4, (st_o.st_mtime, st_o.st_mtime))

            picked = pick_tracklist_txt_for_mp4(td, old_mp4)
            self.assertIsNotNone(picked)
            assert picked is not None
            self.assertEqual(picked.name, "Tracklist_20260502_1510.txt")

            picked_new = pick_tracklist_txt_for_mp4(td, new_mp4)
            self.assertIsNotNone(picked_new)
            assert picked_new is not None
            self.assertEqual(picked_new.name, "Tracklist_20260502_1712.txt")
        finally:
            import shutil

            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
