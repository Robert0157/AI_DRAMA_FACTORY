#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【Protocol L-Archive】冷儲存與容量管理系統
- 原生歌曲 (is_derivative=False) → 冷儲存封存
- 衍生歌曲 (is_derivative=True) → 物理直接刪除
- 90% 閘門 → CEO 授權 FIFO 清理
"""

import os, sys, shutil, json, argparse
from datetime import datetime
from pathlib import Path

# 【跨平台防線】以腳本位置動態推導專案根目錄，禁止硬編碼磁碟機代號
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.common.env_manager import config
WORKSPACE_ROOT = str(config.workspace_root)  # v15.10: 改由 config 派發
MAX_VAULT_CAPACITY = 100
VAULT_WARNING_THRESHOLD = 0.9  # 90%
MAC_SHORT_AUDIO_ROOT = str(config.mac_short_audio_root)  # v15.10: 改由 config 派發

# 動態導入 VaultDatabase
sys.path.insert(0, os.path.join(WORKSPACE_ROOT, "scripts", "gear2_rnd"))
from vault_database import VaultDatabase


def _purge_track(vault: VaultDatabase, track_id: str) -> None:
    """向後相容 purge_track：若 VaultDatabase 無此方法，退回 SQL 刪除。"""
    if hasattr(vault, "purge_track"):
        vault.purge_track(track_id)
        return
    cursor = vault.conn.cursor()
    cursor.execute("DELETE FROM audio_assets WHERE track_id = ?", (track_id,))
    vault.conn.commit()


def _archive_track(vault: VaultDatabase, track_id: str) -> None:
    """向後相容 archive_track：若無方法，改以 is_archived=1 標記。"""
    if hasattr(vault, "archive_track"):
        vault.archive_track(track_id)
        return
    cursor = vault.conn.cursor()
    cursor.execute(
        """
        UPDATE audio_assets
        SET is_archived = 1, archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE track_id = ?
        """,
        (track_id,),
    )
    vault.conn.commit()


def _run_logger(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def _log(msg: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(msg)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    return _log


def _write_shorts_signal(
    *,
    shorts_root: Path,
    channel: str,
    mode: str,
    stats: dict,
    max_actions: int,
) -> Path:
    """
    寫入 Shorts sidecar signal（原子寫入）：
    Windows 端: Y:\\Shorts_audio\\{channel}\\.signal.json
    Mac 端對應: /Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/{channel}/.signal.json
    """
    now = datetime.now()
    signal_path = shorts_root / channel / ".signal.json"
    payload = {
        "schema_version": "shorts-signal-v1",
        "batch_id": now.strftime("%Y%m%d_%H%M%S"),
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": channel,
        "mode": mode,
        "windows_path": str(shorts_root / channel),
        "mac_mount_path": f"{MAC_SHORT_AUDIO_ROOT}/{channel}",
        "stats": stats,
        "max_actions": max_actions,
        "auto_sync_enabled": True,
    }
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = signal_path.with_name(signal_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(signal_path)
    return signal_path


def archive_with_selective_filter(
    target_channel: str = "all",
    *,
    execute: bool = False,
    max_actions: int = 0,
    log_path: Path | None = None,
):
    """
    高使用次數清理邏輯（CTO 規則）：
    - derivation_count >= 3 且非 remix：搬移到 Y:/Shorts_audio/{channel}
    - derivation_count >= 3 且 remix：物理刪除 + DB 清理
    """
    vault = VaultDatabase()
    shorts_root = config.smb_shorts_root  # v15.10 P3#10: 已從硬編碼 Y:/Shorts_audio 改用 config.smb_shorts_root
    shorts_dirs = {
        "light_music": shorts_root / "light_music",
        "lofi": shorts_root / "lofi",
    }
    if target_channel in shorts_dirs:
        channels = [target_channel]
    else:
        channels = ["light_music", "lofi"]
    channels_sql = ",".join(f"'{c}'" for c in channels)
    for d in shorts_dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    log = _run_logger(log_path) if log_path else print
    mode = "EXECUTE" if execute else "DRY-RUN"
    log(
        f"🔍 掃描高使用次數軌道 (derivation_count >= 3, 依 channel={channels}，不看 status)..."
        f" mode={mode}, max_actions={max_actions if max_actions > 0 else 'unlimited'}"
    )
    
    cursor = vault.conn.cursor()
    
    # 查詢所有退役軌道
    cursor.execute(f"""
        SELECT * FROM audio_assets 
        WHERE derivation_count >= 3
          AND channel IN ({channels_sql})
          AND is_archived = 0
        ORDER BY channel, derivation_count DESC
    """)
    retired_tracks = cursor.fetchall()

    moved_count = 0
    deleted_count = 0
    missing_count = 0
    failed_count = 0
    skipped_count = 0
    dryrun_count = 0
    action_count = 0
    channel_stats = {
        ch: {"moved": 0, "deleted": 0, "missing": 0, "failed": 0, "dryrun": 0}
        for ch in channels
    }

    def _is_remix_track(track: dict) -> bool:
        # 依 CTO 指令：僅使用 track_id/檔名關鍵字判斷，不使用 is_derivative。
        name = f"{track.get('track_id', '')} {Path(track.get('original_path', '')).name}".lower()
        remix_keywords = (
            "tempo_down",
            "tempo_up",
            "pitch_up",
            "pitch_down",
            "remix",
            "[remix",
            "(remix",
            "vol.",
            "vol ",
            "mix",
            "edit",
        )
        return any(k in name for k in remix_keywords)
    
    for track_row in retired_tracks:
        if max_actions > 0 and action_count >= max_actions:
            log(f"⏹️ 達到安全上限 max_actions={max_actions}，停止本輪整理。")
            break

        track = dict(track_row)
        track_id = track["track_id"]
        original_path = track["original_path"]
        channel = str(track.get("channel") or "lofi").strip().lower()
        channel = channel if channel in shorts_dirs else "lofi"
        
        if not Path(original_path).exists():
            if execute:
                log(f"⚠️ 檔案已遺失: {original_path}")
                _purge_track(vault, track_id)
                missing_count += 1
                channel_stats[channel]["missing"] += 1
            else:
                log(f"[DRYRUN][MISSING] {track_id} :: {original_path} (將 purge DB)")
                dryrun_count += 1
                channel_stats[channel]["dryrun"] += 1
            action_count += 1
            continue

        if _is_remix_track(track):
            # ====== remix：直接物理刪除 ======
            if not execute:
                log(f"[DRYRUN][DELETE] {track_id} -> {original_path}")
                dryrun_count += 1
                channel_stats[channel]["dryrun"] += 1
            else:
                try:
                    os.remove(original_path)
                    _purge_track(vault, track_id)
                    log(f"🗑️ 【REMIX刪除】 {track_id}")
                    deleted_count += 1
                    channel_stats[channel]["deleted"] += 1
                except Exception as e:
                    log(f"❌ 刪除失敗: {original_path} - {e}")
                    failed_count += 1
                    channel_stats[channel]["failed"] += 1
            action_count += 1
        else:
            # ====== 非 remix：遷移到 Shorts_audio/{channel}（move，非 copy）======
            filename = Path(original_path).name
            src = Path(original_path)
            src_norm = str(src).replace("\\", "/").lower()
            dst_root_norm = str(shorts_dirs[channel]).replace("\\", "/").lower()
            if src_norm.startswith(dst_root_norm + "/"):
                log(f"⏭️ 已在目標資料夾，略過: {track_id} -> {original_path}")
                skipped_count += 1
                action_count += 1
                continue
            dst = shorts_dirs[channel] / filename
            if dst.exists():
                dst = shorts_dirs[channel] / f"{Path(filename).stem}__dup_{track_id}{Path(filename).suffix}"
            if not execute:
                log(f"[DRYRUN][MOVE] {track_id} : {original_path} -> {dst}")
                dryrun_count += 1
                channel_stats[channel]["dryrun"] += 1
            else:
                try:
                    shutil.move(original_path, str(dst))
                    cursor.execute(
                        """
                        UPDATE audio_assets
                        SET original_path = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE track_id = ?
                        """,
                        (str(dst), track_id),
                    )
                    vault.conn.commit()
                    log(f"📦 【遷移至Shorts】 {track_id} → {dst}")
                    moved_count += 1
                    channel_stats[channel]["moved"] += 1
                except Exception as e:
                    log(f"❌ 遷移失敗: {original_path} - {e}")
                    failed_count += 1
                    channel_stats[channel]["failed"] += 1
            action_count += 1

    if execute:
        for ch in channels:
            sig = _write_shorts_signal(
                shorts_root=shorts_root,
                channel=ch,
                mode=mode,
                stats=channel_stats[ch],
                max_actions=max_actions,
            )
            log(f"📡 Shorts Signal 已寫入: {sig}")

    log(
        f"\n✅ 完成: 遷移 {moved_count} 首, 刪除(remix) {deleted_count} 首, "
        f"遺失清理 {missing_count} 首, 略過(已在目標) {skipped_count} 首, 失敗 {failed_count} 首, "
        f"dryrun預計動作 {dryrun_count} 首"
    )

    return moved_count + deleted_count + missing_count


def check_vault_capacity_and_notify():
    """
    檢查冷庫容量，若達到 90%，向 CEO 發送 Telegram 通知
    
    Returns:
        (current_capacity, should_trigger_cleanup_button)
    """
    vault = VaultDatabase()
    if hasattr(vault, "get_vault_capacity"):
        current = vault.get_vault_capacity()
    else:
        # 向後相容：新版 VaultDatabase 無 get_vault_capacity 時，以活躍軌道數估算容量。
        cursor = vault.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audio_assets WHERE is_archived = 0")
        row = cursor.fetchone()
        current = int(row[0] if row else 0)
    threshold = int(MAX_VAULT_CAPACITY * VAULT_WARNING_THRESHOLD)
    
    print(f"📊 冷庫容量: {current}/{MAX_VAULT_CAPACITY} ({current/MAX_VAULT_CAPACITY*100:.1f}%)")
    
    if current >= threshold:
        print(f"🚨 【警告】冷庫已達 {VAULT_WARNING_THRESHOLD*100:.0f}% 容量！")
        return (current, True)
    else:
        return (current, False)


def trigger_fifo_cleanup(cleanup_count: int = None):
    """
    執行加權FIFO清理（考慮基因強度豁免）：
    - 優先保留高基因強度的原生母帶（前20%）
    - 優先刪除無衍生價值的原生曲和衍生曲
    - 按ancient-first順序刪除剩余曲目
    
    Args:
        cleanup_count: 目標保留軌道數 (默認 50)
        
    Returns:
        (deleted_tracks, preserved_tracks, audit_data)
    """
    if cleanup_count is None:
        cleanup_count = MAX_VAULT_CAPACITY // 2
    
    vault = VaultDatabase()
    
    print(f"🧬 【加權FIFO清理】啟動基因強度評估...")
    
    # 計算加權清理方案
    fifo_plan = vault.get_weighted_fifo_candidates(target_count=cleanup_count)
    to_delete = fifo_plan['to_delete']
    to_preserve = fifo_plan['to_preserve']
    
    if not to_delete:
        print(f"✅ 冷庫已在目標水位 ({len(to_preserve)}/{cleanup_count})")
        return ([], to_preserve, {})
    
    print(f"🧹 清理方案：刪除 {len(to_delete)} 首，保留 {len(to_preserve)} 首")
    print(f"   ├─ 豁免保留：{len([t for t in to_preserve if t['derivation_count'] > 0])} 首高價值母帶")
    print(f"   └─ 待刪除：{len(to_delete)} 首無效/衍生曲")
    
    # 執行刪除
    deleted_tracks = []
    space_freed_mb = 0.0
    archive_path = Path(WORKSPACE_ROOT) / "assets" / "audio" / "ceo_archived_beats"
    # v15.10: ceo_archived_beats 已於 LOFI 清除中刪除，若不存在則跳過封存清理
    if not archive_path.exists():
        print(f"  ℹ️ ceo_archived_beats/ 不存在，跳過封存清理")
    
    for track in to_delete:
        track_id = track["track_id"]
        original_path = track["original_path"]
        genetic_score = vault.get_genetic_score(track_id)
        
        # 計算檔案大小
        file_size_mb = 0.0
        if Path(original_path).exists():
            file_size_mb = Path(original_path).stat().st_size / (1024**2)
        
        # 刪除原檔
        if Path(original_path).exists():
            try:
                os.remove(original_path)
                space_freed_mb += file_size_mb
                print(f"  🗑️ 刪除: {track_id} (Genetic Score: {genetic_score:.1f}%, Size: {file_size_mb:.1f}MB)")
            except Exception as e:
                print(f"  ❌ 無法刪除原檔: {e}")
        
        # 刪除封存副本
        for archived_file in archive_path.glob(f"{track_id}_*"):
            try:
                archived_file.unlink()
            except Exception as e:
                print(f"  ⚠️ 無法刪除封存: {e}")
        
        # 更新DB
        _purge_track(vault, track_id)
        deleted_tracks.append({
            'track_id': track_id,
            'genetic_score': genetic_score,
            'size_mb': file_size_mb,
            'archived_at': track['archived_at']
        })
    
    # 生成審計數據
    audit_data = {
        'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
        'total_deleted': len(deleted_tracks),
        'total_preserved': len(to_preserve),
        'space_freed_mb': round(space_freed_mb, 2),
        'deleted_tracks': deleted_tracks,
        'preserved_tracks': [{
            'track_id': t['track_id'],
            'genetic_score': vault.get_genetic_score(t['track_id']),
            'derivation_count': t['derivation_count']
        } for t in to_preserve[:10]]  # 只保留前10個樣本
    }
    
    final_capacity = vault.get_vault_capacity()
    print(f"\n✅ 加權FIFO清理完成: 刪除 {len(deleted_tracks)} 首，釋放 {space_freed_mb:.1f}MB")
    print(f"   冷庫剩餘: {final_capacity} 首")
    
    return (deleted_tracks, to_preserve, audit_data)


def generate_purge_audit_report(audit_data: dict) -> str:
    """
    生成清理審計報告文件
    
    Args:
        audit_data: 清理審計數據
        
    Returns:
        報告檔案路徑
    """
    if not audit_data:
        return ""
    
    timestamp = audit_data['timestamp']
    report_path = Path(WORKSPACE_ROOT) / "assets" / "final_exports" / f"purge_report_{timestamp}.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    report_lines = [
        "=" * 70,
        "【冷庫清理審計報告】",
        "=" * 70,
        f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"清理批次: {timestamp}",
        "",
        "📊 清理統計",
        f"  • 已刪除軌道: {audit_data['total_deleted']} 首",
        f"  • 已保留軌道: {audit_data['total_preserved']} 首",
        f"  • 釋放空間: {audit_data['space_freed_mb']} MB",
        "",
        "🗑️ 被刪除軌道清單（按基因強度排序）",
        "-" * 70,
    ]
    
    # 按基因強度排序被刪除軌道
    deleted_sorted = sorted(
        audit_data['deleted_tracks'],
        key=lambda x: x['genetic_score'],
        reverse=True
    )
    
    for i, track in enumerate(deleted_sorted, 1):
        report_lines.append(
            f"{i:3d}. {track['track_id']:30s} | "
            f"基因強度: {track['genetic_score']:6.1f}% | "
            f"大小: {track['size_mb']:7.1f}MB | "
            f"封存於: {track['archived_at']}"
        )
    
    report_lines.extend([
        "",
        "🏆 豁免保留軌道清單（前10樣本，按基因強度排序）",
        "-" * 70,
    ])
    
    # 按基因強度排序保留軌道
    preserved_sorted = sorted(
        audit_data['preserved_tracks'],
        key=lambda x: x['genetic_score'],
        reverse=True
    )
    
    for i, track in enumerate(preserved_sorted, 1):
        report_lines.append(
            f"{i:3d}. {track['track_id']:30s} | "
            f"基因強度: {track['genetic_score']:6.1f}% | "
            f"衍生次數: {track['derivation_count']}"
        )
    
    report_lines.extend([
        "",
        "=" * 70,
        "【報告完成】",
        "=" * 70,
    ])
    
    # 寫入檔案
    report_text = "\n".join(report_lines)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    print(f"📄 審計報告已生成: {report_path}")
    return str(report_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="高使用次數音檔整理器")
    parser.add_argument(
        "--channel",
        choices=["all", "light_music", "lofi"],
        default="all",
        help="只整理指定頻道（預設 all）",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="實際執行遷移/刪除（未帶此參數時僅 dry-run）",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        default=0,
        help="本輪最多處理幾首（0 代表不限制）",
    )
    parser.add_argument(
        "--log-path",
        type=str,
        default="",
        help="指定固定日誌檔路徑（每輪 append）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("【冷儲存管理系統】")
    print("=" * 60)
    
    # Step 1：執行選擇性封存
    _log_path = Path(args.log_path) if str(args.log_path).strip() else None
    archived = archive_with_selective_filter(
        target_channel=args.channel,
        execute=args.execute,
        max_actions=max(0, int(args.max_actions)),
        log_path=_log_path,
    )
    
    # Step 2：檢查容量並決定是否通知 CEO
    current, should_notify = check_vault_capacity_and_notify()
    
    if should_notify:
        print("\n🚨 需要通知 CEO 進行 FIFO 清理授權")
        print("   (在 Telegram 中會發送 [批准/忽略] 按鈕)")
    
    # 若有命令行參數 --trigger-fifo，直接執行 FIFO 清理
    if "--trigger-fifo" in sys.argv:
        print("\n⚡ 執行 FIFO 清理...")
        trigger_fifo_cleanup()
    
    sys.exit(0)

    