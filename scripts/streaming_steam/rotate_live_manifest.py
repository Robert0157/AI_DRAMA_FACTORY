#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
輪換 OBC 直播槽位：以 **added_at 最小**（同分則 **slot** 較小）選出一格，
將該格 queue 內舊檔移至 frozen_broadcast/，再把 queue_staging/ 內新歌 mv 進 queue/，
最後原子寫回 live_manifest.json（僅更新該筆 entry 的 file + added_at）。

不依賴產線 Python；僅標準庫。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _parse_added_at(raw: str) -> datetime:
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_basename(name: str) -> str:
    base = Path(name).name
    if base != name or "/" in name or "\\" in name or not base.strip():
        _die(f"❌ 僅允許純檔名（不可含路徑）：{name!r}")
    return base


def _unique_frozen_path(frozen_dir: Path, old_base: str) -> Path:
    stem = Path(old_base).stem
    suf = Path(old_base).suffix or ".mp4"
    dest = frozen_dir / old_base
    if not dest.exists():
        return dest
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return frozen_dir / f"{stem}_retired_{ts}{suf}"


def load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        _die(f"❌ 找不到 manifest：{path}")
    except json.JSONDecodeError as e:
        _die(f"❌ JSON 解析失敗：{path}\n   {e}")


def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _probe_av_signature(path: Path) -> tuple[str, str, str, str]:
    ffprobe_bin = (
        shutil.which("ffprobe")
        or ("/opt/homebrew/bin/ffprobe" if Path("/opt/homebrew/bin/ffprobe").is_file() else None)
        or ("/usr/local/bin/ffprobe" if Path("/usr/local/bin/ffprobe").is_file() else None)
    )
    if not ffprobe_bin:
        _die("❌ 找不到 ffprobe（請先安裝 ffmpeg/ffprobe）")

    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_streams",
        "-print_format",
        "json",
        str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
    except subprocess.CalledProcessError as ex:
        _die(f"❌ ffprobe 失敗：{path}\n{ex.stderr.strip()}")
    except subprocess.TimeoutExpired:
        _die(f"❌ ffprobe 逾時：{path}")

    try:
        data = json.loads(out.stdout or "{}")
    except json.JSONDecodeError as ex:
        _die(f"❌ ffprobe 輸出非 JSON：{path} ({ex})")

    streams = data.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v or not a:
        _die(f"❌ 檔案必須同時包含視訊與音訊：{path}")

    v_codec = str(v.get("codec_name") or "")
    v_pix = str(v.get("pix_fmt") or "")
    a_rate = str(a.get("sample_rate") or "")
    a_ch = str(a.get("channels") or "")
    if not all([v_codec, v_pix, a_rate, a_ch]):
        _die(f"❌ ffprobe 取得關鍵欄位不足：{path}")
    return (v_codec, v_pix, a_rate, a_ch)


def _check_compatibility(new_file: Path, refs: list[Path]) -> None:
    new_sig = _probe_av_signature(new_file)
    for ref in refs:
        ref_sig = _probe_av_signature(ref)
        if ref_sig != new_sig:
            _die(
                "❌ ffprobe 相容性檢查失敗：\n"
                f"   new={new_file.name} sig={new_sig}\n"
                f"   ref={ref.name} sig={ref_sig}\n"
                "   需一致欄位：video codec / pix_fmt / audio sample_rate / audio channels"
            )


def main() -> None:
    ap = argparse.ArgumentParser(description="Rotate live slot: min added_at → mv old to frozen, new from staging")
    ap.add_argument(
        "--streaming-root",
        "--steam-root",
        type=Path,
        dest="streaming_root",
        required=True,
        help="Streaming/ 根目錄；--steam-root 為舊別名",
    )
    ap.add_argument("--manifest", type=Path, default=None, help="預設：Streaming/config/live_manifest.json")
    ap.add_argument("--new-file", type=str, required=True, help="queue_staging/ 內之新檔純檔名，例如 hour_new.mp4")
    ap.add_argument("--dry-run", action="store_true", help="只印出將替換哪一格，不搬檔、不寫 manifest")
    ap.add_argument(
        "--retire-mode",
        choices=("deferred", "immediate"),
        default="deferred",
        help="deferred: 舊檔先留在 queue，交由後續清理；immediate: 立即搬到 frozen_broadcast",
    )
    args = ap.parse_args()

    streaming_root = args.streaming_root.resolve()
    manifest_path = (args.manifest or (streaming_root / "config" / "live_manifest.json")).resolve()
    queue = streaming_root / "queue"
    staging_dir = streaming_root / "queue_staging"
    frozen_dir = streaming_root / "frozen_broadcast"

    new_base = _safe_basename(args.new_file)
    staging_file = (staging_dir / new_base).resolve()
    if not staging_file.is_file():
        _die(f"❌ staging 找不到檔案：{staging_file}")
    try:
        staging_file.relative_to(staging_dir.resolve())
    except ValueError:
        _die("❌ staging 路徑越界")

    data = load_manifest(manifest_path)
    if data.get("schema_version") != 1:
        _die(f"❌ 不支援的 schema_version：{data.get('schema_version')!r}")

    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        _die("❌ manifest.entries 必須為非空陣列")

    parsed: list[tuple[datetime, int, int, dict]] = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            _die(f"❌ entries[{i}] 必須為物件")
        slot = e.get("slot")
        if not isinstance(slot, int) or slot < 1:
            _die(f"❌ entries[{i}].slot 無效")
        added = e.get("added_at")
        if not isinstance(added, str) or not added.strip():
            _die(f"❌ entries[{i}] 缺少 added_at（輪換需 ISO-8601 字串，例如 2026-04-19 或 2026-04-19T12:00:00Z）")
        try:
            ts = _parse_added_at(added)
        except ValueError as ex:
            _die(f"❌ entries[{i}].added_at 無法解析：{added!r} ({ex})")
        parsed.append((ts, slot, i, e))

    # 最小 added_at；同時間則 slot 較小者優先（確定式）
    parsed.sort(key=lambda x: (x[0], x[1]))
    victim_ts, victim_slot, victim_idx, victim_entry = parsed[0]
    old_base = _safe_basename(str(victim_entry.get("file", "")))
    if not old_base:
        _die("❌ 被替換槽位 file 無效")
    if new_base == old_base:
        _die("❌ 新檔檔名不可與被替換槽位舊檔同名（請先更名 staging 檔）")

    for j, e in enumerate(entries):
        if j != victim_idx and isinstance(e.get("file"), str) and _safe_basename(e["file"]) == new_base:
            _die(f"❌ 其他槽位已使用檔名 {new_base!r}，請更名 staging 檔")

    queue_old = (queue / old_base).resolve()
    if not queue_old.is_file():
        _die(f"❌ queue 內找不到現播檔（slot {victim_slot}）：{queue_old}")

    # 輪換前相容性檢查：新檔需與其餘在播檔維持相同 AV 簽名
    refs: list[Path] = []
    for j, e in enumerate(entries):
        if j == victim_idx:
            continue
        ref_base = _safe_basename(str(e.get("file", "")))
        ref_path = (queue / ref_base).resolve()
        if not ref_path.is_file():
            _die(f"❌ 相容性參考檔不存在（slot {e.get('slot')}）：{ref_path}")
        refs.append(ref_path)
    if refs:
        _check_compatibility(staging_file, refs)
        print(f"✅ ffprobe 相容性檢查通過（對比 {len(refs)} 支在播檔）")
    else:
        print("ℹ️  僅單槽位或無參考檔，略過 ffprobe 相容性比對。")

    print(
        f"ℹ️  將替換 slot={victim_slot} added_at={victim_entry.get('added_at')!r} old_file={old_base!r} "
        f"→ new_file={new_base!r}"
    )

    if args.dry_run:
        print("ℹ️  --dry-run：未搬檔、未寫 manifest。")
        return

    frozen_dir.mkdir(parents=True, exist_ok=True)
    frozen_dest = _unique_frozen_path(frozen_dir, old_base)
    queue_new = (queue / new_base).resolve()

    if queue_new.exists():
        _die(f"❌ queue 已存在同名檔：{new_base}")

    shutil.move(str(staging_file), str(queue_new))
    retired_msg = ""
    if args.retire_mode == "immediate":
        shutil.move(str(queue_old), str(frozen_dest))
        retired_msg = f"✅ 已將舊檔移至 {frozen_dest}"
    else:
        retired_msg = f"ℹ️  deferred retire：舊檔暫留 queue（待清理）：{queue_old.name}"

    victim_entry["file"] = new_base
    victim_entry["added_at"] = _utc_now_iso()

    atomic_write_json(manifest_path, data)
    print(f"✅ 已將新歌移入 {queue_new}")
    print(retired_msg)
    print(f"✅ 已更新 {manifest_path}（slot {victim_slot}）")


if __name__ == "__main__":
    main()
