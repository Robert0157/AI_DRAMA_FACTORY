#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI/CD 驗證腳本 v15.10
驗證 P0+P1 改善項目：
  - #11 廢棄代碼清理
  - #4  統一 JSON 解析
  - #3  LLM 重試佇列
  - #7  Telegram 健康回報器
  - #2  配額策略配置化
  - #9  金鑰安全管理器
"""

import sys
import json
import importlib
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

total = 0
passed = 0
warnings = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    global total, passed, warnings
    total += 1
    if condition:
        print(f"  {PASS} {name} {detail}")
        passed += 1
        return True
    else:
        print(f"  {FAIL} {name} {detail}")
        return False


def warn_check(name: str, condition: bool, detail: str = ""):
    global total, passed, warnings
    total += 1
    if condition:
        print(f"  {PASS} {name} {detail}")
        passed += 1
    else:
        print(f"  {WARN} {name} {detail}")
        warnings += 1


print("=" * 80)
print("🔍 R&S Echoes CI/CD 驗證 v15.10 — P0+P1 改善檢查")
print("=" * 80)

# ============================================================================
# 1. #11 廢棄代碼清理
# ============================================================================
print("\n【#11】廢棄代碼清理")
scripts_dir = _PROJECT_ROOT / "scripts"
gear1 = scripts_dir / "gear1_prod"
deprecated = gear1 / ".deprecated"

check("rs_manager.py 已移至 .deprecated/", not (gear1 / "rs_manager.py").exists())
check("video_processor.py 已移至 .deprecated/", not (gear1 / "video_processor.py").exists())
check("rs_manager.py 在 .deprecated/", (deprecated / "rs_manager.py").exists())
check("video_processor.py 在 .deprecated/", (deprecated / "video_processor.py").exists())

bak_count = len(list(scripts_dir.rglob("*.bak*")))
check("scripts/ 下無 .bak 檔案", bak_count == 0, f"(殘留: {bak_count})")

# ============================================================================
# 2. #4 統一 JSON 解析
# ============================================================================
print("\n【#4】統一 JSON 解析入口")
try:
    from scripts.common.json_parser_utils import parse_llm_json_response, clean_and_parse_json, atomic_write_json
    check("parse_llm_json_response() 可匯入", True)
    check("clean_and_parse_json() 可匯入", True)
    check("atomic_write_json() 可匯入", True)

    # 測試基本解析
    result = parse_llm_json_response('{"key": "value"}', log_context="CI")
    check("基本 JSON 解析", result == {"key": "value"})

    # 測試 Markdown 清洗
    result2 = parse_llm_json_response('```json\n{"a": 1}\n```', log_context="CI")
    check("Markdown 清洗解析", result2 == {"a": 1})

    # 測試未閉合括號補全
    result3 = parse_llm_json_response('{"items": ["a", "b"', max_retries_on_decode_error=1, log_context="CI")
    check("括號補全解析", isinstance(result3, dict))

    # 測試 llm_client.py 不再有 _clean_json_response
    llm_client_src = (scripts_dir / "common" / "llm_client.py").read_text(encoding="utf-8")
    check("llm_client.py 無 _clean_json_response", "_clean_json_response" not in llm_client_src,
          "(已改用 parse_llm_json_response)")
    check("llm_client.py 匯入 parse_llm_json_response",
          "from scripts.common.json_parser_utils import parse_llm_json_response" in llm_client_src)

except Exception as e:
    check("JSON 模組測試", False, f"異常: {e}")

# ============================================================================
# 3. #3 LLM 重試佇列
# ============================================================================
print("\n【#3】LLM 重試佇列")
try:
    from scripts.common.llm_client import (
        LLMRetryQueue, FailedLLMRequest, get_retry_queue,
        generate_with_full_fallback, generate_structured_json,
    )
    check("LLMRetryQueue 可匯入", True)
    check("FailedLLMRequest 可匯入", True)
    check("get_retry_queue() 可匯入", True)
    check("generate_with_full_fallback() 可匯入", True)

    # 測試佇列基本操作
    queue = get_retry_queue()
    check("全域佇列初始化", queue is not None)

    queue.enqueue("minimax", "sys", "usr", "test-model", Exception("test"))
    check("請求入隊", queue.size >= 1, f"(size={queue.size})")

    queue.clear()
    check("佇列清空", queue.size == 0)

except Exception as e:
    check("重試佇列測試", False, f"異常: {e}")

# ============================================================================
# 4. #7 Telegram 健康回報器
# ============================================================================
print("\n【#7】Telegram 健康回報器")
try:
    from scripts.common.telegram_health_reporter import (
        HealthChecker, HealthReport, ChannelHealth,
        TelegramHealthPusher, HealthReportScheduler,
    )
    check("HealthChecker 可匯入", True)
    check("HealthReport 可匯入", True)
    check("ChannelHealth 可匯入", True)

    # 測試頻道健康檢查（不需資料庫）
    ch = ChannelHealth(channel="test")
    check("ChannelHealth.status", ch.status in ["🟢 HEALTHY", "🔴 CRITICAL", "🟡 WARNING"])
    check("ChannelHealth.alerts", isinstance(ch.alerts, list))

    # 測試健康報告生成
    report = HealthReport()
    report.channels["test"] = ch
    summary = report.summary()
    check("HealthReport.summary()", "<b>R&S Echoes 健康報告</b>" in summary)

except Exception as e:
    check("健康回報器測試", False, f"異常: {e}")

# ============================================================================
# 5. #2 配額策略配置化
# ============================================================================
print("\n【#2】配額策略配置化")
config_path = _PROJECT_ROOT / "configs" / "freshness_policy.json"
check("freshness_policy.json 存在", config_path.exists())

if config_path.exists():
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            policy = json.load(f)

        check("JSON 格式有效", True)
        check("_schema 為 v15.10", policy.get("_schema") == "v15.10")

        fp = policy.get("freshness_policy", {})
        check("enforcement 欄位存在", "enforcement" in fp)

        channels = fp.get("channels", {})
        check("lofi 頻道配置存在", "lofi" in channels)
        check("light_music 頻道配置存在", "light_music" in channels)

        for ch_name in ["lofi", "light_music"]:
            ch = channels.get(ch_name, {})
            check(f"{ch_name}.min_new_ratio", "min_new_ratio" in ch)
            check(f"{ch_name}.gen1_ratio", "gen1_ratio" in ch)
            check(f"{ch_name}.target_tracks", "target_tracks" in ch)

        # 驗證配額總和為 1.0
        for ch_name, ch in channels.items():
            total_ratio = ch.get("min_new_ratio", 0) + ch.get("gen1_ratio", 0)
            gen2 = 1.0 - total_ratio
            check(f"{ch_name} 配額合理化 (gen2={gen2:.0%})",
                  total_ratio <= 1.0 and gen2 >= 0)

        # 檢查策略註冊
        strategies = fp.get("quota_strategies", {})
        check("uniform 策略註冊", "uniform" in strategies.get("available", []))
        check("exponential_decay 策略註冊", "exponential_decay" in strategies.get("available", []))
        check("active 策略設定", strategies.get("active") in strategies.get("available", []))

    except json.JSONDecodeError as e:
        check("JSON 解析", False, f"格式錯誤: {e}")

# ============================================================================
# 6. #9 金鑰安全管理器
# ============================================================================
print("\n【#9】金鑰安全管理器")
try:
    from scripts.common.secrets_manager import (
        SecretsManager, get_secrets,
    )
    check("SecretsManager 可匯入", True)
    check("get_secrets() 可匯入", True)

    secrets = get_secrets()
    check("全域單例初始化", secrets is not None)

    # 測試遮蔽功能
    redacted = secrets.redact("NVIDIA_API_KEY=nvapi-1234567890abcdef1234567890abcdef")
    check("金鑰遮蔽 (nvapi-xxx)", "***REDACTED***" in redacted or "nvapi" not in redacted.lower())

    redacted2 = secrets.redact("TTAPI_KEY=sk-abcdefghijklmnopqrstuvwxyz123456")
    check("金鑰遮蔽 (sk-xxx)", "***REDACTED***" in redacted2 or "sk-" not in redacted2.lower())

    # 測試健康檢查
    health = secrets.health_check()
    check("health_check() 回傳字典", isinstance(health, dict))
    check("health_check() 含必要金鑰", all(k in health for k in ["TTAPI_KEY", "NVIDIA_API_KEY", "GEMINI_API_KEY"]))

    # 測試降級讀取
    ttapi = secrets.get("TTAPI_KEY")
    if ttapi:
        check("TTAPI_KEY 可讀取 (金鑰環或 .env)", True)
    else:
        warn_check("TTAPI_KEY 未設定", False, "(測試環境預期)")

except Exception as e:
    check("金鑰管理器測試", False, f"異常: {e}")

# ============================================================================
# 7. 交叉模組相容性
# ============================================================================
print("\n【交叉相容性】")
try:
    # 確保 llm_client 與 json_parser_utils 整合正常
    from scripts.common.llm_client import generate_structured_json
    check("llm_client 匯入 json_parser_utils", True)

    # 確保 env_manager 未引用 ceo_archived_beats
    env_src = (scripts_dir / "common" / "env_manager.py").read_text(encoding="utf-8")
    warn_check("env_manager.py 無 ceo_archived_beats 引用",
               "ceo_archived_beats" not in env_src,
               "(已清除 — 若有引用需手動移除)")

except Exception as e:
    check("交叉相容性", False, f"異常: {e}")

# ============================================================================
# 最終報告
# ============================================================================
print("\n" + "=" * 80)
print(f"📊 驗證結果: {passed}/{total} 通過, {warnings} 警告, {total - passed - warnings} 失敗")
print("=" * 80)

if total - passed - warnings == 0:
    print(f"\n🎉 全部檢查通過！P0+P1 改善已完成驗證。")
    status = "PASS"
elif warnings > 0 and total - passed - warnings == 0:
    print(f"\n⚠️ 所有必要檢查通過，但有 {warnings} 項警告（測試環境預期）。")
    status = "PASS_WITH_WARNINGS"
else:
    print(f"\n❌ 有 {total - passed - warnings} 項失敗，請修復後重新驗證。")
    status = "FAIL"

print(f"\nCI/CD Status: {status}")
sys.exit(0 if status != "FAIL" else 1)
