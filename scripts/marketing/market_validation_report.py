#!/usr/bin/env python3
"""Weekly market-validation report (distribution cadence + YouTube growth + grade calls).

Outputs to CEO/05_市場驗證/<ISO-week>/: report_md + metrics.json (naming-rule compliant
fixed names: 報告.md / metrics.json). Optionally pushes a Telegram digest.

Data sources:
  - distribution_ledger.py  (cadence: expected vs actual, staleness)
  - market_feedback.db      (views/likes/comments snapshots from yt_metrics_collector.py)
  - configs/market_validation_policy.json (thresholds & grade rules)

Phase-2 note: retention/CTR need the YouTube Analytics API (OAuth scope
yt-analytics.readonly) - out of scope for this phase.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.marketing.distribution_ledger import (  # noqa: E402
    DEFAULT_POLICY,
    cadence_report,
    collect_entries,
    resolve_mac_root,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "assets" / "data" / "market_feedback.db"
DEFAULT_OUT_ROOT = REPO_ROOT / "CEO" / "05_市場驗證"
TELEGRAM_SENDER = REPO_ROOT / "scripts" / "telegram" / "telegram_text_send.py"


def iso_week_label(when: datetime) -> str:
    year, week, _ = when.isocalendar()
    return f"{year}-W{week:02d}"


def load_policy(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def grade_for(kind: str, views_7d: int, like_rate_pct: float, policy: dict[str, Any]) -> str:
    """First matching rule wins; falls back to the last rule's grade."""
    rules = (policy.get(kind) or {}).get("grade_rules") or []
    fallback = "retire"
    for rule in rules:
        min_views = int(rule.get("min_views_7d", 0))
        min_like = float(rule.get("min_like_rate_pct", 0.0))
        if views_7d >= min_views and (min_like <= 0.0 or like_rate_pct >= min_like):
            return str(rule.get("grade", fallback))
    return fallback


def _row_to_video(row: sqlite3.Row | tuple) -> dict[str, Any]:
    return {"video_id": row[0], "channel": row[1], "kind": row[2], "title": row[3]}


def load_videos(conn: sqlite3.Connection, now: datetime) -> list[dict[str, Any]]:
    """Latest snapshot + ~7d-ago baseline per video -> views_7d and like rate."""
    conn.row_factory = sqlite3.Row
    videos = conn.execute(
        "SELECT video_id, channel, kind, title, published_at, first_seen_ts FROM videos"
    ).fetchall()
    cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[dict[str, Any]] = []
    for video in videos:
        vid = video["video_id"]
        latest = conn.execute(
            "SELECT ts, views, likes, comments FROM snapshots WHERE video_id=? ORDER BY ts DESC LIMIT 1",
            (vid,),
        ).fetchone()
        if latest is None:
            continue
        baseline = conn.execute(
            "SELECT views, likes FROM snapshots WHERE video_id=? AND ts<=? ORDER BY ts DESC LIMIT 1",
            (vid, cutoff),
        ).fetchone()
        views_latest = int(latest["views"])
        views_7d = views_latest - (int(baseline["views"]) if baseline else 0)
        likes_latest = int(latest["likes"])
        like_rate = (likes_latest / views_latest * 100.0) if views_latest > 0 else 0.0
        out.append(
            {
                "video_id": vid,
                "channel": video["channel"],
                "kind": video["kind"],
                "title": video["title"],
                "published_at": video["published_at"],
                "views_total": views_latest,
                "views_7d": max(0, views_7d),
                "likes_total": likes_latest,
                "comments_total": int(latest["comments"]),
                "like_rate_pct": round(like_rate, 2),
                "snapshot_ts": latest["ts"],
            }
        )
    out.sort(key=lambda v: v["views_7d"], reverse=True)
    return out


def build_report(
    cadence: dict[str, Any], videos: list[dict[str, Any]], policy: dict[str, Any], now: datetime
) -> tuple[str, dict[str, Any]]:
    """Compose (markdown, machine payload)."""
    week = iso_week_label(now)
    lines: list[str] = [f"# 市場驗證週報 {week}", "", f"生成時間（UTC）：{now.strftime('%Y-%m-%dT%H:%M:%SZ')}", ""]

    lines.append("## 1. 分發節奏（近 14 天）")
    lines.append("")
    lines.append("| 頻道 | 類型 | 實際上傳 | 預期 | 最後上傳 | 距今天數 | 警示 |")
    lines.append("|---|---|---|---|---|---|---|")
    for channel, info in cadence.get("channels", {}).items():
        if not info.get("enabled", True):
            lines.append(f"| {channel} | - | - | - | - | - | 停用（{info.get('note', '')}） |")
            continue
        age_days = "-" if info.get("age_hours") is None else f"{info['age_hours'] / 24:.1f}"
        flags = ", ".join(info.get("alerts", [])) or "ok"
        lines.append(
            f"| {channel} | {info.get('kind', '')} | {info['actual_14d']} | {info['expected_14d']} "
            f"| {info.get('last_ts', '') or 'never'} | {age_days} | {flags} |"
        )
    if cadence.get("alerts"):
        lines.append("")
        for alert in cadence["alerts"]:
            lines.append(f"- ⚠ {alert}")
    lines.append("")

    lines.append("## 2. 市場表現（YouTube 公開統計）")
    lines.append("")
    if not videos:
        lines.append("尚無數據：需設定 `YT_DATA_API_KEY`（Mac: `market_validation.env`）後由 `yt_metrics_collector.py` 回收。")
    else:
        grades = {"scale": [], "iterate": [], "retire": []}
        for video in videos:
            video["grade"] = grade_for(video["kind"], video["views_7d"], video["like_rate_pct"], policy)
            grades.setdefault(video["grade"], []).append(video)
        lines.append(f"共 {len(videos)} 支有數據。近 7 日成長前 10：")
        lines.append("")
        lines.append("| # | 頻道 | 標題 | 7日觀看 | 總觀看 | 讚/觀看 | 評級 |")
        lines.append("|---|---|---|---|---|---|---|")
        for idx, video in enumerate(videos[:10], 1):
            title = video["title"][:42].replace("|", "｜")
            lines.append(
                f"| {idx} | {video['channel']} | {title} | {video['views_7d']} | {video['views_total']} "
                f"| {video['like_rate_pct']}% | {video['grade']} |"
            )
        lines.append("")
        lines.append(
            f"**評級統計**：scale {len(grades.get('scale', []))}／iterate {len(grades.get('iterate', []))}／"
            f"retire {len(grades.get('retire', []))}"
        )
        scale_list = grades.get("scale", [])[:5]
        if scale_list:
            lines.append("")
            lines.append("### 建議放大（scale）")
            for video in scale_list:
                lines.append(f"- {video['channel']}｜{video['title'][:48]}｜7日 {video['views_7d']} 觀看")
    lines.append("")

    lines.append("## 3. 決策規則（依 `configs/market_validation_policy.json`）")
    lines.append("")
    lines.append("- **scale**：達標 → 同題材/風格加開、排入優先上傳")
    lines.append("- **iterate**：中間帶 → 只改 metadata（標題/縮圖/描述）再觀察一週")
    lines.append("- **retire**：低於門檻 → 該題材停止投入，題材庫標記淘汰")
    lines.append("")

    lines.append("## 4. 已知限制（Phase 2）")
    lines.append("")
    lines.append("- 續看率/CTR 需 YouTube Analytics API（OAuth `yt-analytics.readonly`）：待與上傳 OAuth 合併開通")
    lines.append("- B 線頻道（auto_drama）尚未上線：上線後於 policy 啟用 cadence")
    lines.append("")

    payload = {
        "schema": "market_validation.report.v1",
        "week": week,
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cadence": cadence,
        "videos": videos,
        "grade_counts": {
            "scale": sum(1 for v in videos if v.get("grade") == "scale"),
            "iterate": sum(1 for v in videos if v.get("grade") == "iterate"),
            "retire": sum(1 for v in videos if v.get("grade") == "retire"),
        },
    }
    return "\n".join(lines), payload


def notify_telegram(text: str) -> None:
    """Best-effort digest via the shared Mac sender (skipped when absent, e.g. on PC)."""
    if not TELEGRAM_SENDER.is_file():
        print("[info] telegram sender not found; digest printed only")
        return
    env = dict(os.environ)
    env.setdefault(
        "TELEGRAM_ENV_FILE",
        str(Path.home() / "Library/Application Support/AI_Drama_Factory/telegram_queue_notify.env"),
    )
    code = subprocess.call([sys.executable, str(TELEGRAM_SENDER), text], env=env)
    if code != 0:
        print(f"[warn] telegram send failed rc={code}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help=f"metrics db (default: {DEFAULT_DB})")
    parser.add_argument("--policy", help=f"policy file (default: {DEFAULT_POLICY})")
    parser.add_argument("--out-root", help=f"report root (default: {DEFAULT_OUT_ROOT})")
    parser.add_argument("--root", help="Mac workspace root (auto-detected)")
    parser.add_argument("--notify", action="store_true", help="push a Telegram digest")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    policy_path = Path(args.policy) if args.policy else DEFAULT_POLICY
    policy = load_policy(policy_path)

    mac_root = resolve_mac_root(args.root)
    entries, _bad = collect_entries(mac_root)
    cadence = cadence_report(entries, policy, now=now)

    db_path = Path(args.db) if args.db else DEFAULT_DB
    videos: list[dict[str, Any]] = []
    if db_path.is_file():
        conn = sqlite3.connect(str(db_path))
        try:
            videos = load_videos(conn, now)
        finally:
            conn.close()

    markdown, payload = build_report(cadence, videos, policy, now)
    out_root = Path(args.out_root) if args.out_root else DEFAULT_OUT_ROOT
    week_dir = out_root / payload["week"]
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "報告.md").write_text(markdown, encoding="utf-8")
    (week_dir / "metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"REPORT {payload['week']} videos={len(videos)} alerts={len(cadence.get('alerts', []))} -> {week_dir}")

    if args.notify:
        digest_lines = [f"[市場驗證週報 {payload['week']}]"]
        digest_lines.append(f"有數據影片：{len(videos)} 支；評級 scale/iterate/retire = "
                            f"{payload['grade_counts']['scale']}/{payload['grade_counts']['iterate']}/{payload['grade_counts']['retire']}")
        if cadence.get("alerts"):
            digest_lines.append("節奏警示：")
            digest_lines.extend(f"⚠ {a}" for a in cadence["alerts"][:5])
        if videos:
            top = videos[0]
            digest_lines.append(f"本週熱門：{top['channel']}｜{top['title'][:36]}｜7日 {top['views_7d']} 觀看")
        notify_telegram("\n".join(digest_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
