#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ISRC 回寫工具 — 將 DistroKid 核發的 ISRC 碼批次匯入 rs_music_vault.db
──────────────────────────────────────────────────────────────────────────
v15.12 新增：讀取營運人員回填 ISRC 後的 DistroKid CSV，比對 Audio File Name，
將 ISRC 寫入 audio_assets.isrc 欄位。

安全機制：
  - --dry-run：預覽即將更新的紀錄，不實際寫入。
  - 僅更新 ISRC 欄位，絕不修改其他欄位。
  - 找不到匹配記錄時印出警告，略過該行。

用法：
  # 預覽（安全）
  python scripts/maintenance/import_isrc_to_db.py --csv DistroKid_Upload_lofi_filled.csv --dry-run

  # 正式寫入
  python scripts/maintenance/import_isrc_to_db.py --csv DistroKid_Upload_lofi_filled.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import EnvConfig

config = EnvConfig()

# ── v15.12 衍生曲目關鍵字（雙重防禦）──
_DERIVATIVE_KEYWORDS = ["pitch_up", "pitch_down", "tempo_up", "tempo_down"]


def _resolve_track_id_from_filename(audio_filename: str) -> str:
    """從 Audio File Name 推導 track_id。

    DistroKid CSV 的 Audio File Name 欄位為 '01_Something.wav' 或 'track_id.wav'。
    此處移除副檔名即為 track_id（與 vault_ready_for_mix 內檔名一致）。
    """
    stem = Path(audio_filename).stem
    # 若檔名包含曲序前綴（如 '01_Lofi_...'），嘗試剝離
    parts = stem.split("_", 1)
    if parts[0].isdigit() and len(parts) > 1:
        return parts[1]
    return stem


def import_isrc_from_csv(
    csv_path: Path,
    *,
    channel: str = "",
    dry_run: bool = False,
) -> Tuple[int, int, List[str]]:
    """從 CSV 匯入 ISRC 至 audio_assets.isrc。

    Args:
        csv_path: 已回填 ISRC 的 DistroKid CSV 路徑。
        channel: 頻道限制（"lofi" 或 "light_music"）；留空則不限制。
        dry_run: True 時僅預覽，不寫入 DB。

    Returns:
        (updated_count, skipped_count, warnings) —
        updated_count: 成功更新筆數（dry_run 時為「將更新」筆數）
        skipped_count: 略過的筆數（無 ISRC 或找不到匹配）
        warnings: 警告訊息清單
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 檔案不存在: {csv_path}")

    ch_filter = channel.lower().strip() if channel else ""
    if ch_filter and ch_filter not in ("lofi", "light_music"):
        raise ValueError(f"不支援的頻道: {channel}（僅接受 lofi / light_music）")

    from scripts.gear2_rnd.vault_database import VaultDatabase

    vault = VaultDatabase()
    warnings: List[str] = []
    updated = 0
    skipped = 0

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        # 驗證必要欄位
        if "Audio File Name" not in (reader.fieldnames or []):
            raise ValueError("CSV 缺少必要欄位：Audio File Name")
        if "ISRC (Leave Blank)" not in (reader.fieldnames or []):
            raise ValueError("CSV 缺少必要欄位：ISRC (Leave Blank)")

        for row_num, row in enumerate(reader, start=2):  # header 為第 1 行
            isrc = (row.get("ISRC (Leave Blank)") or "").strip()
            audio_filename = (row.get("Audio File Name") or "").strip()
            track_title = (row.get("Track Title") or "").strip()

            # 略過 ISRC 仍為空白的行
            if not isrc:
                skipped += 1
                continue

            if not audio_filename:
                warnings.append(f"第 {row_num} 行：Audio File Name 為空，略過")
                skipped += 1
                continue

            track_id = _resolve_track_id_from_filename(audio_filename)

            # 查詢 DB（若指定 channel 則加入過濾）
            cur = vault.conn.cursor()
            if ch_filter:
                cur.execute(
                    "SELECT track_id FROM audio_assets WHERE track_id = ? AND channel = ?",
                    (track_id, ch_filter),
                )
            else:
                cur.execute(
                    "SELECT track_id FROM audio_assets WHERE track_id = ?",
                    (track_id,),
                )
            match = cur.fetchone()
            if not match:
                # 嘗試模糊比對：original_path LIKE '%filename%'
                if ch_filter:
                    cur.execute(
                        "SELECT track_id FROM audio_assets WHERE original_path LIKE ? AND channel = ?",
                        (f"%{audio_filename}%", ch_filter),
                    )
                else:
                    cur.execute(
                        "SELECT track_id FROM audio_assets WHERE original_path LIKE ?",
                        (f"%{audio_filename}%",),
                    )
                match = cur.fetchone()
                if not match:
                    warnings.append(
                        f"第 {row_num} 行：找不到匹配 track_id（'{track_id}' / '{audio_filename}'），略過"
                    )
                    skipped += 1
                    continue
                # 以模糊比對結果為準
                track_id = match[0]

            # v15.12 雙重防禦：排除衍生曲目（pitch/tempo 變形不應有 ISRC）
            if any(kw in track_id.lower() for kw in _DERIVATIVE_KEYWORDS):
                warnings.append(
                    f"第 {row_num} 行：'{track_id}' 為衍生曲目（含 Remix 關鍵字），略過 ISRC 寫入"
                )
                skipped += 1
                continue

            if dry_run:
                print(
                    f"[DRY-RUN] 將更新 track_id={track_id} "
                    f"（{track_title}）→ ISRC={isrc}"
                )
                updated += 1
            else:
                cur.execute(
                    "UPDATE audio_assets SET isrc = ?, updated_at = CURRENT_TIMESTAMP WHERE track_id = ?",
                    (isrc, track_id),
                )
                vault.conn.commit()
                updated += 1
                print(f"✅ 已寫入 track_id={track_id}（{track_title}）→ ISRC={isrc}")

    vault.close()

    if dry_run:
        print(f"\n🔍 [DRY-RUN 完成] 共 {updated} 筆將更新，{skipped} 筆略過。未對資料庫進行任何寫入。")
    else:
        print(f"\n✅ [匯入完成] 共 {updated} 筆已寫入，{skipped} 筆略過。")

    return updated, skipped, warnings


# ── CLI 入口 ────────────────────────────────────────────────────
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="ISRC 回寫工具 — 將 DistroKid 核發的 ISRC 碼批次寫入 rs_music_vault.db"
    )
    parser.add_argument(
        "--csv", required=True, type=Path,
        help="已回填 ISRC 的 DistroKid CSV 路徑",
    )
    parser.add_argument(
        "--channel", choices=["lofi", "light_music"], default="",
        help="限制只更新指定頻道的 track（建議填寫，避免跨頻道誤寫）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="安全預覽模式：僅顯示即將更新的記錄，不實際寫入資料庫",
    )
    args = parser.parse_args()

    try:
        updated, skipped, warnings = import_isrc_from_csv(
            args.csv, channel=args.channel, dry_run=args.dry_run
        )
        for w in warnings:
            print(f"⚠️  {w}", file=sys.stderr)
        if not args.dry_run and updated == 0:
            print("⚠️  沒有寫入任何 ISRC。請確認 CSV 中 ISRC 欄位已回填且 Audio File Name 正確。")
    except Exception as e:
        print(f"❌ 匯入失敗：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
