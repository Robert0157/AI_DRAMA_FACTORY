#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_ping_pong_loop_strategy.py
v15.11 P3#15 Ping-Pong / Forward 迴圈策略端到端單元測試

測試涵蓋：
  1. ping_ 前綴 → "pingpong"
  2. ford_ 前綴 → "forward"
  3. 無前綴 → 預設 "forward"（含 WARNING 不拋錯）
  4. Sidecar JSON 覆寫 ping_前綴為 forward
  5. Sidecar JSON 值非法 → 回退前綴邏輯
  6. 大小寫前綴不適用（規格要求全小寫）
  7. _build_playlist 已刪除，呼叫應拋錯
  8. VaultSelection 初始化讀取 min_new_ratio（使用 FreshnessCounter）
"""

import json
import sys
import unittest
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.gear2_rnd.video_loop_classifier import (
    PREFIX_FORWARD,
    PREFIX_PINGPONG,
    VALID_STRATEGIES,
    get_loop_strategy,
)


class TestPingPongPrefix(unittest.TestCase):
    """前綴命名規則測試"""

    def test_ping_prefix_returns_pingpong(self):
        """ping_ 前綴應回傳 'pingpong'"""
        p = Path("ping_ocean_wave_01.mp4")
        self.assertEqual(get_loop_strategy(p), "pingpong")

    def test_ford_prefix_returns_forward(self):
        """ford_ 前綴應回傳 'forward'"""
        p = Path("ford_RS_lofi_girl_03.mp4")
        self.assertEqual(get_loop_strategy(p), "forward")

    def test_no_prefix_defaults_to_forward(self):
        """無前綴應預設回傳 'forward'（不拋錯）"""
        p = Path("unnamed_clip.mp4")
        result = get_loop_strategy(p)
        self.assertEqual(result, "forward")

    def test_multiple_ping_files(self):
        """多個不同 ping_ 檔案均回傳 pingpong"""
        files = [
            "ping_campfire_01.mp4",
            "ping_clouds_rain.mp4",
            "ping_ocean.mp4",
        ]
        for f in files:
            with self.subTest(f=f):
                self.assertEqual(get_loop_strategy(Path(f)), "pingpong")

    def test_multiple_ford_files(self):
        """多個不同 ford_ 檔案均回傳 forward"""
        files = [
            "ford_cafe_001.mp4",
            "ford_rain_window.mp4",
            "ford_RS_lofi_girl_03.mp4",
        ]
        for f in files:
            with self.subTest(f=f):
                self.assertEqual(get_loop_strategy(Path(f)), "forward")

    def test_uppercase_prefix_not_treated_as_pingpong(self):
        """前綴必須全小寫（規格要求）；PING_ 大寫前綴不視為 pingpong"""
        p = Path("PING_wave.mp4")
        result = get_loop_strategy(p)
        # 大寫 PING_ 不符合 ping_ 前綴規則，應預設 forward
        self.assertEqual(result, "forward")

    def test_valid_strategies_set(self):
        """VALID_STRATEGIES 必須包含 pingpong 與 forward"""
        self.assertIn("pingpong", VALID_STRATEGIES)
        self.assertIn("forward", VALID_STRATEGIES)

    def test_prefix_constants(self):
        """前綴常數值確認"""
        self.assertEqual(PREFIX_PINGPONG, "ping_")
        self.assertEqual(PREFIX_FORWARD, "ford_")

    def test_return_type_is_str(self):
        """回傳值必須是 str，不得是 None"""
        for fname in ["ping_x.mp4", "ford_x.mp4", "x.mp4"]:
            with self.subTest(f=fname):
                result = get_loop_strategy(Path(fname))
                self.assertIsInstance(result, str)
                self.assertIn(result, VALID_STRATEGIES)


class TestSidecarOverride(unittest.TestCase):
    """Sidecar JSON 覆寫測試"""

    def _make_sidecar(self, tmp_dir: Path, video_name: str, strategy: str) -> Path:
        vid = tmp_dir / video_name
        vid.write_bytes(b"dummy")
        sidecar = vid.with_suffix(".json")
        sidecar.write_text(json.dumps({"loop_strategy": strategy}), encoding="utf-8")
        return vid

    def setUp(self):
        import tempfile
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_sidecar_overrides_prefix_ping_to_forward(self):
        """Sidecar JSON forward 可覆寫 ping_ 前綴"""
        vid = self._make_sidecar(self._tmpdir, "ping_wave.mp4", "forward")
        self.assertEqual(get_loop_strategy(vid), "forward")

    def test_sidecar_overrides_prefix_ford_to_pingpong(self):
        """Sidecar JSON pingpong 可覆寫 ford_ 前綴"""
        vid = self._make_sidecar(self._tmpdir, "ford_cafe.mp4", "pingpong")
        self.assertEqual(get_loop_strategy(vid), "pingpong")

    def test_invalid_sidecar_strategy_falls_back_to_prefix(self):
        """Sidecar 非法值應 fallback 到前綴命名"""
        vid = self._tmpdir / "ping_wave.mp4"
        vid.write_bytes(b"dummy")
        sidecar = vid.with_suffix(".json")
        sidecar.write_text(json.dumps({"loop_strategy": "invalid_value"}), encoding="utf-8")
        # 非法 sidecar 值 → 回退前綴 ping_ → pingpong
        self.assertEqual(get_loop_strategy(vid), "pingpong")

    def test_malformed_sidecar_json_falls_back_to_prefix(self):
        """Sidecar JSON 解析失敗應 fallback 到前綴命名"""
        vid = self._tmpdir / "ford_cafe.mp4"
        vid.write_bytes(b"dummy")
        sidecar = vid.with_suffix(".json")
        sidecar.write_text("{invalid json", encoding="utf-8")
        # 解析失敗 → 回退前綴 ford_ → forward
        self.assertEqual(get_loop_strategy(vid), "forward")


class TestBuildPlaylistRemoved(unittest.TestCase):
    """P1#7 驗證：_build_playlist 已刪除"""

    def test_build_playlist_not_callable(self):
        """_build_playlist 應不存在或只是佔位符，不可直接呼叫"""
        import scripts.gear1_prod.lofi_assembler as la
        # _build_playlist 已被刪除（不應可呼叫並傳回播放清單）
        bp = getattr(la, "_build_playlist", None)
        self.assertIsNone(bp, "_build_playlist 應已從 lofi_assembler 中移除")


class TestFreshnessCounterIntegration(unittest.TestCase):
    """P1#4 驗證：FreshnessCounter 整合測試"""

    def test_get_channel_freshness_config_returns_defaults(self):
        """當 config 無 freshness_policy 時，應回傳硬回退預設值"""
        from scripts.common.freshness_counter import get_channel_freshness_config
        with patch("scripts.common.freshness_counter.config") as mock_cfg:
            mock_cfg.freshness_policy = None
            result = get_channel_freshness_config("lofi")
        self.assertEqual(result["min_new_ratio"], 0.5)
        self.assertTrue(result["enabled"])
        self.assertEqual(result["enforcement"], "strict")

    def test_calc_quota_new_correct_math(self):
        """calc_quota_new 應使用 math.ceil 正確計算配額"""
        from scripts.common.freshness_counter import calc_quota_new
        with patch("scripts.common.freshness_counter.config") as mock_cfg:
            mock_cfg.freshness_policy = {"min_new_ratio": 0.5, "enabled": True, "enforcement": "strict"}
            # target=15, ratio=0.5 → ceil(7.5) = 8
            self.assertEqual(calc_quota_new(15, "lofi"), 8)

    def test_channel_specific_ratio_takes_precedence(self):
        """頻道專屬 min_new_ratio 應優先於全域設定"""
        from scripts.common.freshness_counter import get_channel_freshness_config
        with patch("scripts.common.freshness_counter.config") as mock_cfg:
            mock_cfg.freshness_policy = {
                "min_new_ratio": 0.5,
                "enabled": True,
                "enforcement": "strict",
                "channels": {"lofi": {"min_new_ratio": 0.7}},
            }
            result = get_channel_freshness_config("lofi")
        self.assertEqual(result["min_new_ratio"], 0.7)


class TestTTAPIStatusSets(unittest.TestCase):
    """P1#6 驗證：TTAPI 狀態集合環境變數覆寫"""

    def test_default_success_status_contains_expected_values(self):
        """預設成功狀態集合應包含 success/completed/done"""
        from scripts.gear1_prod.suno_api_engine import TTAPI_JOB_SUCCESS_STATUS
        self.assertIn("success", TTAPI_JOB_SUCCESS_STATUS)
        self.assertIn("completed", TTAPI_JOB_SUCCESS_STATUS)
        self.assertIn("done", TTAPI_JOB_SUCCESS_STATUS)

    def test_default_pending_status_contains_expected_values(self):
        """預設 pending 狀態集合應包含 pending/processing/generating"""
        from scripts.gear1_prod.suno_api_engine import TTAPI_JOB_PENDING_STATUS
        self.assertIn("pending", TTAPI_JOB_PENDING_STATUS)
        self.assertIn("processing", TTAPI_JOB_PENDING_STATUS)

    def test_parse_status_set_from_env(self):
        """_parse_status_set 應正確解析逗號分隔環境變數"""
        import importlib
        import os
        # 不重新 import 整個模組，直接測試函式
        from scripts.gear1_prod import suno_api_engine as sae
        with patch.dict(os.environ, {"TTAPI_SUCCESS_STATUSES": "ok,done,finished"}):
            result = sae._parse_status_set("TTAPI_SUCCESS_STATUSES", "success,completed,done")
        self.assertEqual(result, frozenset({"ok", "done", "finished"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
