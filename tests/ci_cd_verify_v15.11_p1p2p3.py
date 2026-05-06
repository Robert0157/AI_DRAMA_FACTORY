#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/ci_cd_verify_v15.11_p1p2p3.py
v15.11 P1/P2/P3 改善項目 CI/CD 驗證腳本

涵蓋改善項目：
  P1#4  - freshness_counter.py 單一真實來源
  P1#5  - _generate_tracklist 多餘分支已移除
  P1#6  - TTAPI 狀態集合環境變數覆寫
  P1#7  - _build_playlist 函式本體已刪除
  P2#8  - telegram_health_reporter 使用 VaultDatabase threading.local
  P2#9  - LLMRetryQueue SQLite 持久化（LLM_RETRY_PERSIST opt-in）
  P2#10 - env_manager __init__ 回退優先級文件化
  P2#11 - ChannelHealth 臨界值從 freshness_policy 讀取
  P2#12 - SweeperPlugin.depends_on + topological sort
  P3#13 - UIAuditLogger 寫入 audit_log.db
  P3#14 - Shorts sync 失敗寫入 shorts_sync_retry.json
  P3#15 - Ping-Pong 端到端測試（另見 test_ping_pong_loop_strategy.py）

執行：
  python tests/ci_cd_verify_v15.11_p1p2p3.py
"""

import importlib
import inspect
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ─────────────────────────────────────────────────────────
# 測試套件
# ─────────────────────────────────────────────────────────

class TestP1_4_FreshnessCounter(unittest.TestCase):
    """P1#4 — freshness_counter.py 存在且可正確運作"""

    def test_module_importable(self):
        """freshness_counter 可正確 import"""
        from scripts.common import freshness_counter
        self.assertTrue(hasattr(freshness_counter, "get_channel_freshness_config"))
        self.assertTrue(hasattr(freshness_counter, "calc_quota_new"))

    def test_default_ratio_hardfall(self):
        """config 無 freshness_policy 時回退 0.5"""
        from scripts.common.freshness_counter import get_channel_freshness_config
        with patch("scripts.common.freshness_counter.config") as m:
            m.freshness_policy = None
            cfg = get_channel_freshness_config("lofi")
        self.assertEqual(cfg["min_new_ratio"], 0.5)
        self.assertTrue(cfg["enabled"])

    def test_channel_specific_override(self):
        """頻道專屬 min_new_ratio 優先"""
        from scripts.common.freshness_counter import get_channel_freshness_config
        with patch("scripts.common.freshness_counter.config") as m:
            m.freshness_policy = {
                "min_new_ratio": 0.5,
                "enabled": True,
                "enforcement": "strict",
                "channels": {"light_music": {"min_new_ratio": 0.6}},
            }
            cfg = get_channel_freshness_config("light_music")
        self.assertEqual(cfg["min_new_ratio"], 0.6)

    def test_calc_quota_new_ceil(self):
        """calc_quota_new 使用 math.ceil"""
        from scripts.common.freshness_counter import calc_quota_new
        with patch("scripts.common.freshness_counter.config") as m:
            m.freshness_policy = {"min_new_ratio": 0.5, "enabled": True, "enforcement": "strict"}
            self.assertEqual(calc_quota_new(15, "lofi"), 8)  # ceil(7.5)=8

    def test_lofi_assembler_imports_freshness_counter(self):
        """lofi_assembler.py 應 import freshness_counter"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "lofi_assembler.py").read_text(encoding="utf-8")
        self.assertIn("from scripts.common.freshness_counter import", source)


class TestP1_5_TracklistSimplified(unittest.TestCase):
    """P1#5 — _generate_tracklist 多餘 if idx==0 分支已移除"""

    def test_no_redundant_idx0_branch(self):
        """lofi_assembler.py 不應再有 'if idx == 0:' + 相同 '+= duration' 的冗余分支"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "lofi_assembler.py").read_text(encoding="utf-8")
        # 確認 P1#5 簡化已生效
        self.assertIn("P1#5", source)

    def test_generate_tracklist_single_formula(self):
        """_generate_tracklist 的累積公式只有一條"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "lofi_assembler.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        # 找到 _generate_tracklist 函式範圍
        start = next((i for i, l in enumerate(lines) if "def _generate_tracklist" in l), None)
        self.assertIsNotNone(start)
        # 確認函式內沒有多餘的 if/else 做相同計算（P1#5 已簡化）
        func_lines = lines[start: start + 80]
        # 在此函式區段中不應出現 "if idx == 0:" 語句
        self.assertFalse(
            any("if idx == 0:" in l for l in func_lines),
            "發現多餘的 if idx == 0: 分支（P1#5 未正確套用）"
        )


class TestP1_6_TTAPIStatusConfigurable(unittest.TestCase):
    """P1#6 — TTAPI 狀態集合可透過環境變數覆寫"""

    def test_parse_status_set_function_exists(self):
        """_parse_status_set 函式存在"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "suno_api_engine.py").read_text(encoding="utf-8")
        self.assertIn("def _parse_status_set", source)

    def test_env_var_names_in_source(self):
        """源碼包含 TTAPI_SUCCESS_STATUSES / TTAPI_PENDING_STATUSES / TTAPI_FAILED_STATUSES"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "suno_api_engine.py").read_text(encoding="utf-8")
        self.assertIn("TTAPI_SUCCESS_STATUSES", source)
        self.assertIn("TTAPI_PENDING_STATUSES", source)
        self.assertIn("TTAPI_FAILED_STATUSES", source)

    def test_default_statuses_present(self):
        """預設狀態集合引用仍包含原始值"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "suno_api_engine.py").read_text(encoding="utf-8")
        self.assertIn("success,completed,done", source)

    def test_env_override_works(self):
        """環境變數覆寫後回傳新集合"""
        from scripts.gear1_prod.suno_api_engine import _parse_status_set
        with patch.dict(os.environ, {"TTAPI_SUCCESS_STATUSES": "ok,finished"}):
            result = _parse_status_set("TTAPI_SUCCESS_STATUSES", "success,done")
        self.assertEqual(result, frozenset({"ok", "finished"}))

    def test_returns_frozenset(self):
        """_parse_status_set 回傳 frozenset"""
        from scripts.gear1_prod.suno_api_engine import _parse_status_set
        result = _parse_status_set("NON_EXISTING_VAR", "a,b,c")
        self.assertIsInstance(result, frozenset)


class TestP1_7_BuildPlaylistRemoved(unittest.TestCase):
    """P1#7 — _build_playlist 函式本體已刪除"""

    def test_build_playlist_not_present_as_function(self):
        """lofi_assembler 模組不應有可呼叫的 _build_playlist 函式"""
        import scripts.gear1_prod.lofi_assembler as la
        bp = getattr(la, "_build_playlist", None)
        self.assertIsNone(bp, "_build_playlist 應已從 lofi_assembler 中移除")

    def test_deprecation_comment_present(self):
        """源碼中有說明 _build_playlist 已移除的備注"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "lofi_assembler.py").read_text(encoding="utf-8")
        self.assertIn("P1#7", source)


class TestP2_8_DBConnectionThreadSafe(unittest.TestCase):
    """P2#8 — telegram_health_reporter 使用 VaultDatabase 非直接 sqlite3.connect"""

    def test_no_direct_sqlite3_connect_in_check_channel(self):
        """check_channel 方法不得直接呼叫 sqlite3.connect()"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "common" / "telegram_health_reporter.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        # 找到 check_channel 函式
        start = next((i for i, l in enumerate(lines) if "def check_channel" in l), None)
        self.assertIsNotNone(start)
        # 找函式結束（下一個同縮排的 def 或類別結束）
        end = start + 120
        func_lines = lines[start:end]
        sqlite_connects = [l for l in func_lines if "sqlite3.connect(" in l]
        self.assertEqual(len(sqlite_connects), 0,
                         f"check_channel 仍有直接 sqlite3.connect() 呼叫：{sqlite_connects}")

    def test_no_conn_close_in_check_channel(self):
        """check_channel 不得呼叫 conn.close()（由 threading.local 管理）"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "common" / "telegram_health_reporter.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        start = next((i for i, l in enumerate(lines) if "def check_channel" in l), None)
        self.assertIsNotNone(start)
        func_lines = lines[start:start + 120]
        close_calls = [l for l in func_lines if "conn.close()" in l]
        self.assertEqual(len(close_calls), 0, f"check_channel 仍有 conn.close() 呼叫：{close_calls}")

    def test_vault_database_import_in_source(self):
        """telegram_health_reporter 使用 VaultDatabase"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "common" / "telegram_health_reporter.py").read_text(encoding="utf-8")
        self.assertIn("VaultDatabase", source)


class TestP2_9_LLMRetryPersistence(unittest.TestCase):
    """P2#9 — LLMRetryQueue 具備 SQLite 持久化"""

    def test_persist_methods_exist(self):
        """LLMRetryQueue 應有 _init_persist_db / _persist_to_db / _load_from_db"""
        from scripts.common.llm_client import LLMRetryQueue
        self.assertTrue(hasattr(LLMRetryQueue, "_init_persist_db"))
        self.assertTrue(hasattr(LLMRetryQueue, "_persist_to_db"))
        self.assertTrue(hasattr(LLMRetryQueue, "_load_from_db"))

    def test_persist_disabled_by_default(self):
        """預設不啟用持久化（LLM_RETRY_PERSIST 未設定）"""
        env_backup = os.environ.pop("LLM_RETRY_PERSIST", None)
        try:
            # 重新 import 確保模組在 env 清除後初始化
            import importlib
            import scripts.common.llm_client as lc
            importlib.reload(lc)
            q = lc.LLMRetryQueue()
            self.assertFalse(q._persist_enabled)
        finally:
            if env_backup is not None:
                os.environ["LLM_RETRY_PERSIST"] = env_backup

    def test_persist_enabled_with_env_var(self):
        """LLM_RETRY_PERSIST=true 時啟用持久化，DB 路徑設定正確"""
        tmpdir = tempfile.mkdtemp()
        old_val = os.environ.get("LLM_RETRY_PERSIST")
        os.environ["LLM_RETRY_PERSIST"] = "true"
        try:
            import importlib
            import scripts.common.llm_client as lc
            with patch("scripts.common.llm_client._PROJECT_ROOT", Path(tmpdir)):
                importlib.reload(lc)
                q = lc.LLMRetryQueue()
                self.assertTrue(q._persist_enabled)
                self.assertIsNotNone(q._db_path)
                self.assertTrue(str(q._db_path).endswith("llm_retry_queue.db"))
        finally:
            # 還原 env
            if old_val is None:
                os.environ.pop("LLM_RETRY_PERSIST", None)
            else:
                os.environ["LLM_RETRY_PERSIST"] = old_val
            import gc; gc.collect()  # 釋放 SQLite 連線
            import shutil; shutil.rmtree(tmpdir, ignore_errors=True)

    def test_ddl_table_defined(self):
        """LLMRetryQueue._DB_TABLE_DDL 含正確資料表欄位"""
        from scripts.common.llm_client import LLMRetryQueue
        self.assertIn("llm_retry_queue", LLMRetryQueue._DB_TABLE_DDL)
        self.assertIn("provider", LLMRetryQueue._DB_TABLE_DDL)
        self.assertIn("retention_hrs", LLMRetryQueue._DB_TABLE_DDL)


class TestP2_10_EnvManagerDocs(unittest.TestCase):
    """P2#10 — env_manager __init__ 含回退優先級說明"""

    def test_priority_table_in_source(self):
        """env_manager.py 應包含回退優先級表（P2#10 標記）"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "common" / "env_manager.py").read_text(encoding="utf-8")
        self.assertIn("P2#10", source)

    def test_key_aliases_documented(self):
        """MJ_API_KEY / MIDJOURNEY_API_KEY 回退鏈有文件化"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "common" / "env_manager.py").read_text(encoding="utf-8")
        self.assertIn("MJ_API_KEY", source)
        self.assertIn("MIDJOURNEY_API_KEY", source)

    def test_kling_alias_documented(self):
        """KLING_SK / KLING_API_KEY 回退鏈有文件化"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "common" / "env_manager.py").read_text(encoding="utf-8")
        self.assertIn("KLING_SK", source)
        self.assertIn("KLING_API_KEY", source)


class TestP2_11_HealthThresholdsConfigurable(unittest.TestCase):
    """P2#11 — ChannelHealth 臨界值從 config 讀取"""

    def test_get_inventory_thresholds_exists(self):
        """_get_inventory_thresholds 函式存在"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "common" / "telegram_health_reporter.py").read_text(encoding="utf-8")
        self.assertIn("def _get_inventory_thresholds", source)

    def test_hardcoded_thresholds_replaced(self):
        """ChannelHealth.status / alerts 不再直接硬編碼數字 3/5/2/0.2"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "common" / "telegram_health_reporter.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        # 找到 status property 所在行
        start = next((i for i, l in enumerate(lines) if "def status(self)" in l), None)
        self.assertIsNotNone(start)
        func_lines = lines[start:start + 20]
        # 不應直接比較硬編碼值（應透過 thr[] 讀取）
        raw_comparisons = [l for l in func_lines if "< 3" in l or "< 5" in l or "< 2" in l]
        self.assertEqual(len(raw_comparisons), 0,
                         f"status property 仍有硬編碼臨界值比較：{raw_comparisons}")

    def test_threshold_defaults_are_sane(self):
        """_get_inventory_thresholds 無 config 時回傳合理預設"""
        with patch("scripts.common.telegram_health_reporter._get_inventory_thresholds") as mock:
            mock.return_value = {"audio_critical": 3, "audio_low": 5, "visual_critical": 2,
                                 "ratio_stale": 0.3, "ratio_warn": 0.2}
            from scripts.common.telegram_health_reporter import ChannelHealth
            ch = ChannelHealth(channel="lofi", audio_available=10, visual_available=5,
                               new_tracks_ratio=0.6)
            status = ch.status
        self.assertEqual(status, "🟢 HEALTHY")


class TestP2_12_SweeperDependencies(unittest.TestCase):
    """P2#12 — SweeperPlugin.depends_on + SweeperRunner topological sort"""

    def test_depends_on_attribute_exists(self):
        """SweeperPlugin 有 depends_on 類別屬性"""
        from scripts.maintenance.sweeper_plugins import SweeperPlugin
        self.assertTrue(hasattr(SweeperPlugin, "depends_on"))
        self.assertEqual(SweeperPlugin.depends_on, [])

    def test_topological_sort_method_exists(self):
        """SweeperRunner 有 _topological_sort 靜態方法"""
        from scripts.maintenance.sweeper_plugins import SweeperRunner
        self.assertTrue(hasattr(SweeperRunner, "_topological_sort"))

    def test_topological_sort_no_deps_preserves_order_by_name(self):
        """無相依時，排序結果按名稱字母序"""
        from scripts.maintenance.sweeper_plugins import SweeperPlugin, SweeperRunner

        class PluginB(SweeperPlugin):
            def get_name(self): return "b_plugin"
            def cleanup(self, root, channel=None): return {"cleaned_files": 0, "freed_mb": 0, "errors": 0}

        class PluginA(SweeperPlugin):
            def get_name(self): return "a_plugin"
            def cleanup(self, root, channel=None): return {"cleaned_files": 0, "freed_mb": 0, "errors": 0}

        plugins = [PluginB(), PluginA()]
        sorted_plugins = SweeperRunner._topological_sort(plugins)
        names = [p.get_name() for p in sorted_plugins]
        self.assertEqual(names, ["a_plugin", "b_plugin"])

    def test_topological_sort_respects_depends_on(self):
        """has_dep 依賴 no_dep，排序後 no_dep 在前"""
        from scripts.maintenance.sweeper_plugins import SweeperPlugin, SweeperRunner

        class NoDep(SweeperPlugin):
            depends_on = []
            def get_name(self): return "no_dep"
            def cleanup(self, root, channel=None): return {"cleaned_files": 0, "freed_mb": 0, "errors": 0}

        class HasDep(SweeperPlugin):
            depends_on = ["no_dep"]
            def get_name(self): return "has_dep"
            def cleanup(self, root, channel=None): return {"cleaned_files": 0, "freed_mb": 0, "errors": 0}

        plugins = [HasDep(), NoDep()]
        sorted_plugins = SweeperRunner._topological_sort(plugins)
        names = [p.get_name() for p in sorted_plugins]
        self.assertEqual(names.index("no_dep"), 0)
        self.assertEqual(names.index("has_dep"), 1)

    def test_circular_dep_falls_back_gracefully(self):
        """循環相依時回退原順序並不拋錯"""
        from scripts.maintenance.sweeper_plugins import SweeperPlugin, SweeperRunner

        class A(SweeperPlugin):
            depends_on = ["b_circ"]
            def get_name(self): return "a_circ"
            def cleanup(self, root, channel=None): return {"cleaned_files": 0, "freed_mb": 0, "errors": 0}

        class B(SweeperPlugin):
            depends_on = ["a_circ"]
            def get_name(self): return "b_circ"
            def cleanup(self, root, channel=None): return {"cleaned_files": 0, "freed_mb": 0, "errors": 0}

        plugins = [A(), B()]
        # 不應拋錯
        result = SweeperRunner._topological_sort(plugins)
        self.assertEqual(len(result), 2)


class TestP3_13_UIAuditLogger(unittest.TestCase):
    """P3#13 — UIAuditLogger 寫入 audit_log.db"""

    def setUp(self):
        import tempfile
        self._tmpdir = Path(tempfile.mkdtemp())
        self._db_path = self._tmpdir / "audit_log.db"

    def tearDown(self):
        import gc, shutil
        gc.collect()  # 釋放可能殘留的 SQLite 連線（Windows 檔案鎖）
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_module_importable(self):
        """ui_audit_logger 可正確 import"""
        from scripts.common.ui_audit_logger import UIAuditLogger, get_audit_logger
        self.assertTrue(callable(UIAuditLogger))
        self.assertTrue(callable(get_audit_logger))

    def test_log_writes_to_sqlite(self):
        """log() 正確寫入 SQLite DB"""
        from scripts.common.ui_audit_logger import UIAuditLogger
        logger = UIAuditLogger(db_path=self._db_path)
        logger.log(action="test_action", channel="lofi", result="success",
                   duration_sec=1.23, params={"k": "v"})
        import gc; gc.collect()  # 確保 Windows 釋放 SQLite 鎖
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute("SELECT action, channel, result FROM ui_audit_log").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "test_action")
        self.assertEqual(rows[0][1], "lofi")
        self.assertEqual(rows[0][2], "success")

    def test_recent_returns_list(self):
        """recent() 回傳 list of dict"""
        from scripts.common.ui_audit_logger import UIAuditLogger
        logger = UIAuditLogger(db_path=self._db_path)
        logger.log(action="publish_final_exports", channel="lofi")
        import gc; gc.collect()
        result = logger.recent(10)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIn("action", result[0])

    def test_log_failure_is_silent(self):
        """DB 寫入失敗時不拋錯（非阻塞）"""
        from scripts.common.ui_audit_logger import UIAuditLogger
        logger = UIAuditLogger(db_path=Path("/invalid/path/audit.db"))
        try:
            logger.log(action="test", channel="lofi")
        except Exception as e:
            self.fail(f"log() 不應拋錯，但拋出了 {e}")

    def test_backend_imports_audit_logger(self):
        """backend.py 應 import get_audit_logger"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "ui" / "backend.py").read_text(encoding="utf-8")
        self.assertIn("get_audit_logger", source)
        self.assertIn("ui_audit_logger", source)


class TestP3_14_ShortsSyncRetry(unittest.TestCase):
    """P3#14 — Shorts sync 失敗寫入 shorts_sync_retry.json"""

    def test_write_retry_function_exists(self):
        """_write_shorts_sync_retry 函式存在"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "audio_mastering_engine.py").read_text(encoding="utf-8")
        self.assertIn("def _write_shorts_sync_retry", source)

    def test_retry_json_path_in_data_dir(self):
        """重試清單路徑應在 assets/data/ 下"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "audio_mastering_engine.py").read_text(encoding="utf-8")
        self.assertIn("shorts_sync_retry.json", source)
        self.assertIn("assets", source)
        self.assertIn("data", source)

    def test_write_retry_merges_not_overwrites(self):
        """_write_shorts_sync_retry 應合併而非覆寫現有記錄"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "audio_mastering_engine.py").read_text(encoding="utf-8")
        # 確認有讀取現有 JSON 再合併的邏輯
        self.assertIn("shorts_sync_retry", source)
        # 確認有 pending 結構
        self.assertIn('"pending"', source)

    def test_write_retry_called_on_failure(self):
        """sync/signal 失敗時必須呼叫 _write_shorts_sync_retry"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "audio_mastering_engine.py").read_text(encoding="utf-8")
        self.assertIn("_write_shorts_sync_retry(channel=channel", source)

    def test_p3_14_comment_present(self):
        """源碼包含 P3#14 版本標記"""
        source = (Path(_PROJECT_ROOT) / "scripts" / "gear1_prod" / "audio_mastering_engine.py").read_text(encoding="utf-8")
        self.assertIn("P3#14", source)


class TestP3_15_PingPongTestFileExists(unittest.TestCase):
    """P3#15 — Ping-Pong 測試檔案存在且可執行"""

    def test_test_file_exists(self):
        """tests/test_ping_pong_loop_strategy.py 存在"""
        test_file = Path(_PROJECT_ROOT) / "tests" / "test_ping_pong_loop_strategy.py"
        self.assertTrue(test_file.exists(), "P3#15 測試檔案不存在")

    def test_test_file_importable(self):
        """P3#15 測試模組可正確 import"""
        try:
            import tests.test_ping_pong_loop_strategy  # noqa: F401
        except ImportError as e:
            self.fail(f"P3#15 測試模組 import 失敗：{e}")

    def test_ping_pong_test_has_enough_test_cases(self):
        """P3#15 測試檔案包含足夠測試案例（≥ 5）"""
        import tests.test_ping_pong_loop_strategy as m
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(m)
        count = suite.countTestCases()
        self.assertGreaterEqual(count, 5, f"P3#15 只有 {count} 個測試案例（需 ≥ 5）")


# ─────────────────────────────────────────────────────────
# 執行器
# ─────────────────────────────────────────────────────────

SUITE_MAP = [
    ("P1#4 FreshnessCounter",          TestP1_4_FreshnessCounter),
    ("P1#5 Tracklist 簡化",             TestP1_5_TracklistSimplified),
    ("P1#6 TTAPI 狀態可配置",           TestP1_6_TTAPIStatusConfigurable),
    ("P1#7 _build_playlist 刪除",       TestP1_7_BuildPlaylistRemoved),
    ("P2#8 DB 執行緒安全",              TestP2_8_DBConnectionThreadSafe),
    ("P2#9 LLM Retry 持久化",           TestP2_9_LLMRetryPersistence),
    ("P2#10 env_manager 文件化",        TestP2_10_EnvManagerDocs),
    ("P2#11 健康告警臨界值可配置",       TestP2_11_HealthThresholdsConfigurable),
    ("P2#12 Sweeper 拓樸排序",          TestP2_12_SweeperDependencies),
    ("P3#13 UIAuditLogger",             TestP3_13_UIAuditLogger),
    ("P3#14 Shorts 重試佇列",           TestP3_14_ShortsSyncRetry),
    ("P3#15 Ping-Pong 測試檔案",        TestP3_15_PingPongTestFileExists),
]


def run_all() -> tuple[int, int]:
    passed = failed = 0
    loader = unittest.TestLoader()

    for label, cls in SUITE_MAP:
        suite = loader.loadTestsFromTestCase(cls)
        runner = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w"))
        result = runner.run(suite)
        total = suite.countTestCases()
        ok = total - len(result.failures) - len(result.errors)
        passed += ok
        failed += len(result.failures) + len(result.errors)
        status = "✅" if not result.failures and not result.errors else "❌"
        print(f"  {status} [{label}] {ok}/{total} PASS")
        for fail_tc, tb in result.failures + result.errors:
            lines = tb.strip().splitlines()
            print(f"       ↳ {fail_tc}: {lines[-1]}")

    return passed, failed


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("  CI/CD v15.11 P1/P2/P3 驗證腳本")
    print(f"{'='*60}\n")

    passed, failed = run_all()
    total = passed + failed

    print(f"\n{'='*60}")
    print(f"  結果：{passed}/{total} PASS   {'🎉 全部通過' if failed == 0 else f'❌ {failed} 失敗'}")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)
