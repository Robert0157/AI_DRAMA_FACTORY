# -*- coding: utf-8 -*-
"""
lmd_video_chain.py — Auto_Drama live 鏈：以「逐鏡 POST /videos + storyboard_id
+ reference_urls」真正接上 LocalMiniDrama 後端（CEO 唯一合法引擎 Seedance 2.5）。

流程（CEO 授權範圍：2.5 模型切換 + @Image 綁定 + preflight 硬閘門）：
  1) health 檢查
    2) 檢查角色綁定已在開發階段完成（生成時禁止修改）
  3) preflight-reference-assets 整集檢查（缺角色資產即中止）
  4) 逐鏡：
     a. GET omni-reference-plan        （權威 @圖片N 槽位 + 參考圖 URL）
    b. 確保已準備的 universal_segment_text 含 @圖片N（缺少即阻斷）
     c. POST /videos {storyboard_id, prompt(@圖片N), reference_image_urls}
     d. 輪詢 GET /videos/{id} 至 completed
     e. 下載並改名 epXX_scNN_shMMM.mp4（寫入 shots/）
  5) （可選）concat demuxer -c:v copy 無損拼接成單片 + manifest

ZERO SILENT FAILURES：任何一步失敗即 raise，不靜默吞錯。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .ffmpeg import FfmpegError, concat_lossless, ffmpeg_available
from .logging_util import get_logger

log = get_logger()

# CEO §9 命名：ep[集]_sc[場景]_sh[鏡頭].mp4（場景未綁定以 01 帶入）
_AT_IMAGE_RE = re.compile(r"@(?:图片|圖片)\s*(\d+)")


class LmdChainError(RuntimeError):
    """Raised when the Auto_Drama -> LMD video chain fails (never swallowed)."""


def _prepare_locked_shots(lmd: Any, shots_meta: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Validate every prompt and reference before any video request is submitted."""
    prepared = {}
    for meta in shots_meta:
        sid = meta["storyboard_id"]
        plan = lmd.get_omni_reference_plan(sid)
        urls = [item.get("url") for item in plan.get("urls", []) if item.get("url")]
        detail = lmd.get_storyboard(sid)
        prompt = str(detail.get("universal_segment_text") or "").strip()
        tokens = [int(token) for token in _AT_IMAGE_RE.findall(prompt)]
        if not urls or not prompt or not tokens or min(tokens) < 1 or max(tokens) > len(urls):
            raise LmdChainError(
                f"storyboard {sid}: prepare and review prompt/reference bindings before generation; "
                "runtime prompt generation is forbidden"
            )
        prepared[sid] = {"prompt": prompt, "reference_image_urls": urls}
    return prepared


def _sanitize(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", str(name or "").strip()).strip("_")


def _download_media(url: str, dest: Path, timeout: int = 600) -> Path:
    """下載影片到 dest；HTTP 非 2xx 一律 loud raise。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as r:
        if r.status_code >= 400:
            raise LmdChainError(f"download failed HTTP {r.status_code}: {url[:160]}")
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    fh.write(chunk)
    if dest.stat().st_size < 1024:
        raise LmdChainError(f"downloaded file too small / invalid: {dest} ({dest.stat().st_size}B)")
    return dest


def _parse_existing_char_ids(raw: Any) -> List[int]:
    """storyboards.characters 可能是 JSON 字串或 list of {id,name}。"""
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    ids: List[int] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                try:
                    ids.append(int(item.get("id")))
                except (TypeError, ValueError):
                    continue
            else:
                try:
                    ids.append(int(item))
                except (TypeError, ValueError):
                    continue
    return ids


def infer_auto_bindings(storyboards: List[Dict[str, Any]],
                        characters: List[Dict[str, Any]],
                        alias_map: Optional[Dict[str, int]] = None) -> Dict[int, List[int]]:
    """依分鏡文字掃描角色名/別名，回傳 {storyboard_number: [char_id,...]}。

    已綁定的分鏡保留原綁定；角色名與 alias 都未命中則不強加。
    """
    alias = {str(k): int(v) for k, v in (alias_map or {}).items()}
    by_id = {int(c.get("id")): str(c.get("name") or "").strip() for c in characters}
    by_name = {name: cid for cid, name in by_id.items() if name}

    out: Dict[int, List[int]] = {}
    for sb in storyboards:
        try:
            n = int(sb.get("storyboard_number") or sb.get("shot_number") or 0)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        existing = _parse_existing_char_ids(sb.get("characters"))
        if existing:
            out[n] = existing
            continue
        text = " ".join(
            str(sb.get(k) or "") for k in
            ("title", "description", "action", "dialogue", "narration",
             "video_prompt", "universal_segment_text", "result", "atmosphere")
        )
        chosen: List[int] = []
        chosen_set = set()
        for token, cid in alias.items():
            if token and token in text and cid not in chosen_set:
                chosen_set.add(cid)
                chosen.append(cid)
        for name, cid in by_name.items():
            if name and name in text and cid not in chosen_set:
                chosen_set.add(cid)
                chosen.append(cid)
        if chosen:
            out[n] = chosen
    return out


def run_episode_lmd(
    lmd: Any,
    *,
    episode_id: int,
    drama_id: Optional[int] = None,
    series: str = "yuewei",
    episode_title: str = "",
    out_root: Optional[Path] = None,
    bindings: Optional[Dict[int, List[int]]] = None,
    alias_map: Optional[Dict[str, int]] = None,
    model: str = "dreamina-seedance-2-5-260628",
    aspect_ratio: str = "16:9",
    resolution: str = "1080p",
    static_url: str = "http://127.0.0.1:5679/static",
    limit: Optional[int] = None,
    generate_universal: bool = True,
    skip_existing: bool = True,
    concat: bool = True,
    poll_timeout_sec: int = 2400,
) -> Dict[str, Any]:
    """驅動 LMD 指定劇集的整集逐鏡影片生成（含 preflight + @圖片N 綁定）。

    Returns a summary dict with shot records & artifact paths.
    generate_universal is retained for caller compatibility only; runtime
    prompt generation is always forbidden. This preflight is not CP1 approval.
    """
    ep_id = int(episode_id)
    # ---- health ----
    lmd.health()

    # ---- storyboards ----
    ep_data = lmd.list_storyboards(ep_id)
    storyboards = list(ep_data.get("storyboards") or [])
    if not storyboards:
        raise LmdChainError(f"episode {ep_id} has no storyboards")
    storyboards.sort(key=lambda s: int(s.get("storyboard_number") or s.get("id") or 0))

    if drama_id is None:
        drama_id = int(ep_data.get("drama_id") or 0)
    if not drama_id:
        # try full drama resolution through first storyboard detail
        detail0 = lmd.get_storyboard(int(storyboards[0]["id"]))
        raise LmdChainError("drama_id required (could not be derived from episode listing)")

    # ---- (optional) character bindings ----
    bind_map = dict(bindings or {})
    if not bind_map:
        # auto binding needs character names: fetch from drama detail once
        try:
            drama = lmd.get_drama(drama_id)
            chars = drama.get("characters") or []
        except Exception as exc:
            log.warning("fetch drama characters failed; auto-bind skipped: %s", exc)
            chars = []
        auto = infer_auto_bindings(storyboards, chars, alias_map)
        for n, ids in auto.items():
            bind_map.setdefault(n, ids)

    # ---- resolve per-shot identity maps ----
    # detail per shot id (id -> row)
    shots_meta = []  # ordered [ {id, n, duration, title, scene} ]
    for sb in storyboards:
        sid = int(sb.get("id"))
        n = int(sb.get("storyboard_number") or 0)
        shots_meta.append({
            "storyboard_id": sid,
            "storyboard_number": n,
            "duration": sb.get("duration") or None,
            "title": sb.get("title") or "",
            "scene_id": sb.get("scene_id") or None,
        })

    # apply bindings
    for meta in shots_meta:
        ids = bind_map.get(meta["storyboard_number"])
        if not ids:
            continue
        cur = _parse_existing_char_ids(None)
        # re-read current
        try:
            det = lmd.get_storyboard(meta["storyboard_id"])
            cur = _parse_existing_char_ids(det.get("characters"))
        except Exception as exc:
            log.warning("read storyboard %s for binding check failed: %s", meta["storyboard_id"], exc)
        if sorted(cur) == sorted(int(x) for x in ids):
            continue
        raise LmdChainError(
            f"storyboard {meta['storyboard_id']}: character bindings must be prepared and reviewed "
            "before generation; runtime mutation is forbidden"
        )

    # ---- preflight (hard gate) ----
    pf = lmd.preflight_reference_assets(ep_id)
    if not pf.get("can_proceed"):
        missing = pf.get("missing_character_names") or []
        raise LmdChainError(
            f"preflight failed: {pf.get('failed_storyboards')} shots missing character refs -> {missing}"
        )
    log.info("preflight passed: %s shots ok", pf.get("checked_storyboards"))
    prepared = _prepare_locked_shots(lmd, shots_meta)

    # ---- output routing ----
    if out_root is None:
        out_root = Path(__file__).resolve().parents[1] / "output" / "episodes" / series
    ep_dir = out_root / f"ep{ep_id:02d}_{_sanitize(episode_title or f'ep{ep_id}')}"
    shots_dir = ep_dir / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    # ---- per-shot generation ----
    records = []
    if limit:
        shots_meta = shots_meta[: int(limit)]

    for idx, meta in enumerate(shots_meta, start=1):
        sid = meta["storyboard_id"]
        n = meta["storyboard_number"]
        scene_tag = f"{int(meta['scene_id'] or 1):02d}"
        out_name = f"ep{ep_id:02d}_sc{scene_tag}_sh{n:03d}.mp4"
        out_file = shots_dir / out_name
        log.info("[%d/%d] storyboard %s -> %s", idx, len(shots_meta), sid, out_name)

        if skip_existing and out_file.exists() and out_file.stat().st_size > 1024:
            log.info("skip existing %s", out_file.name)
            records.append({"storyboard_id": sid, "storyboard_number": n,
                            "file": str(out_file), "status": "existing"})
            continue

        current = _prepare_locked_shots(lmd, [meta])[sid]
        if current != prepared[sid]:
            raise LmdChainError(f"storyboard {sid}: prompt/references changed after preflight")
        universal = prepared[sid]["prompt"]
        urls = prepared[sid]["reference_image_urls"]

        # c. POST /videos
        payload = {
            "drama_id": int(drama_id),
            "storyboard_id": sid,
            "prompt": universal,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "reference_image_urls": urls,
        }
        if meta.get("duration"):
            payload["duration"] = float(meta["duration"])
        created = lmd.generate_video(payload)
        vg_id = int(created.get("id") or created.get("video_generation_id") or 0)
        if not vg_id:
            raise LmdChainError(f"POST /videos returned no id: {created}")

        # d. poll
        log.info("video_generation %s submitted, polling...", vg_id)
        done = lmd.wait_video_gen(vg_id, timeout_sec=poll_timeout_sec)
        local_path = done.get("local_path") or ""
        video_url = done.get("video_url") or ""
        if not local_path and not video_url:
            raise LmdChainError(f"video_generation {vg_id} completed without url/path")

        # e. download + rename
        tmp = shots_dir / (out_name + ".part")
        source = None
        if local_path:
            rel = str(local_path).replace("\\", "/").lstrip("/")
            source = f"{static_url.rstrip('/')}/{rel}"
        elif video_url:
            source = video_url
        _download_media(source, tmp)
        if out_file.exists():
            out_file.unlink()
        tmp.rename(out_file)
        log.info("saved %s (%s bytes)", out_file.name, out_file.stat().st_size)
        records.append({
            "storyboard_id": sid,
            "storyboard_number": n,
            "video_generation_id": vg_id,
            "file": str(out_file),
            "refs": len(urls),
            "prompt_len": len(universal),
            "model": model,
            "status": "completed",
        })

    # ---- artifacts ----
    manifest = {
        "episode_id": ep_id,
        "drama_id": int(drama_id),
        "episode_title": episode_title,
        "model": model,
        "aspect_ratio": aspect_ratio,
        "shots": records,
    }
    (shots_dir / "shots_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Resume semantics: a shot recorded as "existing" (valid file on disk from an
    # earlier run) is just as usable as "completed". Concat is safe whenever every
    # shot of the requested set has a valid local file (>= 1 KB) - full run or
    # resumed run alike. Partial runs (records < shots) never concat.
    final_path = None
    if concat and len(records) == len(shots_meta) and len(records) > 0 and all(
        r.get("status") in ("completed", "existing")
        and Path(r.get("file", "")).is_file()
        and Path(r["file"]).stat().st_size > 1024
        for r in records
    ):
        try:
            files = [Path(r["file"]) for r in records]
            if not ffmpeg_available():
                raise LmdChainError("FFmpeg is required for requested assembly")
            if files:
                final_path = ep_dir / f"ep{ep_id:02d}_{_sanitize(episode_title or 'episode')}_lmd全自動鏈.mp4"
                concat_lossless(files, final_path)
                log.info("final concat -> %s", final_path)
        except FfmpegError as exc:
            raise LmdChainError(f"final concat failed: {exc}") from exc

    manifest["final_video"] = str(final_path) if final_path else None
    (shots_dir / "shots_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"episode_id": ep_id, "drama_id": int(drama_id), "dir": str(ep_dir),
            "shots": records, "final_video": str(final_path) if final_path else None,
            "publish_eligible": False,
            "pending_reviews": ["delivery_qc", "ceo_cp2"],
            "status": "completed" if records else "empty"}
