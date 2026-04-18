#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📝 齒輪一 (生產部) - 標題與貼文生成器 (v7.10 60s MVP 版)
檔案名稱: title_post_generator.py

讀取 storyboard.json 的動作摘要，使用 GLM-4-Flash 結構化輸出爆款社群文案，
並進行路徑過濾與原子寫入。
這支腳本位於產線最後一關（在 auto_editor.py 剪接完成後執行）。它只讀取分鏡的「動作摘要」，以極低的 Token 成本生出爆款社群貼文與標題
"""

import sys
import json
import argparse
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.common.atomic_io import atomic_write_json
from scripts.common.llm_client import generate_structured_json
from scripts.common.path_sanitize import sanitize_filename

def generate_marketing_copy(storyboard_path: Path, episode_id: str):
    print("\n" + "=" * 60)
    print("📝 啟動社群文案生成器")
    print("=" * 60)
    
    if not storyboard_path.exists():
        raise FileNotFoundError(f"找不到分鏡檔: {storyboard_path}")
        
    sb_data = json.loads(storyboard_path.read_text(encoding="utf-8"))
    theme = sb_data.get("episode_metadata", {}).get("theme", "職場微電影")
    
    # 提取精簡的動作摘要，避免浪費 Token
    # v7.10 schema 對齊：shots（顧問命名）優先，相容舊版 storyboard_sequence
    shot_list = sb_data.get("shots") or sb_data.get("storyboard_sequence", [])
    actions = [f"- {shot.get('action', '')}" for shot in shot_list]
    summary = "\n".join(actions)

    sys_prompt = (
        "你是一位專為 B2B 品牌操作短影音 (Shorts/Reels) 的社群行銷專家。\n"
        "請根據這支 60 秒無對白、定格動畫風格的微電影分鏡摘要，撰寫社群文案。\n"
        "【嚴格規範】\n"
        "必須回傳 JSON Object，欄位如下：\n"
        "  short_titles: 5 個爆款標題（每個 ≥5 字）\n"
        "  hashtags: 10 個帶 # 的標籤\n"
        "  community_posts: 2 個物件，各含 text（貼文內容）與 cta（行動呼籲）\n"
        "  pinned_comment: 1 個置頂留言（≥5 字）\n"
        "  compliance_notes: 可選，版權或平台合規備註字串陣列"
    )
    
    user_prompt = (
        f"微電影主題：{theme}\n"
        f"分鏡動作摘要：\n{summary}\n\n"
        f"請直接輸出符合規範的 JSON Object。"
    )

    print("   🤖 呼叫 GLM-4-Flash...")
    result_json = generate_structured_json(sys_prompt, user_prompt)

    # 補入 job_id 以符合 v7.10 schema 鉚式追蹤要求
    if isinstance(result_json, dict) and "job_id" not in result_json:
        result_json["job_id"] = sanitize_filename(episode_id)
    
    # 利用路徑護法防護資料夾名稱
    safe_episode_id = sanitize_filename(episode_id)
    out_dir = Path(config.workspace_root) / "assets" / "final_exports" / safe_episode_id
    out_dir.mkdir(parents=True, exist_ok=True)
    
    out_file = out_dir / "title_post.json"
    atomic_write_json(out_file, result_json)
    print(f"   ✅ title_post.json 已安全寫入: {out_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--storyboard", required=True, help="storyboard.json 路徑")
    parser.add_argument("--episode-id", required=True)
    args = parser.parse_args()
    generate_marketing_copy(Path(args.storyboard), args.episode_id)