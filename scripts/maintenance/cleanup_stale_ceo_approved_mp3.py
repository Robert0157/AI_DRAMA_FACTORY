#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
已母帶且已上 Mac Shorts 倉、在 CEO 收件匣超過 N 小時的 MP3 — 可自動刪除（需 --apply）。

三條件（全滿足才刪，預設僅列印＋寫 log，不刪）：
  1) 本機 mastered_tracks/{channel}/ 已存在對應 {sanitize(stem)}_YT_*.wav
  2) Y:/Shorts_audio/{channel}/ 上存在**同名**母帶 WAV（與 audio_mastering_engine 同步邏輯一致）
  3) CEO 資料夾內該 .mp3 的 mtime 距離現在 >= --hours（預設 48）

若 Y: 未掛載，無法驗證 (2)，本腳本**不刪除**（保守）。

日誌：assets/.logs/ceo_approved_stale_purge.log
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.path_sanitize import sanitize_filename  # noqa: E402

LOG_REL = Path("assets") / ".logs" / "ceo_approved_stale_purge.log"
SHORTS_ROOT_WIN = Path("Y:/Shorts_audio")


def _append_log(workspace_root: Path, line: str) -> None:
    log_path = workspace_root / LOG_REL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {line}\n")


def resolve_mastered_wav(mp3: Path, workspace_root: Path, channel: str) -> Optional[Path]:
    """對應 audio_mastering_engine：{sanitize(stem)}_YT_*.wav"""
    safe = sanitize_filename(mp3.stem)
    out_dir = workspace_root / "assets" / "audio" / "mastered_tracks" / channel.lower()
    if not out_dir.is_dir():
        return None
    matches = sorted(out_dir.glob(f"{safe}_YT_*.wav"), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def mac_synced_path(master_wav: Path, channel: str) -> Path:
    return SHORTS_ROOT_WIN / channel.lower() / master_wav.name


def scan_channel(
    workspace_root: Path,
    channel: str,
    hours: float,
    apply: bool,
) -> Tuple[int, int, List[str]]:
    """
    Returns: (would_delete_or_deleted, skipped, lines for stdout)
    """
    ceo_dir = workspace_root / "assets" / "audio" / "ceo_approved_beats" / channel.lower()
    lines: List[str] = []
    acted = 0
    skipped = 0

    if not ceo_dir.is_dir():
        lines.append(f"[{channel}] 目錄不存在，略過")
        return 0, 0, lines

    smb_ok = SHORTS_ROOT_WIN.exists()
    if not smb_ok:
        msg = "Y:/Shorts_audio 不可用（未掛載 SMB），無法驗證 Mac 同步 — 本輪不刪任何 CEO MP3"
        lines.append(msg)
        _append_log(workspace_root, f"SKIP_SESSION smb_missing channel={channel}")

    cutoff = time.time() - (hours * 3600.0)
    mp3s = sorted(ceo_dir.glob("*.mp3"))

    for mp3 in mp3s:
        try:
            rel = mp3.relative_to(workspace_root)
        except ValueError:
            rel = mp3
        master = resolve_mastered_wav(mp3, workspace_root, channel)
        if not master:
            skipped += 1
            _append_log(workspace_root, f"SKIP_NO_MASTER {rel}")
            lines.append(f"  SKIP no_master: {mp3.name}")
            continue

        if not smb_ok:
            skipped += 1
            _append_log(workspace_root, f"SKIP_NO_SMB {rel} mastered={master.name}")
            continue

        mac_dst = mac_synced_path(master, channel)
        if not mac_dst.is_file():
            skipped += 1
            _append_log(
                workspace_root,
                f"SKIP_NOT_ON_MAC {rel} expect_mac={mac_dst}",
            )
            lines.append(f"  SKIP not_on_mac: {mp3.name} (need {mac_dst.name})")
            continue

        mtime = mp3.stat().st_mtime
        if mtime > cutoff:
            skipped += 1
            age_h = (time.time() - mtime) / 3600.0
            _append_log(
                workspace_root,
                f"SKIP_TOO_FRESH {rel} age_hours={age_h:.2f} need>={hours}h",
            )
            lines.append(f"  SKIP fresh ({age_h:.1f}h < {hours}h): {mp3.name}")
            continue

        age_h = (time.time() - mtime) / 3600.0
        if apply:
            try:
                mp3.unlink()
                acted += 1
                _append_log(
                    workspace_root,
                    f"DELETED {rel} master={master.name} mac_ok age_hours={age_h:.2f}",
                )
                lines.append(f"  DELETED: {mp3.name} (age {age_h:.1f}h)")
            except OSError as e:
                _append_log(workspace_root, f"FAIL_DELETE {rel} err={e}")
                lines.append(f"  FAIL: {mp3.name} {e}")
        else:
            acted += 1
            _append_log(
                workspace_root,
                f"DRY_RUN_WOULD_DELETE {rel} master={master.name} age_hours={age_h:.2f}",
            )
            lines.append(
                f"  DRY-RUN would delete: {mp3.name} (age {age_h:.1f}h) [use --apply]"
            )

    return acted, skipped, lines


def main() -> int:
    parser = argparse.ArgumentParser(description="清理逾時且已母帶＋已上 Mac 的 CEO MP3")
    parser.add_argument(
        "--workspace",
        type=str,
        default=str(_PROJECT_ROOT),
        help="專案根目錄",
    )
    parser.add_argument(
        "--channel",
        choices=["lofi", "light_music", "all"],
        default="all",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=48.0,
        help="MP3 在 CEO 資料夾內最後修改時間須至少距今若干小時（預設 48）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="實際刪除（預設僅 dry-run + 寫 log）",
    )
    args = parser.parse_args()
    workspace_root = Path(args.workspace).resolve()

    channels = ["lofi", "light_music"] if args.channel == "all" else [args.channel]
    total_act = 0
    total_skip = 0
    print("=" * 70)
    print("cleanup_stale_ceo_approved_mp3 — CEO 收件匣逾時清理")
    print(f"workspace={workspace_root}")
    print(f"hours>={args.hours}, apply={args.apply}")
    print("=" * 70)

    for ch in channels:
        print(f"\n### channel={ch}")
        act, sk, lines = scan_channel(workspace_root, ch, args.hours, args.apply)
        total_act += act
        total_skip += sk
        for ln in lines:
            print(ln)

    print("\n" + "=" * 70)
    print(f"摘要: match={'刪除/將刪' if args.apply else 'dry-run 筆數'}={total_act}, skipped={total_skip}")
    print(f"日誌: {workspace_root / LOG_REL}")
    _append_log(workspace_root, f"SESSION_END apply={args.apply} acted={total_act} skipped={total_skip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
