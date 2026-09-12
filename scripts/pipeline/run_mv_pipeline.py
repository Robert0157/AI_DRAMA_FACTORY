#!/usr/bin/env python3
"""One-button MV pipeline control on the PC side (control plane).

Division of labour
------------------
PC  (this script)  : story generation -> validation -> Toonflow review package -> dispatch
Mac (execution)    : Toonflow review UI (192.168.2.200:12088)
                     Wan 2.1 480p render worker -> concat -> master-track mux

Only the CEO reviews. Everything else is a single command:

  python scripts/pipeline/run_mv_pipeline.py status
  python scripts/pipeline/run_mv_pipeline.py scripts --llm
  python scripts/pipeline/run_mv_pipeline.py review
  python scripts/pipeline/run_mv_pipeline.py render --topic 昭和101年空中都市 --variant 1

Both hosts see the same handoff tree through the SMB share:
  PC : Y:\\AI_Drama_Factory\\Auto_Drama\\output\\handoff
  Mac: /Volumes/AI_Workspace/AI_Drama_Factory/Auto_Drama/output/handoff
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

import requests  # noqa: E402

from scripts.story_room.mv_strategy import MV_PUBLISH_CADENCE  # noqa: E402

TOONFLOW_URL = "http://192.168.2.200:12088"
COMFY_URL = "http://192.168.2.200:8188"
HANDOFF = Path("Y:/AI_Drama_Factory/Auto_Drama/output/handoff")
PYTHON = str(WORKSPACE / "venv" / "Scripts" / "python.exe")


def _call(script: str, args: list[str]) -> int:
    """Run a sibling pipeline script with the workspace interpreter."""
    cmd = [PYTHON, str(WORKSPACE / "scripts" / script), *args]
    print(f"[run] {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=WORKSPACE).returncode


def cmd_scripts(args: argparse.Namespace) -> int:
    """Regenerate the 3 topics x 5 variants story artifacts."""
    from scripts.story_room.experiment import run
    from scripts.story_room.mv_strategy import MV_VALIDATION_TOPICS

    mode = "--llm" if args.llm else "offline"
    print(f"[scripts] {len(MV_VALIDATION_TOPICS)} topics x 5 variants ({mode})")
    results = run(list(MV_VALIDATION_TOPICS), n=5, offline=not args.llm,
                  force=args.force)
    failed = [
        (topic, entry.get("error", "did not pass"))
        for topic, entries in results["topics"].items()
        for entry in entries
        if not entry.get("pass")
    ]
    if failed:
        for topic, reason in failed:
            print(f"[FAIL] {topic}: {reason}")
        return 1
    print("[scripts] all variants passed the world-first contract")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """Import the validated variants into the Mac Toonflow for CEO review."""
    return _call("import_to_toonflow.py", ["--base", args.toonflow])


def cmd_render(args: argparse.Namespace) -> int:
    """Dispatch one variant to the Mac render inbox."""
    argv = ["--topic", args.topic, "--variant", str(args.variant)]
    if args.master_track:
        argv += ["--master-track", args.master_track]
    if args.limit_shots:
        argv += ["--limit-shots", str(args.limit_shots)]
    if args.limit_units:
        argv += ["--limit-units", str(args.limit_units)]
    if args.steps:
        argv += ["--steps", str(args.steps)]
    return _call("pipeline/dispatch_to_mac.py", argv)


def cmd_novel(args: argparse.Namespace) -> int:
    """Export every variant as a readable chapter script (novel format)."""
    from scripts.story_room.novel_format import load_variant, render_novel

    expand = None
    if getattr(args, "llm", False):
        from scripts.story_room.novel_llm import expand_prose

        expand = expand_prose
        print("[novel] LLM prose expansion ENABLED (DeepSeek)")

    out_root = WORKSPACE / "Auto_Drama" / "output" / "sandbox" / "story_room" / "novel_review"
    out_root.mkdir(parents=True, exist_ok=True)
    written = 0
    for topic in args.topics:
        chapters = [
            f"# {topic} — 5 種世界呈現方式\n",
            "> 世界即主角、零對白、零角色累積。以下每一版都是同一座世界的另一種觀看方式。\n",
        ]
        for variant in range(1, args.variants + 1):
            story = load_variant(topic, variant)
            prose = expand(story) if expand else None
            chapters.append("\n---\n")
            chapters.append(render_novel(story, prose=prose))
            written += 1
        target = out_root / f"{topic}.md"
        target.write_text("\n".join(chapters), encoding="utf-8")
        print(f"NOVEL {topic} -> {target} ({args.variants} versions)")
    print(f"NOVEL_TOTAL {written}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Report the whole pipeline: review surface, render queue, handoff buckets."""
    print("=== PUBLISH CADENCE (CEO ruling 2026-09-11) ===")
    print(f"  {MV_PUBLISH_CADENCE['episodes_per_channel_per_week']} episode(s) per "
          f"channel per week at {MV_PUBLISH_CADENCE['resolution']} / "
          f"{MV_PUBLISH_CADENCE['fps']}fps / ~{MV_PUBLISH_CADENCE['target_duration_sec']}s")
    print(f"  channels: {', '.join(MV_PUBLISH_CADENCE['channels'])}")

    print("=== REVIEW SURFACE (Mac Toonflow) ===")
    try:
        session = requests.Session()
        login = session.post(
            f"{args.toonflow}/api/login/login",
            json={"username": "admin", "password": "admin123"}, timeout=30,
        ).json()
        token = (login.get("data") or {}).get("token")
        if not token:
            print(f"  login failed: {login.get('message')}")
        else:
            headers = {"Authorization": token}
            projects = session.post(
                f"{args.toonflow}/api/project/getProject", headers=headers, timeout=60
            ).json().get("data") or []
            print(f"  projects: {len(projects)}")
            for project in projects:
                scripts = session.post(
                    f"{args.toonflow}/api/script/getScrptApi",
                    json={"projectId": project.get("id")}, headers=headers, timeout=60,
                ).json().get("data") or []
                print(f"    - {project.get('name')} ({len(scripts)} scripts)")
    except Exception as exc:  # noqa: BLE001 - status must never crash
        print(f"  unreachable: {exc}")

    print("=== RENDER ENGINE (Mac ComfyUI) ===")
    try:
        queue = requests.get(f"{args.comfy}/queue", timeout=25).json()
        running = queue.get("queue_running") or []
        pending = queue.get("queue_pending") or []
        print(f"  running={len(running)} pending={len(pending)}")
        for item in running:
            graph = item[2]
            latent = graph.get("6", {}).get("inputs", {})
            print(f"    rendering {item[1][:12]} "
                  f"{latent.get('width')}x{latent.get('height')} "
                  f"{latent.get('length')}f")
    except Exception as exc:  # noqa: BLE001
        print(f"  unreachable: {exc}")

    print("=== HANDOFF QUEUE (shared volume) ===")
    if not HANDOFF.exists():
        print(f"  not mounted: {HANDOFF}")
        return 1
    for bucket in ("inbox", "processing", "done", "failed"):
        entries = sorted((HANDOFF / bucket).glob("*"))
        print(f"  {bucket}: {len(entries)}")
    for status_file in sorted((HANDOFF / "done").glob("*/status.json")):
        payload = json.loads(status_file.read_text(encoding="utf-8"))
        print(f"    done {payload.get('job_id')} -> {payload.get('output')} "
              f"({payload.get('size')}, {payload.get('duration_sec')}s, "
              f"{payload.get('elapsed_sec')}s render)")
    for status_file in sorted((HANDOFF / "failed").glob("*/status.json")):
        payload = json.loads(status_file.read_text(encoding="utf-8"))
        print(f"    FAILED {payload.get('job_id')}: {payload.get('error')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toonflow", default=TOONFLOW_URL)
    parser.add_argument("--comfy", default=COMFY_URL)
    sub = parser.add_subparsers(dest="command", required=True)

    p_scripts = sub.add_parser("scripts", help="regenerate 3x5 story artifacts")
    p_scripts.add_argument("--llm", action="store_true", help="use the DeepSeek writer")
    p_scripts.add_argument("--force", action="store_true")
    p_scripts.set_defaults(func=cmd_scripts)

    p_review = sub.add_parser("review", help="import variants into Mac Toonflow")
    p_review.set_defaults(func=cmd_review)

    p_render = sub.add_parser("render", help="dispatch a variant to the Mac renderer")
    p_render.add_argument("--topic", required=True)
    p_render.add_argument("--variant", type=int, required=True)
    p_render.add_argument("--master-track", help="CEO-approved master track (Y: path)")
    p_render.add_argument("--limit-shots", type=int)
    p_render.add_argument("--limit-units", type=int)
    p_render.add_argument("--steps", type=int, help="sampler steps override (throughput lever)")
    p_render.set_defaults(func=cmd_render)

    p_status = sub.add_parser("status", help="report the full pipeline state")
    p_status.set_defaults(func=cmd_status)

    p_novel = sub.add_parser("novel", help="export chapter scripts in novel format")
    p_novel.add_argument(
        "--topics", nargs="+",
        # Current validation batch (2026-09-11): rotate this list when the batch moves on.
        default=["湖光微火", "伸展台之夢", "華服荒原"],
    )
    p_novel.add_argument(
        "--llm", action="store_true",
        help="expand the body prose with DeepSeek (cached per variant)",
    )
    p_novel.add_argument("--variants", type=int, default=5)
    p_novel.set_defaults(func=cmd_novel)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
