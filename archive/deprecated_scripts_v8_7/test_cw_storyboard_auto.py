#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""已移至 .deprecated，請改用 assets/scripts/test_cw_storyboard.py"""

import sys
from pathlib import Path

# 將 canonical 腳本加入搜尋路徑
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "assets" / "scripts"))

try:
    import test_cw_storyboard as storyboard
except ImportError as exc:
    print("❌ 無法載入 canonical 故事板腳本：", exc)
    sys.exit(1)


if __name__ == "__main__":
    print("⚠️  這個腳本已被淘汰並移入 .deprecated，會直接呼叫 assets/scripts/test_cw_storyboard.py")
    storyboard.main()