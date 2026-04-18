#!/usr/bin/env python3
"""檢查 lofi_assembler.py 中 help= 字串是否含 % 字符"""
import re
src = open('scripts/gear1_prod/lofi_assembler.py', encoding='utf-8').read()
found = False
for m in re.finditer(r'help=(["\'])(.+?)\1', src, re.DOTALL):
    h = m.group(2)
    if '%' in h:
        print(f"FOUND % in help: {repr(h[:80])}")
        found = True
if not found:
    print("No % found in help strings - checking f-strings")
    # check for f-strings with help
    for m in re.finditer(r'help=f(["\'])(.+?)\1', src, re.DOTALL):
        h = m.group(2)
        print(f"f-string help: {repr(h[:80])}")
print("done")
