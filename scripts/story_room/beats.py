"""Beat-sheet layer: three-act scaffold + authored beat-sheet loading.

Deterministic and offline: no LLM, no API calls. The scaffold gives the story
room a legal starting point; authored beats (human/LLM) plug in via
`sheet_from_dict`, which is also the round-trip format of `BeatSheet.to_dict`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Act:
    index: int      # 1..3
    title: str
    synopsis: str


@dataclass(frozen=True)
class Beat:
    index: int      # 1-based, order matters
    act: int        # owning act (1..3)
    name: str
    intent: str
    cue: str = ""   # music/lyric sync reference; filled at cue-mapping time


@dataclass
class BeatSheet:
    topic: str
    logline: str
    hook: str
    theme: str
    target_sec: float
    acts: list[Act] = field(default_factory=list)
    beats: list[Beat] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def act_spans(self) -> list[tuple[float, float]]:
        """Three equal act spans across the target duration (rounded to 0.1s)."""
        t = self.target_sec
        b1 = round(t / 3.0, 1)
        b2 = round(2.0 * t / 3.0, 1)
        return [(0.0, b1), (b1, b2), (b2, round(t, 1))]


DEFAULT_ACT_TITLES: tuple[str, str, str] = (
    "第一幕・世界與鉤子",
    "第二幕・試煉與反轉",
    "第三幕・高潮與餘韻",
)

# Generic 12-beat scaffold (skeleton intents; replace with authored text).
_SCAFFOLD: tuple[tuple[int, str, str], ...] = (
    (1, "前3秒鉤子", "以題材鉤子畫面開場，零對白，直接建立懸念"),
    (1, "世界建立", "建立主角所處的世界與日常，環境主導"),
    (1, "日常裂縫", "日常中出現不協調的細節，暗示異變"),
    (1, "召喚出現", "異常事件正式進入主角的世界"),
    (1, "跨越門檻", "主角做出選擇，離開原本狀態"),
    (2, "試煉一", "主角面對第一個障礙，付出小代價"),
    (2, "試煉二", "障礙升級，環境與光線轉為不友善"),
    (2, "中點反轉", "真相或規則揭露，主角的理解被顛覆"),
    (2, "危機逼近", "最壞情況成形，時間或資源耗盡"),
    (2, "最黑暗時刻", "主角失去關鍵之物，幾乎放棄"),
    (3, "高潮", "主角以自身代價回應，完成蛻變"),
    (3, "償付與餘韻", "懸念回收，留下一個可被記住的收尾畫面"),
)


def build_scaffold(
    topic: str,
    target_sec: float = 175.0,
    hook: str = "",
    logline: str = "TODO(CEO): 以一句話定義主角、渴望、阻礙、代價與轉折",
    theme: str = "TODO(CEO): 主題一句話（如：守望與贖回）",
) -> BeatSheet:
    """Build a generic 12-beat three-act skeleton for the given topic."""
    acts = [
        Act(1, DEFAULT_ACT_TITLES[0], "建立世界、主角與懸念（對應歌曲前段）"),
        Act(2, DEFAULT_ACT_TITLES[1], "衝突升級與反轉（對應歌曲主體推進段）"),
        Act(3, DEFAULT_ACT_TITLES[2], "高潮與收束（對應歌曲最高潮與尾聲）"),
    ]
    beats = [Beat(i, a, n, m) for i, (a, n, m) in enumerate(_SCAFFOLD, start=1)]
    return BeatSheet(
        topic=topic,
        logline=logline,
        hook=hook or "TODO(CEO): 前3秒鉤子畫面",
        theme=theme,
        target_sec=float(target_sec),
        acts=acts,
        beats=beats,
    )


def sheet_from_dict(data: dict) -> BeatSheet:
    """Rebuild a BeatSheet from its dict form (authored beats load via this)."""
    acts = [Act(**a) for a in data.get("acts", [])]
    beats = [Beat(**b) for b in data.get("beats", [])]
    return BeatSheet(
        topic=data["topic"],
        logline=data.get("logline", ""),
        hook=data.get("hook", ""),
        theme=data.get("theme", ""),
        target_sec=float(data.get("target_sec", 175.0)),
        acts=acts,
        beats=beats,
    )
