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



# 彈藥庫路徑（遠端 — v15.10: 改由 config 派發）
POOL_PATH = config.smb_queue_staging / "shorts_meta_pool.json"
# 本機副本路徑
LOCAL_POOL_PATH = Path(__file__).resolve().parents[2] / "logs" / "shorts_meta_pool.local.json"
# Log 檔案路徑
LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "shorts_pool.log"
SHORTS_PUBLISH_CFG = _PROJECT_ROOT / "configs" / "shorts_publish_windows.json"


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

sys.stdout = DualLogger(LOG_PATH)

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

def _load_publish_windows_config() -> dict | None:
    """顧問檔期策略（台灣三檔）；不存在則略過。"""
    if not SHORTS_PUBLISH_CFG.is_file():
        return None
    try:
        return json.loads(SHORTS_PUBLISH_CFG.read_text(encoding="utf-8"))
    except Exception:
        return None


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


def _validate_shorts_meta(meta: dict) -> bool:
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
    # 正則邏輯：開頭是一串英文字母/數字/空格/基本標點，接著是 |，然後接著中文字符
    title_pattern = r"^[A-Za-z0-9\s\.\?!,'’-]+\s*\|\s*[\u4e00-\u9fa5]"
    if not re.search(title_pattern, meta["title"]):
        print(f"  ❌ 標題格式錯誤 (必須純英文在前 | 中文在後): {meta['title']}")
        return False

    # 5. 確保標題結尾包含指定的 Hashtags (可選，加強防護)
    if "🌿 #Shorts #NewAgeMusic" not in meta["title"]:
        print(f"  ❌ 標題缺少指定的結尾綴詞")
        return False

    return True
    
def generate_shorts_pool(
    batch_size: int = 30,
    max_retries: int = 3,
    *,
    use_slot_strategy: bool = True,
):
    print(f"\n{'='*60}\n[Shorts 雙語標題彈藥庫生成] 啟動於 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}")
    print(f"🚀 開始透過 MiniMax 2.7 單發單組生成 {batch_size} 組 Shorts 雙語標題...")
    pw_cfg = _load_publish_windows_config() if use_slot_strategy else None
    if use_slot_strategy and pw_cfg:
        print(f"📅 已載入檔期策略: {SHORTS_PUBLISH_CFG.name}（三時段輪替注入提示）")
    elif use_slot_strategy:
        print(f"ℹ️  未找到 {SHORTS_PUBLISH_CFG.name}，略過檔期提示")
    system_prompt = (
        "你是 R&S Echoes 頻道的行銷專家，專精於 New Age, Celtic Ambient 與療癒輕音樂。\n"
        "你的任務是為 YouTube Shorts 撰寫高點擊率的英中雙語標題與描述。\n"
        "【強制規則 - 若違反將導致系統崩潰】：\n"
        "1. 必須輸出純 JSON 物件，絕對不允許任何 Markdown 標記（如 ```json）或說明文字。\n"
        "2. 標題 (title) 格式必須嚴格遵守：「[純英文短句] | [純中文短句] 🌿 #Shorts #NewAgeMusic」。英文在前，中文在後，中間用「 | 」隔開。\n"
        "3. 標題總長度不可超過 80 字元。\n"
        "4. 描述 (description) 必須包含中英文，並引導聽眾點擊 24/7 輕音樂直播。\n"
        "5. 標籤 (tags) 陣列長度【必須剛好是 15 個】，不可多也不可少。\n"
        "6. categoryId 固定 '10'，privacyStatus 固定 'public'，containsSyntheticMedia 固定 true。\n"
        "7. selfDeclaredMadeForKids 固定 false（非兒童導向／非兒童專屬）。\n"
    )
    prod_hints = ""
    if pw_cfg and isinstance(pw_cfg.get("production_reminders"), list):
        prod_hints = (
            "\n【製作與演算法提醒】（文案可含蓄呼應，不必逐字照抄）\n"
            + "\n".join(f"- {x}" for x in pw_cfg["production_reminders"] if str(x).strip())
            + "\n"
        )

    validated_metas = []
    for idx in range(1, batch_size + 1):
        print(f"\n【第 {idx}/{batch_size} 組】MiniMax 2.7 單發生成... (請稍候，進度即時顯示於 logs/shorts_pool.log)")
        local_attempt = 0
        success = False
        while local_attempt < max_retries and not success:
            local_attempt += 1
            user_prompt = (
                f"請生成 1 組符合上述強制規則的 Shorts Metadata。\n"
                f"中文鉤子請聚焦於：清空大腦、深層睡眠、釋放壓力、精靈森林等痛點。\n"
                f"{_slot_prompt_block(pw_cfg, idx)}"
                f"{prod_hints}"
                f"【正確輸出的 JSON 範例】（請模仿此結構，確保 tags 剛好 15 個）：\n"
                f"{{\n"
                f'  "title": "Step into the Elven Forest | 一秒置身精靈森林 🌿 #Shorts #NewAgeMusic",\n'
                f'  "description": "🎧 Let the ethereal sounds guide you. Click "Live" below, and enjoy 24/7 healing light music with you every moment!！ #NewAge #LightMusic",\n'
                f'  "tags": ["Shorts", "NewAgeMusic", "CelticAmbient", "Healing", "StressRelief", "AmbientMusic", "SleepMusic", "DeepFocus", "Relaxation", "RSEchoesNature", "Meditation", "HealingFrequency", "StudyMusic", "AIMusic", "MentalHealth"],\n'
                f'  "categoryId": "10",\n'
                f'  "privacyStatus": "public",\n'
                f'  "containsSyntheticMedia": true,\n'
                f'  "selfDeclaredMadeForKids": false\n'
                f"}}\n"
            )
            try:
                result = generate_structured_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    provider="minimax",
                    model="minimaxai/minimax-m2.7",
                    max_retries=1
                )
                if not isinstance(result, dict):
                    print(f"  ⚠️ LLM 回傳非 dict: {type(result).__name__}")
                    continue
                if not _validate_shorts_meta(result):
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

    # 合併寫入 POOL_PATH（遠端）與 LOCAL_POOL_PATH（本機）
    existing_pool = []
    if POOL_PATH.exists():
        try:
            existing_pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))
        except Exception:
            print(f"{YELLOW}⚠️  讀取遠端彈藥庫失敗，將覆蓋寫入{RESET}")
    existing_pool.extend(validated_metas)
    # 寫入遠端
    POOL_PATH.write_text(json.dumps(existing_pool, ensure_ascii=False, indent=2), encoding="utf-8")
    # 寫入本機副本
    LOCAL_POOL_PATH.write_text(json.dumps(existing_pool, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{GREEN}✅ 成功將 {len(validated_metas)} 組新 Shorts 標題注入彈藥庫" \
          f"\n  遠端路徑：{POOL_PATH.resolve()}" \
          f"\n  本機副本：{LOCAL_POOL_PATH.resolve()}" \
          f"\n  (庫存總量: {len(existing_pool)}){RESET}")
    print(f"[Shorts 雙語標題彈藥庫生成] 完成於 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Shorts 雙語標題彈藥庫生成（單發單組 robust 版）")
    parser.add_argument("batch_size", type=int, nargs="?", default=30, help="生成組數（預設 30）")
    parser.add_argument("--max-retries", type=int, default=3, help="每組最大重試次數（預設 3）")
    parser.add_argument(
        "--no-slot-strategy",
        action="store_true",
        help="不讀取 configs/shorts_publish_windows.json，不注入三檔時段提示",
    )
    args = parser.parse_args()
    generate_shorts_pool(
        batch_size=args.batch_size,
        max_retries=args.max_retries,
        use_slot_strategy=not args.no_slot_strategy,
    )
