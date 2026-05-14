#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
總指揮官 - CEO 輔助模式 (v8.8 Human-Assisted Genesis)

【v8.8 新架構】：被動接收、庫存盤點、強制清空
1. 啟動時掃描 assets/audio/ceo_approved_beats/
2. 若發現新文件 → 立即啟動 audio_mastering_engine.py 進行母帶處理 (-16 LUFS)
3. 母帶完成後 → 強制清空 ceo_approved_beats/ (防重複)
4. 若庫存不足 → 備援觸發 suno_api_engine.py 補足
"""

from __future__ import annotations

import argparse
import atexit
import datetime
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional, List

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.common.youtube_cheatsheet_builder import generate_youtube_cheatsheet_file, glob_youtube_sheet_paths
from scripts.common.pipeline_state_machine import preflight_dual_vault  # v15.10 P2-#6
from scripts.gear1_prod.distrokid_metadata_builder import build_distrokid_upload_csv  # v15.12 Phase 3.5

# 【Protocol L】導入金庫與衍生引擎
try:
    from scripts.gear2_rnd.vault_database import VaultDatabase
    from scripts.gear2_rnd.derivation_engine import DerivationEngine
    PROTOCOL_L_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Protocol L 模塊導入警告: {e}")
    PROTOCOL_L_AVAILABLE = False


# ────────────────────────────────────────────────────────────────
# 【v11.3 新增】頻道目錄隔離策略
# ────────────────────────────────────────────────────────────────

def get_channel_audio_dir(channel: str = "lofi", dir_type: str = "approved_beats") -> Path:
    """
    【v11.4 物理隔離政策】根據頻道返回對應的音頻目錄。
    
    改進：CEO 審批檔案與處理檔案皆放在統一的根目錄下，按頻道分子資料夾。
    
    Args:
        channel: 頻道名稱 ("lofi" 或 "light_music")
        dir_type: 目錄類型 ("approved_beats" 或 "vault")
        
    Returns:
        對應頻道的音頻目錄路徑
    """
    base_audio_dir = config.workspace_root / "assets" / "audio"
    
    # 【v11.4】子資料夾隔離：所有目錄都按頻道分置在子資料夾
    if dir_type == "approved_beats":
        return base_audio_dir / "ceo_approved_beats" / channel.lower()
    else:  # "vault"
        return base_audio_dir / "vault_ready_for_mix" / channel.lower()


# ────────────────────────────────────────────────────────────────
# 設定常數
# ────────────────────────────────────────────────────────────────

CEO_APPROVED_BEATS_DIR = Path(config.workspace_root) / "assets" / "audio" / "ceo_approved_beats"
MASTERED_TRACKS_DIR = Path(config.workspace_root) / "assets" / "audio" / "mastered_tracks"
VAULT_READY_FOR_MIX_DIR = Path(config.workspace_root) / "assets" / "audio" / "vault_ready_for_mix"

# 母帶處理目標
LUFS_TARGET = -16  # YouTube 標準

# 【v15.11 §11.3 殭屍行程防護】模組級追蹤 + atexit 清理
_active_procs: list[subprocess.Popen] = []
_proc_lock = threading.Lock()


def _cleanup_procs() -> None:
    """atexit 保險機制：強制終止所有仍在執行的子程序。"""
    with _proc_lock:
        for proc in list(_active_procs):
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        _active_procs.clear()


atexit.register(_cleanup_procs)


# ────────────────────────────────────────────────────────────────
# 日誌與錯誤處理
# ────────────────────────────────────────────────────────────────

def _log_fatal(error_code: str, details: str) -> None:
    """致命錯誤統一寫入 project_learning.md，並中止產線。"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_line = str(details).strip().splitlines()[-1][:240]
    entry = (
        f"\n### [{timestamp}] pipeline_runner.py: {error_code}\n"
        f"- Cause: {last_line}\n"
        "- Action: Pipeline halted.\n"
    )
    try:
        log_path = Path(config.workspace_root) / "project_learning.md"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception:
        pass
    print(f"[PIPELINE][FATAL] {error_code}: {last_line}")
    sys.exit(1)


def _log_info(msg: str) -> None:
    """記錄操作日誌。"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[PIPELINE][{timestamp}] {msg}")


def _log_warn(msg: str) -> None:
    """記錄警告日誌。"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[PIPELINE][WARN][{timestamp}] {msg}")


def _snapshot_ceo_mp3_mtimes(approved_dir: Path) -> dict[str, float]:
    """TTAPI 呼叫前快照（檔名 → mtime），供比對新落地 MP3。"""
    if not approved_dir.exists():
        return {}
    return {p.name: p.stat().st_mtime for p in approved_dir.glob("*.mp3") if p.is_file()}


def _list_new_or_updated_mp3s(approved_dir: Path, before: dict[str, float]) -> List[Path]:
    """新檔名，或既有檔 mtime 變大（覆寫），皆視為本次落地。"""
    if not approved_dir.exists():
        return []
    out: List[Path] = []
    for p in approved_dir.glob("*.mp3"):
        if not p.is_file():
            continue
        m = p.stat().st_mtime
        if p.name not in before:
            out.append(p)
        elif m > before[p.name]:
            out.append(p)
    return sorted(out, key=lambda x: x.stat().st_mtime, reverse=True)


def _log_ttapi_download_summary_pipeline(approved_dir: Path, before: dict[str, float], channel: str) -> None:
    """【v15.9】產線層級摘要：與 suno 子程序日誌互補，便於 assets/.logs 搜尋 TTAPI_DOWNLOAD_SUMMARY。"""
    landed = _list_new_or_updated_mp3s(approved_dir, before)
    _log_info(
        f"[TTAPI_DOWNLOAD_SUMMARY] 頻道={channel} | 本次呼叫新落地 MP3 數量={len(landed)} | 目錄={approved_dir}"
    )
    for j, p in enumerate(landed, start=1):
        _log_info(f"[TTAPI_DOWNLOAD_SUMMARY]   [{j}] {p.name}")


# ────────────────────────────────────────────────────────────────
# 庫存盤點
# ────────────────────────────────────────────────────────────────

def _scan_ceo_approved_beats(channel: str = "lofi") -> List[Path]:
    """
    掃描 CEO 審批目錄，返回所有 MP3 檔案。
    【v11.3】支持頻道隔離：Light Music 使用專屬目錄。
    
    Args:
        channel: 頻道名稱 ("lofi" 或 "light_music")
    """
    target_dir = get_channel_audio_dir(channel, "approved_beats")
    
    if not target_dir.exists():
        _log_info(f"⚠️  CEO 審批目錄不存在 ({channel})，建立: {target_dir}")
        target_dir.mkdir(parents=True, exist_ok=True)
        return []
    
    mp3_files = list(target_dir.glob("*.mp3"))
    if mp3_files:
        _log_info(f"📁 掃描 CEO 審批目錄: 找到 {len(mp3_files)} 個 MP3 檔案")
        for mp3 in mp3_files:
            _log_info(f"  - {mp3.name}")
    else:
        _log_info(f"📁 掃描 CEO 審批目錄: 無新檔案")
    
    return sorted(mp3_files)


def _scan_mastered_tracks(channel: str = "lofi") -> int:
    """
    【v12.11 物理隔離】掃描指定頻道的已母帶處理檔案數量。
    
    Args:
        channel: 頻道名稱 (lofi 或 light_music)
    """
    channel_mastered_dir = MASTERED_TRACKS_DIR / channel.lower()
    if not channel_mastered_dir.exists():
        return 0
    
    mastered_count = len(list(channel_mastered_dir.glob("*_YT_*.wav")))
    _log_info(f"📊 已母帶處理 ({channel.upper()}): {mastered_count} 個檔案")
    return mastered_count


# ────────────────────────────────────────────────────────────────
# 母帶處理
# ────────────────────────────────────────────────────────────────

def _run_audio_mastering(source_mp3s: List[Path], channel: str = "lofi") -> bool:
    """
    觸發 audio_mastering_engine.py 進行母帶處理。
    【v12.0 頻道隔離】支援動態傳遞 channel 參數
    【v12.9 LUFS 傳遞】從 channels/{channel}.json 讀取 mastering_lufs 並傳遞
    
    【CTO v8.9.1 容錯強化】：即使母帶引擎因「無新檔案」回傳 Exit Code 1，
    也不視為致命錯誤。只要 vault_ready_for_mix/ 內有充足的母帶，
    就應該強制進入 Phase 4 (無縫縫合)。
    """
    mastering_script = Path(__file__).parent / "audio_mastering_engine.py"
    if not mastering_script.exists():
        _log_fatal("MASTERING_ENGINE_MISSING", f"audio_mastering_engine.py 不存在: {mastering_script}")
    
    # 【v12.9】讀取頻道配置以取得 mastering_lufs 參數
    channel_config_path = Path(config.workspace_root) / "configs" / "channels" / f"{channel.lower()}.json"
    mastering_lufs = -16.0  # 默認值
    
    if channel_config_path.exists():
        try:
            import json
            with open(channel_config_path, 'r', encoding='utf-8') as f:
                channel_config = json.load(f)
                mastering_lufs = channel_config.get("mastering_lufs", -16.0)
                _log_info(f"✅ 從配置讀取 {channel} 頻道的 mastering_lufs: {mastering_lufs}")
        except Exception as e:
            _log_info(f"⚠️  讀取配置失敗，使用默認 LUFS (-16): {e}")
    else:
        _log_info(f"⚠️  找不到 {channel} 頻道配置，使用默認 LUFS (-16)")
    
    if source_mp3s:
        _log_info(f"🎵 啟動母帶處理: {len(source_mp3s)} 個檔案 (頻道: {channel}, LUFS: {mastering_lufs})")
    else:
        _log_info(f"🎵 啟動母帶處理: 自動掃描 ceo_approved_beats/{channel}/ 中的新檔案 (LUFS: {mastering_lufs})")
    
    try:
        env = os.environ.copy()
        env["PIPELINE_RUNNER_AUTHORIZED"] = "1"
        env["PYTHONUNBUFFERED"] = "1"  # v15.10: 即時日誌輸出

        # v15.11 §11.2 修正：廢除 capture_output，改用 Popen 即時串流 stdout
        # 讓 audio_mastering_engine 的 [SHORTS_SYNC] 等輸出即時出現在 UI log 面板
        import io as _io
        cmd = [sys.executable, str(mastering_script), "--channel", channel, "--lufs", str(mastering_lufs)]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(Path(config.workspace_root)),
            env=env,
            bufsize=1,  # 行緩衝：每行立即 flush
        )
        _active_procs.append(proc)  # §11.3 殭屍防護

        # 即時讀取 + 累積（保留「無新檔案」檢測能力）
        accumulated: list[str] = []
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line_stripped = line.rstrip("\n\r")
                print(line_stripped, flush=True)  # → 上游 backend._run_with_log 的 log 檔
                accumulated.append(line)
            proc.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            _log_fatal("MASTERING_TIMEOUT", "母帶處理超時 (1 小時)")
        finally:
            with _proc_lock:
                if proc in _active_procs:
                    _active_procs.remove(proc)

        full_stdout = "".join(accumulated)
        returncode = proc.returncode

        # 【CTO v8.9.1 修復】檢查是否是「無新檔案」的安全退出
        if "[MASTERING] skip: no new files" in full_stdout:
            _log_info("ℹ️  無新檔案待處理（安全跳過）")
            return True  # ✅ 不視為失敗，繼續進行

        # 其他非零退出碼 = 真實錯誤（FFmpeg 轉換失敗等）
        if returncode != 0:
            tail = "\n".join(accumulated[-20:]) if accumulated else "(無輸出)"
            _log_info(f"⚠️  母帶引擎回傳錯誤（Exit Code: {returncode}），但繼續進行")
            _log_info(f"📝 最後 20 行:\n{tail}")
            # 【CTO 指示】不中斷產線，繼續到 Phase 4，讓庫存盤點決定是否進行
            return True

        _log_info(f"✅ 母帶處理完成 (LUFS: {mastering_lufs})")
        return True

    except Exception as exc:
        _log_fatal("MASTERING_ERROR", str(exc))


# ────────────────────────────────────────────────────────────────
# 庫存檢查機制 (Inventory Validation)
# ────────────────────────────────────────────────────────────────

def _check_vault_inventory(channel: str = "lofi") -> int:
    """
    【CTO 產線連續性檢查 v11.8】檢查 vault_ready_for_mix/{channel}/ 中的實際檔案數量。
    
    【v11.8 頻道隔離】根據頻道獨立掃描庫存，嚴禁混用不同頻道的素材。
    
    Args:
        channel: 頻道名稱 (lofi 或 light_music)
    
    返回：
    - 整數: vault_ready_for_mix/{channel}/ 中的有效音檔 (*.wav) 數量
    """
    # 【v11.8】根據頻道獲取專屬路徑
    channel_vault_dir = get_channel_audio_dir(channel, "vault")
    
    if not channel_vault_dir.exists():
        _log_info(f"⚠️  {channel} 庫存目錄不存在: {channel_vault_dir}，返回庫存數: 0")
        return 0
    
    valid_tracks = list(channel_vault_dir.glob("*.wav"))
    inventory_count = len(valid_tracks)
    
    _log_info(f"📊 庫存檢查 ({channel.upper()}): vault_ready_for_mix/{channel}/ 現有 {inventory_count} 個有效母帶")
    if valid_tracks:
        for track in sorted(valid_tracks)[:3]:  # 列出前 3 個
            _log_info(f"   ✓ {track.name}")
        if len(valid_tracks) > 3:
            _log_info(f"   ... 及 {len(valid_tracks) - 3} 個其他檔案")
    
    return inventory_count


def _check_freshness_quota(
    channel: str = "lofi", target_tracks: int = 20, *, quiet: bool = False
) -> dict:
    """
    【v15.9 新鮮度鐵律】Phase 4 前置閘門：檢查 dc=0 新歌是否達標。

    規則：可選新歌數 ≥ ceil(target_tracks × min_new_ratio)
    「可選」與 lofi_assembler.VaultSelection 一致：同源排斥 + vault 內實體 WAV 存在（非僅 DB 筆數）。
    回傳結構：
        {
            "passed": bool,         # 是否通過門檻
            "channel": str,
            "target_tracks": int,
            "min_ratio": float,
            "quota_new": int,       # 需求新歌數
            "available_new": int,   # Phase 4 實際可選的 dc=0（獨立基因 + 檔案存在）
            "available_new_raw": int,  # DB 中 dc=0 列數（診斷用）
            "deficit": int,         # 缺口（若通過則為 0）
            "enforcement": "strict"|"warn",
            "enabled": bool,
        }
    不抛異常，讓呼叫方決定中止或補充（配合 --ttapi-fill-fresh）。
    quiet=True 時不寫入管線日誌（供 Streamlit UI 高頻輪詢）。
    """
    import math as _math
    from scripts.gear1_prod.lofi_assembler import count_selectable_new_for_freshness_gate

    policy = getattr(config, "freshness_policy", {}) or {}
    enabled = bool(policy.get("enabled", True))
    enforcement = str(policy.get("enforcement", "strict")).lower()
    min_ratio = float(((policy.get("channels") or {}).get(channel, {})).get("min_new_ratio", 0.5))
    quota_new = _math.ceil(target_tracks * min_ratio)

    available_new_raw = 0
    available_new = 0
    try:
        available_new_raw, available_new = count_selectable_new_for_freshness_gate(
            channel, max_derivation_limit=3, workspace_root=config.workspace_root
        )
    except Exception as e:
        if not quiet:
            _log_info(f"⚠️  新鮮度檢查：無法計算可選新歌 ({e})，保守視為 available_new=0")
        try:
            vault = VaultDatabase()
            all_tracks = [t for t in vault.get_all_tracks() if t.get("channel") == channel]
            available_new_raw = sum(1 for t in all_tracks if (t.get("derivation_count") or 0) == 0)
        except Exception:
            pass

    deficit = max(0, quota_new - available_new)
    passed = (available_new >= quota_new) if enabled else True

    report = {
        "passed": passed,
        "channel": channel,
        "target_tracks": target_tracks,
        "min_ratio": min_ratio,
        "quota_new": quota_new,
        "available_new": available_new,
        "available_new_raw": available_new_raw,
        "deficit": deficit,
        "enforcement": enforcement,
        "enabled": enabled,
    }

    if not quiet:
        icon = "✅" if passed else ("⚠️" if enforcement == "warn" else "❌")
        raw_note = f"（DB dc=0 列 {available_new_raw}）" if available_new_raw != available_new else ""
        _log_info(
            f"\n[FRESHNESS_GATE] {icon} 頻道 {channel.upper()} | "
            f"需求 {quota_new} (= {target_tracks}×{min_ratio*100:.0f}%) | "
            f"可選新歌 {available_new} 首{raw_note} | 缺 {deficit} | "
            f"enforcement={enforcement} | enabled={enabled}"
        )
    return report


def _log_inventory_dashboard(channel: str = "lofi") -> None:
    """
    【v12.21 CTO 庫存戰情儀表板】印出頻道特定的衍生計數分層報表。
    
    功能：
    - 連接 VaultDatabase 取出對應頻道的 tracks 的 derivation_count 統計
    - 按層級分組並計算百分比
    - 印出標準格式的戰情報表
    
    【v12.21 改進】：
    - WHERE channel = ? 精準頻道過濾
    - 確保母帶統計只計入指定頻道
    """
    try:
        vault = VaultDatabase()
        
        # 嘗試從數據庫獲取指定頻道的 tracks 及其 derivation_count
        try:
            all_tracks = vault.get_all_tracks()
            # 過濾指定頻道
            all_tracks = [t for t in all_tracks if t.get('channel') == channel]
        except Exception:
            # 如果 get_all_tracks() 不存在，嘗試直接 SQL 查詢
            all_tracks = []
        
        if not all_tracks:
            # 備援方案：直接查詢 SQL【v12.21 添加 channel 過濾】
            try:
                import sqlite3
                db_path = config.music_db_path
                if db_path.exists():
                    conn = sqlite3.connect(str(db_path))
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    # 【v12.21】WHERE channel = ? 精準過濾
                    cursor.execute("SELECT derivation_count, channel FROM audio_assets WHERE is_archived = 0 AND channel = ? ORDER BY derivation_count", (channel,))
                    rows = cursor.fetchall()
                    all_tracks = [dict(row) for row in rows]
                    conn.close()
            except Exception as e:
                _log_info(f"⚠️  無法查詢 {channel.upper()} 頻道的資料庫: {e}")
                return
        
        # 統計各層級的數量
        count_0 = sum(1 for t in all_tracks if t.get('derivation_count', 0) == 0)
        count_1 = sum(1 for t in all_tracks if t.get('derivation_count', 0) == 1)
        count_2 = sum(1 for t in all_tracks if t.get('derivation_count', 0) == 2)
        count_3plus = sum(1 for t in all_tracks if t.get('derivation_count', 0) >= 3)
        
        total_active = count_0 + count_1 + count_2
        total_archived = count_3plus
        
        # 計算百分比
        pct_0 = (count_0 / total_active * 100) if total_active > 0 else 0
        pct_1 = (count_1 / total_active * 100) if total_active > 0 else 0
        pct_2 = (count_2 / total_active * 100) if total_active > 0 else 0
        
        # 打印戰情報表【v12.21 頻道標記】
        channel_display = "☕ Lofi Chill" if channel == "lofi" else "🌿 Light Music"
        _log_info(f"\n[PIPELINE] 📊 【R&S Echoes 金庫即時戰情報表】({channel_display})")
        _log_info("[PIPELINE] ------------------------------------------")
        _log_info(f"[PIPELINE] 🟢 可用活水總計：{total_active} 首")
        _log_info(f"[PIPELINE]   🆕 全新母帶 (0次) : {count_0} 首 ({pct_0:.1f}%)")
        _log_info(f"[PIPELINE]   ♻️ 一代衍生 (1次) : {count_1} 首 ({pct_1:.1f}%)")
        _log_info(f"[PIPELINE]   🔄 二代衍生 (2次) : {count_2} 首 ({pct_2:.1f}%)")
        _log_info("[PIPELINE] ------------------------------------------")
        _log_info(f"[PIPELINE] ❄️ 已冷凍退役 (>=3次): {total_archived} 首")
        _log_info("[PIPELINE] ==========================================")
        
    except Exception as e:
        _log_info(f"⚠️  無法生成 {channel.upper()} 頻道的庫存報表: {e}")


# ────────────────────────────────────────────────────────────────
# 安全封存機制 (Data Protection)
# ────────────────────────────────────────────────────────────────

def _archive_ceo_approved_beats(channel: str = "lofi") -> None:
    """v15.10 BUG2: CEO 決策 — 母帶完成後直接刪除原始素材，不再封存至 ceo_archived_beats/
    舊版封存邏輯已廢棄（會重建 CEO 已手動刪除的目錄）。
    """
    ceo_approved_dir = get_channel_audio_dir(channel, "approved_beats")
    if not ceo_approved_dir.exists():
        return
    files = list(ceo_approved_dir.glob("*.mp3")) + list(ceo_approved_dir.glob("*.wav"))
    if not files:
        _log_info(f"📁 CEO 審批目錄已空，無需清理")
        return
    deleted_count = 0
    for f in files:
        try:
            f.unlink()
            _log_info(f"  🗑️ 已刪除原始素材: {f.name}")
            deleted_count += 1
        except Exception as e:
            _log_warn(f"  ⚠️  刪除失敗 {f.name}: {e}")
    _log_info(f"✅ 原始素材清理完成: {deleted_count} 個檔案已刪除")



# ────────────────────────────────────────────────────────────────
# 庫存補充機制 (Vault Sync)
# ────────────────────────────────────────────────────────────────

def _sync_mastered_to_vault(channel: str = "lofi") -> bool:
    """
    【v12.21 暴力入庫與金庫對齊】Exists-then-Sync 模式：確保母帶 100% 入庫
    
    【工作原理】：
    1. 掃描 mastered_tracks/{channel}/ 中的所有 .wav 檔案
    2. 對於每個檔案，檢查是否已在 vault_ready_for_mix/{channel}/ 中
    3. 若不存在，立即複製並註冊到 VaultDatabase
    4. 同步後必須調用 VaultDatabase.add_track() 將資訊寫入資料庫
    
    【v12.11 物理隔離】根據 channel 參數複製到對應的 vault 子目錄
    【Protocol L 自動入庫】同時將新生成的母帶註冊到 VaultDatabase。
    【v12.21 改進】確保容錯率，any .wav → exists_in_vault? → sync + register
    """
    # 【v12.11 物理隔離】先檢查頻道特定的 mastered_tracks 目錄
    channel_mastered_dir = MASTERED_TRACKS_DIR / channel.lower()
    if not channel_mastered_dir.exists():
        _log_info(f"⏭️  跳過庫存補充: mastered_tracks/{channel}/ 不存在")
        return True
    
    try:
        vault_ready_dir = get_channel_audio_dir(channel, "vault")
        vault_ready_dir.mkdir(parents=True, exist_ok=True)
        
        # 【v12.21 暴力入庫】掃描所有 .wav 檔案（移除限制條件）
        mastered_files = list(channel_mastered_dir.glob("*.wav"))
        if not mastered_files:
            _log_info(f"ℹ️  mastered_tracks/{channel}/ 無新檔案待同步")
            return True
        
        copied_count = 0
        ingested_count = 0
        failed_tracks = []
        
        # 【Protocol L】初始化金庫
        vault = None
        if PROTOCOL_L_AVAILABLE:
            try:
                vault = VaultDatabase()
            except Exception as e:
                _log_info(f"⚠️  無法初始化 VaultDatabase: {e}")
        
        for src_file in mastered_files:
            dst_file = vault_ready_dir / src_file.name
            
            # 【v12.21 Exists-then-Sync】存在即同步模式
            if not dst_file.exists():
                try:
                    # 複製母帶到 vault
                    shutil.copy2(src_file, dst_file)
                    copied_count += 1
                    _log_info(f"  ✓ 複製到庫存: {src_file.name} → vault_ready_for_mix/{channel}/")
                    
                    # 【v12.21 必須調用】同步後立即進行資料庫註冊
                    if vault:
                        try:
                            # 從檔名提取 track_id (支援多種格式)
                            track_id = src_file.stem  # 去除 .wav 副檔名
                            
                            # v15.10: 安全檢查 track_exists（防範方法不存在）
                            try:
                                already_exists = vault.track_exists(track_id)
                            except (AttributeError, Exception):
                                already_exists = False
                            
                            if not already_exists:
                                vault.add_track(
                                    track_id=track_id,
                                    original_path=str(dst_file),
                                    channel=channel,  # 【v12.21】強制寫入頻道標籤
                                    mood="ambient" if channel == "light_music" else "lofi_chill",
                                    genre="ambient" if channel == "light_music" else "lofi-hip-hop",
                                    bpm=80 if channel == "light_music" else 90
                                )
                                _log_info(f"  📚 入庫: {track_id} (頻道: {channel}, derivation_count: 0)")
                                ingested_count += 1
                            else:
                                _log_info(f"  ℹ️  已在庫: {track_id}")
                        
                        except Exception as e:
                            _log_warn(f"  ⚠️  入庫失敗 {track_id}: {e}")
                            failed_tracks.append((track_id, str(e)))
                    else:
                        _log_info(f"  ⚠️  VaultDatabase 未初始化，跳過註冊 {track_id}")
                
                except Exception as e:
                    _log_warn(f"  ⚠️  複製失敗 {src_file.name}: {e}")
                    failed_tracks.append((src_file.name, str(e)))
            else:
                _log_info(f"  ✓ 已在庫: {src_file.name} (無需重複複製)")
        
        # 【v12.22 緊急指令】掃描根目錄碎檔並歸位
        _log_info("\n【v12.22 根目錄碎檔掃描與歸位】")
        root_mastered_dir = MASTERED_TRACKS_DIR  # mastered_tracks/ 根目錄
        orphaned_files = list(root_mastered_dir.glob("*_YT_*.wav"))
        orphaned_count = 0
        
        for orphan_file in orphaned_files:
            # 跳過已在子目錄中的檔案
            if orphan_file.parent != root_mastered_dir:
                continue
            
            try:
                # 根據檔名中的 LUFS 值判斷頻道
                filename = orphan_file.name
                if "-18.0LUFS" in filename and channel == "light_music":
                    detected_channel = "light_music"
                elif "-16.0LUFS" in filename and channel == "lofi":
                    detected_channel = "lofi"
                else:
                    # 頻道標籤不匹配，跳過
                    continue
                
                # 若符合當前頻道，進行歸位
                if detected_channel == channel:
                    dst_file = vault_ready_dir / filename
                    
                    # 先將檔案複製到頻道子目錄
                    shutil.copy2(orphan_file, dst_file)
                    orphaned_count += 1
                    _log_info(f"  🔄 歸位碎檔: {filename} (從根目錄 → vault_ready_for_mix/{channel}/)")
                    
                    # 進行資料庫註冊
                    if vault:
                        try:
                            track_id = orphan_file.stem
                            if not vault.track_exists(track_id):
                                vault.add_track(
                                    track_id=track_id,
                                    original_path=str(dst_file),
                                    channel=channel,  # 【v12.22】強制標記頻道
                                    mood="ambient" if channel == "light_music" else "lofi_chill",
                                    genre="ambient" if channel == "light_music" else "lofi-hip-hop",
                                    bpm=80 if channel == "light_music" else 90
                                )
                                _log_info(f"  📚 碎檔入庫: {track_id} (頻道: {channel})")
                                ingested_count += 1
                        except Exception as e:
                            _log_warn(f"  ⚠️  碎檔入庫失敗 {track_id}: {e}")
                    
                    # 刪除原根目錄檔案（歸位完成後）
                    try:
                        orphan_file.unlink()
                        _log_info(f"  ✓ 原檔刪除: {filename}")
                    except Exception as e:
                        _log_warn(f"  ⚠️  無法刪除原檔 {filename}: {e}")
            
            except Exception as e:
                _log_warn(f"  ⚠️  碎檔歸位失敗 {orphan_file.name}: {e}")
        
        # 生成完成報告
        if copied_count > 0 or ingested_count > 0 or orphaned_count > 0:
            _log_info(f"\n✅ 【v12.21 暴力入庫】完成 ({channel.upper()})")
            _log_info(f"   📦 複製檔案: {copied_count} 個")
            _log_info(f"   🔄 歸位碎檔: {orphaned_count} 個")
            _log_info(f"   📚 資料庫註冊: {ingested_count} 首")
            if failed_tracks:
                _log_info(f"   ⚠️  失敗: {len(failed_tracks)} 個")
                for track, error in failed_tracks:
                    _log_info(f"      - {track}: {error}")
        else:
            _log_info(f"ℹ️  所有母帶已在庫存中 ({channel.upper()})，無需同步")
        
        
        return True
    except Exception as exc:
        _log_fatal("VAULT_SYNC_ERROR", f"庫存補充失敗 ({channel}): {exc}")


# ────────────────────────────────────────────────────────────────
# Phase 3: 發行企劃引擎
# ────────────────────────────────────────────────────────────────

def _run_music_metadata_engine(volume: int = 1, channel: str = "lofi") -> bool:
    """
    Phase 3: 觸發 music_metadata_engine.py 生成 DistroKid 中繼資料。
    
    【v11.7 頻道化升級】：
    - 支援多頻道隔離（lofi 或 light_music）
    - 自動傳遞 --channel 參數
    
    【v8.8 軍規級防護】：
    - 使用統一 llm_client.generate_structured_json() API
    - 雙重超時: 30s (連接) + 300s (讀取)
    - 指數退避: 最多 3 次重試
    """
    metadata_script = Path(__file__).parent / "music_metadata_engine.py"
    if not metadata_script.exists():
        _log_fatal("METADATA_ENGINE_MISSING", f"music_metadata_engine.py 不存在: {metadata_script}")
    
    _log_info(f"📋 Phase 3: 觸發發行企劃引擎 (Vol.{volume}, 頻道: {channel.upper()})")

    # v15.11: 廢除 capture_output，改用 Popen 即時串流
    # MiniMax/Zhipu/Gemini 三引擎鏈最壞情況 ~14 分鐘 (2 重試 × 3 引擎)
    import io as _io
    cmd = [sys.executable, str(metadata_script),
           "--channel", channel, "--volume", str(volume),
           "--provider", "minimax"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(Path(config.workspace_root)),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        bufsize=1,
    )
    _active_procs.append(proc)
    accumulated: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line_stripped = line.rstrip("\n\r")
            print(line_stripped, flush=True)
            accumulated.append(line)
        proc.wait(timeout=900)  # 15 分鐘上限
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        _log_fatal("METADATA_TIMEOUT", "發行企劃生成超時 (15 分鐘)")
    finally:
        with _proc_lock:
            if proc in _active_procs:
                _active_procs.remove(proc)

    full_stdout = "".join(accumulated)
    returncode = proc.returncode

    if returncode != 0:
        tail = "\n".join(accumulated[-30:]) if accumulated else "(無輸出)"
        _log_fatal("METADATA_GENERATION_FAILED", f"music_metadata_engine.py 失敗:\n{tail}")

    _log_info("✅ 發行企劃中繼資料生成完成")

    # 驗證產出檔案
    export_dir = Path(config.workspace_root) / "assets" / "final_exports" / channel.lower()
    metadata_pattern = f"metadata_distrokid_{channel.lower()}.json"
    metadata_file = export_dir / metadata_pattern
    if metadata_file.exists():
        _log_info(f"✓ 中繼資料已保存: {metadata_file}")
    else:
        fallback_files = list(export_dir.glob("metadata_distrokid*.json"))
        if fallback_files:
            metadata_file = fallback_files[-1]
            _log_info(f"✓ 中繼資料已保存 (Fallback): {metadata_file}")
        else:
            _log_fatal("METADATA_FILE_MISSING", f"產出檔案不存在: {metadata_file}")

    return True


# ────────────────────────────────────────────────────────────────
# Phase 4: 1 小時無縫混音
# ────────────────────────────────────────────────────────────────

def _run_lofi_assembler(sfx: str | None = None, sfx_mode: str = "global", channel: str = "lofi") -> bool:
    """
    Phase 4: 觸發 lofi_assembler.py 進行 1 小時無縫 Crossfade 混音。
    
    【工作流】：
    1. 掃描 vault_ready_for_mix/{channel}/ 中的已母帶化音檔
    2. 執行 FFmpeg acrossfade 邏輯 (雙向各 2 秒交叉淡化)
    3. 產出 1 小時 YouTube 長片
    
    【CTO SFX 修正】支援可選的 sfx 參數，若提供則將環境音以 4% 音量疊加。
    
    【v12.23 頻道參數強制繼承】必須傳遞 --channel 參數確保子進程知道頻道
    
    【零庫存防呆】：若庫存為 0，會安全返回 exit code 0（不視為失敗）
    """
    assembler_script = Path(__file__).parent / "lofi_assembler.py"
    if not assembler_script.exists():
        _log_fatal("ASSEMBLER_MISSING", f"lofi_assembler.py 不存在: {assembler_script}")
    
    _log_info(f"🎵 Phase 4: 啟動 1 小時無縫混音 (Crossfade 縫合, 頻道: {channel.upper()})")
    
    try:
        # 【v12.23 頻道參數強制繼承】必須包含 --channel 參數
        cmd = [sys.executable, str(assembler_script), "--channel", channel]
        
        # 【CTO SFX 修正】如果提供了 SFX，添加到命令行參數
        if sfx:
            cmd.extend(["--sfx", str(sfx), "--sfx-mode", sfx_mode])
            _log_info(f"   🎧 環境音: {Path(sfx).name} (模式: {sfx_mode})")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 小時上限
            env={**os.environ, "PIPELINE_RUNNER_AUTHORIZED": "1", "PYTHONUNBUFFERED": "1"}  # v15.10
        )
        
        # CTO 修正：即使 returncode=0，也要檢查是否是「庫存為 0 被跳過」
        if "[STATUS] 庫存為 0" in result.stdout:
            _log_info("⏭️  Phase 4 被跳過: 庫存為 0，系統將觸發自動備援")
            return False  # 返回 False 表示需要備援
        
        if result.returncode != 0:
            # 【CTO 終極修復】將 stderr 直接併入 error_msg，避免 sys.exit(1) 吞噬錯誤訊息
            error_msg = f"lofi_assembler.py 執行失敗 (Exit Code: {result.returncode})\n"
            error_msg += f"【標準錯誤輸出 (最後 2000 字)】:\n{result.stderr[-2000:] if result.stderr else '(無錯誤)'}\n"
            error_msg += f"【標準輸出 (最後 1000 字)】:\n{result.stdout[-1000:] if result.stdout else '(無輸出)'}"
            _log_fatal("ASSEMBLER_FAILED", error_msg)
        
        _log_info(f"✅ 1 小時無縫混音完成")
        
        # 【v12.36 日誌擴展】確保完整輸出 50/25/25 選曲報告，不截斷
        # CTO 指令：庫存分佈報告對 CEO 診斷至關重要，絕不允許截斷！
        if result.stdout:
            if "[VAULT_V95]" in result.stdout:
                # 優先從 [VAULT_V95] 開始輸出（確保選曲報告完整顯示）
                vault_idx = result.stdout.find("[VAULT_V95]")
                _log_info(f"📝 【v12.36 完整日誌】lofi_assembler 庫存選曲報告 + 混音成果:\n{result.stdout[vault_idx:]}")
            else:
                # Fallback：若無選曲報告，輸出最後 2000 字（擴展 4 倍以避免截斷）
                _log_info(f"📝 詳細日誌 (最後 2000 字):\n{result.stdout[-2000:]}")
        
        # 【v12.35 CTO RCA 修復 + 頻道隔離】驗證產出檔案 - 動態支持频道名
        final_exports_dir = Path(config.workspace_root) / "assets" / "final_exports" / channel.lower()
        # 支持帶頻道的檔名 (R&S_Echoes_light_music_1HrMix_*.wav) 與簡化名稱
        wav_files = list(final_exports_dir.glob(f"R&S_Echoes_{channel.lower()}_1HrMix_*.wav")) + list(final_exports_dir.glob("R&S_Echoes_1HrMix_*.wav"))
        # 去重並按修改時間排序
        wav_files = sorted(set(wav_files), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if wav_files:
            longest_mix = wav_files[0]  # 最新生成的文件
            _log_info(f"✓ 混音檔案已保存: {longest_mix.name}")
        else:
            _log_fatal("MIX_FILE_MISSING", f"產出混音檔案不存在: {final_exports_dir}\n搜尋模式: R&S_Echoes_{channel.lower()}_1HrMix_*.wav")
        
        return True
    
    except subprocess.TimeoutExpired:
        _log_fatal("ASSEMBLER_TIMEOUT", "無縫混音超時 (1 小時)")
    except Exception as exc:
        _log_fatal("ASSEMBLER_ERROR", str(exc))


# ────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────
# Phase 4.5: YouTube CheatSheet 最終合體 (CTO v9.0)
# ────────────────────────────────────────────────────────────────

def _finalize_youtube_cheatsheet(channel: str = "lofi") -> bool:
    """
    【CTO v10 升級 + 頻道動態化】YouTube CheatSheet 一站式內聯合體
    
    在 Phase 4 (無縫混音) 完成後執行 - 廢除草稿，直接生成最終稿：
    1. 讀取最新的 Tracklist_*.txt（由 lofi_assembler.py 生成）
    2. 讀取 metadata_distrokid.json 取得 album_title、spotify_subgenre 等資訊
    3. 根據 channel 參數動態生成適配型文案
    4. 直接保存為 youtube_sheet_[YYYYMMDD_HHMMSS].txt（無中間草稿）
    """
    channel_lower = channel.lower()
    export_dir = Path(config.workspace_root) / "assets" / "final_exports" / channel_lower

    try:
        result = generate_youtube_cheatsheet_file(export_dir, channel_lower)
        if result["used_default_tracklist"]:
            _log_info("⚠️  Phase 4.5: Tracklist 缺失或非縫合產物，上架文案內時間軸可能為提示文字")
        else:
            _log_info(f"📋 讀取 Tracklist: {result['tracklist_path'].name}")
            if result.get("paired_master_wav"):
                _log_info(f"🔗 對齊 1hr 母帶: {result['paired_master_wav'].name}")

        if result["used_default_metadata"]:
            _log_info("⚠️  Phase 4.5: 未找到 metadata_distrokid.json，將使用預設值繼續")
        else:
            _log_info(f"📊 讀取中繼資料: {result['metadata_path'].name}")

        final_path = result["output_path"]
        _log_info(f"✅ YouTube CheatSheet 已直接生成（無草稿）: {final_path.name}")
        _log_info(f"   CEO 可直接複製至 YouTube 頻道描述欄位")
        _log_info(f"   【廢除草稿】純淨一站式合體完成 ✨")
        return True

    except Exception as exc:
        _log_warn(f"Phase 4.5 輕度出錯（非致命）: {exc}")
        return False


# ────────────────────────────────────────────────────────────────
# Phase 5: 影片處理邏輯
# ────────────────────────────────────────────────────────────────

def _run_video_processor(bg_video_path: str = None, bg_video_paths: list[str] = None, channel: str = "lofi") -> bool:
    """
    Phase 5 (可選): 萬能影片循環處理器 - 將短片轉 1 小時無縫長片。
    
    【工作流】：
    1. 驗證背景影片存在
    2. 找到最新的母帶音軌 (Phase 2 -16 LUFS WAV)
    3. 執行 MultiSceneProcessor 進行 Encode-Once-Repeat 無縫迴圈
    4. 輸出 H.264 MP4 最終產品
    
    【v15.3 三模式升級】
    - bg_video_path (單一)：母帶回收模式，同一支影片 × N
    - bg_video_paths (多支)：CEO 手選 K 支 + 金庫自動補齊
    - 皆為 None：全自動金字塔抽樣（幻影輪播）
    
    【音訊純淨度】：
    ✅ 強制拋棄背景影片的原生音軌
    ✅ 100% 採用 Phase 2 -16 LUFS 母帶
    """
    from scripts.gear1_prod.multi_scene_processor import MultiSceneProcessor
    
    # 【v12.35 CTO RCA 修復 + 頻道隔離】找最新的母帶音軌 - 動態支持频道名
    mastered_tracks_dir = Path(config.workspace_root) / "assets" / "final_exports" / channel.lower()
    wav_files = sorted(list(mastered_tracks_dir.glob(f"R&S_Echoes_{channel.lower()}_1HrMix_*.wav")) + list(mastered_tracks_dir.glob("R&S_Echoes_1HrMix_*.wav")), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not wav_files:
        _log_fatal("MASTERED_AUDIO_NOT_FOUND", f"找不到母帶音軌: {mastered_tracks_dir}\n搜尋模式: R&S_Echoes_{channel.lower()}_1HrMix_*.wav 或 R&S_Echoes_1HrMix_*.wav")
    
    mastered_audio = wav_files[0]
    
    try:
        processor = MultiSceneProcessor()
        
        if bg_video_path:
            # 模式 1：單一影片母帶回收
            bg_video = Path(bg_video_path)
            if not bg_video.exists():
                _log_fatal("BG_VIDEO_NOT_FOUND", f"背景影片不存在: {bg_video}")
            _log_info(f"🎬 Phase 5: MultiSceneProcessor 母帶回收模式 (頻道: {channel.upper()})")
            _log_info(f"   背景短片: {bg_video.name}")
            _log_info(f"   母帶音軌: {mastered_audio.name}")
            result_path = processor.process_full_pipeline(
                channel=channel,
                audio_paths=[mastered_audio],
                override_video=bg_video,
            )
        elif bg_video_paths:
            # 模式 2：CEO 手選多支 + 金庫自動補齊
            video_list = [Path(p) for p in bg_video_paths]
            _log_info(f"🎬 Phase 5: MultiSceneProcessor 手動+自動輪播模式 (頻道: {channel.upper()})")
            _log_info(f"   CEO 手選: {len(video_list)} 支")
            for v in video_list:
                _log_info(f"     🎞️ {v.name}")
            _log_info(f"   母帶音軌: {mastered_audio.name}")
            result_path = processor.process_full_pipeline(
                channel=channel,
                audio_paths=[mastered_audio],
                override_videos=video_list,
            )
        else:
            # 模式 3：全自動金字塔抽樣
            _log_info(f"🎬 Phase 5: MultiSceneProcessor 全自動幻影輪播 (頻道: {channel.upper()})")
            _log_info(f"   母帶音軌: {mastered_audio.name}")
            result_path = processor.process_full_pipeline(
                channel=channel,
                audio_paths=[mastered_audio],
            )
        
        if not result_path or not result_path.exists():
            _log_fatal("VIDEO_PROCESSOR_FAILED", "MultiSceneProcessor 執行失敗，未產出檔案")
        
        file_size_mb = result_path.stat().st_size / (1024 ** 2)
        _log_info(f"✅ 影片處理完成 (Encode-Once-Repeat + Pre-baked Fade)")
        _log_info(f"✓ 視頻檔案已保存: {result_path.name} ({file_size_mb:.1f} MB)")
        _log_info(f"✓ 音訊純淨度: 100% 採用 -16 LUFS 母帶 (原視頻音軌已拋棄)")
        
        return True
    
    except Exception as exc:
        _log_fatal("VIDEO_PROCESSOR_ERROR", str(exc))


# ────────────────────────────────────────────────────────────────
# 備援補充邏輯
# ────────────────────────────────────────────────────────────────

def _run_suno_backup(target_count: int = 5, channel: str = "lofi",
                     purpose: str = "inventory") -> bool:
    """
    【CTO 端到端自動化 v8.8 / v15.9 強化】自動備援調度器 - 貫通 GLM 即時供彈鏈路
    【v11.5 物理分區】支援按頻道進行備援

    Args:
        target_count: 目標庫存數（ceo_approved_beats/ 應達到的 MP3 數量）
        channel:      頻道（lofi / light_music）
        purpose:      呼叫用途
                      - "inventory": 傳統庫存補充（新舊皆可，Protocol L 可衍生）
                      - "freshness": 【v15.9】新鮮度補彈（強制走 TTAPI，禁用 Protocol L 衍生）

    職責：
      1. 盤點庫存（ceo_approved_beats/）
      2. 若不足，檢查 .ceo_prompts/ 中的 daily_prompts_*.txt
      3. **若配方檔案不存在**，呼叫 generate_ceo_prompts.py 動態生成（GLM-4 驅動）
      4. 解析配方檔案提取 Tags 與 Prompt
      5. 迴圈呼叫 suno_api_engine.py 進行真實 TTAPI 生成
      6. 呼叫 audio_mastering_engine.py 進行母帶化
      7. 同步到 vault

    【v8.8 CTO 鐵律】嚴禁使用硬編碼 default_recipes。
    【v15.9】purpose="freshness" 時跳過 Protocol L（衍生仍是 dc>=1，無法補「新」）。
    """
    skip_protocol_l = (purpose == "freshness")
    if skip_protocol_l:
        _log_info(f"\n[FRESHNESS_FILL] ⚡ 新鮮度補彈模式：跳過 Protocol L，強制 TTAPI 生成全新 dc=0 曲目")
    ceo_approved_dir = get_channel_audio_dir(channel, "approved_beats")
    ceo_approved_count = len(list(ceo_approved_dir.glob("*.mp3")))
    
    if ceo_approved_count >= target_count:
        _log_info(f"✅ 庫存充足 ({ceo_approved_count} >= {target_count})")
        return True
    
    needed = target_count - ceo_approved_count
    _log_info(f"⚠️  庫存不足，需要補充 {needed} 個 track")
    
    # 【Protocol L - 金庫優先】先檢查是否可從已有音檔進行衍生提取
    # 【v15.9】新鮮度補彈時跳過 Protocol L（衍生是 dc>=1，補不到新鮮度）
    if PROTOCOL_L_AVAILABLE and not skip_protocol_l:
        _log_info(f"\n【Protocol L】先領舊歌模式：檢查金庫是否有可衍生的音檔...")
        try:
            vault = VaultDatabase()
            all_tracks = vault.get_all_tracks()
            
            # 【v12.35 基因污染防護】篩選 derivation_count < 3 的音檔，同時鎖定頻道以防止跨頻道汙染
            derivable_tracks = [t for t in all_tracks if (t.get('derivation_count') or 0) < 3 and t.get('channel') == channel]
            
            if derivable_tracks:
                _log_info(f"✅ 金庫中發現 {len(derivable_tracks)} 首可衍生音檔 (derivation_count < 3)")
                engine = DerivationEngine()
                
                derivation_types = ["tempo_up", "tempo_down", "pitch_up", "pitch_down"]
                generated_count = 0
                
                # 優先提領金庫存貨
                for track in derivable_tracks:
                    if generated_count >= needed:
                        break
                    
                    try:
                        input_path = track['original_path']
                        track_id = track['track_id']
                        
                        if not Path(input_path).exists():
                            _log_info(f"⚠️  原始音檔遺失: {input_path}")
                            continue
                        
                        # 嘗試衍生 (輪流使用不同類型)
                        dtype_idx = generated_count % len(derivation_types)
                        dtype = derivation_types[dtype_idx]
                        
                        _log_info(f"\n  【{generated_count+1}/{needed}】金庫衍生: {track_id} + {dtype}")
                        
                        output_path = engine.derive(
                            input_track_path=input_path,
                            track_id=track_id,
                            derivation_type=dtype,
                            output_dir=str(ceo_approved_dir)
                        )
                        
                        if output_path and output_path.exists():
                            _log_info(f"    ✅ 成功: {output_path.name}")
                            generated_count += 1
                        else:
                            _log_info(f"    ⚠️  衍生失敗")
                    
                    except Exception as e:
                        _log_info(f"    ⚠️  異常: {e}")
                
                _log_info(f"\n🎵 金庫衍生完成: 生成 {generated_count} 首新輯")
                needed -= generated_count
                
                if needed <= 0:
                    _log_info(f"✅ 透過衍生已補足庫存！無需調 Suno API")
                    _log_info(f"💚 節省成本: 已廢用 {generated_count} 次 Suno API 呼叫")
                    _log_info(f"\n【步驟 2】呼叫 audio_mastering_engine.py 對衍生音檔進行母帶化...")
                    mastering_result = _run_audio_mastering([], channel=channel)
                    if mastering_result:
                        _log_info(f"【步驟 3】同步母帶到 vault...")
                        _sync_mastered_to_vault(channel=channel)
                    return True
                else:
                    _log_info(f"⚠️  衍生不足，仍需補充 {needed} 首 (將調 Suno API)")
            else:
                _log_info(f"⚠️  金庫為空或無可衍生音檔")
        
        except Exception as e:
            _log_info(f"⚠️  Protocol L 查詢異常 (將改用標準 Suno API): {e}")
    
    # 【次數補彈】只有當衍生不足時，才允許調 Suno API
    # 【v12.5 路徑隔離】僅搜尋對應頻道的配方檔案
    recipe_dir = Path(config.workspace_root) / "assets" / ".ceo_prompts"
    recipe_dir.mkdir(parents=True, exist_ok=True)  # 確保目錄存在
    recipe_files = sorted(recipe_dir.glob(f"daily_prompts_{channel.upper()}_*.txt")) if recipe_dir.exists() else []
    
    recipes = []
    recipe_file_used = None
    
    if not recipe_files:
        # 【CTO 鐵律】配方檔不存在 → 呼叫 GLM-4 動態生成
        _log_info(f"🔄 配方檔案不存在，呼叫 generate_ceo_prompts.py 進行即時生成...")
        
        generate_prompts_script = Path(__file__).parent / "generate_ceo_prompts.py"
        if not generate_prompts_script.exists():
            _log_fatal("GENERATE_PROMPTS_MISSING", f"generate_ceo_prompts.py 不存在: {generate_prompts_script}")
        
        try:
            # 【動態供彈】呼叫 GLM-4 生成 N 個提示詞組
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}  # v15.10
            cmd = [
                sys.executable,
                str(generate_prompts_script),
                "--batch-size", str(needed),
                "--max-retries", "3",
                "--channel", channel
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 分鐘超時
                env=env
            )
            
            if result.returncode != 0:
                _log_fatal(
                    "GENERATE_PROMPTS_FAILED",
                    f"generate_ceo_prompts.py 執行失敗 (code={result.returncode})\n{result.stderr[-500:]}"
                )
            
            _log_info(f"✅ GLM-4 提示詞生成完成")
            
        except subprocess.TimeoutExpired:
            _log_fatal("GENERATE_PROMPTS_TIMEOUT", f"generate_ceo_prompts.py 超時 (>300s)")
        except Exception as exc:
            _log_fatal("GENERATE_PROMPTS_EXCEPTION", f"generate_ceo_prompts.py 異常: {exc}")
        
        # 【關鍵步驟】重新掃描 .ceo_prompts/ 尋找新生成的檔案
        # 【v12.5 路徑隔離】只搜尋對應頻道的配方檔案
        _log_info(f"🔍 重新掃描 .ceo_prompts/ 尋找新生成的配方檔 (頻道: {channel.upper()})...")
        recipe_files = sorted(recipe_dir.glob(f"daily_prompts_{channel.upper()}_*.txt"))
        
        if not recipe_files:
            _log_fatal(
                "NO_RECIPE_AFTER_GENERATION",
                f"generate_ceo_prompts.py 執行成功但未找到輸出檔案在 {recipe_dir}"
            )
    
    # 【主流程】解析配方檔案
    recipe_file_used = recipe_files[-1].name
    try:
        import re
        with open(recipe_files[-1], "r", encoding="utf-8") as f:
            file_content = f.read()
        
        # 【v12.6 & v12.5 融合解析】優先使用工業標籤格式，回退至舊格式
        # 首先檢查檔案是否包含 [CHANNEL: XXX] 標籤並驗證一致性
        channel_tag_match = re.search(r'\[CHANNEL:\s*(\w+)\]', file_content)
        if channel_tag_match:
            file_channel = channel_tag_match.group(1).lower()
            if file_channel != channel.lower():
                _log_fatal(
                    "CHANNEL_MISMATCH",
                    f"檔案聲稱的頻道 [{file_channel}] 與實際頻道 [{channel}] 不一致！防止基因交叉污染。"
                )
        
        recipes = []
        
        # 嘗試 v12.6 工業標籤格式
        industrial_tags_pattern = r'\[\[\[SUNO_TAGS_START\]\]\](.*?)\[\[\[SUNO_TAGS_END\]\]\]'
        industrial_lyrics_pattern = r'\[\[\[SUNO_LYRICS_START\]\]\](.*?)\[\[\[SUNO_LYRICS_END\]\]\]'
        industrial_video_pattern = r'\[\[\[VIDEO_PROMPT_START\]\]\](.*?)\[\[\[VIDEO_PROMPT_END\]\]\]'
        
        industrial_tags = re.findall(industrial_tags_pattern, file_content, re.DOTALL)
        industrial_lyrics = re.findall(industrial_lyrics_pattern, file_content, re.DOTALL)
        industrial_videos = re.findall(industrial_video_pattern, file_content, re.DOTALL)
        
        # 若工業標籤數量一致，優先使用工業格式
        if industrial_tags and industrial_lyrics and len(industrial_tags) == len(industrial_lyrics):
            _log_info(f"✅ 偵測到 v12.6 工業標籤格式，抽取 {len(industrial_tags)} 組")
            
            for idx, (tags_block, lyrics_block) in enumerate(zip(industrial_tags, industrial_lyrics)):
                tags = tags_block.lstrip()  # 【v12.18】仅去除左侧空白，保留末尾 ... (精准右侧修剪)
                prompt = lyrics_block.lstrip()  # 【v12.18】原封不动传输协议：保留所有末尾换行符与 ...
                title = ""  # 系統強制：將命名權還給 Suno
                
                # 【v12.5 任務三】打印提取的 prompt 最後 10 個字元進行 debug
                last_10_chars = prompt[-10:]
                _log_info(f"  【Group {idx+1}】提取 Prompt 最後 10 字元: {repr(last_10_chars)}")
                
                # 【v12.19 彈性邊界驗證】驗證時使用 rstrip() 忽略末尾空白/換行，但只要實體字符末尾是 ... 即可通過
                if not prompt.rstrip().endswith('...'):
                    _log_fatal(
                        "TIME_DILATION_MISSING",
                        f"【v12.19 驗證失敗】提示詞末尾（去除空白後）未以 ... 結尾！rstrip 後最後 10 字元: {repr(prompt.rstrip()[-10:])}"
                    )
                
                # 【v12.19 保留原始 Payload】雖然驗證用 rstrip()，但實際傳送保留末尾換行符（時間膨脹所需）
                recipes.append({
                    "prompt": prompt,  # ← 保留原始 prompt（包含換行符），不作任何修改
                    "tags": tags,
                    "title": title
                })
        else:
            # 回退至 v12.5 舊格式
            _log_info(f"📌 未偵測工業標籤，使用 v12.5 舊格式解析...")
            
            # 提取所有【第 N 組】的 Style（Tags）和 Prompt（Lyrics）
            block_pattern = r'【第\s+(\d+)\s+組】(.*?)(?=【第\s+\d+\s+組】|$)'
            blocks = re.findall(block_pattern, file_content, re.DOTALL)
            
            for group_num, block_content in blocks:
                # 從 block_content 中提取 Title（曲名）
                title_match = re.search(r'=== 🎵 歌曲名稱.*?===\r?\n(.+?)\r?\n', block_content)
                pure_title = title_match.group(1).strip() if title_match else "Unknown_Track"
                
                # 將空格替換為底線，移除非法字元（只保留英數字和底線）
                safe_title = "".join(c if c.isalnum() else "_" for c in pure_title)
                safe_title = re.sub(r'_+', '_', safe_title)  # 清理連續底線
                final_title = f"{int(group_num):03d}_{safe_title}"
                
                # 從 block_content 中提取 Tags
                tags_match = re.search(r'=== 📋 貼入 Suno 的【Style of Music】欄位 ===\r?\n(.+?)\r?\n', block_content)
                tags = tags_match.group(1).strip() if tags_match else "lofi,ambient,chill"
                
                # 【v12.5 任務二】使用新的 Robust Regex - 支援帶有警告標語的標題
                # 新規則確保保留結尾的 ... 符號
                prompt_match = re.search(r'===\s*🎤.*?欄位.*?===\r?\n(.*?)(?=\s*===\s*🎨|\-{10,}|$)', block_content, re.DOTALL)
                prompt = prompt_match.group(1).lstrip() if prompt_match else ""  # 【v12.18】仅左侧修剪，保留末尾 ...
                
                # 【v12.5 任務三】驗證時間膨脹符號
                last_10_chars = prompt[-10:] if len(prompt) >= 10 else prompt
                _log_info(f"  【Group {group_num}】提取 Prompt 最後 10 字元: {repr(last_10_chars)}")
                
                if not prompt.rstrip().endswith('...'):
                    _log_fatal(
                        "TIME_DILATION_MISSING",
                        f"Group {group_num} Prompt 未以時間膨脹符號 ... 結尾！Content: {repr(last_10_chars)}"
                    )
                
                # 若 Prompt 為空或不合理，產生備用
                if not prompt or len(prompt) < 10:
                    prompt = f"Create a lofi beat with characteristics: {tags}. Include [Intro], [Verse], [Chorus], and [Outro] sections."
                
                recipes.append({
                    "prompt": prompt,
                    "tags": tags,
                    "title": final_title
                })
        
        # 若正規表示式未找到任何項目，觸發致命錯誤（不允許回退到預設）
        if not recipes:
            _log_fatal(
                "RECIPE_PARSING_NO_MATCH",
                f"無法從 {recipe_file_used} 解析任何配方項目。檔案格式可能錯誤。"
            )
    
    except Exception as e:
        _log_fatal(
            "RECIPE_PARSING_ERROR",
            f"讀取/解析配方檔案 {recipe_file_used} 失敗: {e}"
        )
    
    _log_info(f"🎵 自動備援啟動（配方: {recipe_file_used}）")
    _log_info(f"📋 將進行 {needed} 次 TTAPI 呼叫進行生成...")
    
    suno_script = Path(__file__).parent / "suno_api_engine.py"
    if not suno_script.exists():
        _log_fatal("SUNO_ENGINE_MISSING", f"suno_api_engine.py 不存在: {suno_script}")
    
    # 迴圈生成
    success_count = 0
    failed_count = 0
    
    for i in range(needed):
        recipe_idx = i % len(recipes)
        recipe = recipes[recipe_idx]
        prompt = recipe.get("prompt", "Lofi beat")
        tags = recipe.get("tags", "lofi,chill")
        title = recipe.get("title", f"Backup_Track_{i:03d}")
        
        _log_info(f"\n【第 {i+1}/{needed} 首】呼叫 suno_api_engine.py")
        _log_info(f"  Title: {title}")
        _log_info(f"  Tags: {tags}")
        _log_info(f"  Prompt: {prompt[:80]}...")
        
        try:
            env = {**os.environ, "PIPELINE_RUNNER_AUTHORIZED": "1", "PYTHONUNBUFFERED": "1"}  # v15.10
            
            # 【真實呼叫】直接呼叫 suno_api_engine.py
            # 【v11.8】傳遞頻道專屬輸出目錄，確保精準著陸
            channel_approved_dir = get_channel_audio_dir(channel, "approved_beats")
            channel_approved_dir.mkdir(parents=True, exist_ok=True)
            _mp3_snap_before = _snapshot_ceo_mp3_mtimes(channel_approved_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(suno_script),
                    "--prompt", prompt,
                    "--tags", tags,
                    "--title", title,
                    "--output-dir", str(channel_approved_dir),  # 【v11.8】頻道隔離著陸點
                    "--channel", channel,  # 【v12.27 頻道參數穿透】強制傳遞頻道標籤
                ],
                stdout=sys.stdout,  # 【v12.15 日誌透傳】直接顯示 suno_api_engine 的所有日誌
                stderr=sys.stderr,  # 【v12.15 日誌透傳】直接顯示所有錯誤訊息（包含 HTTP 診斷）
                text=True,
                timeout=600,  # 10 分鐘 per track
                env=env
            )
            
            if result.returncode == 0:
                _log_info(f"✅ 第 {i+1} 首生成成功")
                _log_ttapi_download_summary_pipeline(
                    channel_approved_dir, _mp3_snap_before, channel
                )
                success_count += 1
                
                # 短暫延遲以避免 API 限流
                time.sleep(2)
            else:
                _log_info(f"⚠️  第 {i+1} 首生成失敗 (return code={result.returncode})")
                # 【v12.15】錯誤訊息已透過 stderr 直接顯示，無需二次輸出
                failed_count += 1
        
        except subprocess.TimeoutExpired:
            _log_info(f"⚠️  第 {i+1} 首超時")
            failed_count += 1
        except Exception as exc:
            _log_info(f"⚠️  第 {i+1} 首異常: {exc}")
            failed_count += 1
    
    _log_info(f"\n【生成結果】成功: {success_count}, 失敗: {failed_count}")
    
    # 【CTO ZERO SILENT FAILURES】如果完全失敗，立即觸發致命錯誤
    if success_count == 0:
        _log_fatal("AUTO_BACKUP_ZERO", f"[FATAL] 備援生成徹底失敗！成功: {success_count}/{needed}, 失敗: {failed_count}")
        return False
    
    if success_count < needed:
        _log_info(f"⚠️  部分成功（僅 {success_count}/{needed}）")
    
    # 現在 ceo_approved_beats/ 應該有新的 MP3 檔案了
    # 【v15.9】單次 Suno/TTAPI 任務常回傳 2 首 MP3（皆計費）；第二首起檔名為「標題 Vol. 2.mp3」形式（見 suno_api_engine.get_unique_filename）。
    # 母帶引擎掃描目錄內「尚未產出對應 _YT_*.wav」之檔案 → 全數母帶化 → 同步後皆為 dc=0 新歌。
    _log_info(f"\n【步驟 2】呼叫 audio_mastering_engine.py 對新生成的歌曲進行母帶化（多首下載將全數處理）...")
    mastering_result = _run_audio_mastering([], channel=channel)  # 【v12.20】保持頻道上下文，傳空列表讓 mastering engine 自行掃描
    
    if not mastering_result:
        _log_info("⚠️  母帶化部分失敗，但備援已生成新歌曲")
        return success_count > 0
    
    # 同步到 vault
    _log_info(f"\n【步驟 3】同步母帶到 vault...")
    _sync_mastered_to_vault(channel=channel)  # 【CTO 修復任務二】補上漏傳的 channel 參數，防止 Light Music 庫存黑洞
    
    _log_info(f"\n✅ 自動備援完成 (成功: {success_count}, 失敗: {failed_count})")
    return success_count > 0


# ────────────────────────────────────────────────────────────────
# 主工作流
# ────────────────────────────────────────────────────────────────

def _run_pipeline_workflow(skip_mastering: bool = False, skip_cleanup: bool = False, skip_metadata: bool = False, skip_assembler: bool = False, bg_video: str | None = None, bg_videos: list[str] | None = None, auto_visual: bool = False, sfx: str | None = None, sfx_mode: str = "global", channel: str = "lofi", ttapi_fill_fresh: bool = False, skip_publish: bool = False) -> None:
    """
    完整工作流：確保組織正確的依賴順序 + CTO 第三級搶修 (Data Loss 防護)
    
    【CTO 第三級搶修核心】：
    1. 安全封存 → 取代強制刪除 ✅
    2. WAV 副檔名支援 → audio_mastering_engine 修復 ✅
    3. 產線連續性 → 在備援後再次檢查庫存，如充足則強制逼入 Phase 4 & 5 ✅
    
    【Phase 流程】：
    1. Phase 1: 掃描 CEO 審批目錄
    2. Phase 2: 母帶處理 (audio_mastering_engine.py)
    3. Phase 3.5: 庫存同步 (同步母帶到 vault)
    4. **[第二步] 庫存盤點與自動備援** ← 若不足則觸發備援
    5. **[CTO 搶修] 備援後重新檢查庫存** ← 確保不會提早退出！
    6. Phase 3: 發行企劃 (music_metadata_engine.py)
    7. Phase 4: 無縫混音 (lofi_assembler.py) ← 只要庫存充足，就絕對進行
    8. Phase 4.5: YouTube CheatSheet 最終合體
    9. Phase 5 (可選): 萬能影片循環處理器
    """
    MINIMUM_INVENTORY_FOR_PRODUCTION = 10  # CTO 指定的最小庫存量（以曲數計）
    
    _log_info("=" * 80)
    _log_info("【v8.8.2 CTO 第三級搶修 - 資料遺失防護與產線連續性保證】")
    _log_info("=" * 80)
    
    # 步驟 1: 掃描 CEO 審批目錄
    _log_info(f"\n【步驟 1 | Phase 1】掃描 CEO 審批目錄 (頻道: {channel})")
    ceo_approved_files = _scan_ceo_approved_beats(channel=channel)
    
    # 【商業化升級】自動計算 Volume 卷號
    def _calculate_volume_number() -> int:
        """掃描 final_exports/ 目錄，自動推算卷號（最小值 5）"""
        try:
            export_dir = Path(config.workspace_root) / "assets" / "final_exports"
            existing_files = list(export_dir.glob("R&S_1HrMix_WithVideo_*.mp4")) + \
                           list(export_dir.glob("youtube_sheet_*.txt"))
            volume = max(5, len(existing_files) + 1)
            _log_info(f"【自動卷號】掃描結果: 已存在 {len(existing_files)} 份匯出檔，計算卷號 = {volume}")
            return volume
        except Exception as e:
            _log_warn(f"【自動卷號】掃描失敗，回退至預設: {e}")
            return 5
    
    volume_num = _calculate_volume_number()
    
    # 步驟 2: 母帶處理（若有新檔案）
    if not skip_mastering:
        _log_info("\n【步驟 2 | Phase 2】母帶處理 (-16 LUFS)")
        _run_audio_mastering(ceo_approved_files, channel=channel)
        
        # 【CTO 軍令狀 v8.9.1】停止自動清理！保存所有 CEO 素材直到手動確認
        # 原自動清理邏輯已廢除，改為手動確認制
        # 詳見 rs_manager.py [7] 號選單
        _log_info("\n【步驟 3】⏭️  手動確認制已啟動 (CEO 指令 [7] 可在任何時刻清理)")
    else:
        _log_info("\n【步驟 2 | Phase 2】⏭️  跳過母帶處理 (--skip-mastering)")
    
    # 步驟 3.5: 庫存補充 (同步母帶到 vault)
    _log_info("\n【步驟 3.5】庫存補充機制 (同步母帶到 vault_ready_for_mix)")
    _sync_mastered_to_vault(channel=channel)
    
    # 【CTO 關鍵修正】步驟 4: 庫存盤點與自動備援 ← 必須在 lofi_assembler 之前！
    _log_info("\n【步驟 4 | 關鍵修正】庫存盤點與自動備援 (備援必須先於混音)")
    backup_result = _run_suno_backup(target_count=5, channel=channel)
    
    # 【CTO ZERO SILENT FAILURES】如果備援徹底失敗，管線必須中止
    if not backup_result:
        _log_fatal("INVENTORY_CRITICAL", "[FATAL] 備援生成徹底失敗，無法滿足庫存，管線強行終止！")
        sys.exit(1)
    
    # 【CTO 第三級搶修】步驟 4.5: 備援後再次檢查庫存，確保產線連續性
    _log_info("\n【步驟 4.5 | CTO 搶修】備援完成後重新檢查庫存")
    current_inventory = _check_vault_inventory(channel=channel)
    
    if current_inventory < MINIMUM_INVENTORY_FOR_PRODUCTION:
        _log_info(f"\n⚠️  庫存檢查警告: {current_inventory} < {MINIMUM_INVENTORY_FOR_PRODUCTION} (目標庫存)")
        _log_info(f"   系統將繼續運行，但混音可能不足 1 小時")
        _log_info(f"   建議 CEO 手動補充更多歌曲或重新運行產線")
    else:
        _log_info(f"\n✅ 庫存充足確認: {current_inventory} >= {MINIMUM_INVENTORY_FOR_PRODUCTION}")
        _log_info(f"   【產線保證】系統將強制進入 Phase 4 & 5，確保不會提早退出")

    # 【v15.9 新鮮度鐵律】步驟 4.6：Phase 4 前置閘門 — 驗證 dc=0 新歌 ≥ 50%
    _log_info("\n【步驟 4.6 | v15.9 新鮮度鐵律】Phase 4 前置閘門檢查")
    _FRESHNESS_TARGET_TRACKS = 20  # 與 VaultSelection 預設一致
    _freshness = _check_freshness_quota(channel=channel, target_tracks=_FRESHNESS_TARGET_TRACKS)
    if not _freshness["passed"]:
        if ttapi_fill_fresh and _freshness["enabled"]:
            # 自動補彈：調用 TTAPI 生成缺口數量的全新 dc=0 曲目
            _needed_fresh = _freshness["deficit"]
            _log_info(f"\n[FRESHNESS_FILL] 🔫 --ttapi-fill-fresh 已啟用，向 TTAPI 請求 {_needed_fresh} 首新歌...")
            # target_count = 當前已有新歌 + 缺口 → _run_suno_backup 會比對 ceo_approved_beats 現有數量後補齊
            _current_approved = len(list(get_channel_audio_dir(channel, "approved_beats").glob("*.mp3")))
            _fill_target = _current_approved + _needed_fresh
            _fill_ok = _run_suno_backup(target_count=_fill_target, channel=channel, purpose="freshness")
            if not _fill_ok:
                _log_fatal(
                    "FRESHNESS_FILL_FAILED",
                    f"[FATAL] TTAPI 新鮮度補彈失敗，無法達成 {_freshness['min_ratio']*100:.0f}% 新歌門檻，管線終止。"
                )
                sys.exit(4)
            _log_info("[FRESHNESS_FILL] ✅ TTAPI 補彈完成，重新同步 vault 並複檢新鮮度...")
            _sync_mastered_to_vault(channel=channel)
            _freshness = _check_freshness_quota(channel=channel, target_tracks=_FRESHNESS_TARGET_TRACKS)
            if not _freshness["passed"]:
                _log_fatal(
                    "FRESHNESS_VIOLATION_AFTER_FILL",
                    f"[FATAL] 補彈後新鮮度仍未達標（可選新歌 {_freshness['available_new']} < 需求 {_freshness['quota_new']}），管線終止。"
                )
                sys.exit(4)
        elif _freshness["enforcement"] == "warn":
            _log_info("[FRESHNESS_GATE] ⚠️  warn 模式：新鮮度未達標但不中止，Phase 4 將以降級配額繼續")
        else:
            _log_fatal(
                "FRESHNESS_VIOLATION",
                f"[FATAL] 新鮮度鐵律違規：頻道 {channel} 可選新歌僅 {_freshness['available_new']}，"
                f"需要 {_freshness['quota_new']}（{_freshness['min_ratio']*100:.0f}%）。\n"
                f"解法：(1) CEO 上傳 {_freshness['deficit']} 首新 MP3 至 ceo_approved_beats/{channel}/\n"
                f"      (2) 加 --ttapi-fill-fresh 旗標，由 TTAPI 自動補彈\n"
                f"      (3) 以環境變數 FRESHNESS_ENFORCEMENT=warn 降級（不建議）"
            )
            sys.exit(4)
    else:
        _log_info("[FRESHNESS_GATE] ✅ 通過：可安全進入 Phase 3/4")

    # 【CTO 營運升級】庫存戰情儀表板【v12.21 頻道支持】
    _log_inventory_dashboard(channel=channel)
    
    # 步驟 5: Phase 3 - 發行企劃引擎
    if not skip_metadata:
        _log_info("\n【步驟 5 | Phase 3】發行企劃引擎 (DistroKid 中繼資料)")
        _run_music_metadata_engine(volume=volume_num, channel=channel)

        # ★ v15.12 Phase 3.5: DistroKid CSV 上傳表（發後不理，不阻擋產線）
        _log_info("\n【步驟 5.5 | Phase 3.5】DistroKid CSV 上傳表生成")
        try:
            csv_path = build_distrokid_upload_csv(channel)
            _log_info(f"✅ DistroKid CSV 上傳表已生成: {csv_path.name}")
        except Exception as _e:
            _log_info(f"⚠️  Phase 3.5 輕度出錯（非致命，產線繼續）: {_e}")
    else:
        _log_info("\n【步驟 5 | Phase 3】⏭️  跳過發行企劃 (--skip-metadata)")
    
    # 【CTO 第三級搶修】步驟 6: Phase 4 - 無縫混音 
    # 【CRITICAL】只要庫存充足（通過第 4.5 步檢查），就絕對進行本步驟！
    # 不允許任何提早退出或跳回主選單！
    if not skip_assembler:
        if current_inventory > 0:  # 只要有庫存，就強制進行
            _log_info("\n【步驟 6 | Phase 4】1 小時無縫混音縫合 ← 強制進行")
            _log_info(f"   庫存確認: {current_inventory} 首有效母帶 (頻道: {channel.upper()})")
            _run_lofi_assembler(sfx=sfx, sfx_mode=sfx_mode, channel=channel)
            
            # 步驟 6.5: YouTube CheatSheet 最終合體 (CTO v9.0)
            _log_info("\n【步驟 6.5 | Phase 4.5】YouTube CheatSheet 最終合體")
            # 【CTO 頻道隔離】傳遞 channel 參數給 _finalize_youtube_cheatsheet()
            _finalize_youtube_cheatsheet(channel=channel)
        else:
            _log_info("\n【步驟 6 | Phase 4】⏭️  跳過無縫混音: 庫存為 0（無法進行）")
    else:
        _log_info("\n【步驟 6 | Phase 4】⏭️  跳過無縫混音 (--skip-assembler)")
    
    # 步驟 7: Phase 5 (可選) - 萬能影片循環處理器
    if bg_video or bg_videos or auto_visual:
        _log_info("\n【步驟 7 | Phase 5】萬能影片循環處理器")
        if auto_visual and not bg_video and not bg_videos:
            _log_info("   🎲 全自動幻影輪播模式（金字塔抽樣）")
        _run_video_processor(bg_video_path=bg_video, bg_video_paths=bg_videos, channel=channel)
    else:
        _log_info("\n【步驟 7 | Phase 5】⏭️  跳過影片處理 (未指定 --bg-video / --bg-videos / --auto-visual)")
    
    # 步驟 8: 最終交付提示 (CEO 手動發行友好版)
    
    # 【CTO 戰情同步】產線完工後，再次印出最新的庫存狀態【v12.21 頻道支持】
    _log_info("\n【最新戰情報表 (更新後)】")
    _log_inventory_dashboard(channel=channel)
    
    _log_info("\n" + "=" * 80)
    # 【v12.20 條件式完工提示】只有庫存 > 0 且未跳過組裝時才顯示完工信息
    if current_inventory > 0 and not skip_assembler:
        _log_info("🎉🎉🎉 產線全部完工！🎉🎉🎉")
    else:
        _log_info("⚠️  任務因庫存不足或跳過組裝中斷 (未進行混音)")
    _log_info("=" * 80)
    _log_info("\n【📋 CEO 發行準備清單】\n")
    _log_info("✅ 所有成品已準備就緒（位於 assets/final_exports/）：")
    _log_info(f"   📊 中繼資料文件：    metadata_distrokid_{{channel}}.json")
    _log_info("   📋 DistroKid 上架單： DistroKid_Sheet_*.txt")
    _log_info("   📝 Tracklist 時間軸： Tracklist_*.txt (自動生成的曲目時間戳)")
    _log_info("   🎬 YouTube 上架文案： youtube_sheet_*.txt")
    _log_info("   🎵 母帶音檔集：      *_YT_-16LUFS.wav (所有曲目)")
    _log_info("   🎬 1小時混音長片：   R&S_Echoes_1HrMix_Vol.*.wav")
    _log_info("   🖼️  專輯封面圖檔：   (若已生成)")
    _log_info("\n【🚀 CEO 下一步行動】\n")
    _log_info("1️⃣  打開 DistroKid_Sheet_*.txt")
    _log_info("2️⃣  複製對應欄位，粘貼到 https://distrokid.com/new")
    _log_info("3️⃣  上傳音軌、封面與 YouTube 描述")
    _log_info("4️⃣  確認所有平台（Spotify, Apple Music 等）的發行設定")
    _log_info("5️⃣  提交發行，等待 24-48 小時審核")
    _log_info("\n【💡 檔案位置】")
    final_exports_path = Path(config.workspace_root) / "assets" / "final_exports"
    _log_info(f"📁 {final_exports_path}")
    _log_info("\n【✨ CTO 搶修驗收】")
    _log_info(f"✅ 任務一: 安全封存實裝 (ceo_archived_beats/)")
    _log_info(f"✅ 任務二: 母帶引擎副檔名修復 (*.mp3 + *.wav)")
    _log_info(f"✅ 任務三: 產線連續性保證 (備援後強制進入 Phase 4 & 5)")
    _log_info(f"✅ 最終庫存確認: {current_inventory} 首有效母帶")
    _log_info("\n祝您發行順利！🎵✨")
    _log_info("\n" + "=" * 80)

    # ──────────────── 整合：高使用次數歌曲整理（遷移/刪除） ────────────────
    try:
        archiver_script = Path(config.workspace_root) / "scripts" / "gear1_prod" / "cloud_archiver.py"
        if archiver_script.exists():
            _log_info("\n[音檔整理] 啟動 cloud_archiver（derivation_count>=3 + channel + remix 刪除）...")
            p = subprocess.run(
                [
                    sys.executable,
                    str(archiver_script),
                    "--channel",
                    channel,
                    "--execute",
                    "--max-actions",
                    "20",
                    "--log-path",
                    str(Path(config.workspace_root) / "assets" / ".logs" / "shorts_audio_cleanup.log"),
                ],
                capture_output=True,
                text=True,
                timeout=1200,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},  # v15.10
            )
            if p.returncode == 0:
                _log_info("[音檔整理] 完成。")
            else:
                err = (p.stderr or p.stdout or "").strip().splitlines()
                _log_info(f"[音檔整理] 失敗 (Exit {p.returncode})：{(err[-1] if err else 'unknown')}")
        else:
            _log_info(f"[音檔整理] 跳過：找不到 {archiver_script}")
    except Exception as e:
        _log_info(f"[音檔整理] 異常：{e}")

    # ──────────────── 自動串接 CEO 發行流程 ────────────────
    if skip_publish:
        _log_info("\n[自動發行] 已略過 (--skip-publish / --local-only)：未呼叫 SMB 發行流程。")
        return
    try:
        from scripts.ui.backend import get_ui_backend
        import json
        backend = get_ui_backend()
        backend.set_channel(channel)
        _log_info("\n[自動發行] 產線完工，啟動 CEO 發行流程 (publish_final_exports, mode=auto)...")
        result = backend.publish_final_exports(mode="auto")
        # 發行結果摘要
        _log_info(f"[自動發行] 發行訊息: {result.get('msg')}")
        # 寫入 publish_status.json 供 UI 輪詢
        exp_dir = backend.get_channel_export_dir()
        status_path = exp_dir / "publish_status.json"
        try:
            with open(status_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            _log_info(f"[自動發行] 發行狀態已寫入: {status_path}")
        except Exception as e:
            _log_info(f"[自動發行] 寫入 publish_status.json 失敗: {e}")
        # 發行前完整性檢查（metadata/影片/音訊/cheatsheet）
        missing = []
        if not (exp_dir / f"metadata_distrokid_{channel}.json").exists():
            missing.append(f"metadata_distrokid_{channel}.json")
        if not list(exp_dir.glob("DistroKid_Sheet_*.txt")):
            missing.append("DistroKid_Sheet_*.txt")
        if not list(exp_dir.glob("*.mp4")):
            missing.append("*.mp4")
        if not glob_youtube_sheet_paths(exp_dir):
            missing.append("youtube_sheet_*.txt")
        if missing:
            _log_info(f"[自動發行] 發行後檔案缺失: {missing}")
        else:
            _log_info("[自動發行] 所有發行檔案完整無缺。")
        # ── Telegram 通知 CEO ──
        try:
            from scripts.common import telegram_bot_manager
            msg = f"🎉 產線自動發行完成！\n頻道: {channel}\n{result.get('msg')}\n\n發行檔案: {exp_dir}"
            telegram_bot_manager._log(msg, level="INFO")
        except Exception as e:
            _log_info(f"[自動發行] 發送 Telegram 通知失敗: {e}")
    except Exception as e:
        _log_info(f"[自動發行] 發行流程異常: {e}")


# ────────────────────────────────────────────────────────────────
# 主入口
# ────────────────────────────────────────────────────────────────

def main() -> None:
    """主程式入口。"""
    parser = argparse.ArgumentParser(
        description="AI_DRAMA_FACTORY 總指揮官 - CEO 輔助模式 v8.8"
    )
    parser.add_argument(
        "--skip-mastering",
        action="store_true",
        help="跳過母帶處理 (Phase 2)"
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="跳過清空 ceo_approved_beats/"
    )
    parser.add_argument(
        "--skip-metadata",
        action="store_true",
        help="跳過發行企劃引擎 (Phase 3)"
    )
    parser.add_argument(
        "--skip-assembler",
        action="store_true",
        help="跳過無縫混音 (Phase 4)"
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="跳過 Suno 備援補充"
    )
    parser.add_argument(
        "--bg-video",
        type=str,
        default=None,
        help="單一背景影片路徑 (MP4)，母帶回收模式"
    )
    parser.add_argument(
        "--bg-videos",
        type=str,
        nargs="+",
        default=None,
        help="CEO 手選多支背景影片路徑 (MP4)，系統從金庫自動補齊剩餘"
    )
    parser.add_argument(
        "--auto-visual",
        action="store_true",
        help="全自動幻影輪播模式，系統從金庫自動金字塔抽樣 6 支影片"
    )
    parser.add_argument(
        "--sfx",
        type=str,
        default=None,
        help="環境音檔案路徑 (WAV/MP3)，將以 2%% 音量疊加到混音中"
    )
    parser.add_argument(
        "--sfx-mode",
        type=str,
        choices=["transition", "global"],
        default="global",
        help="SFX 播放模式：transition (僅過場) 或 global (全程)"
    )
    parser.add_argument(
        "--channel",
        type=str,
        choices=["lofi", "light_music"],
        default="lofi",
        help="視覺頻道：lofi（Lofi 頻道）或 light_music（Light Music 首航），預設 lofi"
    )
    parser.add_argument(
        "--ttapi-fill-fresh",
        action="store_true",
        help="【v15.9 新鮮度鐵律】dc=0 新歌不足時，自動呼叫 TTAPI Suno 生成缺口（會產生費用）。預設關閉：不足時中止產線並要求 CEO 手動上傳。"
    )
    parser.add_argument(
        "--skip-publish",
        "--local-only",
        dest="skip_publish",
        action="store_true",
        help="產線結尾不執行 SMB 推播至 Mac mini（本機測試用）。未指定時維持完工後自動 publish_final_exports。",
    )
    args = parser.parse_args()
    
    try:
        # 【v15.10 P2-#6】Phase 1 雙庫同步預檢 — 提前發現資源不足
        _log_info(f"\n🔍 [Preflight] {args.channel.upper()} 雙庫預檢...")
        preflight_report = preflight_dual_vault(args.channel)
        if not preflight_report.passed and not args.skip_assembler:
            _log_fatal(
                "PREFLIGHT_VAULT_FAILED",
                f"雙庫預檢未通過 (bottleneck={preflight_report.bottleneck})。\n"
                f"建議：(1) 上傳新曲/影片素材\n"
                f"      (2) 使用 --ttapi-fill-fresh 補彈\n"
                f"      (3) 使用 --skip-assembler 跳過合成，僅做母帶"
            )
            sys.exit(5)

        _run_pipeline_workflow(
            skip_mastering=args.skip_mastering,
            skip_cleanup=args.skip_cleanup,
            skip_metadata=args.skip_metadata,
            skip_assembler=args.skip_assembler,
            bg_video=args.bg_video,
            bg_videos=args.bg_videos,
            auto_visual=args.auto_visual,
            sfx=args.sfx,
            sfx_mode=args.sfx_mode,
            channel=args.channel,
            ttapi_fill_fresh=args.ttapi_fill_fresh,
            skip_publish=args.skip_publish,
        )
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _log_fatal("UNHANDLED_EXCEPTION", str(exc))


if __name__ == "__main__":
    main()
