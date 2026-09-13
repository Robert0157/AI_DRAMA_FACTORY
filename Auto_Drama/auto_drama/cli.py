# -*- coding: utf-8 -*-
"""argparse CLI for Auto_Drama."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Settings, load_settings
from .logging_util import setup_logging
from .paths import Paths

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _cmd_book(args: argparse.Namespace) -> int:
    """python run.py book --source <chapter.txt> [--mock|--live]."""
    source = Path(args.source)
    if not source.exists():
        print(f"[AUTO-DRAMA] source file not found: {source}", file=sys.stderr)
        return 1

    settings = load_settings(_PROJECT_ROOT)
    setup_logging(Paths(settings).log_path())
    from .orchestrator import run_book_pipeline

    mode = "live" if args.live else "mock"
    if args.stage1_only:
        # Override stage switches so only Stage 1 (script) executes.
        raw = {**settings.raw, "stages": {
            "script": True, "visual": False, "audio_lipsync": False, "post": False,
        }}
        settings = Settings(raw)

    source_text = source.read_text(encoding="utf-8-sig", errors="replace")
    summary = run_book_pipeline(
        source_text=source_text,
        book_title=args.title or source.stem,
        series=args.series,
        mode=mode,
        settings=settings,
    )
    print("\n[AUTO-DRAMA] === 產線摘要 ===")
    print(f"  job_id     : {summary['job_id']}")
    print(f"  series     : {summary['series']}")
    print(f"  status     : {summary['status']}")
    print(f"  episode_dir: {summary['episode_dir']}")
    stage_manifests = summary.get("manifest", {})
    for stage, payload in stage_manifests.items():
        print(f"  [{stage}] -> {payload}")
    print("\n產物清單：")
    for p in sorted(Path(summary["episode_dir"]).iterdir()):
        print(f"    {p.name}  ({p.stat().st_size} bytes)")
    return 0 if summary.get("status") == "completed" else 1


def _cmd_preview(args: argparse.Namespace) -> int:
    """python run.py preview --storyboard <json> [--out mp4] — 分鏡 animatic 預覽.

    CEO 預覽鐵律：每次 preview 必須同時產出
      1) 分鏡預覽影片 MP4
      2) 每分鏡靜態截圖組合圖 PNG（接觸圖），讓 CEO 快速理解內容。
    """
    from .animatic import make_animatic, make_contact_sheet

    sb = Path(args.storyboard)
    if not sb.exists():
        print(f"[AUTO-DRAMA] storyboard not found: {sb}", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else sb.with_name(sb.stem + "_animatic_preview.mp4")
    sheet = sb.with_name(sb.stem + "_contact_sheet.png")
    try:
        result = make_animatic(sb, out)
        sheet_result = make_contact_sheet(sb, result, sheet)
    except Exception as exc:
        print(f"[AUTO-DRAMA] preview 產生失敗: {exc}", file=sys.stderr)
        return 1
    print(f"[AUTO-DRAMA] 分鏡預覽影片已產生: {result}")
    print(f"[AUTO-DRAMA] 分鏡截圖組合圖已產生: {sheet_result}")
    return 0


def _cmd_stage2(args: argparse.Namespace) -> int:
    """python run.py stage2 --storyboard <json> — Live Stage2 視覺 + Stage1&2 preview.

    CEO 預覽鐵律：preview 必須是 Stage1+Stage2 成果。本指令
      1) 用 AI 影像引擎（優先 Zhipu CogView，其次 Kling）產生角色肖像 + 每分鏡關鍵幀
      2) 產出 *_visual_preview.mp4（每鏡顯示真實 AI 圖）
      3) 產出 *_visual_contact_sheet.png（每分鏡截圖組合圖）
    需環境變數: ZHIPUAI_API_KEY 或 KLING_AK/KLING_SK。
    """
    import os

    from .animatic import make_contact_sheet, make_visual_preview
    from .stage2_live import run_stage2_visuals

    settings = load_settings(_PROJECT_ROOT)
    setup_logging(Paths(settings).log_path())

    # Pick the image engine by environment keys (Zhipu CogView preferred when
    # present; Kling used otherwise).
    zhipu_key = os.environ.get("ZHIPUAI_API_KEY",
                               os.environ.get("GLM_4V_API_KEY", ""))
    kling_ak = os.environ.get("KLING_AK", os.environ.get("KLING_ACCESS_KEY", ""))
    kling_sk = os.environ.get("KLING_SK", os.environ.get("KLING_SECRET_KEY", ""))
    if zhipu_key:
        from .zhipu_image import ZhipuImageClient

        engine = ZhipuImageClient(api_key=zhipu_key)
        engine_name = "zhipu-cogview"
    elif kling_ak and kling_sk:
        from .kling_image import KlingImageClient

        engine = KlingImageClient(access_key=kling_ak, secret_key=kling_sk)
        engine_name = "kling"
    else:
        print("[AUTO-DRAMA] 需要影像引擎金鑰: ZHIPUAI_API_KEY 或 KLING_AK/KLING_SK",
              file=sys.stderr)
        return 1
    print(f"[AUTO-DRAMA] 影像引擎: {engine_name}")

    sb = Path(args.storyboard)
    if not sb.exists():
        print(f"[AUTO-DRAMA] storyboard not found: {sb}", file=sys.stderr)
        return 1

    out_root = Path(args.episode_dir) if args.episode_dir else sb.parent
    out_root.mkdir(parents=True, exist_ok=True)
    try:
        manifest = run_stage2_visuals(sb, out_root, engine=engine)
    except Exception as exc:
        print(f"[AUTO-DRAMA] Stage 2 視覺產出失敗: {exc}", file=sys.stderr)
        return 1

    stage2_dir = Path(manifest["dir"])
    mp4 = out_root / (sb.stem + "_visual_preview.mp4")
    sheet = out_root / (sb.stem + "_visual_contact_sheet.png")
    try:
        make_visual_preview(sb, stage2_dir, mp4)
        make_contact_sheet(sb, mp4, sheet)
    except Exception as exc:
        print(f"[AUTO-DRAMA] visual preview 產生失敗: {exc}", file=sys.stderr)
        return 1
    print(f"[AUTO-DRAMA] Stage2 完成: {len(manifest['characters'])} 角色 + "
          f"{len(manifest['shots'])} 分鏡圖")
    print(f"[AUTO-DRAMA] Stage1+2 預覽影片: {mp4}")
    print(f"[AUTO-DRAMA] Stage1+2 截圖組合圖: {sheet}")
    return 0


def _cmd_lmd_episode(args: argparse.Namespace) -> int:
    """python run.py lmd-episode --episode-id 1 [--drama-id 1] [--limit 1]...

    Live 鏈：Auto_Drama 以「逐鏡 POST /videos + storyboard_id + reference_urls」
    驅動 LocalMiniDrama 後端（Seedance 2.5 @圖片N 綁定），先打 preflight 硬閘門。
    """
    import json as _json

    settings = load_settings(_PROJECT_ROOT)
    setup_logging(Paths(settings).log_path())

    from .lmd_client import LocalMiniDramaClient
    from .lmd_video_chain import run_episode_lmd

    base = settings.get("lmd.base_url", "http://127.0.0.1:5679")
    prefix = settings.get("lmd.api_prefix", "/api/v1")
    timeout = int(settings.get("lmd.timeout_sec", 60))
    lmd = LocalMiniDramaClient(base_url=base, api_prefix=prefix, timeout_sec=timeout)

    bindings = {}
    if args.bindings:
        raw = _json.loads(Path(args.bindings).read_text(encoding="utf-8"))
        bindings = {int(k): [int(x) for x in v] for k, v in raw.items()}
    aliases = {}
    if args.aliases:
        raw = _json.loads(Path(args.aliases).read_text(encoding="utf-8"))
        aliases = {k: int(v) for k, v in raw.items()}

    try:
        summary = run_episode_lmd(
            lmd,
            episode_id=args.episode_id,
            drama_id=args.drama_id,
            series=args.series,
            episode_title=args.episode_title,
            out_root=Path(args.out_root) if args.out_root else None,
            bindings=bindings,
            alias_map=aliases,
            model=args.model,
            aspect_ratio=args.aspect_ratio,
            resolution=args.resolution,
            static_url=args.static_url,
            limit=args.limit,
            generate_universal=not args.no_generate_universal,
            skip_existing=not args.force,
            concat=not args.no_concat,
            poll_timeout_sec=int(args.poll_timeout),
        )
    except Exception as exc:
        print(f"[AUTO-DRAMA] lmd-episode 失敗: {exc}", file=sys.stderr)
        return 1

    print("\n[AUTO-DRAMA] === lmd-episode 摘要 ===")
    print(f"  dir        : {summary['dir']}")
    print(f"  shots      : {len(summary['shots'])}")
    for rec in summary["shots"]:
        print(f"    sh{rec.get('storyboard_number', 0):03d}  {rec.get('status')}  {rec.get('file')}")
    print(f"  final_video: {summary['final_video']}")
    return 0 if summary.get("status") == "completed" else 1


def _cmd_music_drama(args: argparse.Namespace) -> int:
    """python run.py music-drama --draft <json> [--execute] [--limit N] [--force]

    Music-first MV pipeline (P0b sandbox):
      draft v2 validation -> LMD authoring (drama/episode/cast/storyboards + portrait)
      -> Seedance 2.5 per shot (9:16) -> lossless concat -> song-as-master mux (§10b) -> contact sheet.
    """
    import os

    settings = load_settings(_PROJECT_ROOT)
    setup_logging(Paths(settings).log_path())

    from .music_drama import (
        load_draft,
        make_contact_sheet,
        mux_music_master,
        normalize_storyboards,
        prepare_lmd_episode,
        validate_draft,
    )

    draft_path = Path(args.draft)
    if not draft_path.is_file():
        print(f"[MUSIC-DRAMA] draft not found: {draft_path}", file=sys.stderr)
        return 1

    draft = load_draft(draft_path)
    verdict = validate_draft(draft)
    for w in verdict["warnings"]:
        print(f"[MUSIC-DRAMA][WARN] {w}")
    if verdict["errors"]:
        for e in verdict["errors"]:
            print(f"[MUSIC-DRAMA][FATAL] {e}", file=sys.stderr)
        return 1

    plan = normalize_storyboards(draft)
    audio_path = verdict["audio_path"]
    seg_start, seg_end = verdict["segment"]
    print(f"[MUSIC-DRAMA] draft OK: {len(plan)} shots | segment {seg_start:.1f}-{seg_end:.1f}s "
          f"| audio {audio_path.name}")
    for spec in plan:
        p = spec["payload"]
        cast_tag = "/".join(spec["character_names"]) or "-"
        print(f"    sh{p['storyboard_number']:03d}  {p['duration']:.1f}s  {p['title']}  @{cast_tag}")

    if not args.execute:
        print("[MUSIC-DRAMA] dry-run only — pass --execute to run the live LMD chain.")
        return 0

    # Load workspace .env for API keys (env vars already set win; keys never persisted).
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT.parent / ".env")
    except Exception:
        pass

    from .lmd_client import LocalMiniDramaClient
    from .lmd_video_chain import run_episode_lmd

    portrait_client = None
    zhipu_key = os.environ.get("ZHIPUAI_API_KEY", "")
    if zhipu_key:
        from .zhipu_image import ZhipuImageClient
        portrait_client = ZhipuImageClient(zhipu_key)
    else:
        print("[MUSIC-DRAMA][WARN] ZHIPUAI_API_KEY missing — character portrait skipped")

    base = settings.get("lmd.base_url", "http://127.0.0.1:5679")
    prefix = settings.get("lmd.api_prefix", "/api/v1")
    timeout = int(settings.get("lmd.timeout_sec", 60))
    lmd = LocalMiniDramaClient(base_url=base, api_prefix=prefix, timeout_sec=timeout)
    lmd.health()

    out_root = (Path(args.out_root) if args.out_root
                else Paths(settings).output_root / "sandbox" / draft_path.stem)

    prepared = prepare_lmd_episode(lmd, draft, plan, portrait_client=portrait_client)
    print(f"[MUSIC-DRAMA] LMD prepared: drama={prepared['drama_id']} "
          f"episode={prepared['episode_id']} storyboards={prepared['storyboard_ids']}")
    print(f"[MUSIC-DRAMA] cast map: {prepared['character_ids']}")

    vs = draft.get("visual_style") or {}
    summary = run_episode_lmd(
        lmd,
        episode_id=prepared["episode_id"],
        drama_id=prepared["drama_id"],
        series=str(draft.get("series") or "mv"),
        episode_title=str((draft.get("episode") or {}).get("title") or draft_path.stem),
        out_root=out_root,
        aspect_ratio=str(vs.get("aspect_ratio") or "9:16"),
        # CEO cost policy 2026-09-10: initial runs default to 480p.
        resolution=str(vs.get("resolution") or "480p"),
        limit=int(args.limit) if args.limit else None,
        generate_universal=False,   # draft already ships @图片N universal text
        skip_existing=not args.force,
        concat=not args.no_concat,
        poll_timeout_sec=int(args.poll_timeout),
    )

    print("\n[MUSIC-DRAMA] === shot summary ===")
    for rec in summary["shots"]:
        print(f"    sh{int(rec.get('storyboard_number') or 0):03d}  "
              f"{rec.get('status')}  {rec.get('file')}")

    final = summary.get("final_video")
    if not final:
        print("[MUSIC-DRAMA] no final concat produced — aborting mux", file=sys.stderr)
        return 1

    policy = draft.get("audio_policy") or {}
    mv_out = Path(final).with_name(Path(final).stem + "_mv_music_master.mp4")
    mux_music_master(Path(final), audio_path, mv_out,
                     music_start_sec=seg_start,
                     ambient_gain_db=float(policy.get("ambient_gain_db", -27.0)))
    print(f"[MUSIC-DRAMA] MV master (song = only master track, §10b) -> {mv_out}")

    shots = draft.get("shots") or []
    mids = [round((float(s["start_sec"]) + float(s["end_sec"])) / 2.0, 2) for s in shots]
    sheet = Path(final).parent / "mv_contact_sheet.png"
    make_contact_sheet(mv_out, sheet, mids)
    print(f"[MUSIC-DRAMA] contact sheet -> {sheet}")
    return 0


def _cmd_jobs(args: argparse.Namespace) -> int:
    """python run.py jobs [--limit N]."""
    settings = load_settings(_PROJECT_ROOT)
    paths = Paths(settings)
    from .state import JobStore

    store = JobStore(paths.job_db_path())
    for job in store.list_jobs(limit=args.limit):
        print(f"{job['created_at']}  {job['job_id']}  {job['series']:12s}  "
              f"status={job['status']}  progress={job['stage_progress']}")
    return 0


def _cmd_telegram(args: argparse.Namespace) -> int:
    """python run.py telegram [--token xxx] — remote control (HITL)."""
    from .telegram_ctl import start_telegram

    token = args.token or ""
    return start_telegram(token)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="Auto_Drama",
        description="書本章節 -> 自動短劇產線 (Auto_Drama orchestrator)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_book = sub.add_parser("book", help="從章節文字跑完整產線")
    p_book.add_argument("--source", required=True, help="章節文字檔路徑 (.txt)")
    p_book.add_argument("--title", default="", help="書名/章節標題")
    p_book.add_argument("--series", default="yuewei", help="系列資料夾名稱")
    p_book.add_argument("--live", action="store_true", help="live 模式（需 API keys/後端）")
    p_book.add_argument("--stage1-only", action="store_true",
                        help="只跑 Stage 1（劇本擴寫+分鏡），用於 live 驗證")
    p_book.set_defaults(func=_cmd_book)

    p_jobs = sub.add_parser("jobs", help="列出最近的產線任務")
    p_jobs.add_argument("--limit", type=int, default=10)
    p_jobs.set_defaults(func=_cmd_jobs)

    p_lmd = sub.add_parser("lmd-episode", help="Live 鏈：逐鏡驅動 LMD 後端產 Seedance 2.5 影片")
    p_lmd.add_argument("--episode-id", type=int, required=True, help="LMD episode id")
    p_lmd.add_argument("--drama-id", type=int, default=None, help="LMD drama id（建議給，避免推導失敗）")
    p_lmd.add_argument("--series", default="yuewei", help="輸出 series 資料夾")
    p_lmd.add_argument("--episode-title", default="", help="輸出檔名用集數標題")
    p_lmd.add_argument("--out-root", default="", help="輸出根目錄（預設 Auto_Drama/output/episodes/{series}）")
    p_lmd.add_argument("--bindings", default="", help="JSON 檔：{storyboard_number: [char_id,...]}")
    p_lmd.add_argument("--aliases", default="", help="JSON 檔：{角色別名: char_id}，auto-bind 用")
    p_lmd.add_argument("--model", default="dreamina-seedance-2-5-260628", help="Seedance 模型")
    p_lmd.add_argument("--aspect-ratio", default="16:9")
    p_lmd.add_argument("--resolution", default="480p",
                       help="Output resolution (CEO cost policy: initial runs use 480p)")
    p_lmd.add_argument("--static-url", default="http://127.0.0.1:5679/static", help="LMD 靜態檔根")
    p_lmd.add_argument("--limit", type=int, default=None, help="只跑前 N 鏡（sandbox 驗證用）")
    p_lmd.add_argument("--no-generate-universal", action="store_true", help="不呼叫 LLM 產生 @圖片N 提示詞")
    p_lmd.add_argument("--force", action="store_true", help="重新生成已存在的鏡頭")
    p_lmd.add_argument("--no-concat", action="store_true", help="不執行最終無損拼接")
    p_lmd.add_argument("--poll-timeout", default="2400", help="單鏡輪詢總超時秒數")
    p_lmd.set_defaults(func=_cmd_lmd_episode)

    p_prev = sub.add_parser("preview", help="從分鏡 JSON 產生 animatic 預覽 MP4")
    p_prev.add_argument("--storyboard", required=True, help="epXX_storyboard.json 路徑")
    p_prev.add_argument("--out", default="", help="輸出 MP4 路徑（預設同目錄）")
    p_prev.set_defaults(func=_cmd_preview)

    p_s2 = sub.add_parser("stage2", help="Live Stage2 視覺 + Stage1&2 CEO preview")
    p_s2.add_argument("--storyboard", required=True, help="epXX_storyboard.json 路徑")
    p_s2.add_argument("--episode-dir", default="", help="輸出目錄（預設 storyboard 所在）")
    p_s2.set_defaults(func=_cmd_stage2)

    p_tg = sub.add_parser("telegram", help="啟動 Telegram 遠端控制")
    p_tg.add_argument("--token", default="", help="Telegram bot token（或設 TELEGRAM_BOT_TOKEN）")
    p_tg.set_defaults(func=_cmd_telegram)

    p_md = sub.add_parser("music-drama",
                          help="Music-First MV 產線：草稿 v2 → LMD → 歌曲主軌混音（P0b 沙盒）")
    p_md.add_argument("--draft", required=True, help="music_drama draft v2 JSON 路徑")
    p_md.add_argument("--execute", action="store_true", help="實際執行（預設僅驗證 dry-run）")
    p_md.add_argument("--limit", type=int, default=None, help="只跑前 N 鏡（沙盒）")
    p_md.add_argument("--out-root", default="", help="輸出根目錄（預設 Auto_Drama/output/sandbox/<draft>）")
    p_md.add_argument("--force", action="store_true", help="重生成已存在的鏡頭")
    p_md.add_argument("--no-concat", action="store_true", help="不執行最終無損拼接")
    p_md.add_argument("--poll-timeout", default="2400", help="單鏡輪詢總超時秒數")
    p_md.set_defaults(func=_cmd_music_drama)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n[AUTO-DRAMA] interrupted by user.")
        return 130
