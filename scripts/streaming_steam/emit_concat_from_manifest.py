#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
從 Streaming/config/live_manifest.json 產生 FFmpeg concat demuxer 行（寫 stdout）。
每行格式：file '../queue/<basename>'（相對於 config/concat_playlist.txt 所在目錄）。

由 build_concat_playlist.sh 在偵測到 manifest 存在時呼叫。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        _die(f"❌ 找不到 manifest：{path}")
    except json.JSONDecodeError as e:
        _die(f"❌ JSON 解析失敗：{path}\n   {e}")


def validate_and_emit(*, streaming_root: Path, manifest: dict, out_lines: list[str]) -> None:
    ver = manifest.get("schema_version")
    if ver != 1:
        _die(f"❌ 不支援的 schema_version：{ver!r}（目前僅支援 1）")

    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        _die("❌ manifest 必須包含非空陣列 entries")

    expected = manifest.get("expected_slots")
    if expected is not None:
        if not isinstance(expected, int) or expected < 1:
            _die(f"❌ expected_slots 必須為正整數，目前為：{expected!r}")
        if len(entries) != expected:
            _die(f"❌ entries 筆數 {len(entries)} 與 expected_slots={expected} 不符")

    queue = streaming_root / "queue"
    if not queue.is_dir():
        _die(f"❌ 找不到 queue 目錄：{queue}")

    slots_seen: set[int] = set()
    files_seen: set[str] = set()  # v15.10 P3#12: 防止同一檔案被分配到多個 slot
    rows: list[tuple[int, str]] = []

    for i, raw in enumerate(entries):
        if not isinstance(raw, dict):
            _die(f"❌ entries[{i}] 必須為物件")
        slot = raw.get("slot")
        file_val = raw.get("file")
        if not isinstance(slot, int) or slot < 1:
            _die(f"❌ entries[{i}].slot 必須為 ≥1 的整數")
        if not isinstance(file_val, str) or not file_val.strip():
            _die(f"❌ entries[{i}].file 必須為非空字串")
        base = Path(file_val).name
        if base != file_val or "/" in file_val or "\\" in file_val:
            _die(f"❌ entries[{i}].file 僅允許純檔名（不可含路徑）：{file_val!r}")
        if slot in slots_seen:
            _die(f"❌ 重複的 slot：{slot}")
        slots_seen.add(slot)
        # v15.10 P3#12: 重複 file 防護
        if base in files_seen:
            _die(f"❌ 重複的 file：{base}（出現在多個 slot）")
        files_seen.add(base)

        abs_file = (queue / base).resolve()
        if not abs_file.is_file():
            _die(f"❌ queue 內找不到檔案：{base}（slot {slot}）")
        try:
            abs_file.relative_to(queue.resolve())
        except ValueError:
            _die(f"❌ 路徑越界：{abs_file}")

        rows.append((slot, base))

    rows.sort(key=lambda x: x[0])
    for _slot, base in rows:
        out_lines.append(f"file '../queue/{base}'")


def main() -> None:
    ap = argparse.ArgumentParser(description="Emit concat demuxer lines from live_manifest.json")
    ap.add_argument(
        "--streaming-root",
        "--steam-root",
        type=Path,
        dest="streaming_root",
        required=True,
        help="Streaming/ 根目錄（含 queue/、config/）；--steam-root 為舊別名",
    )
    ap.add_argument("--manifest", type=Path, required=True, help="live_manifest.json 路徑")
    args = ap.parse_args()

    streaming_root = args.streaming_root.resolve()
    manifest_path = args.manifest.resolve()
    data = load_manifest(manifest_path)

    lines: list[str] = []
    validate_and_emit(streaming_root=streaming_root, manifest=data, out_lines=lines)

    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
