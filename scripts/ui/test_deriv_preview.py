#!/usr/bin/env python3
"""驗證 get_audio_deriv_preview / get_visual_deriv_preview 動態預覽方法"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ui.backend import get_ui_backend

b = get_ui_backend()

for ch in ("lofi", "light_music"):
    b.set_channel(ch)
    print(f"\n=== {ch} ===")
    for lim in (1, 2, 3, 5):
        ap = b.get_audio_deriv_preview(lim, ch)
        vp = b.get_visual_deriv_preview(lim, ch)
        a_in, a_out = ap["included"], ap["excluded"]
        v_in, v_out = vp["included"], vp["excluded"]
        a_dist = ap["distribution"]
        v_dist = vp["distribution"]
        print(f"  limit={lim}  audio  入池={a_in:3d} 退出={a_out:3d}  dist={a_dist}")
        print(f"  limit={lim}  visual 入池={v_in:3d} 退出={v_out:3d}  dist={v_dist}")

        # 一致性檢查
        assert ap["included"] + ap["excluded"] == ap["total"]
        assert vp["included"] + vp["excluded"] == vp["total"]
        # limit 上升時 included 不應減少
    print(f"  [OK] {ch} 兩方法回傳一致")

# 確認方法簽名
import inspect
for method in ("get_audio_deriv_preview", "get_visual_deriv_preview"):
    sig = inspect.signature(getattr(b, method))
    assert "max_deriv" in sig.parameters, f"{method}: max_deriv param missing"
    assert "channel" in sig.parameters, f"{method}: channel param missing"

print("\n=== deriv_preview e2e 全通過 ===")
