#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 後端端到端煙霧測試（無需啟動 Streamlit）。

預設 **不** 執行：頻道封存、聽覺金庫 DB 重置。
若需測試請加：--i-know-archive-moves-files / --with-db-reset-lofi
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--i-know-archive-moves-files",
        action="store_true",
        help="執行 archive_channel_workspace(lofi) 真實封存（會移動檔案！）",
    )
    parser.add_argument(
        "--with-db-reset-lofi",
        action="store_true",
        help="執行聽覺金庫重置（會 UPDATE rs_music_vault 當前頻道 derivation_count）",
    )
    args = parser.parse_args()

    from scripts.ui.backend import get_ui_backend

    b = get_ui_backend()
    b.set_channel("lofi")

    # LUFS 歸檔預覽（不搬檔、不混頻）
    ok, msg = b.reconcile_misplaced_audio_by_lufs(dry_run=True)
    assert ok
    print("[OK] reconcile_misplaced_audio_by_lufs (dry_run):", msg[:160].replace("\n", " "))

    if args.with_db_reset_lofi:
        ok, msg = b.reset_hearing_vault_derivations()
        assert isinstance(ok, bool) and isinstance(msg, str)
        print("[OK] reset_hearing_vault_derivations:", ok, msg[:120])
    else:
        print("[SKIP] reset_hearing_vault_derivations（加 --with-db-reset-lofi 才執行）")

    # Protocol L 快照
    snap = b.get_protocol_l_snapshot()
    assert "audio" in snap and "by_channel" in snap
    print("[OK] get_protocol_l_snapshot keys:", list(snap.keys()))

    # 審計
    aud = b.get_asset_audit_for_channel("lofi")
    assert aud["channel"] == "lofi"
    print("[OK] asset_audit ready_count:", aud["ready_count"])

    # 影片 / SFX 清單
    vids = b.list_background_videos()
    sfx = b.list_sfx_files()
    print("[OK] videos:", len(vids), "sfx:", len(sfx))

    # 背景任務
    def job():
        return True, "smoke_bg_ok"

    ok, msg = b.start_background("smoke", job)
    assert ok
    for _ in range(50):
        time.sleep(0.05)
        r = b.poll_background()
        if r is not None:
            assert r["ok"] and r["msg"] == "smoke_bg_ok"
            print("[OK] background job:", r)
            break
    else:
        print("[FAIL] background job timeout")
        return 1

    if args.i_know_archive_moves_files:
        ok, msg = b.archive_channel_workspace("lofi")
        assert ok
        print("[OK] archive_channel_workspace:", msg[:120])
    else:
        print("[SKIP] archive_channel_workspace（加 --i-know-archive-moves-files 才執行）")

    print("\n=== e2e_smoke 全部通過 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
