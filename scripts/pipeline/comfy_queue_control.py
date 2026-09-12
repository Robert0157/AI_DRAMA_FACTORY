#!/usr/bin/env python3
"""Emergency controls for the local ComfyUI queue (no third-party deps).

Used when a render job must be swapped out: interrupt the running prompt and
clear everything still pending, then verify the queue is empty.

Usage (on the ComfyUI host):
  python3 comfy_queue_control.py --status --interrupt --clear
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8188"


def _get(path: str) -> str:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as response:
        return response.read().decode("utf-8", "replace")


def _post(path: str, payload: dict | None = None) -> str:
    data = json.dumps(payload).encode("utf-8") if payload is not None else b""
    request = urllib.request.Request(f"{BASE}{path}", data=data, method="POST")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="print queue depth")
    parser.add_argument("--interrupt", action="store_true", help="stop the running prompt")
    parser.add_argument("--clear", action="store_true", help="drop all pending prompts")
    args = parser.parse_args()

    try:
        if args.status:
            queue = json.loads(_get("/queue"))
            running = len(queue.get("queue_running") or [])
            pending = len(queue.get("queue_pending") or [])
            print(f"QUEUE running={running} pending={pending}")
        if args.interrupt:
            _post("/interrupt")
            print("INTERRUPTED")
        if args.clear:
            _post("/queue", {"clear": True})
            print("CLEARED")
        if args.status:
            queue = json.loads(_get("/queue"))
            running = len(queue.get("queue_running") or [])
            pending = len(queue.get("queue_pending") or [])
            print(f"AFTER running={running} pending={pending}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[FATAL] ComfyUI unreachable: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
