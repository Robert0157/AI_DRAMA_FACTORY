#!/usr/bin/env python3
"""UI 接管清單 v15.3 全量驗證（含 P2-1 ~ P2-4）"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    from scripts.ui.backend import get_ui_backend

    b = get_ui_backend()
    b.set_channel("lofi")

    # ── P2-1: metadata_distrokid_{channel}.json 檔名契約 ──
    import inspect
    import scripts.gear1_prod.music_metadata_engine as mme
    src = inspect.getsource(mme)
    assert "metadata_distrokid_{args.channel}" in src, "P2-1 FAIL: filename not updated"
    assert "DistroKid_CheatSheet_{args.channel}" in src, "P2-1 FAIL: cheatsheet not updated"
    print("[OK] P2-1  metadata_distrokid_{channel} + CheatSheet_{channel} 契約已對齊")

    # ── P2-2: Popen 日誌 ──
    assert hasattr(b, "run_pipeline_with_log"), "P2-2 FAIL: run_pipeline_with_log missing"
    assert hasattr(b, "get_latest_log_lines"),  "P2-2 FAIL: get_latest_log_lines missing"
    assert hasattr(b, "_run_with_log"),          "P2-2 FAIL: _run_with_log missing"
    rc, log_path = b._run_with_log("e2e_test_echo", [sys.executable, "-c", 'print("hello_log")'])
    assert rc == 0, f"P2-2 FAIL: _run_with_log rc={rc}"
    tail = b.get_latest_log_lines(log_path, 5)
    assert "hello_log" in tail, f"P2-2 FAIL: log content missing: {tail!r}"
    print(f"[OK] P2-2  _run_with_log + get_latest_log_lines  log={log_path!r}")

    # ── Tab3: run_mastering_only exists ──
    assert hasattr(b, "run_mastering_only"), "Tab3 FAIL: run_mastering_only missing"
    print("[OK] Tab3  run_mastering_only 方法存在")

    # ── P2-4: get_final_exports ──
    fe = b.get_final_exports()
    for key in ("wav", "mp4", "tracklist", "yt_cheatsheet", "dk_cheatsheet", "metadata", "dir"):
        assert key in fe, f"P2-4 FAIL: key {key!r} missing from get_final_exports()"
    print(
        f"[OK] P2-4  get_final_exports  WAV={len(fe['wav'])}  MP4={len(fe['mp4'])}"
        f"  Tracklist={len(fe['tracklist'])}  YT_CS={len(fe['yt_cheatsheet'])}"
        f"  DK_CS={len(fe['dk_cheatsheet'])}  meta={len(fe['metadata'])}"
    )

    # ── generate_youtube_cheatsheet (standalone, Phase 4.5 port) ──
    assert hasattr(b, "generate_youtube_cheatsheet"), "Phase 4.5 FAIL: method missing"
    yt_ok, yt_msg = b.generate_youtube_cheatsheet("lofi")
    assert yt_ok, f"Phase 4.5 FAIL: {yt_msg}"
    from pathlib import Path
    export_dir = b.get_channel_export_dir()
    yt_files = sorted(export_dir.glob("YouTube_CheatSheet_*.txt"))
    assert yt_files, "Phase 4.5 FAIL: YouTube_CheatSheet_*.txt not found in export dir"
    yt_content = yt_files[-1].read_text(encoding="utf-8")
    assert "TRACKLIST" in yt_content.upper(), "Phase 4.5 FAIL: TRACKLIST section missing in YT CheatSheet"
    assert "YouTube" in yt_content, "Phase 4.5 FAIL: YouTube section missing"
    print(f"[OK] Phase4.5  generate_youtube_cheatsheet → {yt_files[-1].name}")

    # ── 聽覺最大重複次數：lofi_assembler --max-derivation-limit 參數存在 ──
    import subprocess
    import sys as _sys
    assembler = Path(__file__).resolve().parents[2] / "scripts" / "gear1_prod" / "lofi_assembler.py"
    help_out = subprocess.run(
        [_sys.executable, str(assembler), "--help"],
        capture_output=True, text=True
    )
    assert "--max-derivation-limit" in help_out.stdout, \
        f"lofi_assembler FAIL: --max-derivation-limit not in --help\n{help_out.stdout}"
    assert "預設 3" in help_out.stdout or "default 3" in help_out.stdout.lower(), \
        "lofi_assembler FAIL: --help 應標示聽覺上限預設 3（Gen0/1/2）"
    print("[OK] lofi_assembler  --max-derivation-limit 參數已存在且說明含預設 3")

    # ── run_phase4_sequence 簽名包含 max_audio_deriv，預設值 3（與 lofi_assembler 一致）──
    import inspect
    sig = inspect.signature(b.run_phase4_sequence)
    assert "max_audio_deriv" in sig.parameters, "backend FAIL: max_audio_deriv param missing"
    _default = sig.parameters["max_audio_deriv"].default
    assert _default == 3, f"backend FAIL: run_phase4_sequence max_audio_deriv 預設應為 3，現為 {_default!r}"
    print(f"[OK] backend  run_phase4_sequence(max_audio_deriv=3) 預設值正確")

    # ── LUFS 推斷 helper ──
    assert b.infer_channel_from_audio_filename("track_-16.0LUFS.wav") == "lofi"
    assert b.infer_channel_from_audio_filename("track_-18.0LUFS.wav") == "light_music"
    assert b.infer_channel_from_audio_filename("track_no_lufs.wav") is None
    print("[OK] LUFS  infer_channel_from_audio_filename 全 3 case 通過")

    # ── 基礎 smoke (不執行破壞性操作) ──
    ok, msg = b.reconcile_misplaced_audio_by_lufs(dry_run=True)
    assert ok, f"reconcile dry_run FAIL: {msg}"
    print(f"[OK] LUFS  reconcile dry_run: {msg[:80].replace(chr(10), ' ')}")

    snap = b.get_protocol_l_snapshot()
    assert "audio" in snap and "by_channel" in snap
    print(f"[OK] ProtocolL  snapshot keys: {list(snap.keys())}")

    aud = b.get_asset_audit_for_channel("lofi")
    assert aud["channel"] == "lofi"
    print(f"[OK] Audit  lofi ready_count={aud['ready_count']}")

    inv = b.get_dual_channel_inventory()
    assert "lofi" in inv and "light_music" in inv
    print(f"[OK] Inventory  lofi vault={inv['lofi']['vault_wav']}  lm vault={inv['light_music']['vault_wav']}")

    # ── 背景任務 ──
    import time
    ok, msg = b.start_background("e2e_bg", lambda: (True, "bg_done"))
    assert ok
    for _ in range(30):
        time.sleep(0.05)
        r = b.poll_background()
        if r is not None:
            assert r["ok"] and r["msg"] == "bg_done"
            print(f"[OK] BgJob  {r}")
            break
    else:
        print("[FAIL] BgJob timeout"); return 1

    print()
    print("=== UI 接管清單 v15.3 全量驗證通過 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
