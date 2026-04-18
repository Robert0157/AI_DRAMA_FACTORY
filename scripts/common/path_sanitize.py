#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common/path_sanitize.py
v7.10 MVP 底層護法：路徑與檔名安全過濾 (Path Sanitization)
防禦 LLM 幻覺造成的非法字元與目錄穿越攻擊 (Directory Traversal)。
防護目標：防範大模型產生的幻覺標題帶有非法字元，導致 FFmpeg 崩潰或引發 Command Injection；防止目錄穿越 (../) 污染 Mac 系統
"""

import re
from pathlib import Path
from typing import Union

def sanitize_filename(name: str, max_length: int = 150) -> str:
    """
    過濾檔名中的危險字元，替換為底線。
    允許：英數字、中文字、底線、連字號、點號、空白。
    """
    if not name:
        return "unnamed"
        
    # 移除非法與控制字元
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name))
    # 移除頭尾空白與點號 (防止隱藏檔或系統誤判)
    safe_name = safe_name.strip(' .')
    
    if not safe_name:
        return "unnamed"
        
    return safe_name[:max_length]

def safe_join(base_dir: Union[str, Path], *parts: str) -> Path:
    """
    安全的拼接路徑，嚴格防範目錄穿越 (例如 '../')。
    若發現嘗試跳出 base_dir，將強制拋出 ValueError。
    """
    base = Path(base_dir).resolve()
    # 拼接後解析絕對路徑
    target = base.joinpath(*parts).resolve()
    
    # 檢查 target 是否以 base 開頭
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Directory traversal attack detected! Attempted to access: {target}"
        )
        
    return target