#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【CEO 決策同步工具】v8.7

功能：
- CEO 在 Telegram 上已做決策但系統未記錄時使用
- 手動同步 CEO 的決策到 JSON 檔案
- 更新配額計數

用法：
  python sync_ceo_decisions.py "Midnight Margin" approve
  python sync_ceo_decisions.py "Vast Stillness" reject
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 工作目錄
WORKSPACE_ROOT = Path(__file__).resolve().parent
QUEUE_FILE = WORKSPACE_ROOT / "assets" / ".approval_queue.json"
QUOTA_FILE = WORKSPACE_ROOT / "assets" / ".daily_quota.json"

def sync_decision(track_name: str, decision: str) -> bool:
    """同步單一音軌決策"""
    
    if decision not in ["approve", "reject"]:
        print(f"❌ 無效決策: {decision} (必須是 approve 或 reject)")
        return False
    
    # 確保檔案存在
    if not QUEUE_FILE.exists():
        print(f"❌ 隊列檔案不存在: {QUEUE_FILE}")
        return False
    
    if not QUOTA_FILE.exists():
        print(f"❌ 配額檔案不存在: {QUOTA_FILE}")
        return False
    
    # 載入隊列
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        queue_data = json.load(f)
    
    # 尋找音軌
    track_record = None
    for record in queue_data.get("queue", []):
        if record["track_name"] == track_name:
            track_record = record
            break
    
    if not track_record:
        print(f"❌ 音軌不存在: {track_name}")
        print(f"   可用音軌: {[r['track_name'] for r in queue_data.get('queue', [])]}")
        return False
    
    if track_record["status"] != "pending":
        print(f"⚠️  音軌已處理 (狀態: {track_record['status']}): {track_name}")
        return False
    
    # 更新音軌狀態
    track_record["status"] = decision
    track_record["ceo_decision_at"] = datetime.now().isoformat(timespec="seconds")
    
    # 儲存隊列
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue_data, f, indent=2, ensure_ascii=False)
    
    # 更新配額
    with open(QUOTA_FILE, "r", encoding="utf-8") as f:
        quota_data = json.load(f)
    
    today = datetime.now().strftime("%Y-%m-%d")
    if today not in quota_data["quotas"]:
        quota_data["quotas"][today] = {
            "date": today,
            "approved_count": 0,
            "rejected_count": 0,
            "pending_count": 0,
            "approved_tracks": []
        }
    
    quota_today = quota_data["quotas"][today]
    
    if decision == "approve":
        quota_today["approved_count"] += 1
        quota_today["approved_tracks"].append(track_name)
        symbol = "✅"
    else:
        quota_today["rejected_count"] += 1
        symbol = "❌"
    
    quota_today["pending_count"] = max(0, quota_today["pending_count"] - 1)
    
    with open(QUOTA_FILE, "w", encoding="utf-8") as f:
        json.dump(quota_data, f, indent=2, ensure_ascii=False)
    
    print(f"{symbol} {track_name} → {decision} ✓")
    print(f"   當日進度: {quota_today['approved_count']}/10 採用, {quota_today['rejected_count']} 拒絕")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    
    track_name = sys.argv[1]
    decision = sys.argv[2].lower()
    
    if sync_decision(track_name, decision):
        print("\n✅ 同步完成\n")
        sys.exit(0)
    else:
        print("\n❌ 同步失敗\n")
        sys.exit(1)
