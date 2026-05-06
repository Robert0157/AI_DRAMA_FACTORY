#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common/secrets_manager.py
v15.10 金鑰安全管理器 — 作業系統金鑰環整合。

功能：
- 從 OS 原生金鑰環讀取 API 金鑰（不落地明文於 .env）
- 支援 macOS Keychain / Windows Credential Manager
- 自動偵測並遮蔽日誌中的敏感資訊
- 若金鑰環不可用，降級為 .env 讀取（含警告）

使用方式：
    from scripts.common.secrets_manager import SecretsManager
    secrets = SecretsManager()
    ttapi_key = secrets.get("TTAPI_KEY")
    safe_log = secrets.redact("Log with TTAPI_KEY=sk-abc123")
"""

import os
import re
import sys
import platform
from pathlib import Path
from typing import Optional, Dict, List
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 確保 .env 已載入（作為降級方案）
load_dotenv()

# ============================================================================
# 敏感金鑰名稱清單（用於自動遮蔽）
# ============================================================================

_SENSITIVE_KEY_PATTERNS = [
    "TTAPI_KEY",
    "NVIDIA_API_KEY",
    "GEMINI_API_KEY",
    "ZHIPUAI_API_KEY",
    "KLING_AK",
    "KLING_SK",
    "MJ_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "NGROK_AUTHTOKEN",
]

# 常見金鑰前綴（用於正則匹配）
_SENSITIVE_VALUE_PATTERNS = [
    r'(?:nvapi|sk-|AKIA|ghp_|glpat-|xox[bpras]-)[A-Za-z0-9_\-]{20,}',
]


# ============================================================================
# 平台抽象層
# ============================================================================


class _KeychainBackend:
    """金鑰環後端基底類別"""

    def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    def set(self, key: str, value: str) -> bool:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return False


class _MacKeychainBackend(_KeychainBackend):
    """macOS Keychain 後端"""

    @property
    def available(self) -> bool:
        return platform.system() == "Darwin"

    def get(self, key: str) -> Optional[str]:
        import subprocess
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", f"AI_Drama_Factory_{key}", "-w"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def set(self, key: str, value: str) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["security", "add-generic-password", "-s", f"AI_Drama_Factory_{key}",
                 "-a", os.getenv("USER", "robert"), "-w", value, "-U"],
                capture_output=True, timeout=5
            )
            return True
        except Exception:
            return False


class _WindowsCredentialBackend(_KeychainBackend):
    """Windows Credential Manager 後端"""

    @property
    def available(self) -> bool:
        return platform.system() == "Windows"

    def get(self, key: str) -> Optional[str]:
        """使用 PowerShell 讀取 Credential Manager"""
        import subprocess
        try:
            ps_cmd = (
                f'$cred = Get-StoredCredential -Target "AI_Drama_Factory_{key}" -ErrorAction SilentlyContinue;'
                f'if ($cred) {{ $cred.GetNetworkCredential().Password }}'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            if output and result.returncode == 0:
                return output
        except Exception:
            pass
        return None

    def set(self, key: str, value: str) -> bool:
        import subprocess
        try:
            ps_cmd = (
                f'$cred = New-Object System.Management.Automation.PSCredential('
                f'"AI_Drama_Factory_{key}", (ConvertTo-SecureString "{value}" -AsPlainText -Force));'
                f'Install-Module -Name CredentialManager -Force -Scope CurrentUser -ErrorAction SilentlyContinue;'
                f'New-StoredCredential -Target "AI_Drama_Factory_{key}" -Credential $cred -Persist LocalMachine'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, timeout=15
            )
            return True
        except Exception:
            return False


class _EnvFallbackBackend(_KeychainBackend):
    """環境變數降級後端（.env 檔案）"""

    @property
    def available(self) -> bool:
        return True

    def get(self, key: str) -> Optional[str]:
        return os.getenv(key)

    def set(self, key: str, value: str) -> bool:
        os.environ[key] = value
        return True


# ============================================================================
# 安全管理器
# ============================================================================


class SecretsManager:
    """
    v15.10 金鑰安全管理器。
    
    優先使用 OS 原生金鑰環，不可用時降級為 .env 讀取（含警告）。
    支援自動遮蔽日誌中的敏感值。
    """

    def __init__(self):
        self._backend = self._detect_backend()
        self._cache: Dict[str, Optional[str]] = {}
        self._warned_keys: set = set()

    def _detect_backend(self) -> _KeychainBackend:
        """自動偵測最安全的後端"""
        for backend_cls in [_MacKeychainBackend, _WindowsCredentialBackend]:
            backend = backend_cls()
            if backend.available:
                print(f"🔐 [SecretsManager] 使用金鑰環後端: {backend_cls.__name__}")
                return backend

        print("⚠️ [SecretsManager] 金鑰環不可用，降級為 .env 讀取（金鑰為明文存儲）")
        return _EnvFallbackBackend()

    def get(self, key: str) -> Optional[str]:
        """
        取得 API 金鑰。
        
        優先級：金鑰環 → .env（含快取以減少重複查詢）
        """
        if key in self._cache:
            return self._cache[key]

        value = self._backend.get(key)
        if value is None:
            value = os.getenv(key)

        self._cache[key] = value

        if value is not None and not isinstance(self._backend, _EnvFallbackBackend):
            # 金鑰環成功讀取，不需警告
            pass
        elif value is not None and isinstance(self._backend, _EnvFallbackBackend):
            if key not in self._warned_keys:
                print(f"⚠️ [SecretsManager] {key} 從 .env 明文讀取（建議遷移至金鑰環）")
                self._warned_keys.add(key)

        return value

    def set(self, key: str, value: str) -> bool:
        """寫入金鑰到金鑰環"""
        self._cache[key] = value
        return self._backend.set(key, value)

    def redact(self, text: str) -> str:
        """
        自動遮蔽文字中的敏感金鑰值。
        
        Example:
            secrets.redact("Log: NVIDIA_API_KEY=nvapi-abc123def456")
            # → "Log: NVIDIA_API_KEY=***REDACTED***"
        """
        if not text:
            return text

        result = text

        # 方法 1：根據已知金鑰值遮蔽
        for key in _SENSITIVE_KEY_PATTERNS:
            val = self.get(key)
            if val and len(val) > 8:
                result = result.replace(val, "***REDACTED***")

        # 方法 2：根據常見金鑰格式正則遮蔽
        for pattern in _SENSITIVE_VALUE_PATTERNS:
            result = re.sub(pattern, "***REDACTED***", result)

        return result

    def list_configured(self) -> List[str]:
        """列出所有已在金鑰環中有值的金鑰名稱"""
        configured = []
        for key in _SENSITIVE_KEY_PATTERNS:
            val = self.get(key)
            if val:
                configured.append(key)
        return configured

    def health_check(self) -> Dict[str, bool]:
        """
        健康檢查：回報每個金鑰的設定狀態。
        """
        status = {}
        for key in _SENSITIVE_KEY_PATTERNS:
            val = self.get(key)
            status[key] = val is not None and len(val) > 8
        return status


# ============================================================================
# 全域單例
# ============================================================================

_secrets_instance: Optional[SecretsManager] = None


def get_secrets() -> SecretsManager:
    """取得全域 SecretsManager 單例"""
    global _secrets_instance
    if _secrets_instance is None:
        _secrets_instance = SecretsManager()
    return _secrets_instance


# ============================================================================
# CLI 入口（用於獨立測試）
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="R&S Echoes 金鑰安全管理器")
    parser.add_argument("--check", action="store_true", help="健康檢查：列出所有金鑰狀態")
    parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="寫入金鑰到金鑰環")
    parser.add_argument("--redact", type=str, help="測試文字遮蔽功能")
    args = parser.parse_args()

    secrets = get_secrets()

    if args.check:
        print("🔐 金鑰健康檢查：")
        for key, ok in secrets.health_check().items():
            icon = "✅" if ok else "❌"
            print(f"  {icon} {key}")

    if args.set:
        key, val = args.set
        ok = secrets.set(key, val)
        print(f"{'✅' if ok else '❌'} {key} {'已寫入金鑰環' if ok else '寫入失敗'}")

    if args.redact:
        print(f"原始: {args.redact}")
        print(f"遮蔽: {secrets.redact(args.redact)}")
