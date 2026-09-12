"""Adversarial story loop: Writer -> Critic (find holes) -> Director (decide).

P0 core of Story Room v3. Offline mode is deterministic and API-free (template
writer + rule-based critique) so the loop is testable for $0. Live mode uses the
DeepSeek text channel (llm_text) - still zero video generation.
"""
from __future__ import annotations

from . import critic_dims, llm_text
from .beats import build_scaffold
from .diversity import StructurePlan
from .hooks import canonical_opening_rules, get_hook
from .mv_strategy import apply_music_world_strategy
from .twists import get_twist

RUBRIC_WEIGHTS: dict[str, float] = {
    "hook": 0.20,
    "logic": 0.20,
    "motivation": 0.15,
    "pacing": 0.15,
    "feasibility": 0.20,
    "foreshadow": 0.10,
}
_SEVERITY_COST = {"error": 3.0, "warn": 1.5, "info": 0.5}


def template_story(topic: str, plan: StructurePlan, golden: dict | None = None) -> dict:
    """Deterministic offline story built from the structure plan."""
    hook, twist = get_hook(plan.hook_id), get_twist(plan.twist_id)
    openings = canonical_opening_rules(topic)
    sheet = build_scaffold(topic, target_sec=175.0, hook=hook.desc)
    beats = [{"index": b.index, "act": b.act, "name": b.name, "intent": b.intent} for b in sheet.beats]
    acts = [
        {"act": a.index, "title": t, "synopsis": a.synopsis}
        for a, t in zip(
            sheet.acts,
            (f"第一幕・{plan.arc}之始", f"第二幕・{twist.name}暗流", f"第三幕・{plan.ending}"),
        )
    ]
    foreshadows = [{
        "setup": f"Act1：{twist.requirement}",
        "payoff": f"Act3：{twist.name} 揭示——{twist.desc}",
    }]
    if golden:
        foreshadows.append({"setup": "Act1：金樣本式物件埋設", "payoff": "Act3：情感回收"})
    shots = [
        {"no": i + 1, "title": f"鏡{i + 1}",
         "desc": sheet.beats[min(i, len(sheet.beats) - 1)].intent,
         "duration_sec": 29.2 if i < 5 else 29.0}
        for i in range(6)
    ]
    story = {
        "topic": topic, "variant": plan.variant, "structure": plan.to_dict(),
        "title": f"{topic}（變體{plan.variant}）",
        "logline": f"以「{openings[0]['name']}」與「{openings[1]['name']}」建立跨文化視角，再用「{hook.name}」開場、「{twist.name}」收束：{topic}的三幕視覺敘事。",
        "hook": f"{openings[0]['name']}：{openings[0]['desc']}；{openings[1]['name']}：{openings[1]['desc']}；{hook.name}：{hook.desc}",
        "opening_frame": openings,
        "theme": f"{plan.arc} × {plan.ending}（視角：{plan.pov}）",
        "acts": acts, "beats": beats, "foreshadows": foreshadows, "shots": shots,
        "characters": [],
        "source": "offline_template",
    }
    return apply_music_world_strategy(story, topic, plan.variant)


_SYS = (
    "你是頂級音樂世界觀 MV 編劇。鐵律：①零對白、零畫面文字、沒有固定主角，世界本身就是主角 "
    "③10–12 個節拍 ④6 顆鏡頭、每鏡 4–30 秒、總長 175 秒 "
    "⑤懸疑靠環境伏筆（2–3 條 setup→payoff）⑥固定年代、建築、色盤、天候與三個地標，"
    "讓地標跨鏡頭重現；人物只可作無名遠景、背影或剪影，不可有臉部近景 "
    "⑦畫面依歌曲段落與節拍剪輯，不要求生成模型製作音訊 ⑧只回傳 JSON，不要其他文字。"
)


def llm_story(topic: str, plan: StructurePlan, golden_snippet: str | None = None,
              model: str | None = None) -> dict:
    """Live writer call (DeepSeek). Returns a normalized story dict."""
    golden_txt = f"\n金樣本節錄（風格錨）：\n{golden_snippet}" if golden_snippet else ""
    user = (
        f"題材：{topic}\n結構方案：{plan.to_dict()}\n"
        "製作模式：Lofi／Light Music 世界觀 MV；本地 Wan 2.1 為主；不可設計固定角色。\n"
        "請輸出 JSON：{title, logline, hook, theme, "
        "opening_frame:[{name,desc,cue}], "
        "acts:[3]{title,synopsis}, beats:[10-12]{index,act,name,intent}, "
        "foreshadows:[2-3]{setup,payoff}, shots:[6]{no,title,desc,duration_sec}}"
        f"{golden_txt}"
    )
    data = llm_text.extract_json(llm_text.deepseek_chat(_SYS, user, model=model))
    data.update({"topic": topic, "variant": plan.variant,
                 "structure": plan.to_dict(), "source": "deepseek"})
    return apply_music_world_strategy(data, topic, plan.variant)


def critique(story: dict, use_llm: bool = False, model: str | None = None) -> list[dict]:
    """Critic: rule dimensions first, optional LLM deep pass."""
    findings = list(critic_dims.review_story(story)["findings"])
    for key, domain, level in (("logline", "motivation", "error"),
                               ("theme", "motivation", "warn"),
                               ("hook", "hook", "error")):
        if not str(story.get(key, "")).strip():
            findings.append({"domain": domain, "level": level, "msg": f"{key} 缺失"})
    if len(story.get("beats", [])) < 10:
        findings.append({"domain": "pacing", "level": "warn",
                         "msg": f"節拍數 {len(story.get('beats', []))} < 10"})
    if use_llm and llm_text.available():
        try:
            fb = llm_text.extract_json(llm_text.deepseek_chat(
                "你是嚴格的劇本審稿人。只回傳 JSON：{\"findings\":[{\"domain\",\"level\",\"msg\"}]}",
                f"審查以下劇本，找出邏輯漏洞、懸疑薄弱點、伏筆未回收：\n{story}", model=model))
            for f in fb.get("findings", []):
                findings.append({"domain": f.get("domain", "logic"),
                                 "level": f.get("level", "warn"),
                                 "msg": str(f.get("msg", ""))[:300]})
        except Exception as exc:  # noqa: BLE001 - surface, do not hide
            findings.append({"domain": "logic", "level": "info",
                             "msg": f"LLM critique unavailable: {exc}"})
    return findings


def score(story: dict, findings: list[dict]) -> dict:
    """Weighted rubric score (1-10); hook/logic/pacing/foreshadow feed domains."""
    dom = {d: 9.0 for d in RUBRIC_WEIGHTS}
    for f in findings:
        d = f.get("domain") if f.get("domain") in dom else "logic"
        dom[d] = max(1.0, dom[d] - _SEVERITY_COST.get(f.get("level", "warn"), 1.0))
    total = round(sum(dom[d] * w for d, w in RUBRIC_WEIGHTS.items()), 1)
    return {"domains": {k: round(v, 1) for k, v in dom.items()}, "total": total}


def revise(story: dict, findings: list[dict], use_llm: bool = False,
           model: str | None = None) -> dict:
    """Director: LLM rewrite when live; deterministic patch otherwise."""
    if use_llm and llm_text.available():
        try:
            fixed = llm_text.extract_json(llm_text.deepseek_chat(
                "你是編劇，請依審稿意見修訂劇本，維持原 JSON 結構並補滿所有欄位。只回傳 JSON。",
                f"原稿：{story}\n審稿意見：{findings}", model=model))
            fixed.update({"topic": story.get("topic"), "variant": story.get("variant"),
                          "structure": story.get("structure"),
                          "source": str(story.get("source", "")) + "+rev"})
            return fixed
        except Exception:  # noqa: BLE001 - fall through to offline patch
            pass
    patched = dict(story)
    patched["director_note"] = "; ".join(f"[{f['domain']}] {f['msg']}" for f in findings)[:500]
    if not str(patched.get("theme", "")).strip():
        patched["theme"] = "以物件敘事承載情感（自動補位）"
    if not str(patched.get("hook", "")).strip():
        patched["hook"] = "異常物開場（自動補位）"
    patched["source"] = str(story.get("source", "")) + "+patch"
    return patched


def run_adversarial(topic: str, plan: StructurePlan,
                    golden: dict | None = None, golden_snippet: str | None = None,
                    offline: bool = True, max_rounds: int = 3, threshold: float = 7.0,
                    model: str | None = None) -> dict:
    """Run the full Writer->Critic->Director loop; returns story + scores + log."""
    live = (not offline) and llm_text.available()
    if live:
        try:
            story = llm_story(topic, plan, golden_snippet=golden_snippet, model=model)
        except Exception as exc:  # noqa: BLE001 - degrade, never abort the batch
            story = template_story(topic, plan, golden=golden)
            story["source"] = f"offline_fallback: {str(exc)[:100]}"
            live = False
    else:
        story = template_story(topic, plan, golden=golden)
    story = apply_music_world_strategy(story, topic, plan.variant)
    log: list[dict] = []
    sc: dict = {"domains": {}, "total": 0.0}
    for rnd in range(1, max_rounds + 1):
        findings = critique(story, use_llm=live, model=model)
        sc = score(story, findings)
        log.append({"round": rnd, "score": sc["total"], "findings": len(findings),
                    "errors": sum(1 for f in findings if f.get("level") == "error")})
        if sc["total"] >= threshold or rnd == max_rounds:
            break
        story = revise(story, findings, use_llm=live, model=model)
        story = apply_music_world_strategy(story, topic, plan.variant)
    return {"story": story, "score": sc, "log": log,
            "pass": sc["total"] >= threshold, "mode": "llm" if live else "offline"}
