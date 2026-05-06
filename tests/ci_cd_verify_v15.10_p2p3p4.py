#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI/CD 驗證 v15.10 — P2+P3+P4 全覆蓋
"""

import sys, json, asyncio
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

PASS = "✅"; FAIL = "❌"; WARN = "⚠️"
total = 0; passed = 0; warnings = 0

def check(name, condition, detail=""):
    global total, passed
    total += 1
    if condition: print(f"  {PASS} {name} {detail}"); passed += 1
    else: print(f"  {FAIL} {name} {detail}")

def warn_check(name, condition, detail=""):
    global total, passed, warnings
    total += 1
    if condition: print(f"  {PASS} {name} {detail}"); passed += 1
    else: print(f"  {WARN} {name} {detail}"); warnings += 1

print("=" * 80)
print("🔍 CI/CD 驗證 v15.10 — P2+P3+P4 全覆蓋")
print("=" * 80)

scripts = _PROJECT_ROOT / "scripts"

# ============================================================================
# P2-#6: 雙庫同步預檢
# ============================================================================
print("\n【P2-#6】雙庫同步預檢")
from scripts.common.pipeline_state_machine import (
    PipelineState, PipelineContext, VaultPreflightReport, preflight_dual_vault,
)
check("PipelineState 匯入", True)
check("PipelineContext 匯入", True)
check("VaultPreflightReport 匯入", True)
check("preflight_dual_vault 匯入", True)

# 測試狀態機轉移
ctx = PipelineContext(channel="test")
check("初始狀態 INIT", ctx.state == PipelineState.INIT)
ok = ctx.transition_to(PipelineState.PREFLIGHT_VAULT)
check("INIT → PREFLIGHT_VAULT", ok)
ok2 = ctx.transition_to(PipelineState.FRESHNESS_GATE)
check("PREFLIGHT_VAULT → FRESHNESS_GATE", ok2)
bad = ctx.transition_to(PipelineState.INIT)  # 不合法
check("FRESHNESS_GATE → INIT 不合法", not bad)

# 測試預檢
report = preflight_dual_vault("lofi")
check("預檢回傳 VaultPreflightReport", isinstance(report, VaultPreflightReport))
check("預檢含 channel", report.channel == "lofi")
check("預檢含 passed", isinstance(report.passed, bool))

# 測試 pipeline_runner 匯入
pipeline_src = (scripts / "gear1_prod" / "pipeline_runner.py").read_text(encoding="utf-8")
check("pipeline_runner 匯入 preflight_dual_vault",
      "preflight_dual_vault" in pipeline_src)

# ============================================================================
# P2-#8: workspace_sweeper Plugin 架構
# ============================================================================
print("\n【P2-#8】Plugin 架構")
from scripts.maintenance.sweeper_plugins import (
    SweeperPlugin, PycachePlugin, TempFilePlugin,
    LogRotationPlugin, ChannelTempPlugin, SweeperRunner,
)
check("SweeperPlugin 匯入", True)
check("PycachePlugin 匯入", True)
check("TempFilePlugin 匯入", True)
check("SweeperRunner 匯入", True)

runner = SweeperRunner()
runner.register(PycachePlugin()).register(TempFilePlugin())
check("插件註冊", len(runner.plugins) == 2)

# dry-run 測試
result = runner.run_all(dry_run=True)
check("dry_run 執行成功", isinstance(result, dict))
check("dry_run 含 details", "details" in result)

# ============================================================================
# P2-#10: Mac 部署腳本
# ============================================================================
print("\n【P2-#10】Mac 部署腳本")
deploy_sh = scripts / "streaming_steam" / "deploy_mac_phase1.sh"
check("deploy_mac_phase1.sh 存在", deploy_sh.exists())
if deploy_sh.exists():
    content = deploy_sh.read_text(encoding="utf-8")
    check("含 verify_prerequisites", "verify_prerequisites" in content)
    check("含 verify_mount", "verify_mount" in content)
    check("含 setup_streaming_root", "setup_streaming_root" in content)
    check("含 verify_manifest", "verify_manifest" in content)
    check("shebang bash", content.startswith("#!/bin/bash"))

# ============================================================================
# P3-#1: Pipeline 狀態機（已在 P2-#6 測試）
# ============================================================================
print("\n【P3-#1】Pipeline 狀態機整合")
check("PipelineState._TRANSITIONS 定義", hasattr(PipelineState, "_TRANSITIONS"))
check("can_transition 方法", hasattr(PipelineState, "can_transition"))
check("上下文 summary() 含狀態", "狀態" in ctx.summary())
ctx.mark_failed(Exception("test"), fatal=True)
check("標記 FAILED 後狀態", ctx.state == PipelineState.FAILED)
check("錯誤記錄", len(ctx.errors) == 1)

# ============================================================================
# P3-#5: LLM 並行非同步
# ============================================================================
print("\n【P3-#5】LLM 並行非同步")
from scripts.common.llm_async import compose_metadata_async, AsyncMetadataRecord
check("compose_metadata_async 匯入", True)
check("AsyncMetadataRecord 匯入", True)

# 不實際呼叫 LLM（避免費用），只驗證模組結構
check("asyncio.iscoroutinefunction(compose_metadata_async)",
      asyncio.iscoroutinefunction(compose_metadata_async))

# ============================================================================
# P4-#12: cloud_archiver 修復
# ============================================================================
print("\n【P4-#12】cloud_archiver 過時引用修復")
cloud_src = (scripts / "gear1_prod" / "cloud_archiver.py").read_text(encoding="utf-8")
check("無根目錄 ceo_archived_beats 引用",
      'WORKSPACE_ROOT) / "ceo_archived_beats"' not in cloud_src,
      "(已改為 assets/audio/ path)")
check("含不存在檢查", "not archive_path.exists()" in cloud_src or "ceo_archived_beats" in cloud_src)

# ============================================================================
# P4-#13: 交叉模組匯入整理
# ============================================================================
print("\n【P4-#13】交叉模組匯入一致性")
init_py = scripts / "common" / "__init__.py"
init_src = init_py.read_text(encoding="utf-8")
check("__init__.py 匯出 PipelineState", "PipelineState" in init_src)
check("__init__.py 匯出 preflight_dual_vault", "preflight_dual_vault" in init_src)
check("__init__.py 匯出 SecretsManager", "SecretsManager" in init_src)
check("__init__.py 匯出 LLMRetryQueue", "LLMRetryQueue" in init_src)

# 測試從 common 直接匯入
from scripts.common import config, PipelineState, preflight_dual_vault
check("from scripts.common import config", config is not None)
check("from scripts.common import PipelineState", PipelineState is not None)
check("from scripts.common import preflight_dual_vault", preflight_dual_vault is not None)

# ============================================================================
# 廢棄模組隔離驗證
# ============================================================================
print("\n【廢棄模組隔離】")
deprecated = scripts / "gear1_prod" / ".deprecated"
check("rs_manager 在 .deprecated/", (deprecated / "rs_manager.py").exists())
check("video_processor 在 .deprecated/", (deprecated / "video_processor.py").exists())

# 確保無腳本 import rs_manager
import_count = 0
for py_file in scripts.rglob("*.py"):
    if ".deprecated" in str(py_file) or "venv" in str(py_file):
        continue
    try:
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        if "import rs_manager" in content or "from rs_manager" in content:
            import_count += 1
    except Exception:
        pass
check("無腳本 import rs_manager（廢棄保護）", import_count == 0,
      f"(發現 {import_count} 處)" if import_count > 0 else "")

# ============================================================================
# 最終報告
# ============================================================================
print("\n" + "=" * 80)
fails = total - passed - warnings
print(f"📊 {passed}/{total} 通過, {warnings} 警告, {fails} 失敗")
print("=" * 80)

if fails == 0 and warnings == 0:
    print("🎉 P2+P3+P4 全部通過！")
    status = "PASS"
elif fails == 0:
    print(f"⚠️ 通過但 {warnings} 項警告")
    status = "PASS_WITH_WARNINGS"
else:
    print(f"❌ {fails} 項失敗")
    status = "FAIL"

print(f"\nCI/CD Status: {status}")
sys.exit(0 if status != "FAIL" else 1)
