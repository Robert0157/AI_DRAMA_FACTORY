#!/usr/bin/env python3
"""驗證文件補生成方法"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ui.backend import get_ui_backend
b = get_ui_backend()
b.set_channel("lofi")

# ① generate_distrokid_docs 方法存在且簽名正確
import inspect
assert hasattr(b, "generate_distrokid_docs"), "generate_distrokid_docs missing"
assert hasattr(b, "generate_placeholder_tracklist"), "generate_placeholder_tracklist missing"
assert hasattr(b, "regenerate_all_missing_docs"), "regenerate_all_missing_docs missing"
print("[OK] 三個補生成方法均存在")

# ② generate_placeholder_tracklist（vault 有 WAV 才能成功）
tl_ok, tl_msg = b.generate_placeholder_tracklist("lofi")
print(f"[{'OK' if tl_ok else 'SKIP'}] generate_placeholder_tracklist: {tl_msg[:80]}")

# ③ generate_youtube_cheatsheet（已在 e2e_full_check 驗過，此處再確認）
yt_ok, yt_msg = b.generate_youtube_cheatsheet("lofi")
assert yt_ok, f"generate_youtube_cheatsheet FAIL: {yt_msg}"
print(f"[OK] generate_youtube_cheatsheet: {yt_msg[:80]}")

# ④ regenerate_all_missing_docs 回傳 (bool, str)
ok, msg = b.regenerate_all_missing_docs()
assert isinstance(ok, bool) and isinstance(msg, str)
print(f"[OK] regenerate_all_missing_docs: ok={ok}")
for line in msg.splitlines():
    print(f"      {line}")

print("\n=== 補生成方法驗證通過 ===")
