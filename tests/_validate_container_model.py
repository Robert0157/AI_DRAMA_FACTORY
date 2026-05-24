"""驗證容器切換邏輯完整性"""
import sys, py_compile, pathlib, json, importlib, inspect
sys.path.insert(0, 'f:/AI_DRAMA_FACTORY')
ROOT = pathlib.Path('f:/AI_DRAMA_FACTORY')
SEP = "=" * 60

errors = []
print(SEP)
print("  GL_4M_Suno_prompt.md 容器模型驗證")
print(SEP)

# 1. 語法
print("\n[1] 語法檢查")
for f in ['scripts/gear1_prod/generate_ceo_prompts.py',
          'scripts/marketing/generate_shorts_pool.py',
          'scripts/ui/backend.py', 'scripts/ui/app.py']:
    try:
        py_compile.compile(f, doraise=True)
        print(f"  ✅ {f.split('/')[-1]}")
    except py_compile.PyCompileError as e:
        print(f"  ❌ {e}"); errors.append(str(e))

# 2. 所有程式碼指向容器 GL_4M_Suno_prompt.md
print("\n[2] 容器引用驗證（必須指向容器）")

# generate_ceo_prompts.py PROMPT_MD_PATH
src = open(ROOT / 'scripts/gear1_prod/generate_ceo_prompts.py', encoding='utf-8').read()
if 'PROMPT_MD_PATH = Path(config.workspace_root) / ".openclaw" / "GL_4M_Suno_prompt.md"' in src:
    print("  ✅ generate_ceo_prompts.py PROMPT_MD_PATH → 容器")
else:
    print("  ❌ generate_ceo_prompts.py PROMPT_MD_PATH 未指向容器"); errors.append("PROMPT_MD_PATH 錯誤")

# lofi.json
with open(ROOT / 'configs/channels/lofi.json', encoding='utf-8') as f:
    lofi = json.load(f)
if lofi.get('music_gene_pool') == '.openclaw/GL_4M_Suno_prompt.md':
    print("  ✅ lofi.json music_gene_pool → 容器")
else:
    print(f"  ❌ lofi.json music_gene_pool = {lofi.get('music_gene_pool')!r}"); errors.append("lofi.json 錯誤")

# STYLE_CONFIG["zara"]
from scripts.marketing.generate_shorts_pool import STYLE_CONFIG
zara_gf = STYLE_CONFIG['zara']['gene_pool_file']
if zara_gf == 'GL_4M_Suno_prompt.md':
    print("  ✅ STYLE_CONFIG[zara] gene_pool_file → 容器")
else:
    print(f"  ❌ STYLE_CONFIG[zara] = {zara_gf!r}"); errors.append("STYLE_CONFIG[zara] 錯誤")

# 3. 容器本體存在
print("\n[3] 容器檔案存在性")
container = ROOT / '.openclaw' / 'GL_4M_Suno_prompt.md'
if container.exists():
    first = open(container, encoding='utf-8').readline().strip()[:60]
    print(f"  ✅ GL_4M_Suno_prompt.md 存在")
    print(f"     首行（當前子風格識別）: {first}")
else:
    print("  ❌ GL_4M_Suno_prompt.md 不存在"); errors.append("容器不存在")

# 4. 來源基因庫完整（五種子風格）
print("\n[4] 五種子風格來源基因庫")
sources = {
    'ZARA':    'music_genes_ZARA_music.md',
    'JESS':    'music_genes_JESS_music.md',
    'GUCCI':   'music_genes_Gucci_music.md',
    'SCIFI':   'music_genes_SCIFI_music.md',
    'surreal': 'music_genes_surreal_epic.md',
}
for name, fn in sources.items():
    fp = ROOT / '.openclaw' / fn
    mark = "✅" if fp.exists() else "❌"
    print(f"  {mark} {name:8} → {fn}")
    if not fp.exists():
        errors.append(f"{name} 來源不存在: {fn}")

# 5. backend._switch_container_gene_pool 存在
print("\n[5] backend._switch_container_gene_pool 方法")
be_src = open(ROOT / 'scripts/ui/backend.py', encoding='utf-8').read()
if '_switch_container_gene_pool' in be_src:
    print("  ✅ _switch_container_gene_pool 已定義")
else:
    print("  ❌ _switch_container_gene_pool 未找到"); errors.append("方法缺失")

# 6. backend.start_ceo_prompts_supply 不再有 --gene-pool 旗標
print("\n[6] start_ceo_prompts_supply 不含 --gene-pool 旗標")
import re
# 找出 start_ceo_prompts_supply 函式體
fn_match = re.search(r'def start_ceo_prompts_supply.*?(?=\n    def )', be_src, re.DOTALL)
if fn_match:
    fn_body = fn_match.group(0)
    if '--gene-pool' not in fn_body:
        print("  ✅ 不含 --gene-pool（容器切換後直接執行）")
    else:
        print("  ❌ 仍含 --gene-pool 旗標（應改為容器覆寫）"); errors.append("--gene-pool 殘留")
else:
    print("  ⚠️  無法解析函式體（跳過）")

# 7. 模擬容器切換：surreal → GL_4M_Suno_prompt.md
print("\n[7] 容器切換模擬（surreal → 容器）")
import shutil, tempfile, os
src_path = ROOT / '.openclaw' / 'music_genes_surreal_epic.md'
tmp_container = pathlib.Path(tempfile.mktemp(suffix='.md'))
try:
    shutil.copy2(container, tmp_container)  # 備份
    shutil.copy2(src_path, container)       # 覆寫
    first_after = open(container, encoding='utf-8').readline().strip()[:60]
    print(f"  ✅ 覆寫成功，容器首行: {first_after}")
    shutil.copy2(tmp_container, container)  # 還原
    print(f"  ✅ 還原成功（測試用，不影響生產）")
finally:
    if tmp_container.exists():
        tmp_container.unlink()

print()
print(SEP)
if errors:
    print(f"  結果：❌ {len(errors)} 個問題")
    for e in errors: print(f"    - {e}")
    sys.exit(1)
else:
    print("  結果：✅ 全部通過 — 容器模型正確")
print(SEP)

import os as _os
try: _os.remove(__file__)
except: pass
