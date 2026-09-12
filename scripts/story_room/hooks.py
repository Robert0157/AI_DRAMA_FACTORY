"""Hook Bank: 30 opening-hook archetypes for story diversification.

A hook is the first-3-seconds visual device that creates suspense without
dialogue. Selection is deterministic (seeded) so experiments are reproducible.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Hook:
    id: str
    name: str
    desc: str


HOOKS: tuple[Hook, ...] = (
    Hook("H01", "異常物開場", "一個不該存在的物品先行出現，人物後到"),
    Hook("H02", "倒數計時", "畫面出現明確期限暗示（時鐘、水位、燃燒）"),
    Hook("H03", "缺席訊息", "該出現的人事物缺席，只留下痕跡"),
    Hook("H04", "規則宣告", "場景內文字/招牌揭示世界規則"),
    Hook("H05", "反常日常", "日常行為中出現百分之五的偏差"),
    Hook("H06", "監視視角", "以監視器、反射或倒影觀看事件"),
    Hook("H07", "逆向動作", "物理常識被輕輕違反一下"),
    Hook("H08", "重複標記", "同一符號或聲音出現第二次"),
    Hook("H09", "被跟隨感", "影子、腳印或視線暗示有人同行"),
    Hook("H10", "時間錯位", "時鐘、日曆或光影暗示時間不對"),
    Hook("H11", "假裝完成", "儀式看似完成後才發現缺件"),
    Hook("H12", "遺物指路", "亡者之物指向某個地方"),
    Hook("H13", "二選一壓迫", "畫面呈現兩扇門或兩條路"),
    Hook("H14", "溫柔警告", "善意的動作帶著警告意味"),
    Hook("H15", "象徵天候", "天候與情緒或事件同步變化"),
    Hook("H16", "生物反常", "動物行為揭示異常"),
    Hook("H17", "鏡像破綻", "倒影與本體不一致"),
    Hook("H18", "訊息延遲", "動作與結果之間隔了一拍"),
    Hook("H19", "失而復得", "消失之物以不同形式歸來"),
    Hook("H20", "錯位聲源", "聲音來源與畫面不符"),
    Hook("H21", "第一人稱物", "以物件視角見證事件"),
    Hook("H22", "儀式缺角", "儀式中少了一步"),
    Hook("H23", "遠方閃光", "地平線出現微弱信號"),
    Hook("H24", "數字巧合", "重複出現的數字或次數"),
    Hook("H25", "空間摺疊", "走過的門回到同一處"),
    Hook("H26", "記憶碎片", "快速閃回一幀畫面"),
    Hook("H27", "交接瞬間", "兩者交接的零點幾秒被放大"),
    Hook("H28", "起點終點重疊", "開場與結尾使用同一構圖"),
    Hook("H29", "旁觀者視角", "全程有一個不介入的旁觀者"),
    Hook("H30", "靜物變化", "靜物在兩鏡之間悄悄改變"),
)

_BY_ID = {h.id: h for h in HOOKS}


def all_hooks() -> tuple[Hook, ...]:
    return HOOKS


def get_hook(hook_id: str) -> Hook:
    return _BY_ID[hook_id]


def pick_hooks(n: int, seed: int | None = None, exclude_ids: tuple[str, ...] = ()) -> list[Hook]:
    """Pick n distinct hooks (reproducible when seed is given)."""
    pool = [h for h in HOOKS if h.id not in exclude_ids]
    if n > len(pool):
        raise ValueError(f"not enough hooks: want {n}, pool {len(pool)}")
    rng = random.Random(seed)
    return rng.sample(pool, n)


def hooks_to_dicts() -> list[dict]:
    return [asdict(h) for h in HOOKS]


def modern_lens_opening(topic: str) -> dict:
    """Return a modern-entry framing rule for ancient tales and legends.

    This keeps the opening anchored in a present-day viewer's question before
    the story crosses into the historical or mythical world.
    """
    return {
        "name": "現代視角切入",
        "desc": f"先用現代人的疑問打開 {topic}，再把鏡頭切入古代傳說或歷史場景",
        "cue": "開場先出現當代觀眾能理解的問題、比較或旁白，再無縫切到古代世界",
    }


def vlog_time_travel_opening(topic: str) -> dict:
    """Return a first-person travel-vlog framing rule.

    The narrator is a present-day witness who personally enters the ancient world,
    which keeps the story accessible for both Eastern and Western audiences.
    """
    return {
        "name": "第一人稱穿越 Vlog",
        "desc": f"用第一人稱旅行紀錄感打開 {topic}，讓現代旁白親自走進古代世界",
        "cue": "開場像旅遊 vlog：我在哪裡、我看到了什麼、我正走進哪個古代現場",
    }


def canonical_opening_rules(topic: str) -> list[dict]:
    """Return the default opening rules used by Story Room for cross-cultural stories."""
    return [modern_lens_opening(topic), vlog_time_travel_opening(topic)]
