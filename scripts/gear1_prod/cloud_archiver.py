#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【Protocol L-Archive】冷儲存與容量管理系統
- 原生歌曲 (is_derivative=False) → 冷儲存封存
- 衍生歌曲 (is_derivative=True) → 物理直接刪除
- 90% 閘門 → CEO 授權 FIFO 清理
"""

import os, sys, shutil, json
from datetime import datetime
from pathlib import Path

# 【跨平台防線】以腳本位置動態推導專案根目錄，禁止硬編碼磁碟機代號
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", str(_PROJECT_ROOT))
MAX_VAULT_CAPACITY = 100
VAULT_WARNING_THRESHOLD = 0.9  # 90%

# 動態導入 VaultDatabase
sys.path.insert(0, os.path.join(WORKSPACE_ROOT, "scripts", "gear2_rnd"))
from vault_database import VaultDatabase


def archive_with_selective_filter():
    """
    選擇性封存邏輯：
    - 原生歌曲 → ceo_archived_beats/ 並保留 DB 記錄
    - 衍生歌曲 → 物理刪除 + DB 標記已清理
    """
    vault = VaultDatabase()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 建立封存目錄
    archive_dir = Path(WORKSPACE_ROOT) / "ceo_archived_beats"
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🔍 掃描退役軌道 (derivation_count >= 3)...")
    
    cursor = vault.conn.cursor()
    
    # 查詢所有退役軌道
    cursor.execute("""
        SELECT * FROM audio_assets 
        WHERE derivation_count >= 3 AND status = 'active'
        ORDER BY derivation_count DESC
    """)
    retired_tracks = cursor.fetchall()
    
    original_count = 0
    derivative_count = 0
    
    for track_row in retired_tracks:
        track = dict(track_row)
        track_id = track["track_id"]
        original_path = track["original_path"]
        is_derivative = track["is_derivative"]
        
        if not Path(original_path).exists():
            print(f"⚠️ 檔案已遺失: {original_path}")
            vault.purge_track(track_id)
            continue
            
        if is_derivative:
            # ====== 衍生歌曲：直接物理刪除 ======
            try:
                os.remove(original_path)
                vault.purge_track(track_id)
                print(f"🗑️ 【衍生刪除】 {track_id}")
                derivative_count += 1
            except Exception as e:
                print(f"❌ 刪除失敗: {original_path} - {e}")
                
        else:
            # ====== 原生歌曲：封存到 ceo_archived_beats/ ======
            try:
                # 複製到封存目錄
                filename = Path(original_path).name
                archive_path = archive_dir / f"{track_id}_{filename}"
                shutil.copy2(original_path, archive_path)
                
                # 標記為已封存
                vault.archive_track(track_id)
                print(f"📦 【原生封存】 {track_id} → {archive_path.name}")
                original_count += 1
            except Exception as e:
                print(f"❌ 封存失敗: {original_path} - {e}")
    
    print(f"\n✅ 退役完成: {original_count} 個原生歌曲已封存, {derivative_count} 個衍生歌曲已刪除")
    
    return original_count + derivative_count


def check_vault_capacity_and_notify():
    """
    檢查冷庫容量，若達到 90%，向 CEO 發送 Telegram 通知
    
    Returns:
        (current_capacity, should_trigger_cleanup_button)
    """
    vault = VaultDatabase()
    current = vault.get_vault_capacity()
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
    archive_path = Path(WORKSPACE_ROOT) / "ceo_archived_beats"
    
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
        vault.purge_track(track_id)
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
    print("=" * 60)
    print("【冷儲存管理系統】")
    print("=" * 60)
    
    # Step 1：執行選擇性封存
    archived = archive_with_selective_filter()
    
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

    