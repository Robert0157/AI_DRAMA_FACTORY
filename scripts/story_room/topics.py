"""Topic bank for the Story Room (30 candidates; CEO top-10 marked 2026-09-10).

Tags:
- channel   : "lofi" | "light_music" | "both"
- style     : "surreal" (Surreal AI direction) | "hollywood" (live-action feel) | "mixed"
- difficulty: AI-generation feasibility only ("low" | "mid" | "high"),
              NOT story quality. "high" means human-performance close-ups
              (a known model weak spot) - handle with the shot-language shield.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    name: str
    hook: str          # First-3-seconds visual hook (zero dialogue)
    channel: str       # lofi | light_music | both
    style: str         # surreal | hollywood | mixed
    difficulty: str    # low | mid | high
    selected: bool = False  # True for the CEO top-10 list


# CEO-selected top-10 (2026-09-10), in the order the CEO provided them.
TOP10_NAMES: tuple[str, ...] = (
    "燈塔守夜人",
    "貓與老麵包店",
    "雲端列車",
    "沙漠巨械獸",
    "修書人的記憶",
    "月球玫瑰",
    "石像山神",
    "舊錄影帶",
    "極光守望者",
    "森林裡的機械鹿",
)

TOPICS: tuple[Topic, ...] = (
    Topic("深夜末班地鐵", "車門將關，濕透的身影滑進車廂——倒影卻留在月台", "lofi", "surreal", "mid"),
    Topic("雨夜的便利店", "監視器視角：凌晨三點，貨架上的傘一把把自己撐開", "lofi", "surreal", "low"),
    Topic("霓虹雨巷快遞", "後照鏡裡，整座城市正在向後跑", "lofi", "hollywood", "mid"),
    Topic("屋頂天文台", "望遠鏡裡那顆星，每晚向地球靠近一格", "lofi", "surreal", "mid"),
    Topic("打烊的唱片行", "唱針自己落下，播放一首還沒被寫出來的歌", "lofi", "surreal", "low"),
    Topic("洗衣店的銀河", "滾筒轉動——裡面不是衣服，是星空", "lofi", "surreal", "low"),
    Topic("深夜拉麵攤", "老闆把一顆蛋放進空碗——那碗是給誰的？", "lofi", "hollywood", "mid"),
    Topic("燈塔守夜人", "暴風雨夜，燈塔光掃過海面，照出消失三十年的船", "both", "hollywood", "mid", selected=True),
    Topic("高架橋下的鋼琴", "沒人彈的鋼琴響了，整條車流開始放慢", "lofi", "surreal", "low"),
    Topic("貓與老麵包店", "每天清晨五點，門口的貓叼來一張不同的舊車票", "lofi", "hollywood", "low", selected=True),
    Topic("城市最後一盞路燈", "全城停電，只剩一盞燈還亮，燈下聚滿螢火蟲", "light_music", "surreal", "low"),
    Topic("雲端列車", "列車衝出雲海，前方游過一群鯨魚", "light_music", "surreal", "mid", selected=True),
    Topic("沙漠巨械獸", "沙丘動了——那不是沙丘，是沉睡的機械獸", "light_music", "surreal", "mid", selected=True),
    Topic("海底圖書館", "潛水燈照到沉船書架，一隻章魚正在翻書", "light_music", "surreal", "mid"),
    Topic("星塵郵差", "郵差把一顆星放進郵筒，整片夜空暗了一秒", "light_music", "surreal", "mid"),
    Topic("螢光鯨遷徙", "月下峽谷裡，整條河在發光——是鯨群", "light_music", "surreal", "mid"),
    Topic("玻璃工坊的火鳳凰", "匠人吹一口氣，火焰在玻璃裡變成鳳凰", "light_music", "hollywood", "mid"),
    Topic("修書人的記憶", "打開修好的舊書，書頁開始播放雨聲", "both", "surreal", "low", selected=True),
    Topic("極光守望者", "二十年來第一晚他沒上山頂，極光卻降到他家門口", "light_music", "hollywood", "mid", selected=True),
    Topic("森林裡的機械鹿", "雨中的鹿抬起頭，眼睛是兩顆正在充電的綠燈", "light_music", "surreal", "mid", selected=True),
    Topic("倒轉的鐘錶店", "全店時鐘同時倒轉，小鎮多出一小時", "both", "surreal", "low"),
    Topic("海邊的電話亭", "電話亭響起，來電顯示是十年前", "both", "surreal", "low"),
    Topic("月球玫瑰", "月球溫室玻璃罩下，第一朵玫瑰正在開", "light_music", "surreal", "mid", selected=True),
    Topic("城市上空的鯨", "早高峰，一頭鯨的陰影掠過整條街", "light_music", "surreal", "mid"),
    Topic("舊錄影帶", "修好錄影機的瞬間，螢幕裡的母親向他招手", "lofi", "hollywood", "high", selected=True),
    Topic("冰海鋼琴", "琴鍵落下，腳下的海冰裂出五線譜", "light_music", "surreal", "mid"),
    Topic("櫻隧信件", "少年衝進櫻花隧道，信紙在風裡像雪一樣飛", "lofi", "hollywood", "low"),
    Topic("發條小鎮", "正午十二點，全鎮建築同時上發條，只有鐘樓停了", "both", "surreal", "mid"),
    Topic("石像山神", "暴雪中，手電筒照到一尊會流淚的石像", "both", "surreal", "mid", selected=True),
    Topic("月台倒影", "列車進站，玻璃倒影裡的人比他先上了車", "lofi", "surreal", "low"),
)

_BY_NAME = {t.name: t for t in TOPICS}


def get_topic(name: str) -> Topic | None:
    """Look up a topic by exact name; returns None when not in the bank."""
    return _BY_NAME.get(name)


def top10() -> tuple[Topic, ...]:
    """Return the CEO-selected top-10 topics."""
    return tuple(t for t in TOPICS if t.selected)
