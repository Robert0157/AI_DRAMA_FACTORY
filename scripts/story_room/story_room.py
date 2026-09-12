"""Story Room v2 CLI - draft a story-first MV scaffold from the topic bank.

Usage:
    python scripts/story_room/story_room.py --topic 燈塔守夜人 \
        [--beats beats.json] [--world lofi] [--target-sec 175] \
        [--n-shots 6] [--out draft.json]

Hard rule: this tool NEVER calls a video-generation API (Seedance freeze). It
writes text/JSON drafts only; generation happens later via the normal pipeline
after CEO approval.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a plain script: add the package parent (scripts/) to sys.path.
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from story_room import (  # noqa: E402
    build_draft,
    build_scaffold,
    format_report,
    get_topic,
    review,
    sheet_from_dict,
    top10,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Story Room v2 (draft only, no generation)")
    ap.add_argument("--topic", required=True, help="topic name from the bank, or free text")
    ap.add_argument("--beats", default=None, help="authored beat-sheet JSON (optional)")
    ap.add_argument("--world", default="lofi", choices=("lofi", "light_music"))
    ap.add_argument("--episode-id", default="epXX")
    ap.add_argument("--target-sec", type=float, default=175.0)
    ap.add_argument("--n-shots", type=int, default=6)
    ap.add_argument("--out", default=None, help="write draft JSON here (omit for preview only)")
    ap.add_argument("--list-top10", action="store_true", help="print the CEO top-10 and exit")
    args = ap.parse_args()

    if args.list_top10:
        for t in top10():
            print(f"{t.name} | {t.channel} | {t.style} | {t.difficulty}")
        return

    topic = get_topic(args.topic)
    hook = topic.hook if topic else ""
    if args.beats:
        sheet = sheet_from_dict(json.loads(Path(args.beats).read_text(encoding="utf-8")))
    else:
        sheet = build_scaffold(args.topic, target_sec=args.target_sec, hook=hook)

    draft = build_draft(
        sheet,
        world=args.world,
        episode_id=args.episode_id,
        n_shots=args.n_shots,
    )
    result = review(draft)
    print(format_report(result))
    print(f"SHOTS {len(draft['shots'])} | TOTAL {sheet.target_sec:.1f}s | TOPIC {sheet.topic}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(draft, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"WROTE {out}")


if __name__ == "__main__":
    main()
