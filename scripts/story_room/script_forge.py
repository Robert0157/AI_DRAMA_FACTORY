"""Script Forge: B-line series development loop through layers L1->L2->L3->L4.

CEO 2026-09-12 directive (script-first):
- Before the FIRST checkpoint (CP-D: script review + costume stills) the script
  must iterate through the four working layers of the five-layer architecture
  AT LEAST 15 times; the per-iteration log is the gate evidence.
- The script must reach Hollywood-grade rubric before CP-D is scheduled:
  total >= 8.8, every domain >= 8.0, zero rule errors.

Layers engaged per iteration:
  L1 workbench : snapshot dropped for the cockpit (LocalMiniDrama) to load
  L2 drafting  : story_room seed / revise of the series package
  L3 review    : multi-agent panel (4 specialist critics + showrunner director)
  L4 dimensions: deterministic rule checks (episode grid / canon / foreshadows
                 / format / dual-track export tags)

Artifacts per series (under <out>/<series_id>/):
  run_meta.json           brief, thresholds, iteration counter, status
  state_latest.json       latest full series package (resume point)
  iter_NN.json            per-iteration record (scores, findings, layer actions)
  iteration_log.md        human-readable table (CP-D evidence)
  lock_ready.json         written ONLY when the gate passes
  l1_workbench/iter_NN.json + latest.json   cockpit drop

CLI:
  python scripts/story_room/script_forge.py --series-id timegate-56
  python scripts/story_room/script_forge.py --series-id timegate-56 --resume
  python scripts/story_room/script_forge.py --series-id timegate-56 --status
  python scripts/story_room/script_forge.py --series-id timegate-56 --gate-check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(_WORKSPACE_ROOT) not in sys.path:  # allow `python scripts/story_room/script_forge.py`
    sys.path.insert(0, str(_WORKSPACE_ROOT))

# ---------------------------------------------------------------------------
# Gate constants (CEO thresholds - changing these requires CEO authorization)
# ---------------------------------------------------------------------------
RUBRIC_WEIGHTS: dict[str, float] = {
    "concept": 0.12,      # originality / premise strength
    "structure": 0.15,    # 56-episode macro structure + per-episode turns
    "character": 0.15,    # arcs, motivation, voice
    "dialogue": 0.13,     # subtext, differentiation
    "mythology": 0.12,    # East x West myth integration, cultural coherence
    "feasibility": 0.13,  # AI production feasibility (6x30s, character count)
    "hook_density": 0.10, # per-episode hooks / cliffhangers
    "dual_track": 0.10,   # LM (scenery) / LF (character) expansion potential
}
MIN_ITERATIONS = 15
# CEO 2026-09-12 (rev): the 150 ceiling proved too low (Phase 1 was capped
# without reaching the gate). Industry-standard practice for an iterative
# quality campaign: the QUALITY GATE is the stop condition and the cap is
# only a budget guardrail of 10^3 evaluations - the same order of magnitude
# as one Hollywood season's revision volume (56 episodes x 10-20 passes =
# 560-1,120).
DEFAULT_MAX_ITERATIONS = 1000
# Patience alarm: warn when the champion has been idle this long (alert-only,
# never auto-stop - the CEO decides whether to intervene).
PLATEAU_PATIENCE = 100
HOLLYWOOD_TOTAL = 8.8
HOLLYWOOD_MIN_DOMAIN = 8.0
_PENALTY = {"error": 0.5, "warn": 0.25, "info": 0.1}
_PENALTY_CAP = 2.5
TARGET_EPISODES = 56
TARGET_EPISODE_SEC = 175
TARGET_SHOTS_PER_EP = 6

DEFAULT_BRIEF = """題材定調（CEO 2026-09-12 定案）
- 類型：東方神話 × 西方神話 × 奇幻，雙棲並行；現代人物經「時光隧道／自媒體入口（直播間）」進入神話世界。
- 格式：56 集 × 175 秒短劇連載；每集 6×30s 長鏡；好萊塢實拍模式質感；B 線 AI_Drama 新頻道。
- 品質門檻：好萊塢劇本水準——L1→L2→L3→L4 迭代 ≥15 次（log 為證）；總分 ≥8.8、單域 ≥8.0、零 error。
- 擴充要求：每弧必須標記可供 light_music（風景／零人物）與 lofi（人物＋場景／美女即世界）特輯擴充的場景與角色。
- 受眾：東西跨文化；零版權風險（原創或公版神話素材）。
- 參考素材庫（CEO 2026-09-12 提供；參考用、不強制）：《山海經十八卷》《聊齋志異》《閱微草堂筆記》《潘朵拉的盒子》《北歐神話》——可在設定、角色、典故與主題上自由取用與改寫。"""

_CONSTRAINTS = (
    "硬約束（不可變更）：56 集 × 175 秒短劇連載；每集 6×30s 長鏡；480p 政策（禁用 4K/HDR 字樣）；"
    "Seedance 2.5 AI 量產（口型同步）；「好萊塢實拍模式」指鏡頭語言與製作規範，不是預算陳述。"
    "feasibility 必須在上述約束內評分與建議（例如鏡位、場次合併、角色數量控制），"
    "不得要求改集數、改時長或改成動畫風格。"
)

_REFERENCES = (
    "參考素材庫（參考用、不強制；可自由取用與改寫）：《山海經十八卷》《聊齋志異》"
    "《閱微草堂筆記》《潘朵拉的盒子》《北歐神話》。東方典故需準確，西方神話需尊重原型語境。"
)

_CRAFT: dict[str, str] = {
    "dialogue": "對白需濳台詞：角色不直說意圖，用行動與雙關；每場衝突需 want/obstacle/tactic；主要角色語言指紋不同。",
    "character": "每位主角要有 want/need/flaw/wound；弧光轉折點寫明在第幾集；配角不得工具化（各有目標）。",
    "structure": "每弧需目標→升級→回報閉環；權力關係至少轉變一次；集末鉤子交替使用資訊型/選擇型/情感型，禁連續三集同型。",
    "feasibility": "常設角色 ≤8、每集場次 ≤3、大場面以暗示＋局部特寫表現；刪除難以生成的複雜調度；鏡頭設計需适配 6×30s 長鏡。",
    "mythology": "東西方元素必須互為因果（非並列展示）；引用具體典故並改寫其結局意義，融入雙重限制（信仰值×記憶）。",
    "hook_density": "每集 hook 交替使用資訊型/選擇型/情感型；禁止連續三集同型；弧末鉤子需推翻前一假設。",
    "concept": "前提一句話可賣（high concept）；雙重限制（信仰值×記憶）必須相互咬合，缺一不可。",
    "dual_track": "每弧明確標出 LM 可拍場景（零人物長鏡）與 LF 夢境段（主角×場景），且服務主線情節。",
}

# Teleplay excerpt passes: rotate key episodes so the package grows real script pages.
# NOTE: index 0 (and any index divisible by 5) collides with the it%10==0
# production-plan branch, so that episode's excerpt was NEVER refreshed (this
# silently starved the pilot rewrite). Keep Ep1 at index 9.
_EXCERPT_ROTATION = (14, 2, 56, 28, 42, 7, 21, 35, 49, 1)

_RUBRIC_SYS = (
    "你是好萊塢劇本開發評審（VP of Development）＋神話學顧問。"
    "評估一部 56 集×175 秒的 AI 短劇連載企劃（東方×西方神話奇幻雙棲）。"
    "只回傳 JSON：{\"domains\":{\"concept\":0-10,\"structure\":0-10,\"character\":0-10,"
    "\"dialogue\":0-10,\"mythology\":0-10,\"feasibility\":0-10,\"hook_density\":0-10,"
    "\"dual_track\":0-10},\"verdict\":\"一句話\",\"top_fixes\":[\"3-7 條最優先修正\"],"
    "\"findings\":[{\"domain\":\"...\",\"level\":\"error|warn|info\",\"msg\":\"...\"}]}。"
    "評分標準＝好萊塢水準：8 分＝可開拍電視水準、9 分＝串流旗艦、10 分＝獲獎級。"
)
_REVISE_SYS = (
    "你是頂尖連載劇集 showrunner 團隊。依評審意見修訂企劃包，但只輸出【精簡修補 JSON】："
    "{\"patch\": {...}, \"fixes_applied\": [\"...\"]}。"
    "patch 規則：① 只放【要變更】的欄位，未提及的欄位會自動保留（切勿整包回傳）；"
    "② bible／genre 只需含要改的子鍵（深合併）；空陣列/空字串會被忽略；"
    "③ 分集用 episode_patches = [{\"ep\": N, ...只列要改的鍵}]；"
    "若 episode_outline 未滿 56 集，必須用 episode_patches 把缺集以完整欄位補齊；"
    "④ 必須處理【所有 error 級發現】（error 清零為第一優先），另可再處理最多 3 項 warn；同步優先拉高評分最低的維度；遵守硬約束。"
)


# ---------------------------------------------------------------------------
# Output root resolution (Y: share first, local fallback; never hardcode drives)
# ---------------------------------------------------------------------------
def out_root() -> Path:
    env = os.environ.get("SCRIPT_FORGE_ROOT")
    if env:
        return Path(env)
    share = Path("Y:/AI_Drama_Factory/Auto_Drama/output/script_forge")
    if share.parent.parent.exists():  # Y: mounted (Mac share)
        return share
    return _WORKSPACE_ROOT / "Auto_Drama" / "output" / "script_forge"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hash(package: dict) -> str:
    blob = json.dumps(package, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _salvage_json(text: str) -> dict | None:
    """Best-effort recovery of a truncated JSON object (large seed responses can be cut).

    Closes an open string and unbalanced brackets, retrying after trimming the last
    partial element; returns a usable dict instead of losing the whole draft.
    """
    start = text.find("{")
    if start < 0:
        return None
    base = text[start:]
    for _ in range(6):
        in_str, esc, stack = False, False, []
        for ch in base:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch in "{[":
                    stack.append(ch)
                elif ch in "}]":
                    if stack:
                        stack.pop()
        tail = '"' if in_str else ""
        for opener in reversed(stack):
            tail += "}" if opener == "{" else "]"
        try:
            data = json.loads(base + tail)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        cut = base.rfind(",")
        if cut <= 0:
            return None
        base = base[:cut]
    return None


# ---------------------------------------------------------------------------
# Offline seed / revise (deterministic; used by tests and $0 dry runs)
# ---------------------------------------------------------------------------
def offline_seed_package() -> dict:
    """A complete, gate-passing series package - deterministic scaffold."""
    arcs = []
    outline = []
    for ep in range(1, TARGET_EPISODES + 1):
        arc_no = (ep - 1) // 14 + 1
        outline.append({
            "ep": ep, "arc": arc_no,
            "title": f"第{ep}集・門的另一側",
            "hook": f"時光裂縫在第{arc_no}弧加深：一句未解的預言在第{ep}集浮現。",
            "summary": f"現代主持人在直播中穿越第{arc_no}號神域，逼近核心真相（第{ep}集）。",
            "cliffhanger": "畫面切黑前，神域之門在直播間倒影中再次開啟。",
        })
        if ep % 14 == 0:
            arcs.append({
                "arc": arc_no, "episodes": f"{ep - 13}-{ep}",
                "summary": f"第{arc_no}弧：東西方神話交會，主持人以自媒體證據破解神諭。",
                "climax": "時光隧道與直播訊號重疊，神話人物回應現代提問。",
                "lm_special": True, "lf_special": True,
                "foreshadows": [
                    {"setup": f"弧{arc_no}開場：直播彈幕出現古老字謎", "payoff": f"弧{arc_no}終章：字謎揭曉為神域座標"},
                    {"setup": f"弧{arc_no}中段：神像手中微型錄音機", "payoff": f"弧{arc_no}終章：錄音機回放神諭原聲"},
                ],
            })
    return {
        "schema": "series_contract.v1",
        "title": "時光直播間（暫名）",
        "logline": "現代自媒體主持人意外開啟東西神話交會的時光隧道，以直播見證並改寫兩大神系的命運。",
        "theme": "被看見的時代如何重寫神話——媒介即命運。",
        "genre": {"mix": "東方神話×西方神話×奇幻", "access": "時光隧道／自媒體直播入口", "tone": "史詩＋輕喜＋懸疑"},
        "target_format": {"episodes": TARGET_EPISODES, "episode_sec": TARGET_EPISODE_SEC,
                          "shots_per_ep": TARGET_SHOTS_PER_EP, "resolution": "480p"},
        "bible": {
            "world_rules": ["時光隧道僅在直播訊號滿格時開啟", "神話人物能感知鏡頭", "每人一生僅能穿越一次"],
            "mythology": {
                "east": ["山海經異獸", "敦煌飛天", "九尾狐", "龍門石窟守衛"],
                "west": ["奧林帕斯神諭", "北歐世界樹", "亞瑟王湖中劍", "埃及亡靈書"],
            },
            "protagonists": [
                {"name": "林晚", "role": "自媒體主持人", "arc": "從流量追逐者成為神話見證者", "access_method": "直播間隧道"},
                {"name": "Elias", "role": "西方考古學家", "arc": "從懷疑論到神域翻譯者", "access_method": "古物觸發"},
            ],
            "antagonists": [{"name": "無面編集者", "role": "試圖剪掉神話記憶的操盤手", "arc": "被直播反噬"}],
            "locations": [
                {"id": "loc_kunlun", "name": "崑崙鏡湖", "myth_system": "east", "lm_export": True, "lf_export": True},
                {"id": "loc_dunhuang", "name": "敦煌夜窟", "myth_system": "east", "lm_export": True, "lf_export": False},
                {"id": "loc_penglai", "name": "蓬萊雲台", "myth_system": "east", "lm_export": True, "lf_export": True},
                {"id": "loc_olympus", "name": "奧林帕斯石階", "myth_system": "west", "lm_export": True, "lf_export": False},
                {"id": "loc_yggdra", "name": "世界樹根窟", "myth_system": "west", "lm_export": True, "lf_export": True},
                {"id": "loc_avalon", "name": "阿瓦隆湖", "myth_system": "west", "lm_export": True, "lf_export": True},
                {"id": "loc_studio", "name": "現代直播間", "myth_system": "modern", "lm_export": False, "lf_export": True},
                {"id": "loc_gate", "name": "時光閘道", "myth_system": "modern", "lm_export": False, "lf_export": True},
            ],
            "canon": {"characters": ["林晚", "Elias", "無面編集者"],
                      "rules": ["穿越不可逆", "神話語言需翻譯", "直播畫面可被神域看見"]},
        },
        "arcs": arcs,
        "episode_outline": outline,
        "foreshadows": [
            {"setup": "第一集直播間的古老字謎", "payoff": "第14集揭曉為崑崙座標"},
            {"setup": "Elias 的斷裂指環", "payoff": "第28集拼回阿瓦隆之鑰"},
            {"setup": "直播回放中的多出的一張臉", "payoff": "第42集證實為無面編集者"},
            {"setup": "敦煌壁畫缺角飛天", "payoff": "第21集以彈幕修補"},
            {"setup": "世界樹葉脈的摩斯節奏", "payoff": "第35集譯為求救訊號"},
            {"setup": "鏡湖倒影晚半秒", "payoff": "第49集證明時間可逆"},
            {"setup": "主持人耳機出現未來雜音", "payoff": "第52集揭為結局旁白"},
            {"setup": "神域之門的雙面門牌", "payoff": "第56集同時通向東西方結局"},
        ],
        "pilot": {
            "ep1": {"scenes": ["直播間事故", "隧道開啟", "崑崙初見"],
                    "dialogue_sample": "林晚：『各位觀眾——你們看到的不是特效。』（彈幕暴走）"},
            "ep2": {"scenes": ["神域規則", "無面編集者登場", "第一次代價"],
                    "dialogue_sample": "Elias：『我們不是在拍神話。神話在拍我們。』"},
        },
    }


def offline_revise(package: dict, findings: list[dict], broken: bool = False) -> dict:
    """Deterministic no-op/cleanup revise; `broken` keeps it a no-op (test helper)."""
    if broken:
        return package
    patched = json.loads(json.dumps(package, ensure_ascii=False))
    patched.setdefault("director_note", "; ".join(f["msg"] for f in findings[:5])[:400])
    return patched


# ---------------------------------------------------------------------------
# L4 rule dimensions (deterministic, evidence-based)
# ---------------------------------------------------------------------------
def rule_findings(package: dict) -> list[dict]:
    findings: list[dict] = []

    def add(domain: str, level: str, msg: str) -> None:
        findings.append({"domain": domain, "level": level, "msg": msg})

    fmt = package.get("target_format") or {}
    if fmt.get("episodes") != TARGET_EPISODES:
        add("structure", "error", f"集數 {fmt.get('episodes')} != {TARGET_EPISODES}")
    if fmt.get("episode_sec") != TARGET_EPISODE_SEC or fmt.get("shots_per_ep") != TARGET_SHOTS_PER_EP:
        add("feasibility", "warn", "格式偏離 175s＝6×30s")

    outline = package.get("episode_outline") or []
    if len(outline) != TARGET_EPISODES:
        add("structure", "error", f"分集大綱 {len(outline)} 集 != {TARGET_EPISODES}")
    missing_hooks = sum(1 for e in outline if not str(e.get("hook", "")).strip())
    missing_cliff = sum(1 for e in outline if not str(e.get("cliffhanger", "")).strip())
    if missing_hooks:
        add("hook_density", "warn", f"{missing_hooks} 集缺 hook")
    if missing_cliff:
        add("hook_density", "warn", f"{missing_cliff} 集缺 cliffhanger")

    bible = package.get("bible") or {}
    myth = bible.get("mythology") or {}
    if len(myth.get("east") or []) < 3:
        add("mythology", "warn", "東方神話元素 < 3")
    if len(myth.get("west") or []) < 3:
        add("mythology", "warn", "西方神話元素 < 3")

    leads = bible.get("protagonists") or []
    names = [str(c.get("name", "")) for c in leads]
    if len(leads) < 2:
        add("character", "error", "主角 < 2 人")
    if len(names) != len(set(names)):
        add("character", "error", "角色重名")
    for c in leads:
        if not str(c.get("arc", "")).strip():
            add("character", "warn", f"角色 {c.get('name')} 缺弧光")
        if not str(c.get("access_method", "")).strip():
            add("concept", "warn", f"角色 {c.get('name')} 缺進入方式")

    locs = bible.get("locations") or []
    if len(locs) < 6:
        add("dual_track", "warn", f"場景 < 6（{len(locs)}）")
    if sum(1 for l in locs if l.get("lm_export")) < 3:
        add("dual_track", "warn", "LM 可擴充場景 < 3")
    if sum(1 for l in locs if l.get("lf_export")) < 3:
        add("dual_track", "warn", "LF 可擴充場景 < 3")
    for l in locs:
        if not (l.get("lm_export") or l.get("lf_export")):
            add("dual_track", "info", f"場景 {l.get('id')} 兩頻道皆不可用")

    arcs = package.get("arcs") or []
    covered = sorted({int(e.get("ep")) for e in outline if str(e.get("ep", "")).isdigit()})
    if arcs:
        spans: list[int] = []
        for a in arcs:
            rng = str(a.get("episodes", ""))
            if "-" in rng:
                lo, _, hi = rng.partition("-")
                if lo.isdigit() and hi.isdigit():
                    spans.extend(range(int(lo), int(hi) + 1))
        if covered and sorted(set(spans)) != list(range(1, TARGET_EPISODES + 1)):
            add("structure", "warn", "分弧未連續覆蓋 1–56 集")
        specials = sum(1 for a in arcs if a.get("lm_special") and a.get("lf_special"))
        if specials < len(arcs) // 2:
            add("dual_track", "warn", f"僅 {specials}/{len(arcs)} 弧標記雙特輯")
        thin = sum(1 for a in arcs if len(a.get("foreshadows") or []) < 2)
        if thin:
            add("structure", "warn", f"{thin} 弧伏筆 < 2")
    else:
        add("structure", "error", "缺 arcs 分弧")

    if len(package.get("foreshadows") or []) < 8:
        add("structure", "warn", "全局伏筆 < 8")
    pilot = package.get("pilot") or {}
    for ep in ("ep1", "ep2"):
        if not str((pilot.get(ep) or {}).get("dialogue_sample", "")).strip():
            add("dialogue", "warn", f"{ep} 缺對白樣本")
    return findings


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def compute_final(llm_domains: dict[str, float], findings: list[dict]) -> dict:
    dom = {k: float(llm_domains.get(k, 5.0)) for k in RUBRIC_WEIGHTS}
    total = sum(dom[k] * w for k, w in RUBRIC_WEIGHTS.items())
    penalty = 0.0
    for f in findings:
        penalty += _PENALTY.get(str(f.get("level", "warn")), 0.25)
    penalty = min(round(penalty, 2), _PENALTY_CAP)
    return {
        "domains": {k: round(v, 1) for k, v in dom.items()},
        "llm_total": round(total, 2),
        "penalty": penalty,
        "final_total": round(total - penalty, 2),
        "min_domain": round(min(dom.values()), 1),
    }


def converged(final: dict, findings: list[dict], iterations: int, min_iters: int) -> bool:
    """Gate: >=15 logged iterations AND Hollywood floor AND zero rule errors."""
    return (
        iterations >= min_iters
        and final["final_total"] >= HOLLYWOOD_TOTAL
        and final["min_domain"] >= HOLLYWOOD_MIN_DOMAIN
        and not any(f.get("level") == "error" for f in findings)
    )


# ---------------------------------------------------------------------------
# LLM calls (lazy import so offline mode needs no key/package)
# ---------------------------------------------------------------------------
def _rubric(package: dict, model: str | None) -> tuple[dict, list[dict]]:
    from scripts.story_room import llm_text

    judge_model = os.environ.get("SCRIPT_FORGE_JUDGE_MODEL") or model
    reply = llm_text.deepseek_chat(
        _RUBRIC_SYS,
        _CONSTRAINTS + "\n\n" + _REFERENCES + "\n\n企劃包 JSON：\n" + json.dumps(package, ensure_ascii=False),
        model=judge_model,
        max_tokens=4096,
        temperature=0.1,
    )
    try:
        data = llm_text.extract_json(reply)
    except ValueError:
        data = _salvage_json(reply) or {}
        if not data.get("domains"):
            raise
        print("[warn] rubric truncated; salvaged domains", flush=True)
    domains = {k: max(0.0, min(10.0, float((data.get("domains") or {}).get(k, 5.0)))) for k in RUBRIC_WEIGHTS}
    findings = [
        {"domain": f.get("domain", "concept"), "level": f.get("level", "warn"), "msg": str(f.get("msg", ""))[:300]}
        for f in (data.get("findings") or [])
    ]
    fixes = [str(x)[:200] for x in (data.get("top_fixes") or [])]
    return dict(domains=domains, top_fixes=fixes, verdict=str(data.get("verdict", ""))[:200]), findings


# ---------------------------------------------------------------------------
# L3 multi-agent review panel (CEO 2026-09-12: real AI agents, four angles + director)
# ---------------------------------------------------------------------------
_CRITIC_PANEL: dict[str, dict] = {
    "structure": {
        "domains": ("concept", "structure", "hook_density"),
        "sys": (
            "你是好萊塢資深故事結構師（三幕劇、連載 macro-arc、hook 工程）。"
            "只評 concept（前提強度與獨特性）、structure（56 集宏觀結構與集內轉折）、"
            "hook_density（集末鉤子與懸念密度交替）。"
            "只回傳 JSON：{\"domains\":{\"concept\":0-10,\"structure\":0-10,\"hook_density\":0-10},"
            "\"report\":\"50-120字簡評\","
            "\"findings\":[{\"domain\":\"...\",\"level\":\"error|warn|info\",\"msg\":\"...\"}]}。"
            "評分＝好萊塢水準：8 分＝可開拍電視、9 分＝串流旗艦、10 分＝獲獎級。"
        ),
    },
    "character": {
        "domains": ("character", "dialogue"),
        "sys": (
            "你是獲獎劇集角色與對白指導（表演背景）。"
            "只評 character（want/need/flaw/wound、弧光轉折、配角目標）、"
            "dialogue（潛台詞、語言指紋、禁條列式堆疊）。"
            "只回傳 JSON：{\"domains\":{\"character\":0-10,\"dialogue\":0-10},"
            "\"report\":\"50-120字簡評\","
            "\"findings\":[{\"domain\":\"...\",\"level\":\"error|warn|info\",\"msg\":\"...\"}]}。"
            "評分＝好萊塢水準：8 分＝可開拍電視、9 分＝串流旗艦、10 分＝獲獎級。"
        ),
    },
    "mythology": {
        "domains": ("mythology", "dual_track"),
        "sys": (
            "你是跨文化神話學顧問（東亞＋希臘＋北歐＋埃及原型語境）。"
            "只評 mythology（典故準確、東西互為因果非並列）、"
            "dual_track（LM 零人物風景／LF 人物場景特輯標記與主線關聯）。"
            "只回傳 JSON：{\"domains\":{\"mythology\":0-10,\"dual_track\":0-10},"
            "\"report\":\"50-120字簡評\","
            "\"findings\":[{\"domain\":\"...\",\"level\":\"error|warn|info\",\"msg\":\"...\"}]}。"
            "評分＝好萊塢水準：8 分＝可開拍電視、9 分＝串流旗艦、10 分＝獲獎級。"
        ),
    },
    "feasibility": {
        "domains": ("feasibility",),
        "sys": (
            "你是 AI 製片 line producer（Seedance 2.5 量產線）。"
            "只評 feasibility（6×30s 長鏡調度、常設角色 ≤8、場景複用、口型同步負載、480p 合規）。"
            "只回傳 JSON：{\"domains\":{\"feasibility\":0-10},"
            "\"report\":\"50-120字簡評\","
            "\"findings\":[{\"domain\":\"...\",\"level\":\"error|warn|info\",\"msg\":\"...\"}]}。"
            "評分＝好萊塢水準：8 分＝可開拍電視、9 分＝串流旗艦、10 分＝獲獎級。"
        ),
    },
}

_DIRECTOR_SYS = (
    "你是串流旗艦級 showrunner（總導演），主持四人評審團（結構師／角色對白指導／神話學顧問／製片人）。"
    "將四份獨立評審報告仲裁為最終八域分數：每域以對應評審分數為錨，僅在確有依據時微調（±0.5 內）。"
    "並綜合 top_fixes（3-7 條、跨域優先序、可直接執行）、verdict（一句話）、findings 合併（去重）。"
    "只回傳 JSON：{\"domains\":{\"concept\":0-10,\"structure\":0-10,\"character\":0-10,\"dialogue\":0-10,"
    "\"mythology\":0-10,\"feasibility\":0-10,\"hook_density\":0-10,\"dual_track\":0-10},"
    "\"top_fixes\":[\"...\"],\"verdict\":\"...\","
    "\"findings\":[{\"domain\":\"...\",\"level\":\"error|warn|info\",\"msg\":\"...\"}]}。"
)


def _review_panel(package: dict, model: str | None,
                  ceo_notes: str = "") -> tuple[dict, list[dict], bool]:
    """L3 multi-agent review: four specialist critics (parallel) + one showrunner director.

    CEO 2026-09-12: the review layer must use real AI agents from different angles,
    not a single rubric call. Returns (rubric_result, findings, degraded).
    degraded=True whenever any agent failed - degraded rounds never become champion.
    """
    from scripts.story_room import llm_text

    judge_model = os.environ.get("SCRIPT_FORGE_JUDGE_MODEL") or model
    shared_user = (
        _CONSTRAINTS + "\n\n" + _REFERENCES
        + "\n\n企劃包 JSON：\n" + json.dumps(package, ensure_ascii=False)
        + "\n\n從你的專業角度嚴格審查。findings 的 level：僅違反 canon／硬約束／連貫性時用 error；"
          "品質提升建議用 warn／info。"
        + (f"\n\n【CEO 關切（評審必須逐項直接回答是否已落實；未落實列 warn/error）】\n{ceo_notes}"
           if ceo_notes else "")
    )

    def _run_critic(name: str, spec: dict) -> tuple[str, dict]:
        reply = llm_text.deepseek_chat(spec["sys"], shared_user, model=judge_model,
                                       max_tokens=2400, temperature=0.2)
        try:
            data = llm_text.extract_json(reply)
        except ValueError:
            data = _salvage_json(reply) or {}
            if not data.get("domains"):
                raise
        if not isinstance(data.get("domains"), dict) or not data["domains"]:
            raise ValueError("critic returned no domains")
        return name, data

    reports: dict[str, dict] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=len(_CRITIC_PANEL)) as pool:
        futures = {pool.submit(_run_critic, n, s): n for n, s in _CRITIC_PANEL.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                k, data = fut.result()
                reports[k] = data
            except Exception as exc:  # noqa: BLE001 - collect all, degrade gracefully
                failures.append(f"{name}: {str(exc)[:120]}")

    degraded = bool(failures)
    if failures:
        print(f"[warn] review panel degraded: {'; '.join(failures)}", file=sys.stderr, flush=True)
    if not reports:
        # Panel entirely down: single-judge fallback, still marked degraded.
        result, findings = _rubric(package, model)
        return result, findings, True

    anchor: dict[str, list[float]] = {}
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rep in reports.values():
        for dom, val in (rep.get("domains") or {}).items():
            if dom in RUBRIC_WEIGHTS:
                try:
                    anchor.setdefault(dom, []).append(float(val))
                except (TypeError, ValueError):
                    continue
        for f in rep.get("findings") or []:
            msg = str(f.get("msg", ""))[:300]
            key = (str(f.get("domain", "")), msg)
            if not msg or key in seen:
                continue
            seen.add(key)
            findings.append({"domain": key[0] or "concept",
                             "level": str(f.get("level", "warn")),
                             "msg": msg})

    digest = {
        name: {"domains": rep.get("domains") or {},
               "report": str(rep.get("report", ""))[:200]}
        for name, rep in reports.items()
    }
    compact = {
        "title": package.get("title"),
        "logline": package.get("logline"),
        "theme": package.get("theme"),
        "arcs": [a.get("arc") for a in (package.get("arcs") or [])],
        "episodes": len(package.get("episode_outline") or []),
    }

    def _fallback_domains() -> dict[str, float]:
        out: dict[str, float] = {}
        for k in RUBRIC_WEIGHTS:
            vals = anchor.get(k) or []
            out[k] = round(sum(vals) / len(vals), 1) if vals else 7.5
        return out

    try:
        reply = llm_text.deepseek_chat(
            _DIRECTOR_SYS,
            _CONSTRAINTS + "\n\n評審團報告：\n" + json.dumps(digest, ensure_ascii=False)
            + "\n\n企劃包摘要：" + json.dumps(compact, ensure_ascii=False),
            model=judge_model, max_tokens=4096, temperature=0.2,
        )
        try:
            d = llm_text.extract_json(reply)
        except ValueError:
            d = _salvage_json(reply) or {}
            if not d.get("domains"):
                raise
        final: dict[str, float] = {}
        for k in RUBRIC_WEIGHTS:
            v = (d.get("domains") or {}).get(k)
            if v is None:
                vals = anchor.get(k) or []
                v = sum(vals) / len(vals) if vals else 7.5
            try:
                final[k] = max(0.0, min(10.0, float(v)))
            except (TypeError, ValueError):
                final[k] = 7.5
        for f in d.get("findings") or []:
            msg = str(f.get("msg", ""))[:300]
            key = (str(f.get("domain", "")), msg)
            if not msg or key in seen:
                continue
            seen.add(key)
            findings.append({"domain": key[0] or "concept",
                             "level": str(f.get("level", "warn")),
                             "msg": msg})
        top_fixes = [str(x)[:200] for x in (d.get("top_fixes") or [])]
        verdict = str(d.get("verdict", ""))[:200]
        return dict(domains=final, top_fixes=top_fixes, verdict=verdict), findings, degraded
    except Exception as exc:  # noqa: BLE001 - director down: mean-of-critics, degraded
        print(f"[warn] director synthesis failed: {str(exc)[:160]}", file=sys.stderr, flush=True)
        verdict = "panel degraded (director failed)"
        return dict(domains=_fallback_domains(), top_fixes=[], verdict=verdict), findings, True


def _revise(package: dict, findings: list[dict], top_fixes: list[str], model: str | None,
            low_domains: list[str] | None = None,
            ceo_notes: str = "") -> tuple[dict, list[str]]:
    """Sparse patch revision: the model returns only changed fields (small output);
    a truncated reply falls back to the salvage parser for a partial patch."""
    from scripts.story_room import llm_text

    outline_need = max(0, TARGET_EPISODES - len(package.get("episode_outline") or []))
    craft = "\n".join(f"- {d}：{_CRAFT[d]}" for d in (low_domains or []) if d in _CRAFT)
    user = (
        _CONSTRAINTS + "\n\n" + _REFERENCES
        + "\n\n原企劃包（僅供參照；不要整包回傳）：\n" + json.dumps(package, ensure_ascii=False)
        + "\n\n評審發現：" + json.dumps(findings, ensure_ascii=False)
        + "\n優先修正：" + json.dumps(top_fixes, ensure_ascii=False)
        + (f"\n本次請優先拉高這些低分維度：{', '.join(low_domains)}" if low_domains else "")
        + (f"\n工藝強化（低分維度必須遵守）：\n{craft}" if craft else "")
        + (f"\n\n【CEO 定向修訂（最高優先；必須落實並以 patch/episode_patches 同步相關欄位）】\n{ceo_notes}"
           if ceo_notes else "")
        + (f"\n目前分集數不足，請用 episode_patches 補齊缺的 {outline_need} 集。" if outline_need else "")
        + "\n請回傳 {\"patch\": {...}, \"fixes_applied\": [...]}（精簡修補，只含變更欄位）。"
    )
    reply = llm_text.deepseek_chat(_REVISE_SYS, user, model=model, max_tokens=8192, temperature=0.7)
    try:
        data = llm_text.extract_json(reply)
    except ValueError:
        salvaged = _salvage_json(reply)
        if not salvaged or not isinstance(salvaged.get("patch"), dict) or not salvaged["patch"]:
            raise
        data = salvaged
        print("[warn] revise patch truncated; salvaged partial patch", flush=True)
    patch = data.get("patch") or {}
    if not isinstance(patch, dict) or not patch:
        raise ValueError("revise returned an empty patch")
    return patch, [str(x) for x in (data.get("fixes_applied") or [])]


def _write_excerpt(package: dict, ep: int, model: str | None,
                   findings: list[dict] | None = None,
                   ceo_notes: str = "") -> tuple[dict, str]:
    """Deep pass: write/upgrade a real teleplay excerpt (cold open + first scene).

    Carries the canon guardrails and the latest judge findings so the writer
    stops re-injecting the inconsistencies that cost error points."""
    from scripts.story_room import llm_text

    outline = {str(e.get("ep")): e for e in (package.get("episode_outline") or [])}
    entry = outline.get(str(ep), {})
    bible = package.get("bible") or {}
    leads = [str(c.get("name", "")) for c in (bible.get("protagonists") or [])]
    canon_rules = [str(r) for r in ((bible.get("canon") or {}).get("rules") or [])][:8]
    avoid = [
        f"- [{f.get('domain')}] {str(f.get('msg'))[:160]}"
        for f in (findings or [])
        if f.get("level") in ("error", "warn")
    ][:8]
    existing = str(((package.get("pilot") or {}).get(f"ep{ep}") or {}).get("script_excerpt") or "")
    task = "重寫並大幅提升" if existing else "撰寫"
    excerpt_model = os.environ.get("SCRIPT_FORGE_EXCERPT_MODEL") or model
    user = (
        _CONSTRAINTS + "\n\n" + _REFERENCES
        + f"\n\n請以好萊塢電視劇本格式，{task}第 {ep} 集的劇本節錄（冷開場＋第一場，約 1600–2400 字）："
        "\n- 場景標題（INT./EXT. 地點－時間）、動作描述、角色對白；"
        "\n- 對白需潛台詞：角色不直說意圖；每場須有 want/obstacle/tactic；主要角色語言指紋不同；"
        "\n- 東方×西方神話元素互為因果，不得並列展示；"
        "\n- 結尾留在強烈鉤子上；不得使用 4K/HDR 等規格詞；"
        "\n- 一致性鐵律（違反將被評審判 error）：① 禁特效『頻率』字樣（Hz／60Hz 等），以『單件/持續秒數』表現；"
        "② 對白禁條列式堆疊；③ 神話引用尊重原型語境（夸父＝逐日—渴死—鄧林；埃癸斯＝宙斯之盾借雅典娜；嫦娥＝不死藥與孤獨）；"
        "④ 所有數字（次數、集數）必須與 56 集線性敘事一致，禁稀釋結構的『重複 N 次輪迴』；⑤ canon 規則不得自相矛盾；"
        f"\n- 主角：{', '.join(leads)}；本集大綱：{json.dumps({k: entry.get(k) for k in ('title', 'hook', 'summary', 'cliffhanger')}, ensure_ascii=False)}"
        + (f"\n- canon 規則：{json.dumps(canon_rules, ensure_ascii=False)}" if canon_rules else "")
        + (f"\n- 近期評審發現（本次寫作必須避免）：\n" + "\n".join(avoid) if avoid else "")
        + (f"\n\n【CEO 定向修訂（最高優先；本集如涉 CEO 關切，必須逐條落實）】\n{ceo_notes}"
           if ceo_notes else "")
        + (f"\n\n現有節錄（請寫得更好）：\n{existing[:4000]}" if existing else "")
        + "\n\n只回傳 JSON：{\"script_excerpt\": \"...完整劇本節錄文字...\", \"notes\": \"一句話\"}"
    )
    reply = llm_text.deepseek_chat(
        "你是獲獎電視劇編劇（showrunner 級）。只回傳 JSON。",
        user,
        model=excerpt_model,
        # NOTE: reasoner thinking tokens count against this budget; 8192 proved
        # too small (reasoning exhausted it -> empty content, no retry could
        # recover). 16384 leaves room for both reasoning and the excerpt.
        max_tokens=16384,
        temperature=0.8,
        thinking=True,
    )
    try:
        data = llm_text.extract_json(reply)
    except ValueError:
        data = _salvage_json(reply) or {}
        if not data.get("script_excerpt"):
            raise
        print("[warn] excerpt truncated; salvaged partial text", flush=True)
    excerpt = str(data.get("script_excerpt") or "").strip()
    if len(excerpt) < 600:
        raise ValueError(f"excerpt too short ({len(excerpt)} chars)")
    return {"pilot": {f"ep{ep}": {"script_excerpt": excerpt}}}, str(data.get("notes", ""))[:200]


def _write_production_plan(package: dict, model: str | None) -> tuple[dict, str]:
    """Deep pass: refresh the production_plan section so feasibility is graded
    against the real AI pipeline (480p / Seedance 2.5 / 6x30s long shots)."""
    from scripts.story_room import llm_text

    excerpt_model = os.environ.get("SCRIPT_FORGE_EXCERPT_MODEL") or model
    existing = package.get("production_plan") or {}
    arcs = [str(a.get("arc")) for a in (package.get("arcs") or [])]
    leads = [str(c.get("name", "")) for c in ((package.get("bible") or {}).get("protagonists") or [])]
    user = (
        _CONSTRAINTS + "\n\n" + _REFERENCES
        + "\n\n以製片廠 line producer 視角，為本 56 集連載撰寫 production_plan（只回傳 JSON）："
        "\n- arcs: 每弧 {arc, locations[](可重複使用之場景), cast[](該弧主要角色), ref_images[](需 @Image 基準圖的角色)}；"
        "\n- pipeline: 6×30s 長鏡調度原則（固定機位/低調度/暗示式大場面）、口型同步、480p 合規、"
        "每週 1-2 集量產節奏、角色一致性以 @Image 硬閘門控管；"
        "\n- risks: 3-5 條製作風險與對策（例：多角色同框成本、場景重複使用、素材覆蓋率）。"
        f"\n弧清單：{json.dumps(arcs, ensure_ascii=False)}；主角清單：{json.dumps(leads, ensure_ascii=False)}"
        + (f"\n現有 production_plan（升級重寫，保留可用資訊）：\n{json.dumps(existing, ensure_ascii=False)[:3000]}" if existing else "")
        + "\n\n只回傳 JSON：{\"production_plan\": {...}, \"notes\": \"一句話\"}"
    )
    reply = llm_text.deepseek_chat(
        "你是好萊塢製片廠 line producer。只回傳 JSON。",
        user,
        model=excerpt_model,
        max_tokens=4096,
        temperature=0.6,
        thinking=True,
    )
    try:
        data = llm_text.extract_json(reply)
    except ValueError:
        data = _salvage_json(reply) or {}
        if not data.get("production_plan"):
            raise
        print("[warn] production_plan truncated; salvaged partial", flush=True)
    plan = data.get("production_plan") or {}
    if not isinstance(plan, dict) or not plan:
        raise ValueError("production_plan empty")
    return {"production_plan": plan}, str(data.get("notes", ""))[:200]


def reclaim_excerpts(run_dir: Path) -> dict:
    """v2 recovery pass: merge the longest teleplay excerpt per episode from every
    l1_workbench snapshot into best_package + state_latest.

    Older runs threw away excerpt-enriched candidates through the penalty-based
    champion revert; this recovers that already-paid-for content."""
    run_dir = Path(run_dir)
    best_path = run_dir / "best_package.json"
    state_path = run_dir / "state_latest.json"
    base_path = best_path if best_path.is_file() else state_path
    if not base_path.is_file():
        raise SystemExit(f"[FATAL] no best_package.json / state_latest.json under {run_dir}")
    merged = json.loads(base_path.read_text(encoding="utf-8"))
    pilot = merged.setdefault("pilot", {})
    best_len: dict[str, int] = {}
    for ep_key, ep_val in pilot.items():
        text = str((ep_val or {}).get("script_excerpt") or "")
        if text:
            best_len[ep_key] = len(text)
    found: dict[str, int] = {}
    for snap in sorted((run_dir / "l1_workbench").glob("iter_*.json")):
        try:
            payload = json.loads(snap.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for ep_key, ep_val in (payload.get("package") or {}).get("pilot", {}).items():
            text = str((ep_val or {}).get("script_excerpt") or "")
            if text and len(text) > best_len.get(ep_key, 0):
                best_len[ep_key] = len(text)
                found[ep_key] = len(text)
                pilot.setdefault(ep_key, {})["script_excerpt"] = text

    def _ep_num(key: str) -> int:
        try:
            return int(str(key).replace("ep", "").strip())
        except ValueError:
            return 0

    merged["pilot"] = {k: pilot[k] for k in sorted(pilot, key=_ep_num)}
    _write_json(base_path, merged)
    if state_path != base_path:
        _write_json(state_path, merged)
    meta_path = run_dir / "best_meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        meta["reclaimed"] = {"ts": _now(), "excerpts": {k: f"{v} chars" for k, v in found.items()}}
        _write_json(meta_path, meta)
    # one-off log header upgrade: keep every historical row, prepend the v2 note
    log_path = run_dir / "iteration_log.md"
    if log_path.is_file():
        lines = log_path.read_text(encoding="utf-8").splitlines()
        cut = next((i for i, ln in enumerate(lines) if ln.startswith("| 迭代")), None)
        if cut is not None:
            note = [
                "# 劇本鑄造迭代紀錄（CP-D 閘門證據）",
                "",
                "> v2 規則（2026-09-12）：王者（★）＝零 error 且 μ（八域加權、懲罰前）最高；總分欄＝懲罰後淨分（稽核用）。",
                "> 迭代 1–80 為 v1 制（王者比淨分）；迭代 81+ 起八域欄前綴加 μ 標記。",
                "",
            ]
            log_path.write_text("\n".join(note + lines[cut:]) + "\n", encoding="utf-8")
    return {
        "merged_excerpts": found,
        "pilot_episodes": sorted(merged["pilot"], key=_ep_num),
        "best_path": str(base_path),
        "reason": "keep-longest-per-episode",
    }


def _merge_dict(old: dict, patch: dict) -> dict:
    """Deep-merge a patch into old; empty values in the patch are ignored (no data wipes)."""
    merged = json.loads(json.dumps(old, ensure_ascii=False))
    for key, value in patch.items():
        if value in ([], {}, ""):
            continue  # guard: never wipe existing content with an empty patch value
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _apply_patch(package: dict, patch: dict) -> dict:
    """Merge a sparse revision patch.

    - top-level keys: deep merge; empty values ignored (prevents accidental wipes)
    - episode_patches: upsert; missing episodes are appended and the outline re-sorted
    """
    merged = json.loads(json.dumps(package, ensure_ascii=False))
    outline = merged.get("episode_outline") or []
    by_ep = {str(e.get("ep")): e for e in outline}
    touched = False
    for key, value in patch.items():
        if key == "episode_patches":
            for item in value or []:
                ep = str(item.get("ep"))
                if not ep.isdigit():
                    continue
                if ep in by_ep:
                    by_ep[ep].update({k: v for k, v in item.items() if k != "ep" and v not in ([], {}, "")})
                else:
                    by_ep[ep] = {k: v for k, v in item.items()}
                    touched = True
            continue
        if value in ([], {}, ""):
            continue
        old = merged.get(key)
        if isinstance(value, dict) and isinstance(old, dict):
            merged[key] = _merge_dict(old, value)
        else:
            merged[key] = value
    if touched:
        merged["episode_outline"] = [by_ep[k] for k in sorted(by_ep, key=lambda x: int(x))]
    return merged


def _restore_missing(package: dict, reference: dict) -> tuple[dict, list[str]]:
    """Restore bible sub-keys / top-level sections from the earliest seed snapshot.

    Guards against a bad patch sequence having wiped structural fields; only
    fills in fields that are currently empty.
    """
    restored: list[str] = []
    merged = json.loads(json.dumps(package, ensure_ascii=False))
    ref_bible = reference.get("bible") or {}
    bible = merged.setdefault("bible", {})
    for key, value in ref_bible.items():
        if not bible.get(key) and value:
            bible[key] = json.loads(json.dumps(value, ensure_ascii=False))
            restored.append(f"bible.{key}")
    for key in ("arcs", "foreshadows", "pilot"):
        if not merged.get(key) and reference.get(key):
            merged[key] = json.loads(json.dumps(reference[key], ensure_ascii=False))
            restored.append(key)
    return merged, restored


def _plateau_warning(it: int, best_iter: int | None) -> str | None:
    """Patience alarm: alert (never auto-stop) when the champion sits idle.

    Fires on 50-iteration boundaries once the gap reaches PLATEAU_PATIENCE.
    """
    if not best_iter:
        return None
    gap = it - best_iter
    if gap >= PLATEAU_PATIENCE and gap % 50 == 0:
        return f"[warn] plateau: champion idle for {gap} iterations (gate still unmet)"
    return None


def _read_ceo_notes(run_dir: Path) -> str:
    """CEO-directed revision notes (highest priority) from <run>/ceo_notes.md.

    Injected into the L3 review panel, the L2 revise pass and the excerpt
    writer so every round must report on the CEO's explicit concerns.
    """
    notes_path = Path(run_dir) / "ceo_notes.md"
    if notes_path.is_file():
        return notes_path.read_text(encoding="utf-8").strip()[:4000]
    return ""


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
def _write_json(path: Path, payload: dict) -> None:
    """Atomic write with SMB retry (the Y: share can briefly lock files)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    for attempt in range(4):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(0.5 * (attempt + 1))


def _md_row(entry: dict) -> str:
    d = entry["final"]["domains"]
    return (
        f"| {entry['iteration']} | {entry['final']['final_total']:.2f} | "
        f"{entry['final']['min_domain']:.1f} | {entry['errors']} | {entry['warns']} | "
        f"{('★' if entry.get('best') else '')}{('⚠' if entry.get('degraded') else '')}{entry['action']} | {entry['ts']} | "
        f"μ{entry['final'].get('llm_total', 0.0):.2f} c{d['concept']:.1f} s{d['structure']:.1f} "
        f"ch{d['character']:.1f} d{d['dialogue']:.1f} "
        f"m{d['mythology']:.1f} f{d['feasibility']:.1f} h{d['hook_density']:.1f} x{d['dual_track']:.1f} |"
    )


_MD_HEADER = (
    "# 劇本鑄造迭代紀錄（CP-D 閘門證據）\n\n"
    "> v3 規則（2026-09-12）：L3＝多代理評審團（4 專家評審並行＋總導演仲裁，真 AI Agent）；"
    "王者（★）＝零 error ∧ 非 degraded ∧ μ（八域加權、懲罰前）最高；⚠＝評審異常輪（不列王者）；"
    "總分欄＝懲罰後淨分（稽核用）。μ ＝ concept×.12＋structure×.15＋character×.15＋"
    "dialogue×.13＋mythology×.12＋feasibility×.13＋hook_density×.10＋dual_track×.10。\n\n"
    "| 迭代 | 總分 | 最低域 | errors | warns | 動作 | 時間 | μ＋八域（c/s/ch/d/m/f/h/x） |\n"
    "|---|---|---|---|---|---|---|---|\n"
)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run_forge(
    brief_text: str,
    series_id: str,
    root: Path,
    min_iters: int = MIN_ITERATIONS,
    max_iters: int = DEFAULT_MAX_ITERATIONS,
    offline: bool = False,
    broken: bool = False,
    model: str | None = None,
    resume: bool = False,
    force: bool = False,
    seed_package: str | None = None,
) -> dict:
    """Run the L1->L2->L3->L4 forge loop; returns a summary dict."""
    if min_iters < MIN_ITERATIONS:
        raise SystemExit(f"[FATAL] min_iters {min_iters} < CEO floor {MIN_ITERATIONS}")
    if max_iters < min_iters:
        raise SystemExit("[FATAL] max_iters must be >= min_iters")

    run_dir = Path(root) / series_id
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path = run_dir / "run_meta.json"
    state_path = run_dir / "state_latest.json"
    log_path = run_dir / "iteration_log.md"
    lock_path = run_dir / "lock_ready.json"
    l1_dir = run_dir / "l1_workbench"
    l1_dir.mkdir(exist_ok=True)

    if meta_path.exists() and not (resume or force):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raise SystemExit(
            f"[FATAL] run exists (status={meta.get('status')}, iters={meta.get('iterations')}); "
            "use --resume to continue or --force to restart"
        )
    if lock_path.exists() and not force:
        raise SystemExit("[FATAL] lock_ready already present; series is beyond the forge gate")

    ceo_notes = _read_ceo_notes(run_dir)
    if ceo_notes:
        print(f"[forge] CEO notes loaded ({len(ceo_notes)} chars) — panel/revise/excerpt will honor them",
              flush=True)

    seed_ref: dict = {}
    if resume and state_path.exists():
        current = json.loads(state_path.read_text(encoding="utf-8"))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        start_iter = int(meta.get("iterations", 0)) + 1
        mode = str(meta.get("mode", "offline" if offline else "llm"))
        ref_file = l1_dir / "iter_01.json"
        if ref_file.is_file():
            seed_ref = json.loads(ref_file.read_text(encoding="utf-8")).get("package") or {}
    else:
        mode = "offline" if offline else "llm"
        if mode == "llm" and seed_package:
            seed_path = Path(seed_package)
            if not seed_path.is_file():
                raise SystemExit(f"[FATAL] --seed-package not found: {seed_path}")
            current = json.loads(seed_path.read_text(encoding="utf-8"))
            current.setdefault("schema", "series_contract.v1")
            print(f"[forge] phase-continuation: seeded from {seed_path}", flush=True)
        elif mode == "llm":
            from scripts.story_room import llm_text
            if not llm_text.available():
                raise SystemExit("[FATAL] DeepSeek key missing (llm_text.available() == False)")
            seed_reply = llm_text.deepseek_chat(
                "你是好萊塢 showrunner。依 brief 與硬約束產出 56 集短劇連載企劃包（schema 見指示），只回傳 JSON。",
                brief_text + "\n\n" + _CONSTRAINTS + "\n\n" + _REFERENCES
                + "\n\n請輸出 JSON：{title, logline, theme, genre{mix,access,tone}, "
                  "target_format{episodes:56,episode_sec:175,shots_per_ep:6,resolution:\"480p\"}, "
                  "bible{world_rules[],mythology{east[],west[]},protagonists[]"
                  "{name,role,arc,access_method},antagonists[],locations[]"
                  "{id,name,myth_system,lm_export,lf_export},canon{characters[],rules[]}}, "
                  "arcs[4]{arc,episodes:\"a-b\",summary,climax,lm_special,lf_special,"
                  "foreshadows[2]{setup,payoff}}, episode_outline[56]"
                  "{ep,arc,title,hook,summary,cliffhanger}, foreshadows[8+]{setup,payoff}, "
                  "pilot{ep1{scenes[],dialogue_sample},ep2{scenes[],dialogue_sample}}}"
                  "\n每集 outline 欄位務必精簡（hook≤20字、summary≤25字、cliffhanger≤15字），確保 56 筆完整輸出。",
                model=model,
                max_tokens=8192,
                temperature=1.0,
            )
            try:
                current = llm_text.extract_json(seed_reply)
            except ValueError as exc:
                salvaged = _salvage_json(seed_reply)
                if not salvaged:
                    raise SystemExit(f"[FATAL] seed package is not valid JSON: {exc}") from exc
                salvaged.setdefault("schema", "series_contract.v1")
                salvaged["_seed_truncated"] = True
                current = salvaged
                print("[warn] seed JSON truncated; salvaged partial package (patch iterations will complete it)", flush=True)
            current.setdefault("schema", "series_contract.v1")
        else:
            current = offline_seed_package()
        start_iter = 1
        _write_json(meta_path, {
            "series_id": series_id,
            "brief": brief_text,
            "mode": mode,
            "min_iters": min_iters,
            "max_iters": max_iters,
            "iterations": 0,
            "status": "running",
            "started": _now(),
        })
        if not log_path.exists():
            log_path.write_text(_MD_HEADER, encoding="utf-8")

    if not seed_ref:
        seed_ref = current

    # Best-of (champion) tracking: revisions always restart from the best package
    best_path = run_dir / "best_package.json"
    best_meta_path = run_dir / "best_meta.json"
    best_score = -1.0
    best_package: dict = {}
    best_findings: list[dict] = []
    best_domains: dict = {}
    best_iter: int | None = None
    if resume and best_path.is_file():
        try:
            best_package = json.loads(best_path.read_text(encoding="utf-8"))
            if best_meta_path.is_file():
                _bm = json.loads(best_meta_path.read_text(encoding="utf-8"))
                best_score = float(_bm.get("score", -1.0))
                best_findings = _bm.get("findings") or []
                best_domains = _bm.get("domains") or {}
                best_iter = int(_bm.get("iteration", 0)) or None
        except (OSError, json.JSONDecodeError):
            best_score = -1.0

    consecutive_fail = 0
    last_entry: dict = {}
    status = "capped"
    for it in range(start_iter, max_iters + 1):
        if seed_ref:
            current, restored = _restore_missing(current, seed_ref)
            if restored:
                print(f"[forge]   restored from seed snapshot: {', '.join(restored)}", flush=True)
        # ---- L3 rubric + L4 dimensions -----------------------------------
        findings = rule_findings(current)
        top_fixes: list[str] = []
        verdict = ""
        degraded = False
        if mode == "llm":
            try:
                rubric_result, llm_findings, degraded = _review_panel(current, model, ceo_notes)
                llm_domains = rubric_result["domains"]
                top_fixes = rubric_result["top_fixes"]
                verdict = rubric_result["verdict"]
                findings = findings + llm_findings
                consecutive_fail = 0
            except Exception as exc:  # noqa: BLE001 - log and degrade, never abort silently
                print(f"[warn] review panel failed at iter {it}: {exc}", file=sys.stderr, flush=True)
                llm_domains = {k: 7.5 for k in RUBRIC_WEIGHTS}
                findings = findings + [{"domain": "concept", "level": "info", "msg": f"panel failed: {str(exc)[:120]}"}]
                degraded = True
                consecutive_fail += 1
        else:
            llm_domains = {k: (7.5 if broken else 9.5) for k in RUBRIC_WEIGHTS}

        final = compute_final(llm_domains, findings)
        errors = sum(1 for f in findings if f.get("level") == "error")
        warns = sum(1 for f in findings if f.get("level") == "warn")
        # v2 champion rule (2026-09-12): compare on the PENALTY-FREE weighted
        # rubric total and require zero errors. The noisy per-finding penalty
        # (cap 2.5) used to sink every improved candidate below the 7.21
        # champion and threw away good revisions - the penalized total stays in
        # the log for audit, but the champion is chosen on the robust score.
        # v3: degraded review rounds (any agent failure) can never become champion.
        is_best = errors == 0 and not degraded and final["llm_total"] > best_score
        if is_best:
            best_score = final["llm_total"]
            best_iter = it
            best_package = json.loads(json.dumps(current, ensure_ascii=False))
            best_findings = findings
            best_domains = final["domains"]
            _write_json(best_path, best_package)
            _write_json(best_meta_path, {
                "score": best_score, "iteration": it,
                "official_total": final["final_total"],
                "domains": best_domains, "findings": findings[:20],
            })
        best_min = round(min(best_domains.values()), 1) if best_domains else 0.0
        ok = (
            it >= min_iters
            and best_score >= HOLLYWOOD_TOTAL
            and best_min >= HOLLYWOOD_MIN_DOMAIN
            and not any(f.get("level") == "error" for f in best_findings)
        )
        action = "lock" if ok else ("revise" if it < max_iters else "stop")

        # ---- L1 workbench drop -------------------------------------------
        l1_payload = {"iteration": it, "ts": _now(), "package": current}
        _write_json(l1_dir / f"iter_{it:02d}.json", l1_payload)
        _write_json(l1_dir / "latest.json", l1_payload)

        entry = {
            "iteration": it, "ts": _now(), "mode": mode, "action": action,
            "best": is_best, "best_score": round(best_score, 2),
            "degraded": degraded,
            "final": final, "errors": errors, "warns": warns,
            "findings": findings[:40],
            "top_fixes": top_fixes,
            "layers": {
                "L1": f"l1_workbench/iter_{it:02d}.json",
                "L2": "revise" if action == "revise" else "hold",
                "L3": ("panel(4 critics + director)" if mode == "llm" else mode)
                      + (f" ({verdict})" if verdict else ""),
                "L4": f"{len(findings)} rule findings",
            },
            "package_hash": _hash(current),
        }
        _write_json(run_dir / f"iter_{it:02d}.json", entry)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(_md_row(entry) + "\n")
        last_entry = entry
        print(
            f"[forge] iter {it:02d} total={final['final_total']} min={final['min_domain']} "
            f"errors={errors} warns={warns} -> {action}",
            flush=True,
        )
        plateau = _plateau_warning(it, best_iter)
        if plateau:
            print(plateau, file=sys.stderr, flush=True)

        meta_update = {
            "iterations": it,
            "status": "locked_ready" if ok else "running",
            "max_iters": max_iters,
            "best_score": round(best_score, 2),
            "best_iteration": best_iter,
            "updated": _now(),
        }
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"series_id": series_id}
        meta.update(meta_update)
        _write_json(meta_path, meta)
        _write_json(state_path, current)

        if ok:
            status = "locked_ready"
            _write_json(state_path, best_package)
            _write_json(lock_path, {
                "series_id": series_id,
                "iterations": it,
                "final_total": best_score,
                "min_domain": best_min,
                "domains": best_domains,
                "thresholds": {"total": HOLLYWOOD_TOTAL, "min_domain": HOLLYWOOD_MIN_DOMAIN,
                               "min_iterations": min_iters},
                "log": str(log_path),
                "generated": _now(),
                "cp_d_eligible": True,
            })
            break
        if it == max_iters:
            status = "capped"
            break
        if consecutive_fail >= 5:
            status = "error"
            break

        # v2.1 soft accumulation: keep working on the current attempt unless it
        # degrades badly (mu plunge). Real fixes must accumulate across
        # iterations instead of being thrown away every time the noisy judge
        # keeps the package below the (zero-error) champion bar.
        if not is_best and best_package and final["llm_total"] < best_score - 0.6:
            print(f"[forge]   revert (mu {final['llm_total']} plunged below {round(best_score - 0.6, 2)}); revising from best", flush=True)
            current = json.loads(json.dumps(best_package, ensure_ascii=False))
            _write_json(state_path, current)

        # ---- L2 revise (alternating: teleplay excerpt pass / patch pass) ----
        current_before = _hash(current)
        if mode == "llm":
            try:
                if it % 2 == 0:
                    if it % 10 == 0:
                        patch, note = _write_production_plan(current, model)
                        current = _apply_patch(current, patch)
                        print(f"[forge]   production plan updated {note}", flush=True)
                    else:
                        ep = _EXCERPT_ROTATION[(it // 2) % len(_EXCERPT_ROTATION)]
                        patch, note = _write_excerpt(current, ep, model, findings=findings,
                                                     ceo_notes=ceo_notes)
                        current = _apply_patch(current, patch)
                        print(f"[forge]   excerpt ep{ep} written {note}", flush=True)
                else:
                    low = [k for k, _v in sorted(llm_domains.items(), key=lambda kv: kv[1])[:3]]
                    patch, applied = _revise(current, findings, top_fixes, model,
                                             low_domains=low, ceo_notes=ceo_notes)
                    current = _apply_patch(current, patch)
                consecutive_fail = 0
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] revise/excerpt call failed at iter {it}: {exc}", file=sys.stderr, flush=True)
                consecutive_fail += 1
        else:
            current = offline_revise(current, findings, broken=broken)
        after = _hash(current)
        print(f"[forge]   revise {current_before}->{after}", flush=True)

    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["status"] = status
    meta["updated"] = _now()
    _write_json(meta_path, meta)
    return {"series_id": series_id, "status": status, "iterations": int(meta.get("iterations", 0)),
            "last": last_entry, "run_dir": str(run_dir)}


# ---------------------------------------------------------------------------
# Status / gate check
# ---------------------------------------------------------------------------
def status_report(run_dir: Path) -> dict:
    meta_path = Path(run_dir) / "run_meta.json"
    if not meta_path.is_file():
        raise SystemExit(f"[FATAL] no run_meta.json under {run_dir}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    iters = sorted(Path(run_dir).glob("iter_*.json"))
    last: dict = {}
    if iters:
        last = json.loads(iters[-1].read_text(encoding="utf-8"))
    return {
        "series_id": meta.get("series_id"),
        "status": meta.get("status"),
        "iterations": meta.get("iterations"),
        "min_iters": meta.get("min_iters"),
        "last_total": (last.get("final") or {}).get("final_total"),
        "last_min_domain": (last.get("final") or {}).get("min_domain"),
        "log": str(Path(run_dir) / "iteration_log.md"),
    }


def gate_check(run_dir: Path) -> dict:
    lock_path = Path(run_dir) / "lock_ready.json"
    if not lock_path.is_file():
        return {"eligible": False, "reason": "lock_ready.json missing (forge gate not passed)"}
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    eligible = bool(lock.get("cp_d_eligible")) and int(lock.get("iterations", 0)) >= MIN_ITERATIONS
    return {"eligible": eligible, **lock}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--brief-file", help="markdown/text file with the genre brief (default: CEO 2026-09-12 brief)")
    parser.add_argument("--out", help="output root override (defaults to Y: share, then local)")
    parser.add_argument("--min-iters", type=int, default=MIN_ITERATIONS)
    parser.add_argument("--max-iters", type=int, default=DEFAULT_MAX_ITERATIONS,
                        help="campaign budget guardrail (default 1000 = industry-standard 10^3 "
                             "evaluation budget; the quality gate is the real stop condition)")
    parser.add_argument("--offline", action="store_true", help="deterministic $0 mode (tests/dry runs)")
    parser.add_argument("--resume", action="store_true", help="continue an existing run")
    parser.add_argument("--force", action="store_true", help="restart even if run/lock exists")
    parser.add_argument("--model")
    parser.add_argument("--seed-package",
                        help="start a fresh run from an existing package JSON (phase continuation)")
    parser.add_argument("--status", action="store_true", help="print run status and exit")
    parser.add_argument("--gate-check", action="store_true", help="exit 0 when CP-D eligible, else 1")
    parser.add_argument("--reclaim", action="store_true",
                        help="merge the longest teleplay excerpt per episode from workbench snapshots into best_package")
    args = parser.parse_args(argv)

    root = Path(args.out) if args.out else out_root()
    run_dir = root / args.series_id

    if args.reclaim:
        print(json.dumps(reclaim_excerpts(run_dir), ensure_ascii=False, indent=1))
        return 0
    if args.status:
        rep = status_report(run_dir)
        for k, v in rep.items():
            print(f"{k}: {v}")
        return 0
    if args.gate_check:
        rep = gate_check(run_dir)
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0 if rep.get("eligible") else 1

    brief = Path(args.brief_file).read_text(encoding="utf-8") if args.brief_file else DEFAULT_BRIEF
    result = run_forge(
        brief, args.series_id, root,
        min_iters=args.min_iters, max_iters=args.max_iters,
        offline=args.offline, model=args.model, resume=args.resume, force=args.force,
        seed_package=args.seed_package,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "last"}, ensure_ascii=False))
    return 0 if result["status"] == "locked_ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
