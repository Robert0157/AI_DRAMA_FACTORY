#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/maintenance/sweeper_plugins.py
v15.10 workspace_sweeper Plugin 架構 — 可插拔清理策略。

取代 workspace_sweeper.py 中重複的 delete_directory / purge_files 模式。
新增清理策略只需實作 SweeperPlugin，無需修改主邏輯。
"""

from __future__ import annotations

import sys
import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, List

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ============================================================================
# Plugin 基底類別
# ============================================================================

class SweeperPlugin(ABC):
    """清理策略插件基底類別"""

    # v15.11 P2#12：宣告依賴的前置插件名稱；SweeperRunner.run_all() 依此進行拓樸排序
    depends_on: list = []

    @abstractmethod
    def get_name(self) -> str:
        """回傳插件名稱（用於日誌）"""
        ...

    @abstractmethod
    def cleanup(self, target_root: Path, channel: Optional[str] = None) -> Dict[str, int]:
        """
        執行清理。

        Returns:
            {"cleaned_files": N, "freed_mb": M, "errors": E}
        """
        ...

    def dry_run(self, target_root: Path, channel: Optional[str] = None) -> List[str]:
        """預覽將被清理的檔案（不回傳實際操作）"""
        return []


# ============================================================================
# 內建插件
# ============================================================================

class PycachePlugin(SweeperPlugin):
    """清理 __pycache__ 目錄"""

    def get_name(self) -> str:
        return "__pycache__"

    def cleanup(self, target_root: Path, channel: Optional[str] = None) -> Dict[str, int]:
        result = {"cleaned_files": 0, "freed_mb": 0, "errors": 0}
        for pycache in target_root.rglob("__pycache__"):
            if pycache.is_dir() and "venv" not in str(pycache):
                try:
                    size = sum(f.stat().st_size for f in pycache.rglob("*") if f.is_file())
                    shutil.rmtree(pycache)
                    result["cleaned_files"] += 1
                    result["freed_mb"] += int(size / (1024 * 1024))
                except Exception:
                    result["errors"] += 1
        return result

    def dry_run(self, target_root: Path, channel: Optional[str] = None) -> List[str]:
        return [str(p.relative_to(target_root)) for p in target_root.rglob("__pycache__")
                if p.is_dir() and "venv" not in str(p)]


class TempFilePlugin(SweeperPlugin):
    """清理暫存檔案（.tmp, .temp, ~$*）"""

    PATTERNS = ["*.tmp", "*.temp", "~$*"]

    def get_name(self) -> str:
        return "temp_files"

    def cleanup(self, target_root: Path, channel: Optional[str] = None) -> Dict[str, int]:
        result = {"cleaned_files": 0, "freed_mb": 0, "errors": 0}
        for pattern in self.PATTERNS:
            for f in target_root.rglob(pattern):
                if f.is_file() and "venv" not in str(f) and ".git" not in str(f):
                    try:
                        size = f.stat().st_size
                        f.unlink()
                        result["cleaned_files"] += 1
                        result["freed_mb"] += int(size / (1024 * 1024))
                    except Exception:
                        result["errors"] += 1
        return result


class LogRotationPlugin(SweeperPlugin):
    """輪轉舊日誌檔案（> 30 天）"""

    def __init__(self, days_old: int = 30):
        self.days_old = days_old

    def get_name(self) -> str:
        return f"log_rotation_{self.days_old}d"

    def cleanup(self, target_root: Path, channel: Optional[str] = None) -> Dict[str, int]:
        result = {"cleaned_files": 0, "freed_mb": 0, "errors": 0}
        cutoff = time.time() - (self.days_old * 86400)
        log_dir = target_root / "logs"
        if not log_dir.exists():
            return result

        for f in log_dir.rglob("*.log"):
            if f.is_file() and f.stat().st_mtime < cutoff:
                try:
                    size = f.stat().st_size
                    f.unlink()
                    result["cleaned_files"] += 1
                    result["freed_mb"] += int(size / (1024 * 1024))
                except Exception:
                    result["errors"] += 1
        return result


class ChannelTempPlugin(SweeperPlugin):
    """清理指定頻道的暫存輸出"""

    def __init__(self, hours_old: int = 48):
        self.hours_old = hours_old

    def get_name(self) -> str:
        return f"channel_temp_{self.hours_old}h"

    def cleanup(self, target_root: Path, channel: Optional[str] = None) -> Dict[str, int]:
        result = {"cleaned_files": 0, "freed_mb": 0, "errors": 0}
        if not channel:
            return result

        cutoff = time.time() - (self.hours_old * 3600)
        export_dir = target_root / "assets" / "final_exports" / channel

        if not export_dir.exists():
            return result

        # 清理舊 MP4
        for mp4 in export_dir.glob("*1HrMix*.mp4"):
            if mp4.stat().st_mtime < cutoff:
                try:
                    size = mp4.stat().st_size
                    mp4.unlink()
                    result["cleaned_files"] += 1
                    result["freed_mb"] += int(size / (1024 * 1024))
                except Exception:
                    result["errors"] += 1

        # 清理暫存音檔
        for wav in export_dir.glob("temp_*.wav"):
            try:
                size = wav.stat().st_size
                wav.unlink()
                result["cleaned_files"] += 1
                result["freed_mb"] += int(size / (1024 * 1024))
            except Exception:
                result["errors"] += 1

        return result


class DeprecatedDirPlugin(SweeperPlugin):
    """安全封存過時模組（移至 .deprecated/）"""

    def __init__(self, target_files: List[str]):
        self.target_files = target_files

    def get_name(self) -> str:
        return "deprecated_modules"

    def cleanup(self, target_root: Path, channel: Optional[str] = None) -> Dict[str, int]:
        result = {"cleaned_files": 0, "freed_mb": 0, "errors": 0}
        deprecated_dir = target_root / "scripts" / ".deprecated"
        deprecated_dir.mkdir(parents=True, exist_ok=True)

        for fname in self.target_files:
            for src in target_root.rglob(fname):
                if "venv" not in str(src) and ".deprecated" not in str(src):
                    try:
                        dst = deprecated_dir / src.name
                        shutil.move(str(src), str(dst))
                        result["cleaned_files"] += 1
                    except Exception:
                        result["errors"] += 1
        return result


# ============================================================================
# SweeperRunner — 統一執行器
# ============================================================================

class SweeperRunner:
    """載入並執行所有已註冊的清理插件"""

    def __init__(self, target_root: Path = None):
        self.target_root = target_root or _PROJECT_ROOT
        self.plugins: List[SweeperPlugin] = []

    def register(self, plugin: SweeperPlugin) -> "SweeperRunner":
        self.plugins.append(plugin)
        return self

    def register_defaults(self) -> "SweeperRunner":
        """註冊預設插件組合"""
        self.register(PycachePlugin())
        self.register(TempFilePlugin())
        self.register(LogRotationPlugin(days_old=30))
        return self

    @staticmethod
    def _topological_sort(plugins: List["SweeperPlugin"]) -> List["SweeperPlugin"]:
        """
        v15.11 P2#12：依 depends_on 做拓樸排序（Kahn's Algorithm）。
        若偵測到循環相依，退回原始注冊順序並輸出警告。
        """
        name_map = {p.get_name(): p for p in plugins}
        in_degree = {p.get_name(): 0 for p in plugins}
        adjacency: Dict[str, List[str]] = {p.get_name(): [] for p in plugins}

        for plugin in plugins:
            for dep in (plugin.depends_on or []):
                if dep in name_map:
                    adjacency[dep].append(plugin.get_name())
                    in_degree[plugin.get_name()] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        sorted_names: List[str] = []
        while queue:
            queue.sort()  # 同優先級按名稱排序，確保可重現
            node = queue.pop(0)
            sorted_names.append(node)
            for neighbour in adjacency.get(node, []):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if len(sorted_names) != len(plugins):
            print("  ⚠️ [SweeperRunner] 偵測到循環相依，退回原始注冊順序")
            return plugins
        return [name_map[n] for n in sorted_names]

    def run_all(self, channel: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """執行所有已註冊插件（v15.11 P2#12：依 depends_on 拓樸排序後執行）"""
        total = {"cleaned_files": 0, "freed_mb": 0, "errors": 0}
        details = {}

        for plugin in self._topological_sort(self.plugins):
            name = plugin.get_name()
            print(f"\n🔧 [{name}] 執行中...")

            if dry_run:
                preview = plugin.dry_run(self.target_root, channel)
                print(f"   [DRY-RUN] 將清理 {len(preview)} 項")
                details[name] = {"dry_run": len(preview), "preview": preview[:10]}
            else:
                try:
                    result = plugin.cleanup(self.target_root, channel)
                    total["cleaned_files"] += result["cleaned_files"]
                    total["freed_mb"] += result["freed_mb"]
                    total["errors"] += result["errors"]
                    details[name] = result
                    print(f"   ✅ 清理 {result['cleaned_files']} 檔案, "
                          f"釋放 {result['freed_mb']} MB, {result['errors']} 錯誤")
                except Exception as e:
                    total["errors"] += 1
                    details[name] = {"error": str(e)}
                    print(f"   ❌ 異常: {e}")

        total["details"] = details
        return total


# ============================================================================
# CLI 入口
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="R&S Echoes Plugin 清理器")
    parser.add_argument("--channel", help="指定頻道")
    parser.add_argument("--dry-run", action="store_true", help="僅預覽")
    parser.add_argument("--all", action="store_true", help="執行所有預設插件")
    args = parser.parse_args()

    runner = SweeperRunner()
    if args.all:
        runner.register_defaults()
        runner.register(ChannelTempPlugin())

    if not runner.plugins:
        runner.register_defaults()

    result = runner.run_all(channel=args.channel, dry_run=args.dry_run)

    print(f"\n📊 總計: {result['cleaned_files']} 檔案, {result['freed_mb']} MB, {result['errors']} 錯誤")
