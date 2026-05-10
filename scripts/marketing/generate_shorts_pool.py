#!/usr/bin/env python3
# -*- coding: utf-8 -*-


# Robust 單發單組模式，與 generate_ceo_prompts.py 一致
import json
import sys
import logging
import datetime
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.common.llm_client import generate_structured_json



# 彈藥庫路徑（遠端 — v15.10: 改由 config 派發；v15.11: 頻道化後綴）
# POOL_PATH / LOCAL_POOL_PATH / LOG_PATH 由 generate_shorts_pool() 根據 --channel 動態設定
SHORTS_PUBLISH_CFG = _PROJECT_ROOT / "configs" / "shorts_publish_windows.json"
GENE_POOL_DIR = _PROJECT_ROOT / ".openclaw"

# ════════════════════════════════════════════════════════════════
# v15.11 風格配置字典 (Style Mapping)
# CEO 新增風格時只需在此加入新條目，其餘代碼零修改。
# gene_pool_file: 對應 .openclaw/ 下的基因庫檔案 (僅提取行銷語境)
# ════════════════════════════════════════════════════════════════
STYLE_CONFIG: dict[str, dict[str, str]] = {
    # ── light_music 四大子風格 ──
    "light_music_default": {
        "label": "Light Music (Nature / Celtic Ambient / Zen)",
        "hook": "清空大腦、深層睡眠、釋放壓力、精靈森林等痛點",
        "suffix": "🌿 #Shorts #NewAgeMusic",
        "example_title": "Step into the Elven Forest | 一秒置身精靈森林",
        "gene_pool_file": "music_genes_light_music.md",
    },
    "celtic": {
        "label": "Light Music — CelticFolk (居爾特奇幻民謠)",
        "hook": "清晨生機、森林靈動、微風感、精靈奇幻世界",
        "suffix": "🌿 #Shorts #CelticAmbient",
        "example_title": "Celtic Morning Glow | 塞爾特晨光微風",
        "gene_pool_file": "music_genes_light_music.md",
    },
    "piano": {
        "label": "Light Music — PianoImpression (印象派純鋼琴)",
        "hook": "午後陽光、讀書陪伴、純粹留白、水彩光影",
        "suffix": "🎹 #Shorts #SoloPiano",
        "example_title": "Afternoon Watercolor | 午後水彩光影",
        "gene_pool_file": "music_genes_light_music.md",
    },
    "neoclassical": {
        "label": "Light Music — NeoClassical (新古典史詩)",
        "hook": "黃昏曠野、深沉情感、電影級張力、時光流逝",
        "suffix": "🎻 #Shorts #NeoClassical",
        "example_title": "Frontier Echoes | 曠野史詩迴響",
        "gene_pool_file": "music_genes_light_music.md",
    },
    "zen": {
        "label": "Light Music — ZenAmbient (禪意環境聲景)",
        "hook": "深夜助眠、冥想、絕對平靜、靈魂出竅、零旋律起伏",
        "suffix": "🧘 #Shorts #ZenMeditation",
        "example_title": "Midnight Stillness | 午夜禪定虛空",
        "gene_pool_file": "music_genes_light_music.md",
    },
    # ── lofi 四大子風格 ──
    "zara": {
        "label": "Retail BGM (Minimal House / Tech House)",
        "hook": "提升工作效率、寫程式心流、保持專注、現代都會時尚感",
        "suffix": "☕ #Shorts #MinimalHouse",
        "example_title": "Urban Focus Flow | 都會極簡專注心流",
        "gene_pool_file": "GL_4M_Suno_prompt.md",
    },
    "gucci": {
        "label": "High-End Luxury (Avant-Garde / Neo-Classical)",
        "hook": "高級感、極致戲劇張力、前衛藝術、精品展場氛圍",
        "suffix": "✨ #Shorts #AvantGarde",
        "example_title": "Velvet Labyrinth | 奢華黑絲絨的迷宮",
        "gene_pool_file": "music_genes_Gucci_music.md",
    },
    "scifi": {
        "label": "Sci-Fi & Cyberpunk (Synthwave / Glitch IDM)",
        "hook": "駭客任務、寫程式專用、AI 運算、無重力深空探險",
        "suffix": "👾 #Shorts #Cyberpunk",
        "example_title": "Neural Network Boot | 神經網絡啟動",
        "gene_pool_file": "music_genes_SCIFI_music.md",
    },
    "jazz": {
        "label": "24/7 Jazz Lounge (Smooth Jazz / Cafe Bossa)",
        "hook": "深夜酒廊、午後咖啡廳、放鬆微醺、都會夜駕",
        "suffix": "🎷 #Shorts #JazzLounge",
        "example_title": "Midnight City Cruise | 午夜都會巡航",
        "gene_pool_file": "music_genes_JESS_music.md",
    },
}


# light_music 四大風格旋轉清單（A→B→C→D 依序輪替）
_LIGHT_MUSIC_STYLE_KEYS = ["celtic", "piano", "neoclassical", "zen"]


def _resolve_style(channel: str, sub_style: str | None) -> tuple[str, dict[str, str]]:
    """v15.11: 解析風格 key 與對應 STYLE_CONFIG 條目。
    回傳 (style_key, style_dict)。
    
    light_music: sub_style 可為 "celtic"/"piano"/"neoclassical"/"zen"/"auto"/None。
    "auto"/None → style_key="auto", 觸發循環內風格輪轉。
    lofi: sub_style 可為 "zara"/"gucci"/"scifi"/"jazz"。
    """
    if channel.lower() == "light_music":
        key = (sub_style or "auto").lower()
        if key in _LIGHT_MUSIC_STYLE_KEYS:
            return key, STYLE_CONFIG[key]
        if key == "auto":
            return "auto", STYLE_CONFIG["light_music_default"]
        return "default", STYLE_CONFIG["light_music_default"]
    # lofi
    key = (sub_style or "zara").lower()
    lofi_valid = [k for k in STYLE_CONFIG if k not in ("light_music_default",) and k not in _LIGHT_MUSIC_STYLE_KEYS]
    if key not in lofi_valid:
        _fatal_exit("INVALID_STYLE", f"未知子風格: {key}。有效值: {', '.join(lofi_valid)}")
    return key, STYLE_CONFIG[key]


def _extract_style_context(style_dict: dict[str, str]) -> str:
    """v15.11: 從基因庫 .md 提取行銷語境 (Persona + 四大風格 + Universal Ban)。
    只提取「鐵律一」之前的內容，跳過音樂生成指令、JSON Schema、QA 清單。
    提取失敗不中斷，回傳空字串。"""
    gene_file = style_dict.get("gene_pool_file", "")
    if not gene_file:
        return ""
    file_path = GENE_POOL_DIR / gene_file
    if not file_path.is_file():
        print(f"  {YELLOW}⚠️  基因庫不存在: {file_path}，略過語境注入{RESET}")
        return ""
    try:
        full_text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  {YELLOW}⚠️  基因庫讀取失敗: {e}，略過語境注入{RESET}")
        return ""

    # 截取「鐵律一」之前的內容 (行銷語境 = Persona + 四大風格屬性 + Universal Ban)
    cutoff = full_text.find("【鐵律一")
    context = full_text[:cutoff].strip() if cutoff > 0 else ""
    if not context:
        # 無「鐵律一」標記，取前 60 行作為安全備援
        lines = full_text.splitlines()
        context = "\n".join(lines[:60])
    return context


RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# 設定 logging（即時落盤，stdout 也同步顯示）
class DualLogger:
    def __init__(self, logfile):
        self.terminal = sys.stdout
        self.log = open(logfile, "a", encoding="utf-8")
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
    def flush(self):
        self.terminal.flush()
        self.log.flush()

# 注意：sys.stdout 重導向在 generate_shorts_pool() 內依 channel 動態執行
# 此處不再於模組頂層固定寫死 LOG_PATH

def _fatal_exit(error_code: str, details: str) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_line = str(details).strip().splitlines()[-1][:240]
    warning_msg = (
        f"\n{RED}{'='*80}{RESET}\n"
        f"{RED}🚨 [FATAL] {error_code}{RESET}\n"
        f"{RED}{last_line}{RESET}\n"
        f"{RED}{'='*80}{RESET}\n"
    )
    print(warning_msg)
    sys.exit(1)

import re

def _load_publish_windows_config(channel: str = "lofi") -> dict | None:
    """v15.11 頻道感知檔期策略：channel 級 slots 覆寫 > 全域 slots。
    light_music → 14:00 + 22:00（CEO 指定雙檔）。
    """
    if not SHORTS_PUBLISH_CFG.is_file():
        return None
    try:
        cfg: dict = json.loads(SHORTS_PUBLISH_CFG.read_text(encoding="utf-8"))
    except Exception:
        return None
    # 頻道級覆寫
    ch_cfg = (cfg.get("channels") or {}).get(channel.lower())
    if isinstance(ch_cfg, dict) and "slots" in ch_cfg:
        return {
            "slots": ch_cfg["slots"],
            "timezone_label": cfg.get("timezone_label", ""),
            "production_reminders": cfg.get("production_reminders", []),
        }
    return cfg


def _slot_prompt_block(pw: dict | None, index_one_based: int) -> str:
    """輪替三檔，讓標題／描述潛在對齊 08:00／14:00／20:00 情境。"""
    if not pw:
        return ""
    slots = pw.get("slots") or []
    if not slots:
        return ""
    s = slots[(index_one_based - 1) % len(slots)]
    if not isinstance(s, dict):
        return ""
    lt = s.get("local_time", "")
    lab = s.get("label", "")
    mood = s.get("mood", "")
    hint = s.get("content_hint", "")
    ov = (s.get("overseas_note") or "").strip()
    extra = f"\n跨時區備註：{ov}" if ov else ""
    return (
        f"\n【建議投放時段（台灣）】約 {lt} — {lab}。\n"
        f"受眾心理：{mood}。文案請含蓄呼應情境（非強制寫時間）：{hint}。{extra}\n"
    )


def _validate_shorts_meta(meta: dict, expected_suffix: str = "🌿 #Shorts #NewAgeMusic") -> bool:
    """v15.11: expected_suffix 由 STYLE_CONFIG 動態注入，不再硬編碼。"""
    # 1. 基本欄位檢查
    required_fields = [
        "title",
        "description",
        "tags",
        "categoryId",
        "privacyStatus",
        "containsSyntheticMedia",
        "selfDeclaredMadeForKids",
    ]
    for f in required_fields:
        if f not in meta:
            print(f"  ❌ 欄位缺失: {f}")
            return False
        if f in ("containsSyntheticMedia", "selfDeclaredMadeForKids"):
            continue
        if not meta[f]:
            print(f"  ❌ 欄位為空: {f}")
            return False
    if meta.get("containsSyntheticMedia") is not True:
        print("  ❌ containsSyntheticMedia 必須為 true（合成／變造內容申報為是）")
        return False
    if meta.get("selfDeclaredMadeForKids") is not False:
        print("  ❌ selfDeclaredMadeForKids 必須為 false（非兒童導向）")
        return False
            
    # 2. 標題長度檢查
    if len(meta["title"]) > 80:
        print(f"  ❌ 標題超過 80 字元 (目前 {len(meta['title'])} 字元)")
        return False

    # 3. 嚴格驗證 tags 數量 (必須剛好 15 個)
    if not isinstance(meta["tags"], list) or len(meta["tags"]) != 15:
        print(f"  ❌ Tags 數量錯誤: 目前 {len(meta.get('tags', []))} 個，嚴格要求 15 個")
        return False

    # 4. 嚴格驗證標題格式：英文在前 | 中文在後
    title_pattern = r"^[A-Za-z0-9\s\.\?!,'’-]+\s*\|\s*[\u4e00-\u9fa5]"
    if not re.search(title_pattern, meta["title"]):
        print(f"  ❌ 標題格式錯誤 (必須純英文在前 | 中文在後): {meta['title']}")
        return False

    # 5. v15.11 動態驗證：標題結尾必須包含當前風格專屬 Hashtag
    if expected_suffix not in meta["title"]:
        print(f"  ❌ 標題缺少風格專屬結尾綴詞: 必須包含 {expected_suffix}")
        return False

    return True
    
def generate_shorts_pool(
    batch_size: int = 30,
    max_retries: int = 3,
    *,
    channel: str = "lofi",
    sub_style: str | None = None,
    use_slot_strategy: bool = True,
):
    """v15.11: 頻道隔離 + 風格動態注入 — POOL_PATH 為 shorts_meta_pool_{channel}_{style}.json"""
    ch_lower = channel.lower()
    style_key, current_style = _resolve_style(ch_lower, sub_style)
    pool_path = config.smb_queue_staging / f"shorts_meta_pool_{ch_lower}_{style_key}.json"
    local_pool_path = _PROJECT_ROOT / "logs" / f"shorts_meta_pool_{ch_lower}_{style_key}.local.json"
    log_path = _PROJECT_ROOT / "logs" / f"shorts_pool_{ch_lower}_{style_key}.log"

    # 重導 stdout 到 log 檔案
    sys.stdout = DualLogger(log_path)

    # 提取基因庫行銷語境
    style_context = _extract_style_context(current_style)

    print(f"\n{'='*60}\n[Shorts 雙語標題彈藥庫生成] 啟動於 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"頻道: {ch_lower.upper()}  |  風格: {style_key}  |  目標: {batch_size} 組  |  MiniMax 2.7 單發單組")
    print(f"遠端路徑: {pool_path.resolve()}")
    print(f"本機副本: {local_pool_path.resolve()}")
    if style_context:
        print(f"基因語境: {current_style.get('gene_pool_file', '')} ({len(style_context)} 字元)")
    print(f"{'='*60}")
    pw_cfg = _load_publish_windows_config(ch_lower) if use_slot_strategy else None
    if use_slot_strategy and pw_cfg:
        pw_slots = pw_cfg.get("slots", []) if isinstance(pw_cfg, dict) else []
        pw_times = ", ".join(s.get("local_time", "?") for s in pw_slots if isinstance(s, dict))
        print(f"📅 已載入檔期策略 ({ch_lower}): {SHORTS_PUBLISH_CFG.name}（{len(pw_slots)} 檔: {pw_times}）")
    elif use_slot_strategy:
        print(f"ℹ️  未找到 {SHORTS_PUBLISH_CFG.name}，略過檔期提示")
    # ── 舊版靜態 system_prompt 已廢除，改由循環內 item_system_prompt ──
    prod_hints = ""
    if pw_cfg and isinstance(pw_cfg.get("production_reminders"), list):
        prod_hints = (
            "\n【製作與演算法提醒】（文案可含蓄呼應，不必逐字照抄）\n"
            + "\n".join(f"- {x}" for x in pw_cfg["production_reminders"] if str(x).strip())
            + "\n"
        )

    # v15.11 light_music 風格自動輪轉：若未指定單一風格，每組依序切換 A→B→C→D
    _lm_rotate = (ch_lower == "light_music" and style_key == "auto")
    if _lm_rotate:
        print(f"🔄 風格自動輪轉模式: {' → '.join(_LIGHT_MUSIC_STYLE_KEYS)}")

    # 預先提取基因庫行銷語境（共用，不變）
    _gene_ctx = style_context

    validated_metas = []
    for idx in range(1, batch_size + 1):
        # 決定本組的風格
        if _lm_rotate:
            item_style_key = _LIGHT_MUSIC_STYLE_KEYS[(idx - 1) % 4]
            item_style = STYLE_CONFIG[item_style_key]
        else:
            item_style = current_style
            item_style_key = style_key

        # v15.11 每組獨立 system_prompt（風格專屬後綴）
        item_system_prompt = (
            f"你是 R&S Echoes {item_style['label']} 頻道的行銷專家。\n"
            "你的任務是為 YouTube Shorts 撰寫高點擊率的英中雙語標題與描述。\n"
            "【強制規則 - 若違反將導致系統崩潰】：\n"
            "1. 必須輸出純 JSON 物件，絕對不允許任何 Markdown 標記（如 ```json）或說明文字。\n"
            f"2. 標題 (title) 格式必須嚴格遵守：「[純英文短句] | [純中文短句] {item_style['suffix']}」。英文在前，中文在後，中間用「 | 」隔開。\n"
            "3. 標題總長度不可超過 80 字元。\n"
            "4. 描述 (description) 必須包含中英文，並引導聽眾點擊 24/7 輕音樂直播。\n"
            "5. 標籤 (tags) 陣列長度【必須剛好是 15 個】，不可多也不可少。\n"
            "6. categoryId 固定 '10'，privacyStatus 固定 'public'，containsSyntheticMedia 固定 true。\n"
            "7. selfDeclaredMadeForKids 固定 false（非兒童導向／非兒童專屬）。\n"
        )

        print(f"\n【第 {idx}/{batch_size} 組】MiniMax 2.7 單發生成 — 風格: {item_style_key}...")
        local_attempt = 0
        success = False
        while local_attempt < max_retries and not success:
            local_attempt += 1
            # v15.11 動態 user_prompt：基因語境 + 風格專屬鉤子 + 專屬範例標題
            # light_music 注入目標風格鎖定指令
            _style_lock = (
                f"【本次生成之強制風格：{item_style['label']}】\n"
                f"標題與內容必須完全契合此風格，絕不可使用其他自然風格的語彙。\n"
                f"符號必須配對風格（CelticFolk→🌿, Piano→🎹, NeoClassical→🎻, Zen→🧘）。\n\n"
            ) if ch_lower == "light_music" else ""

            user_prompt = (
                f"請生成 1 組符合上述強制規則的 Shorts Metadata。\n"
                f"{_style_lock}"
                f"中文鉤子請聚焦於：{item_style['hook']}。\n"
                + (f"參考以下風格核心美學：\n{_gene_ctx}\n\n" if _gene_ctx else "") +
                f"{_slot_prompt_block(pw_cfg, idx)}"
                f"{prod_hints}"
                f"【正確輸出的 JSON 範例】（請模仿此結構，確保 tags 剛好 15 個）：\n"
                f"{{\n"
                f'  "title": "{item_style["example_title"]} {item_style["suffix"]}",\n'
                f'  "description": "🎧 ... 引導聽眾點擊 24/7 輕音樂直播 ...",\n'
                f'  "tags": ["Shorts", "NewAgeMusic", "CelticAmbient", "Healing", "StressRelief", "AmbientMusic", "SleepMusic", "DeepFocus", "Relaxation", "RSEchoesNature", "Meditation", "HealingFrequency", "StudyMusic", "AIMusic", "MentalHealth"],\n'
                f'  "categoryId": "10",\n'
                f'  "privacyStatus": "public",\n'
                f'  "containsSyntheticMedia": true,\n'
                f'  "selfDeclaredMadeForKids": false\n'
                f"}}\n"
            )
            try:
                result = generate_structured_json(
                    system_prompt=item_system_prompt,
                    user_prompt=user_prompt,
                    provider="minimax",
                    model="minimaxai/minimax-m2.7",
                    max_retries=1
                )
                if not isinstance(result, dict):
                    print(f"  ⚠️ LLM 回傳非 dict: {type(result).__name__}")
                    continue
                if not _validate_shorts_meta(result, expected_suffix=item_style["suffix"]):
                    print(f"  ❌ 欄位驗證失敗，重試 {local_attempt}/{max_retries}")
                    continue
                print(f"  {GREEN}✅ 驗証通過{RESET}，成功生成 [{idx}/{batch_size}]")
                validated_metas.append(result)
                success = True
            except Exception as e:
                print(f"  ⚠️ 單發呼叫異常: {e}")
        if not success:
            print(f"  ❌ 第 {idx} 組經過 {max_retries} 次重試後仍失敗，跳過此組。")

    if not validated_metas:
        _fatal_exit("NO_VALID_SHORTS_GENERATED", f"無法產生任何合格的 Shorts Metadata。\n累計嘗試：{batch_size} 組 × {max_retries} 次重試\n請檢查 API 狀態與網路連線。")

    # 合併寫入（遠端 + 本機）
    # light_music auto 模式：統整寫入 shorts_meta_pool_light_music_default.json
    _actual_pool = pool_path
    _actual_local = local_pool_path
    if _lm_rotate:
        _actual_pool = config.smb_queue_staging / f"shorts_meta_pool_{ch_lower}_default.json"
        _actual_local = _PROJECT_ROOT / "logs" / f"shorts_meta_pool_{ch_lower}_default.local.json"

    existing_pool = []
    if _actual_pool.exists():
        try:
            existing_pool = json.loads(_actual_pool.read_text(encoding="utf-8"))
        except Exception:
            print(f"{YELLOW}⚠️  讀取遠端彈藥庫失敗，將覆蓋寫入{RESET}")
    existing_pool.extend(validated_metas)
    # 寫入遠端
    _actual_pool.write_text(json.dumps(existing_pool, ensure_ascii=False, indent=2), encoding="utf-8")
    # 寫入本機副本
    _actual_local.write_text(json.dumps(existing_pool, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{GREEN}✅ 成功將 {len(validated_metas)} 組新 Shorts 標題注入彈藥庫" \
          f"\n  遠端路徑：{_actual_pool.resolve()}" \
          f"\n  本機副本：{_actual_local.resolve()}" \
          f"\n  (庫存總量: {len(existing_pool)}){RESET}")
    print(f"[Shorts 雙語標題彈藥庫生成] 完成於 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}\n")

if __name__ == "__main__":
    import argparse
    lofi_styles = ["zara", "gucci", "scifi", "jazz"]
    lm_styles = ["auto"] + _LIGHT_MUSIC_STYLE_KEYS
    all_styles = lofi_styles + lm_styles
    parser = argparse.ArgumentParser(description="Shorts 雙語標題彈藥庫生成（v15.11 頻道+風格隔離）")
    parser.add_argument("batch_size", type=int, nargs="?", default=30, help="生成組數（預設 30）")
    parser.add_argument("--max-retries", type=int, default=3, help="每組最大重試次數（預設 3）")
    parser.add_argument("--channel", type=str, default="lofi", choices=["lofi", "light_music"],
                        help="主頻道分類")
    parser.add_argument("--sub-style", type=str, default=None, choices=all_styles,
                        help=f"子風格 (lofi: {', '.join(lofi_styles)} | light_music: {', '.join(lm_styles)})")
    parser.add_argument(
        "--no-slot-strategy",
        action="store_true",
        help="不讀取 configs/shorts_publish_windows.json，不注入三檔時段提示",
    )
    args = parser.parse_args()
    generate_shorts_pool(
        batch_size=args.batch_size,
        max_retries=args.max_retries,
        channel=args.channel,
        sub_style=args.sub_style,
        use_slot_strategy=not args.no_slot_strategy,
    )
