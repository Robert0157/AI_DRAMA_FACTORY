#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common/atomic_io.py
v7.10 MVP 底層護法：原子寫入 (Atomic Writes)
確保檔案寫入時若發生中斷，不會損毀原檔案。
防護目標：徹底根絕斷電、USB 瞬斷或程式崩潰導致的 JSON/文字檔變成 0KB (檔案損毀)。
實作細節：強制寫入 .tmp 暫存檔，寫入成功後才呼叫系統級層次的 os.replace 進行無縫覆蓋。
"""

import os
import json
from pathlib import Path
from typing import Union, Dict, List

def atomic_write_text(path: Union[str, Path], text: str, encoding: str = "utf-8") -> None:
    """原子化寫入純文字。"""
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    
    try:
        # 1. 寫入暫存檔
        tmp_path.write_text(text, encoding=encoding)
        # 2. 系統級覆蓋 (在 POSIX 上是原子操作，Windows 上是安全的替換)
        os.replace(tmp_path, target_path)
    except Exception as e:
        # 若寫入途中失敗，清理殘留的 tmp 檔，保護原檔不受影響
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise RuntimeError(f"Atomic write failed for {target_path.name}: {e}")

def atomic_write_json(path: Union[str, Path], data: Union[Dict, List], indent: int = 2) -> None:
    """原子化寫入 JSON 結構。"""
    # 確保資料可以被序列化，提早報錯，不要等到寫入 tmp 時才報錯
    try:
        json_str = json.dumps(data, ensure_ascii=False, indent=indent)
    except TypeError as e:
        raise ValueError(f"Data is not JSON serializable: {e}")
        
    atomic_write_text(path, json_str)