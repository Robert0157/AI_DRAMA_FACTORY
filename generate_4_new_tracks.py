#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【淨室重置 - 真實 Suno API 生成 + A/B 雙軌提取】
v9.0 CTO 修復版：
  ✅ 真實非同步下載輪詢（wait_audio=True + poll_until_done）
  ✅ A/B 雙軌完整提取（count=4 → 2 次請求 × 2 tracks）
  ✅ 輪詢日誌可視化（「等待 Suno 生成中... (10s, 20s, ...)」）
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 使用新的 generate_instrumental 進行真實下載輪詢
from scripts.gear1_prod.suno_api_engine import generate_instrumental, poll_until_done, custom_generate, download_audio
from scripts.common.env_manager import config


def log_fatal(msg: str) -> None:
    """記錄致命錯誤至 project_learning.md"""
    learning_log = config.workspace_root / "project_learning.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"\n---\n### ❌ [{timestamp}] generate_4_new_tracks.py\n- **Error**: {msg}\n"
    try:
        with open(learning_log, "a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception as e:
        print(f"⚠️  無法寫入 learning log: {e}")


def main():
    print("\n" + "="*80)
    print("🎵 【真實生成驗證】Suno API A/B 雙軌完整提取")
    print("="*80)
    print("📋 策略: count=4 → 2 次請求 × 2 tracks (A/B 雙軌完整利用 CEO 算力)")
    print("="*80)
    
    # 讀取提示詞批次
    prompt_file = _PROJECT_ROOT / "assets" / "final_exports" / "suno_prompt_batch.json"
    
    if not prompt_file.exists():
        print("❌ 提示詞檔案不存在: " + str(prompt_file))
        log_fatal(f"提示詞檔案不存在: {prompt_file}")
        sys.exit(1)
    
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            batch_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ 提示詞 JSON 解析失敗: {e}")
        log_fatal(f"JSON 解析失敗: {e}")
        sys.exit(1)
    
    # 提取提示詞列表
    prompts = batch_data.get("batch", []) if isinstance(batch_data, dict) else []
    if not prompts:
        prompts = [item for item in (batch_data if isinstance(batch_data, list) else [])]
    
    print(f"\n✅ 已讀取 {len(prompts)} 個提示詞")
    
    if len(prompts) < 2:
        print("❌ 至少需要 2 個提示詞才能生成 4 首歌 (A/B 雙軌)")
        log_fatal(f"提示詞不足: 只有 {len(prompts)} 個，需要 2 個")
        sys.exit(1)
    
    # 新策略: 2 次請求 → 4 首歌
    # 每次 custom_generate 會回傳 2 個 track (A/B)
    prompts_to_use = prompts[:2]
    
    generated_tracks = []
    audio_download_dir = _PROJECT_ROOT / "assets" / "audio" / "raw_tracks"
    audio_download_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n🚀 開始生成 (使用前 2 個提示詞 → 2 次請求 × 2 tracks = 4 首歌)")
    
    for req_idx, prompt_obj in enumerate(prompts_to_use, 1):
        # 【CTO v12.0 - 雙軌分離】讀取分離的 tags 和 prompt
        tags_text = prompt_obj.get("tags", "") if isinstance(prompt_obj, dict) else ""
        prompt_text = prompt_obj.get("prompt") if isinstance(prompt_obj, dict) else str(prompt_obj)
        request_title = prompt_obj.get("title", f"Request_{req_idx}_Batch") if isinstance(prompt_obj, dict) else f"Request_{req_idx}_Batch"
        
        print(f"\n【Request {req_idx}/2】")
        print(f"結構標籤: {prompt_text[:80]}...")
        print(f"風格參數: {tags_text[:80]}...")
        
        # ========== 【修復一】真實非同步下載輪詢 ==========
        try:
            print("⏳ 正在提交 Suno API 請求...")
            start_time = time.time()
            
            # custom_generate 會回傳 list[dict]，通常 2 個 track (A/B)
            # 【CTO v12.0】分離傳遞 tags（style 參數）和 prompt
            tracks = custom_generate(
                prompt=prompt_text,           # 【新】結構元標籤（[Intro]/[Verse] 等）
                style=tags_text,              # 【新】風格參數（樂器、技術規格等）
                title=request_title,
                make_instrumental=True,
                model="chirp-crow",
                wait_audio=False,  # 不阻塞，改用 poll
            )
            
            if not tracks:
                err_msg = f"【Request {req_idx}/2】API 返回空 track 列表"
                print(f"❌ {err_msg}")
                log_fatal(err_msg)
                sys.exit(1)
            
            track_ids = [t.get("id") for t in tracks if t.get("id")]
            print(f"✅ 取得 {len(track_ids)} 個 Track ID: {track_ids}")
            
            # ========== 【修復一】輪詢直到完成 ==========
            print("⏳ 等待 Suno 生成中... ", end="", flush=True)
            poll_start = time.time()
            
            final_tracks = poll_until_done(track_ids, poll_interval=10, max_attempts=72)
            
            poll_elapsed = time.time() - poll_start
            elapsed = time.time() - start_time
            print(f"\n✅ 輪詢完成 ({poll_elapsed:.0f}s 內)")
            print(f"   總耗時: {elapsed:.1f}s")
            
            # ========== 【修復二】A/B 雙軌完整提取與下載 ==========
            for track_idx, track in enumerate(final_tracks, 1):
                track_id = track.get("id")
                track_title = track.get("title", f"Track_{track_idx}")
                audio_url = track.get("audio_url")
                
                if not audio_url:
                    print(f"⚠️  Track {track_idx} (ID: {track_id[:8]}) 無 audio_url，跳過下載")
                    continue
                
                # 真實下載
                try:
                    local_path = download_audio(track, dest_dir=audio_download_dir)
                    print(f"✅ Track {track_idx} 已下載: {local_path}")
                    
                    # 全局索引 (1-4)
                    global_idx = (req_idx - 1) * 2 + track_idx
                    
                    generated_tracks.append({
                        "idx": global_idx,
                        "request": req_idx,
                        "track_idx": track_idx,
                        "track_id": track_id,
                        "title": track_title,
                        "audio_url": audio_url,
                        "local_path": str(local_path),
                        "status": "complete",
                    })
                    
                    print(f"   【{global_idx}/4】{track_title}")
                    
                except Exception as dl_err:
                    print(f"❌ Track {track_idx} 下載失敗: {dl_err}")
                    log_fatal(f"Track {track_id} 下載失敗: {dl_err}")
                    sys.exit(1)
        
        except Exception as e:
            print(f"❌ 【Request {req_idx}/2】生成失敗: {e}")
            log_fatal(f"Request {req_idx} 失敗: {e}")
            sys.exit(1)
    
    # 最終報告
    print("\n" + "="*80)
    print(f"✅ 完成: {len(generated_tracks)}/4 首歌曲已生成與下載")
    print("="*80)
    
    # 保存記錄
    generation_record = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(generated_tracks),
        "tracks": generated_tracks,
        "strategy": "A/B 雙軌: 2 次 API 請求 × 2 tracks = 4 首完整歌曲",
        "test_note": "CTO v9.0 修復 - 真實下載輪詢 + 完整 A/B 提取驗證",
    }
    
    record_file = _PROJECT_ROOT / "assets" / "final_exports" / "new_tracks_generated.json"
    try:
        with open(record_file, "w", encoding="utf-8") as f:
            json.dump(generation_record, f, ensure_ascii=False, indent=2)
        print(f"\n📊 已保存至: {record_file}")
    except Exception as e:
        print(f"\n⚠️  無法保存記錄: {e}")
    
    # 下載驗證
    print(f"\n📁 已下載至: {audio_download_dir}")
    try:
        local_files = list(audio_download_dir.glob("*.mp3"))
        print(f"   找到 {len(local_files)} 個本地 MP3 檔案:")
        for mp3 in sorted(local_files)[-4:]:
            print(f"   • {mp3.name}")
    except Exception as e:
        print(f"   ⚠️  無法列舉本地檔案: {e}")
    
    print(f"\n🚀 接下來執行:")
    print(f"   python scripts/gear1_prod/audio_mastering_engine.py --timeout-sec 180")


if __name__ == "__main__":
    main()
