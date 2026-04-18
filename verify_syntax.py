#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
語法驗證腳本 - 檢查 lofi_assembler.py v13.2
"""
import ast
import sys

file_path = r"scripts/gear1_prod/lofi_assembler.py"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # 嘗試解析
    ast.parse(code)
    print(f"✅ {file_path} 語法完全正確！")
    print(f"   - 代碼行數: {len(code.splitlines())}")
    print(f"   - 編碼: UTF-8")
    sys.exit(0)
    
except SyntaxError as e:
    print(f"❌ 語法錯誤在第 {e.lineno} 行: {e.msg}")
    print(f"   - 錯誤文本: {e.text}")
    sys.exit(1)
    
except Exception as e:
    print(f"❌ 驗證失敗: {e}")
    sys.exit(1)
