#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎛️ R&S Echoes Lofi Factory - CEO 終極中控台 (v8.9)
=====================================================

【CEO 一鍵中控台】
提供最頂級的「主理人體驗」，將分散的腳本封裝成友善的互動式選單。

【v12.1 頻道感知升級】
✨ 全選單頻道導航化：菜單 [1][2][5] 現具備頻道選擇機制
✨ 自訂視覺發行：選擇背景影片 + 一鍵執行全產線（支援多頻道）
✅ 動態影片掃描、頻道隔離庫存戰報
✅ CEO 友善的互動式介面
"""

import os
import sys
import subprocess
import time
import shutil
from pathlib import Path

# 添加專案根目錄到 Python 路徑
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # ✅ 向上跳兩級，到達 F:\AI_DRAMA_FACTORY
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.gear2_rnd.vault_database import VaultDatabase
from scripts.gear1_prod.multi_scene_processor import MultiSceneProcessor


def print_header():
    """清空螢幕並打印標題"""
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*65)
    print(" 🎛️  R&S Echoes Lofi Factory - CEO 終極中控台 (v8.9) ")
    print("="*65)


def _prompt_channel_selection() -> str:
    """
    【v12.1 頻道感知】建立標準的頻道選擇 UI 區塊
    
    返回:
        str: 選擇的頻道 ("lofi" 或 "light_music")
    """
    print_header()
    print("\n🌐 請選擇操作頻道：\n")
    print("  [1] ☕ Lofi Chill (有人物、Lofi Hip-Hop 風格)")
    print("  [2] 🌿 Light Music (純淨風景、療癒 Ambient 風格)")
    print("-" * 65)
    
    while True:
        channel_choice = input("\n👉 請選擇頻道 (1-2): ").strip()
        if channel_choice == "1":
            print("✅ 已選擇: ☕ Lofi Chill")
            return "lofi"
        elif channel_choice == "2":
            print("✅ 已選擇: 🌿 Light Music")
            return "light_music"
        else:
            print("❌ 無效選擇，請輸入 1 或 2")
            continue


def _show_inventory_dashboard():
    """
    【v11.8 庫存戰報儀表板】顯示頻道化的庫存統計
    ☕ Lofi 與 🌿 Light Music 剩餘曲數在同一畫面上清楚標示
    """
    from pathlib import Path
    
    print_header()
    print("\n【v11.8 頻道化庫存戰報】\n")
    print("="*65)
    
    # 掃描兩個頻道的目錄 (任務三修復: 使用 _PROJECT_ROOT 確保跨平台路徑)
    lofi_ceo_dir = _PROJECT_ROOT / "assets" / "audio" / "ceo_approved_beats" / "lofi"
    light_ceo_dir = _PROJECT_ROOT / "assets" / "audio" / "ceo_approved_beats" / "light_music"
    lofi_vault_dir = _PROJECT_ROOT / "assets" / "audio" / "vault_ready_for_mix" / "lofi"
    light_vault_dir = _PROJECT_ROOT / "assets" / "audio" / "vault_ready_for_mix" / "light_music"
    
    # 統計 CEO 批准的歌曲
    lofi_ceo_count = len(list(lofi_ceo_dir.glob("*.mp3"))) if lofi_ceo_dir.exists() else 0
    light_ceo_count = len(list(light_ceo_dir.glob("*.mp3"))) if light_ceo_dir.exists() else 0
    
    # 統計 Vault 母帶
    lofi_vault_count = len(list(lofi_vault_dir.glob("*.wav"))) if lofi_vault_dir.exists() else 0
    light_vault_count = len(list(light_vault_dir.glob("*.wav"))) if light_vault_dir.exists() else 0
    
    # 顯示統計信息
    print("📊 CEO 批准庫存 (ceo_approved_beats/)")
    print("-"*65)
    print(f"  ☕ Lofi 頻道:      {lofi_ceo_count:3d} 首歌曲")
    print(f"  🌿 Light Music:   {light_ceo_count:3d} 首歌曲")
    print(f"  📈 合計:          {lofi_ceo_count + light_ceo_count:3d} 首歌曲")
    
    print("\n🎵 Vault 母帶庫存 (vault_ready_for_mix/)")
    print("-"*65)
    print(f"  ☕ Lofi 頻道:      {lofi_vault_count:3d} 首母帶")
    print(f"  🌿 Light Music:   {light_vault_count:3d} 首母帶")
    print(f"  📈 合計:          {lofi_vault_count + light_vault_count:3d} 首母帶")
    
    # 庫存狀態警告
    print("\n⚠️  庫存狀態檢查")
    print("-"*65)
    lofi_status = "✅ 充足" if lofi_vault_count >= 10 else "🔴 不足"
    light_status = "✅ 充足" if light_vault_count >= 10 else "🔴 不足"
    print(f"  ☕ Lofi 產線: {lofi_status} ({lofi_vault_count}/10)")
    print(f"  🌿 Light Music: {light_status} ({light_vault_count}/10)")
    
    # 隔離檢查
    print("\n🔒 頻道隔離狀態")
    print("-"*65)
    lofi_has_stock = lofi_ceo_count > 0 or lofi_vault_count > 0
    light_has_stock = light_ceo_count > 0 or light_vault_count > 0
    
    if lofi_has_stock and light_has_stock:
        print("  ✅ 兩個頻道均有庫存，隔離完整")
    elif lofi_has_stock:
        print("  ⚠️  Lofi 有庫存，Light Music 為空")
    elif light_has_stock:
        print("  ⚠️  Light Music 有庫存，Lofi 為空")
    else:
        print("  ⚠️  兩個頻道庫存均為空！")
    
    print("="*65)
    input("\n按 Enter 鍵返回主選單...")


def _list_sfx_files():
    """列出 assets/sfx 資料夾中的所有 SFX 檔案"""
    sfx_dir = _PROJECT_ROOT / "assets" / "sfx"  # 任務三修復: _PROJECT_ROOT 相對路徑
    sfx_dir.mkdir(parents=True, exist_ok=True)
    return sorted([f for f in sfx_dir.iterdir() if f.suffix.lower() in {'.wav', '.mp3', '.flac', '.aiff', '.m4a'}]) if sfx_dir.exists() else []


def _prompt_sfx_selection(sfx_files):
    """提示使用者選擇 SFX 檔案
    
    返回:
        int: 所選 SFX 的索引（0 表示無環境音）
    """
    print_header()
    print("🎧 請選擇要疊加的大自然環境音 (SFX)：\n")
    print("  [0] 無 (純淨 Lofi 音樂)")
    
    for idx, sfx_file in enumerate(sfx_files, 1):
        file_size_mb = sfx_file.stat().st_size / (1024 ** 2)
        print(f"  [{idx}] {sfx_file.name} ({file_size_mb:.1f} MB)")
    
    if not sfx_files:
        print("  （無可用環境音，若要使用請放入 assets/sfx/）")
    
    while True:
        sfx_choice = input(f"\n👉 請選擇 SFX 代碼 (0-{len(sfx_files)}): ").strip()
        try:
            sfx_idx = int(sfx_choice)
            if sfx_idx < 0 or sfx_idx > len(sfx_files):
                print(f"❌ 錯誤: SFX 代碼必須在 0-{len(sfx_files)} 之間")
                continue
            return sfx_idx
        except ValueError:
            print("❌ 錯誤: 請輸入有效的數字")
            continue


# ❌ 【CTO v14.1 廢除虛假選單】_prompt_sfx_mode() 函式已完全刪除
# 理由：底層 lofi_assembler.py 已廢除 Transition 模式，改為全域 SFX 4% 音量
# UI/底層架構必須 100% 對齐，不再提示虛假選項


def _show_asset_audit():
    """
    【CEO 資產審計儀表板】
    🛠️ CTO 軍令狀實裝
    
    核心邏輯：
    • 全局統計：金庫總量、各頻道佔比
    • 待命部隊清單：derivation_count == 0 的歌曲（全新未使用）
    • 功勳英雄榜：使用次數最高的前 10 名
    • 頻道隔離：區分 lofi 與 light_music
    """
    print_header()
    print("📊 【CEO 資產審計儀表板】")
    print("=" * 65)
    
    try:
        db = VaultDatabase()
        stats = db.get_statistics()
        all_tracks = db.get_all_tracks()
        
        # 全局統計
        print(f"\n📁 金庫總量: {stats.get('total_tracks', 0)} 首有效母帶")
        print(f"💾 資料庫體積: {stats.get('database_size_mb', 0):.2f} MB")
        print(f"📈 總衍生次數: {stats.get('total_derivations', 0)}")
        print(f"⏱️  平均衍生次數: {stats.get('avg_derivations', 0):.2f}")
        print("-" * 65)
        
        # 分頻道統計與顯示
        for channel in ["lofi", "light_music"]:
            # 篩選該頻道的所有軌道
            channel_tracks = [t for t in all_tracks if t.get("channel") == channel]
            
            # 待命部隊（全新）：derivation_count == 0
            ready_to_work = [t for t in channel_tracks if t.get("derivation_count", 0) == 0]
            
            # 已服役：derivation_count >= 1
            in_service = [t for t in channel_tracks if t.get("derivation_count", 0) > 0]
            
            channel_display = "☕ Lofi" if channel == "lofi" else "🌿 Light Music"
            
            print(f"\n【頻道：{channel_display}】")
            print(f"  🟢 待命部隊 (全新, 未使用): {len(ready_to_work)} 首")
            print(f"  🔵 已服役 (1次+): {len(in_service)} 首")
            
            # 最近入庫的新兵 Top 5
            if ready_to_work:
                print(f"  📅 最近入庫的新兵 (Top 5):")
                # 排序依照 created_at，最新的優先
                ready_sorted = sorted(
                    ready_to_work, 
                    key=lambda t: t.get("created_at", ""), 
                    reverse=True
                )[:5]
                for idx, t in enumerate(ready_sorted, 1):
                    track_id = t.get("track_id", "Unknown")
                    created_at = t.get("created_at", "Unknown")
                    print(f"      {idx}. {track_id} (入庫: {created_at})")
        
        # 功勳英雄榜
        print(f"\n🏆 【功勳英雄榜 - 使用次數最高 Top 10】")
        print("-" * 65)
        most_used = db.get_most_used_tracks(limit=10)
        
        if most_used:
            for idx, t in enumerate(most_used, 1):
                track_id = t.get("track_id", "Unknown")
                deriv_count = t.get("derivation_count", 0)
                print(f"  {idx:2d}. 🔥 {track_id} (已在 {deriv_count} 個影片中出現)")
        else:
            print("  （暫無記錄）")
        
        print("\n" + "=" * 65)
        print("✅ 審計完成。您現在可以精準掌握資產狀態！")
        print("💡 提示：若待命部隊 < 20 首，建議立即從 Suno 補充新素材。")
        
    except Exception as e:
        print(f"\n❌ 審計失敗: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n按 Enter 鍵返回主選單...")


def main():
    """主程式入口"""
    # 確保視覺素材資料夾存在
    video_dir = _PROJECT_ROOT / "assets" / "video_clips"  # 任務三修復: _PROJECT_ROOT 相對路徑
    video_dir.mkdir(parents=True, exist_ok=True)

    while True:
        print_header()
        print("請選擇您要執行的營運指令：\n")
        print("  [0] 📊 查看庫存戰報 (頻道化統計 - Lofi & Light Music)")
        print("  [1] 🚀 啟動全自動產線 (無背景影片，僅產出音樂)")
        print("  [2] 🧠 獲取明日靈感 (單獨呼叫 GLM 生成 Prompt 配方)")
        print("  [3] 🧹 靶場重置 (徹底清空所有庫存與產出，用於重新測試)")
        print("  [4] 🚪 退出系統")
        print("-" * 65)
        print("  [5] 🎬 自訂視覺發行 (選擇影片背景 + 啟動全自動產線) ✨")
        print("  [6] 💰 查詢音樂金庫 (Protocol L - 保鮮庫庫存統計) 🌟")
        print("  [7] 🗑️ 驗收完畢，清空靶場 (CEO 雙重核可) 🔐")
        print("-" * 65)
        print("  [8] � CEO 資產審計儀表板 (掌握金庫狀態、待命部隊、功勳榜) 🎯")
        print("-" * 65)
        
        choice = input("\n👉 請輸入代碼 (0-8): ").strip()
        
        if choice == '0':
            # 【v11.8 庫存戰報】新增菜單項
            _show_inventory_dashboard()
            
        elif choice == '1':
            # 【v12.1 頻道感知】先詢問頻道，然後傳遞給產線
            channel = _prompt_channel_selection()
            print(f"\n[啟動] 正在喚醒總指揮官 pipeline_runner.py (頻道: {channel.upper()})...")
            time.sleep(1)
            # 【CTO 修復 v8.8.4】確保阻塞調用並檢查返回碼
            result = subprocess.run([sys.executable, "scripts/gear1_prod/pipeline_runner.py", "--channel", channel])
            if result.returncode != 0:
                print(f"\n⚠️  產線執行異常 (Exit Code: {result.returncode})")
            input("\n按 Enter 鍵返回主選單...")
            
        elif choice == '2':
            # 【v12.1 頻道感知】CEO 重點要求：先詢問頻道，然後傳遞給提示詞生成
            channel = _prompt_channel_selection()
            print(f"\n[啟動] 正在喚醒靈感兵工廠 generate_ceo_prompts.py (頻道: {channel.upper()})...")
            time.sleep(1)
            # 【CTO 修復 v8.8.4】確保阻塞調用並檢查返回碼
            result = subprocess.run([sys.executable, "scripts/gear1_prod/generate_ceo_prompts.py", "--channel", channel, "--batch-size", "5"])
            if result.returncode != 0:
                print(f"\n⚠️  靈感生成異常 (Exit Code: {result.returncode})")
            input("\n按 Enter 鍵返回主選單...")
            
        elif choice == '3':
            print("\n[清理] 正在執行靶場重置 (Daily GC)...")
            print("⚠️  此操作將刪除以下所有檔案：")
            dirs_to_clean = [
                "assets/audio/ceo_approved_beats/lofi",
                "assets/audio/ceo_approved_beats/light_music",
                "assets/audio/mastered_tracks",
                "assets/audio/vault_ready_for_mix/lofi",
                "assets/audio/vault_ready_for_mix/light_music",
                "assets/audio/raw_tracks",
                "assets/final_exports",
                "assets/.ceo_prompts"
            ]
            for d in dirs_to_clean:
                print(f"  🗑️  {d}")
            
            confirm = input("\n確認清空? (輸入 'YES' 確認): ").strip().upper()
            if confirm == "YES":
                for d in dirs_to_clean:
                    path = Path(d)
                    if path.exists():
                        for file in path.glob("*"):
                            try:
                                if file.is_file():
                                    file.unlink()
                            except Exception:
                                pass
                print("✅ 所有庫存與產出目錄已徹底清空！")
            else:
                print("❌ 已取消清空操作")
            input("\n按 Enter 鍵返回主選單...")
            
        elif choice == '4':
            print("\n👋 感謝使用 R&S Echoes 中控台，祝您發行順利！")
            break
            
        elif choice == '5':
            # 【v12.1 頻道感知】在選擇影片前，先鎖定頻道
            channel = _prompt_channel_selection()
            
            # 動態掃描影片
            videos = sorted([v for v in video_dir.glob("*.mp4") if v.is_file()])
            if not videos:
                print(f"\n❌ 找不到任何背景影片！")
                print(f"📂 請先將您的短片 (.mp4) 放入以下資料夾：")
                print(f"   {video_dir.absolute()}")
                print(f"\n📝 推薦做法：")
                print(f"   • 短片時長：3~10 秒")
                print(f"   • 格式：MP4 (H.264)")
                print(f"   • 分辨率：1080p 或更高")
                input("\n按 Enter 鍵返回主選單...")
                continue
            
            print_header()
            print("🎬 請選擇您要使用的背景影片：\n")
            for idx, v in enumerate(videos, 1):
                file_size_mb = v.stat().st_size / (1024 ** 2)
                print(f"  [{idx}] {v.name} ({file_size_mb:.1f} MB)")
            
            v_choice = input(f"\n👉 請選擇影片代碼 (1-{len(videos)}): ").strip()
            try:
                v_idx = int(v_choice)
                # 【CTO v8.8.6 修復】嚴格的邊界檢查 (Off-by-One 防禦)
                if v_idx < 1 or v_idx > len(videos):
                    print(f"\n❌ 錯誤: 影片代碼必須在 1-{len(videos)} 之間")
                    input("\n按 Enter 鍵返回主選單...")
                    continue
                
                selected_video = videos[v_idx - 1]
                
                # 【CTO v8.8.5 修復】驗證視覺檔案是否有效
                if not selected_video.exists():
                    print(f"\n❌ 錯誤: 影片檔案不存在: {selected_video.name}")
                    input("\n按 Enter 鍵返回主選單...")
                    continue
                
                file_size = selected_video.stat().st_size
                if file_size < 1024 * 100:  # 最小 100 KB
                    print(f"\n❌ 錯誤: 影片檔案過小（{file_size / 1024:.1f} KB），可能損損或無效")
                    input("\n按 Enter 鍵返回主選單...")
                    continue
                
                # ========================================================
                # 【CTO 母帶回收再利用機制 v13.0】
                # ========================================================
                target_dir = _PROJECT_ROOT / "assets" / "final_exports" / channel
                existing_wavs = []
                if target_dir.exists():
                    # 搜尋該頻道下所有的 .wav 檔案 (已生成的 1 小時母帶)
                    existing_wavs = sorted([w for w in target_dir.glob("*.wav") if w.is_file()])
                
                selected_audio = None
                
                if existing_wavs:
                    print_header()
                    print(f"🎬 【自訂視覺發行 + 母帶回收】\n")
                    print(f"📁 發現 {len(existing_wavs)} 首已存在的 1 小時母帶 ({channel} 頻道)：")
                    print("  [0] 🆕 不選擇，我要製作全新的母帶 (執行完整產線)")
                    for idx, wav in enumerate(existing_wavs, 1):
                        size_mb = wav.stat().st_size / (1024 * 1024)
                        print(f"  [{idx}] 🎵 {wav.name} ({size_mb:.1f} MB)")
                    
                    while True:
                        try:
                            choice_audio = int(input(f"\n請選擇母帶編號 (0-{len(existing_wavs)}): "))
                            if 0 <= choice_audio <= len(existing_wavs):
                                if choice_audio > 0:
                                    selected_audio = existing_wavs[choice_audio - 1]
                                break
                            else:
                                print("❌ 無效的選擇，請重試。")
                        except ValueError:
                            print("❌ 請輸入數字。")
                
                # ========================================================
                # 執行分支 (Branching)
                # ========================================================
                if selected_audio:
                    # 情況 A：CEO 選擇了現有母帶 -> 直接呼叫 MultiSceneProcessor（母帶回收模式）
                    print(f"\n✅ 已選擇現有母帶：{selected_audio.name}")
                    print("🚀 直接進入影片縫合階段 (跳過音樂生成)...")
                    
                    processor = MultiSceneProcessor()
                    result_path = processor.process_full_pipeline(
                        channel=channel,
                        audio_paths=[selected_audio],
                        override_video=selected_video,
                    )
                    
                    print("\n" + "="*65)
                    if result_path and result_path.exists():
                        print(f"✅ 視覺重製完成！成品：{result_path.name}")
                    else:
                        print(f"⚠️  視覺縫合異常")
                    
                else:
                    # 情況 B：沒有現有母帶，或 CEO 選擇 [0] -> 執行原始的 pipeline_runner 流程
                    print("\n🚀 將執行完整產線生成全新母帶...")
                    
                    # 【CTO UI 修補】使用輔助函數進行 SFX 選擇流程
                    sfx_files = _list_sfx_files()
                    sfx_idx = _prompt_sfx_selection(sfx_files)
                    
                    # 根據選擇初始化 SFX 參數
                    selected_sfx = None
                    sfx_mode = "global"  # 預設模式
                    
                    # 【CTO v14.1 廢除虛假選單】系統強制綁定 Global 全域模式
                    # 理由：底層已廢除 Transition，全域 4% 音量為唯一標準配置
                    if sfx_idx > 0:
                        selected_sfx = sfx_files[sfx_idx - 1]
                        sfx_mode = "global"  # 系統強制綁定，移除虛假 Transition 選項
                        print(f"✅ 已啟用 Global 全域鋪底模式 (4% 音量)")
                    
                    # 組合發射指令
                    cmd_args = [
                        sys.executable, 
                        "scripts/gear1_prod/pipeline_runner.py",
                        "--channel", channel,  # 【v12.1】添加頻道參數
                        "--bg-video", 
                        str(selected_video)
                    ]
                    
                    # 【CTO v10】SFX 與模式參數傳遞
                    selected_sfx_name = "無環境音"
                    if selected_sfx is not None:
                        cmd_args.extend(["--sfx", str(selected_sfx), "--sfx-mode", sfx_mode])
                        selected_sfx_name = f"{selected_sfx.name} ({sfx_mode})"
                    
                    print(f"\n[啟動] 視覺:【{selected_video.name}】 | 聽覺:【{selected_sfx_name}】")
                    # 【CTO 修復 v8.8.4】確保阻塞調用並檢查返回碼
                    result = subprocess.run(cmd_args)
                    if result.returncode != 0:
                        print(f"\n⚠️  視覺發行異常 (Exit Code: {result.returncode})")
                
                
            except (ValueError, IndexError):
                print("\n❌ 無效的選擇，請輸入正確的數字。")
            
            input("\n按 Enter 鍵返回主選單...")
        
        elif choice == '6':
            # 【Protocol L】音樂金庫查詢
            print_header()
            print("\n🎵 【Protocol L】音樂資產保鮮庫\n")
            
            try:
                vault = VaultDatabase()
                stats = vault.get_statistics()
                
                print("="*65)
                print("📊 保鮮庫統計信息")
                print("="*65)
                print(f"\n📁 資料庫位置: {stats['database_path']}")
                print(f"\n✅ 總音檔數: {stats['total_tracks']}")
                print(f"📈 總衍生次數: {stats['total_derivations']}")
                print(f"⏱️  平均衍生次數: {stats['avg_derivations']}")
                print(f"💾 資料庫大小: {stats['database_size_mb']} MB")
                
                # 心情分布
                if stats['mood_distribution']:
                    print(f"\n😊 心情分布:")
                    for mood, count in stats['mood_distribution'].items():
                        print(f"   • {mood}: {count} 首")
                
                # 類型分布
                if stats['genre_distribution']:
                    print(f"\n🎼 類型分布:")
                    for genre, count in stats['genre_distribution'].items():
                        print(f"   • {genre}: {count} 首")
                
                # 最多使用的音檔
                print(f"\n🏆 最常使用的音檔:")
                popular = vault.get_most_used_tracks(limit=5)
                if popular:
                    for idx, track in enumerate(popular, 1):
                        print(f"   {idx}. {track['track_id']} (衍生 {track['derivation_count']} 次)")
                else:
                    print("   （暫無記錄）")
                
                print("\n" + "="*65)
                
            except Exception as e:
                print(f"\n❌ 查詢失敗: {e}")
            
            input("\n按 Enter 鍵返回主選單...")
        
        elif choice == '7':
            # 【v12.10 UI 戰報精準化】CEO 雙重核可刪除制 + 頻道隔離
            channel = _prompt_channel_selection()  # 先詢問目標頻道
            
            print_header()
            print(f"\n🗑️ 【CEO 雙重核可刪除制】清理 {channel.upper()} 頻道\n")
            print("="*65)
            print("⚠️  清理前的最後檢查清單：")
            print("="*65)
            
            # 【v12.10 Stats Isolation】僅掃描指定頻道的目錄
            ceo_approved_channel = Path(f"assets/audio/ceo_approved_beats/{channel}")
            vault_ready_channel = Path(f"assets/audio/vault_ready_for_mix/{channel}")
            
            ceo_approved_count = len(list(ceo_approved_channel.glob("*"))) if ceo_approved_channel.exists() else 0
            vault_ready_count = len(list(vault_ready_channel.glob("*"))) if vault_ready_channel.exists() else 0
            total_files = ceo_approved_count + vault_ready_count
            
            print(f"\n📊 待清理檔案統計 ({channel.upper()})：")
            print(f"  • ceo_approved_beats/{channel}/：{ceo_approved_count} 個檔案")
            print(f"  • vault_ready_for_mix/{channel}/：{vault_ready_count} 個檔案")
            print(f"  • 【{channel.upper()}】總計：{total_files} 個檔案")
            
            if total_files == 0:
                print(f"\n✅ 無待清理檔案，靶場已乾淨")
                input("\n按 Enter 鍵返回主選單...")
                continue
            
            print("\n【防線 1】確認視覺檔案")
            print("請確認最新的 1 小時影片 (FINAL_*.mp4) 已下載並播放正常無瑕疵")
            confirm1 = input("👉 您是否已確認最新的 1 小時影片播放正常無瑕疵？(Y/N): ").strip().upper()
            if confirm1 not in ['Y', 'YES']:
                print("\n❌ 已取消清理操作（防線 1 確認失敗）")
                input("\n按 Enter 鍵返回主選單...")
                continue
            
            print("\n【防線 2】授權清理確認")
            print("清理後將無法復原所有素材檔案（備份已移至安全封存區）")
            confirm2 = input("👉 您是否明確授權系統清空靶場？(Y/N): ").strip().upper()
            if confirm2 not in ['Y', 'YES']:
                print("\n❌ 已取消清理操作（防線 2 確認失敗）")
                input("\n按 Enter 鍵返回主選單...")
                continue
            
            # 【一鍵大掃除】執行清理
            print("\n🔄 正在執行一鍵大掃除...")
            try:
                archived = _PROJECT_ROOT / "assets" / "audio" / "ceo_archived_beats"  # 任務三修復: _PROJECT_ROOT
                archived.mkdir(parents=True, exist_ok=True)
                
                files_moved = 0
                
                # 【v12.10 頻道隔離清理】僅清理指定頻道的檔案
                for channel_dir in [ceo_approved_channel, vault_ready_channel]:
                    if channel_dir.exists():
                        for item in channel_dir.glob("*"):
                            try:
                                if item.is_file():
                                    shutil.move(str(item), str(archived / item.name))
                                    files_moved += 1
                                elif item.is_dir():
                                    shutil.move(str(item), str(archived / item.name))
                                    files_moved += 1
                            except Exception as e:
                                print(f"  ⚠️  移動失敗: {item.name} - {e}")
                
                if files_moved > 0:
                    print(f"\n✅ 一鍵大掃除完成：{files_moved} 個 {channel.upper()} 檔案已安全封存")
                    print(f"   📁 位置：assets/audio/ceo_archived_beats/")
                    print(f"   【DATA PROTECTION】所有 {channel.upper()} 檔案已妥善保留")
                    print(f"   【{channel.upper()} 頻道乾淨狀態】下次產線啟動將從零開始！")
                else:
                    print("\nℹ️  無檔案需要移動（{channel.upper()} 可能已清理）")
                
            except Exception as e:
                print(f"\n❌ 清理失敗: {e}")
            
            input("\n按 Enter 鍵返回主選單...")
        
        elif choice == '8':
            # 【CTO 軍令狀】CEO 資產審計儀表板
            _show_asset_audit()
        
        else:
            print("\n❌ 無效的輸入，請輸入 1-8 之間的數字。")
            time.sleep(1)


# ========================================================================
# 【v12.0】ChannelAwareRunner - 安全的頻道感知後端引擎
# ========================================================================

class ChannelAwareRunner:
    """
    【v12.0 CEO 一鍵中控台】
    frequency道感知的 subprocess 運行器，確保所有操作都帶入正確的頻道參數。
    
    特性：
    • 自動注入頻道參數（--channel lofi 或 --channel light_music）
    • 預設路徑保護：運行失敗時自動回落至 Lofi
    • Log 記錄：所有執行情況持久化
    """
    
    VALID_CHANNELS = ["lofi", "light_music"]
    DEFAULT_CHANNEL = "lofi"
    
    def __init__(self, channel: str = "lofi"):
        """
        初始化 ChannelAwareRunner
        
        Args:
            channel: 頻道名稱 ("lofi" 或 "light_music")
        """
        if channel not in self.VALID_CHANNELS:
            print(f"⚠️  警告：頻道 {channel} 無效，回落至 {self.DEFAULT_CHANNEL}")
            self.channel = self.DEFAULT_CHANNEL
        else:
            self.channel = channel
    
    def run_generate_prompts(self, batch_size: int = 5) -> dict:
        """
        運行提示詞生成
        
        Args:
            batch_size: 生成組數
            
        Returns:
            dict: 包含 returncode, stdout, stderr 的訊息
        """
        cmd = [
            sys.executable,
            "scripts/gear1_prod/generate_ceo_prompts.py",
            "--channel", self.channel,
            "--batch-size", str(batch_size)
        ]
        
        try:
            result = subprocess.run(cmd, text=True, timeout=600,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout or "",
                "stderr": "",
                "channel": self.channel
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "生成超時（超過 10 分鐘）",
                "channel": self.channel
            }
        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "channel": self.channel
            }
    
    def run_pipeline(self, **kwargs) -> dict:
        """
        運行完整產線
        
        Args:
            **kwargs: 其他參數（如 bg_video, sfx 等）
            
        Returns:
            dict: 執行結果
        """
        cmd = [
            sys.executable,
            "scripts/gear1_prod/pipeline_runner.py",
            "--channel", self.channel
        ]
        
        # 添加其他參數 (任務一修復: 布林值標誌參數需特殊處理)
        for key, value in kwargs.items():
            if value is not None:
                # 對於布林值：True 時添加 Flag，False 時跳過整個參數
                if isinstance(value, bool):
                    if value:
                        # 布林值為 True，只添加 Flag，不添加值
                        cmd.append(f"--{key.replace('_', '-')}")
                    # 布林值為 False 時，跳過該參數整體
                else:
                    # 非布林值：先添加 Flag 再添加值
                    cmd.append(f"--{key.replace('_', '-')}")
                    cmd.append(str(value))
        
        try:
            print(f"\n🚀 產線已啟動 ({self.channel.upper()})，請監控以下即時戰報：\n" + "="*65)
            # 【CTO 致盲修復】移除 capture_output=True，讓 stdout/stderr 直接打印到 CEO 的終端機
            result = subprocess.run(cmd, timeout=3600)
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": "【產線即時輸出已發送至終端機，請查看上方日誌】",
                "stderr": "",
                "channel": self.channel
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "產線超時（超過 1 小時）",
                "channel": self.channel
            }
        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "channel": self.channel
            }


if __name__ == "__main__":
    main()
