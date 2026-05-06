#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CTO 假發行壓力測試：在 Y:/Long_Queue 可寫時，連續呼叫 publish_final_exports(mode=auto)，
驗證原子邊車寫入與 MP4／JSON 配對。

前置：subst 或 SMB 掛載 Y:；final_exports/{channel} 五檔齊全。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Sidecar 連續發行壓力測試")
    p.add_argument("--runs", type=int, default=5, help="連續執行次數")
    p.add_argument("--channel", type=str, default="lofi", choices=["lofi", "light_music"])
    args = p.parse_args()

    if not Path("Y:/").exists():
        print("SKIP: Y: 不存在。請以 subst 或 SMB 掛載本機目錄為 Y: 後再執行。")
        return 2

    from scripts.ui.backend import get_ui_backend

    backend = get_ui_backend()
    backend.set_channel(args.channel)

    for i in range(1, args.runs + 1):
        print(f"[{i}/{args.runs}] publish_final_exports(mode=auto)...")
        res = backend.publish_final_exports(channel=args.channel, mode="auto")
        if not res.get("ok"):
            print("FAIL:", res.get("msg"))
            return 1
        vid = Path(res["video_path"])
        side = vid.with_suffix(".json")
        tmp = side.with_name(side.name + ".tmp")
        if tmp.exists():
            print("FAIL: 殘留原子暫存檔", tmp)
            return 1
        if not side.exists():
            print("FAIL: 缺少邊車", side)
            return 1
        try:
            body = json.loads(side.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print("FAIL: JSON 無法解析", side, e)
            return 1

        from scripts.common.long_queue_sidecar_v1 import validate_long_upload_v1

        ok_v, err_v = validate_long_upload_v1(body, vid.name)
        if not ok_v:
            print("FAIL: preflight", err_v)
            return 1

        for key in (
            "schema_version",
            "video_file",
            "title",
            "description",
            "privacy",
            "categoryId",
            "tags",
            "notifySubscribers",
            "idempotency_key",
            "source_system",
            "created_at",
            "auto_publish_enabled",
            "containsSyntheticMedia",
            "selfDeclaredMadeForKids",
        ):
            if key not in body:
                print("FAIL: 缺少欄位", key, "in", side)
                return 1
        if body.get("schema_version") != "long-upload-v1":
            print("FAIL: schema_version 應為 long-upload-v1")
            return 1
        if body.get("auto_publish_enabled") is not True:
            print("FAIL: auto_publish_enabled 應為 true (mode=auto)")
            return 1
        if body.get("privacy") != "public":
            print("FAIL: mode=auto 時 privacy 應為 public")
            return 1
        if not vid.exists() or vid.stat().st_size <= 0:
            print("FAIL: MP4 不存在或為空", vid)
            return 1
        print("  OK:", vid.name, "<->", side.name)

    print("ALL_OK:", args.runs, "runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
