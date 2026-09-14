#!/usr/bin/env python3
"""CP-D world-proposal engine: weekly intake images -> ranked world drafts.

Pipeline
  1. Read this week's intake manifest (images downloaded by stock_search.py).
  2. Optional vision analysis (Gemini Flash) of a spread of images.
  3. Build 3-5 candidate world specs:
     - images matching an existing world  -> deterministic derivative mutants
     - generic images                     -> new worlds clustered by vision tags
  4. Rank with world_library.novelty / propose_batch (never commits).
  5. Write the CP-D review pack and push a Telegram notification:
       <intake_root>/cp_d/<week>/proposal.json   (machine-readable)
       <intake_root>/cp_d/<week>/proposal.md     (CEO review copy)
       <intake_root>/cp_d/<week>/veo_prompts.txt (VEO fallback prompts)

Hard rule: this engine only PROPOSES. World-library commits happen later,
exclusively after the CEO approves at CP-D (world_library.commit()).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import date, datetime
from itertools import zip_longest
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

import requests  # noqa: E402

from scripts.reference_intake.daily_intake import (  # noqa: E402
    INTAKE_ROOT,
    load_env_files,
    notify,
)


def week_dir() -> Path:
    """Compat shim (2026-09-14): the fixed inbox replaces weekly folders; the
    proposal flow is PAUSED pending redesign around VEO_download/Approved_material."""
    return INTAKE_ROOT
from scripts.story_room import world_library as wl  # noqa: E402

CP_D_ROOT = INTAKE_ROOT.parent / "cp_d"

VISION_MODEL = "gemini-2.5-flash"
VISION_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{VISION_MODEL}:generateContent"
)
GLM_MODEL = "glm-4v-flash"
GLM_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
VISION_PROMPT = (
    "你是 MV 世界觀美術總監。分析這張參考圖，只輸出一個 JSON 物件，欄位："
    "scene_type(繁體中文,場景類型)、subjects(繁體中文,主體)、"
    "palette(3 個 #hex 色碼)、mood(繁體中文,情緒)、light(繁體中文,光線)、"
    "time_of_day(繁體中文)、weather(繁體中文,天候)、"
    "tags_en(5 個英文標籤,小寫單詞)。不要輸出 JSON 以外的任何文字。"
)
NOVELTY_MIN = 0.25
DEFAULT_N = 4
DEFAULT_MAX_IMAGES = 8
TAG_MERGE_THRESHOLD = 0.34  # Jaccard overlap for greedy tag clustering

REVIEW_TEMPLATE = """<!doctype html>
<html lang="zh-Hant"><meta charset="utf-8">
<title>CP-D 世界草案 — {week}</title>
<style>
 body {{ font-family: -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif; margin: 24px; background:#101014; color:#eee; }}
 h1 {{ font-size: 22px; }} h2 {{ font-size: 18px; margin-top: 8px; }} small {{ color:#9aa; font-weight: normal; }}
 section {{ border:1px solid #333; border-radius:12px; padding:16px; margin:18px 0; background:#181820; }}
 .imgs {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap:10px; }}
 .imgs img {{ width:100%; border-radius:8px; display:block; }}
 figcaption {{ font-size:12px; color:#889; margin-top:4px; }}
 .sw {{ display:inline-block; width:28px; height:28px; border-radius:6px; margin-right:6px; border:1px solid #444; vertical-align:middle; }}
 .meta {{ color:#bbd; font-size:13px; }}
 .char {{ background:#1d2330; border-left:3px solid #6ab; padding:8px 10px; border-radius:6px; font-size:13px; }}
 pre {{ white-space:pre-wrap; background:#0c0c10; padding:10px; border-radius:8px; font-size:12px; }}
 summary {{ cursor:pointer; color:#8bd; font-size:13px; }}
</style>
<body>
<h1>CP-D 世界草案審核 — {week}</h1>
<p class="meta">看圖判斷即可；「VEO 備援提示詞」用不到可以不用展開。批准回覆 <b>Approve 世界名</b>；退回回覆 <b>Reject 世界名 原因</b>。</p>
{cards}
</body></html>
"""


# --------------------------------------------------------------------------
# Vision analysis
# --------------------------------------------------------------------------
def _parse_vision_text(text: str) -> dict[str, Any]:
    """Parse model JSON output, tolerating accidental code fences."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
    return json.loads(text)


def vision_analyze_image_gemini(path: Path, api_key: str, timeout: int = 60) -> dict[str, Any]:
    """Analyze one image with Gemini Flash; raises RuntimeError with the API body."""
    payload = {
        "contents": [{
            "parts": [
                {"text": VISION_PROMPT},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                    }
                },
            ]
        }],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
    }
    response = requests.post(
        VISION_ENDPOINT,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(f"gemini http {response.status_code}: {response.text[:200]}")
    return _parse_vision_text(response.json()["candidates"][0]["content"]["parts"][0]["text"])


def vision_analyze_image_glm(path: Path, api_key: str, timeout: int = 90) -> dict[str, Any]:
    """Analyze one image with GLM-4V-Flash (Zhipu AI free tier)."""
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": GLM_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
        "temperature": 0.4,
    }
    response = requests.post(
        GLM_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(f"glm http {response.status_code}: {response.text[:200]}")
    return _parse_vision_text(response.json()["choices"][0]["message"]["content"])


def pick_spread(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Round-robin across labels so every theme is represented in the analysis."""
    by_label: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_label.setdefault(item.get("label", "?"), []).append(item)
    interleaved: list[dict[str, Any]] = []
    for row in zip_longest(*by_label.values()):
        interleaved.extend(item for item in row if item)
    return interleaved[:limit]


def analyze_week(week_path: Path, manifest: dict[str, Any], max_images: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (analyses, vision_meta) using the provider chain Gemini -> GLM-4V."""
    providers: list[tuple[str, str, Any]] = []
    gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    glm_key = (os.getenv("GLM_4V_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
    if gemini_key:
        providers.append((VISION_MODEL, gemini_key, vision_analyze_image_gemini))
    if glm_key:
        providers.append((GLM_MODEL, glm_key, vision_analyze_image_glm))
    meta: dict[str, Any] = {
        "enabled": bool(providers),
        "chain": [name for name, _key, _fn in providers],
        "provider": None,
        "images_analyzed": 0,
        "warnings": [],
    }
    if not providers:
        meta["warnings"].append("no vision API key available: running in degraded (metadata-only) mode")
        return [], meta
    analyses: list[dict[str, Any]] = []
    for item in pick_spread(list(manifest.get("items") or []), max_images):
        image_path = week_path / item.get("file", "")
        if not image_path.is_file():
            meta["warnings"].append(f"missing file: {item.get('file')}")
            continue
        record = None
        for name, key, fn in list(providers):
            try:
                record = fn(image_path, key)
                meta["provider"] = name
                break
            except Exception as exc:  # noqa: BLE001 - one bad image never kills the run
                meta["warnings"].append(f"{name} failed for {item.get('file')}: {exc}")
                lowered = str(exc).lower()
                if "http 400" in lowered or "http 401" in lowered or "invalid" in lowered:
                    providers = [p for p in providers if p[0] != name]
                    meta["warnings"].append(f"{name} disabled for the rest of this run")
        if record is None:
            continue
        record.update({"file": item.get("file"), "label": item.get("label"), "query": item.get("query")})
        analyses.append(record)
    meta["images_analyzed"] = len(analyses)
    return analyses, meta


# --------------------------------------------------------------------------
# Candidate construction
# --------------------------------------------------------------------------
def _cluster_by_tags(analyses: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Greedy Jaccard clustering over tags_en; largest clusters first."""
    clusters: list[list[dict[str, Any]]] = []
    for record in analyses:
        tags = {str(t).lower() for t in (record.get("tags_en") or [])}
        placed = False
        for cluster in clusters:
            other: set[str] = set()
            for member in cluster:
                other |= {str(t).lower() for t in (member.get("tags_en") or [])}
            if tags and other and len(tags & other) / len(tags | other) >= TAG_MERGE_THRESHOLD:
                cluster.append(record)
                placed = True
                break
        if not placed:
            clusters.append([record])
    return sorted(clusters, key=len, reverse=True)


def _mode(values: list[str], fallback: str) -> str:
    freq: dict[str, int] = {}
    for value in values:
        if value:
            freq[value] = freq.get(value, 0) + 1
    return max(freq, key=freq.get) if freq else fallback


def _top_palette(analyses: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for record in analyses:
        for color in record.get("palette") or []:
            if isinstance(color, str) and color.startswith("#") and color not in seen:
                seen.append(color)
    return (seen + ["#101014", "#8899aa", "#e8d8c0"])[:3]


def _slug(name: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    return slug or "world"


def _character_line(channel: str) -> str:
    """Channel casting rule: lofi shows a beauty (the world's face); light_music has no people."""
    if channel == "lofi":
        return (
            "featuring one beautiful young East-Asian woman in her early 20s, natural elegant beauty, "
            "soft cinematic styling, she is the emotional face of the world"
        )
    return "no people in frame - landscape and architecture only"


def _veo_prompt(tags_en: list[str], channel: str) -> str:
    """Channel-aware Veo 3.1 prompt (Ingredients-friendly, MV-safe, 9:16)."""
    uniq = list(dict.fromkeys(t for t in tags_en if t))[:6]
    scene = ", ".join(uniq) if uniq else "atmospheric cinematic scene"
    return (
        f"Cinematic 9:16 music-video frame of {scene}, {_character_line(channel)}, "
        "slow cinematic push-in, moody cinematic lighting, film grain, shallow depth of field, "
        "8-second shot, no dialogue, no text, no watermark, ultra detailed film still"
    )


def _veo_character_spec(channel: str) -> dict[str, Any] | None:
    """Character-casting guidance for Veo 3.1 'Ingredients -> Character reference'."""
    if channel != "lofi":
        return None
    return {
        "casting": "one woman, early 20s, elegant and natural; keep the same person across every shot",
        "flow_usage": (
            "Flow → Ingredients：上傳同一張人物參考圖（正面清晰、自然光）作為角色 ingredient，"
            "再用同一提示詞生成每個鏡頭，即可鎖定跨鏡一致性"
        ),
    }


def new_world_candidate(cluster: list[dict[str, Any]], channel: str) -> dict[str, Any]:
    """Build a fresh world spec from one vision cluster.

    Tags prefer ASCII (English) so names and VEO prompts stay Latin-script;
    when the vision model returns CJK tags only, the English search query is
    used as the fallback source (RCA 2026-09-12).
    """
    tags: list[str] = []
    for record in cluster:
        tags.extend(str(t) for t in (record.get("tags_en") or []))
    ordered = list(dict.fromkeys(t for t in tags if t))
    ascii_tags = [t for t in ordered if re.fullmatch(r"[ -~]+", t)]
    query_words: list[str] = []
    if not ascii_tags:
        joined = " ".join(str(r.get("query") or "") for r in cluster)
        query_words = [w for w in re.split(r"[^A-Za-z]+", joined) if len(w) > 2]
    usable = ascii_tags or query_words or ordered
    dominant = usable[:2] or ["untitled", "dream"]
    base_name = "-".join(word.title() for word in dominant)
    scene = _mode([str(r.get("scene_type") or "") for r in cluster], "未知場景")
    mood = _mode([str(r.get("mood") or "") for r in cluster], "靜謐")
    light = _mode([str(r.get("light") or "") for r in cluster], "柔和光")
    tod = _mode([str(r.get("time_of_day") or "") for r in cluster], "黃昏")
    weather = _mode([str(r.get("weather") or "") for r in cluster], "薄霧")
    anchors = [str(r.get("file")) for r in cluster[:3] if r.get("file")]
    name = unique_name(base_name)
    return {
        "name": name,
        "channel": channel,
        "era": f"{tod}的{scene}",
        "architecture": "、".join(dict.fromkeys(str(r.get("scene_type") or "") for r in cluster if r.get("scene_type")))[:120] or f"以{scene}為核心的建築語彙",
        "palette": _top_palette(cluster),
        "weather": f"{weather}、{light}",
        "landmarks": [f"{scene}的主景", f"{tod}光線下的地標", f"{mood}角落"][:3],
        "figures": "beauty" if channel == "lofi" else "none",
        "chronicle": (
            f"（CP-D 草案，待 CEO 核准）在{tod}的{scene}裡，{mood}是這個世界的基本音。"
            f"參考素材顯示{weather}與{light}；本世界將以此為視覺母題擴寫世界史。"
        ),
        "source": "reference_intake.world_proposal",
        "anchors": anchors,
        "veo_prompt": _veo_prompt(usable, channel),
        "veo_character": _veo_character_spec(channel),
        "veo_target": f"veo_{_slug(name)}_01.png",
    }


def derived_candidates(label: str, worlds: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic mutants of an existing world that appears in the intake."""
    base = worlds.get(label)
    if not base:
        return []
    made: list[dict[str, Any]] = []
    for axis, value, suffix in (("season", "冬", "冬霧"), ("time_of_day", "dawn", "破曉")):
        try:
            mutant = wl.mutate(base, axis, value)
        except (ValueError, KeyError):
            continue
        name = unique_name(f"{label}·{suffix}")
        mutant.update({
            "name": name,
            "channel": base.get("channel", "lofi"),
            "source": "reference_intake.world_proposal.mutant",
            "derived_from": {"axis": axis, "value": value},
        })
        mutant["anchors"] = []
        mutant["veo_prompt"] = _veo_prompt([label, suffix], mutant.get("channel", "lofi"))
        mutant["veo_character"] = _veo_character_spec(mutant.get("channel", "lofi"))
        mutant["veo_target"] = f"veo_{_slug(name)}_01.png"
        made.append(mutant)
    return made


def unique_name(base: str) -> str:
    """Ensure candidate names never clash with the current world library."""
    existing = set(wl.all_worlds())
    if base not in existing:
        return base
    index = 2
    while f"{base}·{index}" in existing:
        index += 1
    return f"{base}·{index}"


def _balanced_pick(
    scored: list[tuple[str, float, dict[str, Any]]],
    n: int,
    novelty_floor: float | None = NOVELTY_MIN,
) -> list[tuple[str, float, dict[str, Any]]]:
    """Pick top candidates with round-robin balancing across channels.

    RCA 2026-09-12: ranking by novelty alone let whichever channel was
    inserted first fill every slot (lofi-only CP-D packs). Candidates are
    ranked by novelty inside each channel, then alternated across channels.
    """
    by_channel: dict[str, list[tuple[str, float, dict[str, Any]]]] = {}
    for row in scored:
        if novelty_floor is not None and row[1] < novelty_floor:
            continue
        by_channel.setdefault(str(row[2].get("channel", "lofi")), []).append(row)
    channels = sorted(by_channel)
    picked: list[tuple[str, float, dict[str, Any]]] = []
    idx = 0
    while len(picked) < n and any(by_channel.values()):
        channel = channels[idx % len(channels)]
        if by_channel[channel]:
            picked.append(by_channel[channel].pop(0))
        idx += 1
    return picked


def build_candidates(manifest: dict[str, Any], analyses: list[dict[str, Any]], n: int) -> tuple[dict[str, Any], list[str]]:
    """Return ({name: spec}, warnings) with up to n candidates."""
    warnings: list[str] = []
    worlds = wl.all_worlds()
    labels = list(dict.fromkeys(item.get("label", "?") for item in (manifest.get("items") or [])))
    candidates: dict[str, Any] = {}

    for label in labels:
        if label in worlds:
            for spec in derived_candidates(label, worlds):
                candidates[spec["name"]] = spec
        else:
            channel = "light_music" if str(label).lower().startswith("light_music") else "lofi"
            cluster_analyses = [a for a in analyses if a.get("label") == label]
            if not cluster_analyses:
                # Degraded mode: seed from the query text instead of vision tags.
                queries = [i.get("query", "") for i in (manifest.get("items") or []) if i.get("label") == label]
                seed = queries[0] if queries else label
                pretty = "-".join(word.title() for word in re.split(r"\s+", seed.strip()))[:48] or label
                spec = wl.draft_from_seed(seed, channel)
                spec["name"] = unique_name(pretty)
                template = spec.pop("template", {})
                spec.update(template)
                spec["anchors"] = []
                spec["veo_prompt"] = _veo_prompt([seed], channel)
                spec["veo_character"] = _veo_character_spec(channel)
                spec["veo_target"] = f"veo_{_slug(spec['name'])}_01.png"
                candidates[spec["name"]] = spec
                continue
            for cluster in _cluster_by_tags(cluster_analyses):
                spec = new_world_candidate(cluster, channel)
                candidates[spec["name"]] = spec

    # Rank by novelty (world_library owns the scoring) and keep the top n.
    scored = sorted(
        ((name, wl.novelty(spec, worlds), spec) for name, spec in candidates.items()),
        key=lambda row: row[1],
        reverse=True,
    )
    picked = _balanced_pick(scored, n)
    if len(picked) < min(3, len(scored)):
        warnings.append(
            "fewer than 3 candidates reached novelty >= 0.25; topping up with the next best drafts"
        )
        picked = _balanced_pick(scored, min(n, len(scored)), novelty_floor=None)
    result = {}
    for name, score, spec in picked:
        spec["novelty"] = score
        spec["low_novelty"] = score < NOVELTY_MIN
        result[name] = spec
    return result, warnings


# --------------------------------------------------------------------------
# Pack writing + notification
# --------------------------------------------------------------------------
def render_markdown(week_name: str, drafts: dict[str, Any], meta: dict[str, Any], manifest: dict[str, Any]) -> str:
    """CEO review copy: one block per draft with everything needed for CP-D."""
    vision_info = meta.get("vision") or {}
    chain = "→".join(vision_info.get("chain") or []) or "（未設定）"
    used = vision_info.get("provider") or ("未啟用" if not vision_info.get("images_analyzed") else "?")
    lines = [
        f"# CP-D 世界草案審核包 — {week_name}",
        "",
        f"- 產生時間：{meta.get('generated')}",
        f"- 素材來源：{meta.get('week_path')}（{len(manifest.get('items') or [])} 張）",
        f"- 視覺分析：**{used}**（備援鏈 {chain}），已分析 {vision_info.get('images_analyzed', 0)} 張",
        "",
        "> **審核方式（CP-D）**：逐座檢視 → 批准則回覆 `Approve <世界名>`；退回回覆 `Reject <世界名> <原因>`。",
        "> 對草案圖不滿意時，可用下方 VEO 備援提示詞到 Flow 免費重生，再丟回 intake 續審。",
        "> 本檔為文字備份；**圖形審核請開同資料夾的 `review.html`**（瀏覽器直接看圖）。",
        "",
    ]
    for name, spec in drafts.items():
        flag = "　⚠️ novelty < 0.25" if spec.get("low_novelty") else ""
        lines += [
            f"## {name}{flag}",
            "",
            f"- **channel**：{spec.get('channel')}　**novelty**：{spec.get('novelty')}",
            f"- **era**：{spec.get('era')}",
            f"- **palette**：{'、'.join(spec.get('palette') or [])}",
            f"- **weather**：{spec.get('weather')}",
            f"- **landmarks**：{'、'.join(spec.get('landmarks') or [])}",
            f"- **錨點圖**：{'、'.join(spec.get('anchors') or []) or '（衍生草案：以母世界為準）'}",
            "",
            f"**chronicle 草稿**：{spec.get('chronicle')}",
            "",
            f"**VEO 備援提示詞**（存檔為 `{spec.get('veo_target')}`）：",
            "",
            f"`{spec.get('veo_prompt')}`",
            "",
        ]
    return "\n".join(lines)


def write_pack(cp_d_dir: Path, week_name: str, drafts: dict[str, Any], meta: dict[str, Any], manifest: dict[str, Any], warnings: list[str]) -> Path:
    """Write proposal.json / proposal.md / veo_prompts.txt; returns the folder."""
    cp_d_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "cp_d.proposal.v1",
        "generated": meta.get("generated"),
        "week": week_name,
        "sources": {"week_path": meta.get("week_path"), "manifest_items": len(manifest.get("items") or [])},
        "vision": meta.get("vision") or {},
        "warnings": (meta.get("vision", {}).get("warnings") or []) + warnings,
        "drafts": drafts,
    }
    (cp_d_dir / "proposal.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (cp_d_dir / "proposal.md").write_text(
        render_markdown(week_name, drafts, {**meta, "vision": meta.get("vision") or {}}, manifest),
        encoding="utf-8",
    )
    veo_lines = ["# VEO fallback prompts (Flow free tier) - save each image under the target name", ""]
    for name, spec in drafts.items():
        veo_lines += [f"## {name}", f"target: {spec.get('veo_target')}", spec.get("veo_prompt", ""), ""]
    (cp_d_dir / "veo_prompts.txt").write_text("\n".join(veo_lines), encoding="utf-8")
    return cp_d_dir


def write_review_html(
    cp_d_dir: Path,
    week_name: str,
    drafts: dict[str, Any],
    manifest: dict[str, Any],
    week_path: Path,
) -> Path:
    """CEO-facing IMAGE-FIRST review page: open review.html in any browser."""
    import html as html_mod

    cards: list[str] = []
    for name, spec in drafts.items():
        files = [str(f) for f in (spec.get("anchors") or []) if f]
        if not files:
            label = name.split("\u00b7")[0]
            files = [
                str(i.get("file")) for i in (manifest.get("items") or [])
                if i.get("label") == label
            ][:3]
        images = []
        for fname in files:
            if not fname:
                continue
            rel = os.path.relpath(str(week_path / fname), str(cp_d_dir)).replace("\\", "/")
            images.append(
                "<figure><img src=\"{0}\" alt=\"{1}\"><figcaption>{1}</figcaption></figure>".format(
                    html_mod.escape(rel), html_mod.escape(fname)
                )
            )
        swatches = "".join(
            "<span class=\"sw\" style=\"background:{0}\"></span>".format(html_mod.escape(str(c)))
            for c in (spec.get("palette") or [])
        )
        char_html = ""
        character = spec.get("veo_character") or {}
        if character:
            char_html = (
                "<p class=\"char\"><b>角色設定（Veo Ingredients）</b>：{0}<br>{1}</p>".format(
                    html_mod.escape(str(character.get("casting", ""))),
                    html_mod.escape(str(character.get("flow_usage", ""))),
                )
            )
        cards.append(
            "<section>\n"
            "<h2>{name} <small>{channel}｜novelty {novelty}</small></h2>\n"
            "<div class=\"imgs\">{images}</div>\n"
            "<p class=\"palette\">色票 {swatches}</p>\n"
            "<p class=\"meta\">{era}｜{weather}</p>\n"
            "<p class=\"meta\">錨點：{anchors}</p>\n"
            "{char}\n"
            "<details><summary>VEO 備援提示詞（點開）</summary><pre>{prompt}</pre></details>\n"
            "</section>".format(
                name=html_mod.escape(name),
                channel=html_mod.escape(str(spec.get("channel"))),
                novelty=html_mod.escape(str(spec.get("novelty"))),
                images="".join(images) or "<em>（衍生草案：以母世界視覺為準）</em>",
                swatches=swatches,
                era=html_mod.escape(str(spec.get("era"))),
                weather=html_mod.escape(str(spec.get("weather"))),
                anchors=html_mod.escape("、".join(files)),
                char=char_html,
                prompt=html_mod.escape(str(spec.get("veo_prompt"))),
            )
        )
    page = REVIEW_TEMPLATE.format(week=html_mod.escape(week_name), cards="\n".join(cards))
    target = cp_d_dir / "review.html"
    target.write_text(page, encoding="utf-8")
    return target


def notify_album(week_name: str, drafts: dict[str, Any], week_path: Path, max_photos: int = 4) -> bool:
    """Push one anchor image per draft as a Telegram album (CEO reviews images)."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        return False
    photos: list[tuple[Path, str]] = []
    for name, spec in drafts.items():
        files = [f for f in (spec.get("anchors") or []) if f]
        if not files:
            continue
        candidate = week_path / str(files[0])
        if candidate.is_file():
            photos.append((candidate, f"<b>{name}</b>（{spec.get('channel')}）"))
    if not photos:
        return False
    photos = photos[:max_photos]
    media = [
        {"type": "photo", "media": f"attach://photo{i}", "caption": cap, "parse_mode": "HTML"}
        for i, (_path, cap) in enumerate(photos)
    ]
    handles: dict[str, Any] = {}
    try:
        for i, (path, _cap) in enumerate(photos):
            handles[f"photo{i}"] = (path.name, path.open("rb"), "image/jpeg")
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMediaGroup",
            data={"chat_id": chat, "media": json.dumps(media, ensure_ascii=False)},
            files=handles,
            timeout=120,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - notification failure is reported, not fatal
        print(f"[warn] telegram album failed: {exc}", file=sys.stderr, flush=True)
        return False
    finally:
        for handle in handles.values():
            try:
                handle[1].close()
            except Exception:  # noqa: BLE001
                pass


def main() -> int:
    load_env_files()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", help="ISO week override, e.g. 2026-W37 (defaults to current)")
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="number of drafts (3-5)")
    parser.add_argument("--limit-images", type=int, default=DEFAULT_MAX_IMAGES)
    parser.add_argument("--no-vision", action="store_true", help="skip Gemini; metadata-only drafts")
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args()

    week_path = week_dir() if not args.week else week_dir().parent / args.week
    manifest_file = week_path / "manifest.json"
    if not manifest_file.is_file():
        print(f"[FATAL] no manifest for week at {manifest_file}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    analyses: list[dict[str, Any]] = []
    vision_meta: dict[str, Any] = {"enabled": False, "images_analyzed": 0, "warnings": []}
    if not args.no_vision:
        analyses, vision_meta = analyze_week(week_path, manifest, args.limit_images)

    drafts, warnings = build_candidates(manifest, analyses, max(3, min(5, args.n)))
    meta = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "week_path": str(week_path),
        "vision": vision_meta,
    }
    cp_d_dir = CP_D_ROOT / week_path.name
    write_pack(cp_d_dir, week_path.name, drafts, meta, manifest, warnings)
    review_page = write_review_html(cp_d_dir, week_path.name, drafts, manifest, week_path)

    summary = [
        f"[CP-D] {week_path.name} 世界草案 {len(drafts)} 座（圖片已隨本訊息附上）",
        "、".join(f"{name}（novelty {spec.get('novelty')}）" for name, spec in drafts.items()),
        f"圖形審核頁：{review_page}",
        "回覆 Approve／Reject 完成 CP-D；不滿意可用審核頁內提示詞免費重生。",
    ]
    print("\n".join(summary), flush=True)
    if not args.no_telegram:
        sent = notify_album(week_path.name, drafts, week_path)
        notify("\n".join(summary) + ("" if sent else "（注意：相簿推送失敗，請直接開審核頁）"))
    return 0


# The engine deliberately never calls world_library.commit(): commits are a
# CEO-only gate (CP-D -> commit) handled by a separate approved flow.
if __name__ == "__main__":
    raise SystemExit(main())
