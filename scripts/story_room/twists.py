"""Twist Bank: 20 reversal archetypes, each with a planting requirement.

`requirement` describes what must be planted early so the twist feels earned
(used by the foreshadow ledger in critic_dims).
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Twist:
    id: str
    name: str
    desc: str
    requirement: str


TWISTS: tuple[Twist, ...] = (
    Twist("T01", "物件雙重用途", "前文物品其實另有用途", "該物品須在 Act1 出現且用途被誤導"),
    Twist("T02", "身份錯置", "以為的身份其實是另一人", "須先建立一個可信的錯誤身份線索"),
    Twist("T03", "時間倒錯", "片段順序被重新定義", "須有一個可信的時間錨點被誤讀"),
    Twist("T04", "視角反轉", "觀眾一直看的是另一方", "須全程維持觀點一致性，尾段才翻轉"),
    Twist("T05", "假勝利", "成功其實是陷阱", "須先讓一次小型成功顯得真實"),
    Twist("T06", "假失敗", "失敗其實是保護", "須鋪陳一個看似殘酷的拒絕或失去"),
    Twist("T07", "善意謊言", "體貼的真相被延遲", "須有一個刻意隱藏的善意行為"),
    Twist("T08", "替代犧牲", "代價被他人悄悄承擔", "須出現一個主動讓位的角色動作"),
    Twist("T09", "迴圈契約", "事件曾在更早發生過", "須有一個可重複識別的畫面記號"),
    Twist("T10", "需求誤認", "主角要的不是他以為的", "須讓主角的目標物件反覆出現"),
    Twist("T11", "守護者身份", "阻礙者其實是守護者", "須讓阻礙行為付出可見代價"),
    Twist("T12", "遺失的收件人", "訊息寄給的不是眼前人", "須先展示訊息內容的一角"),
    Twist("T13", "空房間真相", "缺席者一直在場", "須有一個被忽略的空間線索"),
    Twist("T14", "分裂的善意", "兩個善意互相抵消", "須建立兩個彼此不知情的動機"),
    Twist("T15", "時間膠囊", "現在的行動是過去的回應", "須先埋一個無法解釋的舊物"),
    Twist("T16", "名字的重量", "一個名字被誤讀多年", "須讓名字以物件形式出現至少兩次"),
    Twist("T17", "規則漏洞", "世界規則存在例外", "須先明確展示規則本身"),
    Twist("T18", "同物異主", "雙方爭奪同一物卻各有所求", "須讓物件同時具備兩種價值"),
    Twist("T19", "謊言成真", "假裝的事後來成真", "須先有一次被識破的假裝"),
    Twist("T20", "第四面窗", "一直守望的外部視角現身", "須全程保留一個不明觀看者痕跡"),
)

_BY_ID = {t.id: t for t in TWISTS}


def all_twists() -> tuple[Twist, ...]:
    return TWISTS


def get_twist(twist_id: str) -> Twist:
    return _BY_ID[twist_id]


def pick_twists(n: int, seed: int | None = None, exclude_ids: tuple[str, ...] = ()) -> list[Twist]:
    pool = [t for t in TWISTS if t.id not in exclude_ids]
    if n > len(pool):
        raise ValueError(f"not enough twists: want {n}, pool {len(pool)}")
    rng = random.Random(seed)
    return rng.sample(pool, n)


def twists_to_dicts() -> list[dict]:
    return [asdict(t) for t in TWISTS]
