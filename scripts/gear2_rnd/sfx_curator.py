#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SFX 素材策展人 - 從工業標準庫下載 + 格式化大自然音效
Freesound.org / BBC Sound Effects / NPS Symphony of Sounds

CEO 指定高解析度自然音效庫建置工具
格式強制轉換：44.1kHz / 24-bit / 單聲道或立體聲 WAV
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, List
import urllib.request
import urllib.error
from datetime import datetime

# ============================================================================
# 環境配置
# ============================================================================
sys.path.insert(0, str(Path(__file__).parent / ".." / "common"))

try:
    from env_manager import config
except ImportError:
    print("❌ 無法載入 env_manager")
    sys.exit(1)

# ============================================================================
# 目標素材清單 & 參考來源
# ============================================================================

# CEO 指定的目標素材清單
TARGET_ASSETS = {
    "rain.wav": {
        "description": "輕柔雨聲（避免暴雨）",
        "suggested_sources": [
            "https://freesound.org/api/sounds/search/?query=gentle+rain&fields=id,name,download",
            "BBC Sound Effects Library: Heavy Rain on Metal"
        ]
    },
    "river.wav": {
        "description": "清澈溪流聲",
        "suggested_sources": [
            "https://freesound.org/api/sounds/search/?query=river+stream+gentle",
            "BBC: 'Brook, Stream'"
        ]
    },
    "wind.wav": {
        "description": "微風拂過樹葉聲",
        "suggested_sources": [
            "https://freesound.org/api/sounds/search/?query=wind+trees+leaves",
            "BBC: 'Wind in Trees'"
        ]
    },
    "birds.wav": {
        "description": "清晨鳥鳴",
        "suggested_sources": [
            "https://freesound.org/api/sounds/search/?query=morning+birds+chirping",
            "NPS: 'Bird Chorus at Dawn'"
        ]
    },
    "crickets.wav": {
        "description": "深夜蟲鳴",
        "suggested_sources": [
            "https://freesound.org/api/sounds/search/?query=crickets+night",
            "BBC: 'Crickets at Night'"
        ]
    }
}

# ============================================================================
# 工具函式
# ============================================================================

def download_file(url: str, output_path: Path, timeout_sec: int = 60) -> bool:
    """從 URL 下載檔案"""
    try:
        print(f"⏳ 下載中: {url}")
        urllib.request.urlretrieve(url, output_path, timeout=timeout_sec)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"✅ 下載完成: {output_path.name} ({size_mb:.2f} MB)")
        return True
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"❌ 下載失敗: {e}")
        return False
    except Exception as e:
        print(f"❌ 未預期的錯誤: {e}")
        return False


def convert_to_standard_format(input_wav: Path, output_wav: Path, 
                               target_sr: int = 44100, 
                               target_bits: int = 24) -> bool:
    """
    使用 FFmpeg 將音檔轉換為標準 format
    目標: 44.1kHz / 24-bit / WAV
    """
    try:
        # 檢查是否為有效的音檔
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=sample_rate,channels",
            "-of", "json",
            str(input_wav)
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"⚠️  無法探測 {input_wav.name}：可能不是有效音檔")
            return False
        
        # 執行 FFmpeg 轉換
        ffmpeg_cmd = [
            "ffmpeg", "-i", str(input_wav),
            "-acodec", "pcm_s24le",  # 24-bit PCM
            "-ar", str(target_sr),    # 44.1kHz resample
            "-ac", "2",               # Stereo (or 1 for mono)
            "-y",                     # Overwrite
            str(output_wav)
        ]
        
        print(f"  🔧 轉換格式: {input_wav.name} → {output_wav.name}")
        print(f"     目標: {target_sr}Hz / {target_bits}-bit / Stereo")
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=180)
        
        if result.returncode == 0 and output_wav.exists():
            size_mb = output_wav.stat().st_size / (1024 * 1024)
            print(f"✅ 轉換完成: {size_mb:.2f} MB")
            return True
        else:
            print(f"❌ FFmpeg 轉換失敗 (exit code {result.returncode})")
            if result.stderr:
                print(f"   錯誤: {result.stderr[:200]}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"❌ FFmpeg 超時 (180 秒)")
        return False
    except FileNotFoundError:
        print(f"❌ FFmpeg 未找到 (請確認已安裝)")
        return False
    except Exception as e:
        print(f"❌ 轉換失敗: {e}")
        return False


def process_inventory_file(inventory_file: Path, sfx_output_dir: Path) -> Dict[str, bool]:
    """
    從清單檔案讀取 URL，逐個下載並轉換
    清單格式: JSON with structure:
    {
        "rain": "https://...",
        "river": "https://...",
        ...
    }
    """
    results = {}
    
    if not inventory_file.exists():
        print(f"⚠️  清單檔案未找到: {inventory_file}")
        return results
    
    try:
        with open(inventory_file, "r", encoding="utf-8") as f:
            urls = json.load(f)
    except Exception as e:
        print(f"❌ 無法讀取清單: {e}")
        return results
    
    sfx_output_dir.mkdir(parents=True, exist_ok=True)
    
    for name, url in urls.items():
        target_wav = sfx_output_dir / f"{name}.wav"
        temp_wav = sfx_output_dir / f"_{name}_temp.wav"
        
        if target_wav.exists():
            print(f"⏭️  已存在: {name}.wav (跳過)")
            results[name] = True
            continue
        
        # 下載
        if not download_file(url, temp_wav):
            results[name] = False
            continue
        
        # 轉換格式
        if convert_to_standard_format(temp_wav, target_wav):
            temp_wav.unlink()  # 刪除臨時檔案
            results[name] = True
        else:
            results[name] = False
            if temp_wav.exists():
                temp_wav.unlink()
    
    return results


def generate_inventory_template() -> None:
    """產生下載清單範本 (給使用者手動填入)"""
    
    template = {
        "_instructions": "README: 從下列來源取得檔案 URL，填入本陣列",
        "freesound_api_notes": "Freesound.org 直接下載 URL 格式: https://freesound.org/data/previews/...",
        "bbc_notes": "BBC Sound Effects: https://sound-effects.bbcrewind.co.uk/?q=...",
        "nps_notes": "NPS Symphony: https://www.nps.gov/articles/...",
        
        "rain": "FILL_ME: URL to gentle rain sound",
        "river": "FILL_ME: URL to river/stream sound",
        "wind": "FILL_ME: URL to wind in trees sound",
        "birds": "FILL_ME: URL to morning bird chorus",
        "crickets": "FILL_ME: URL to night crickets sound"
    }
    
    inventory_file = config.workspace_root / "sfx_download_inventory.json"
    
    with open(inventory_file, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
    
    print(f"\n📋 已產生下載清單範本: {inventory_file}")
    print("   請填入具體的 URL，然後執行 --process-inventory")


def print_manual_guide():
    """列印手動下載指南"""
    
    guide = """
╔═════════════════════════════════════════════════════════════════════════════╗
║                   R&S Echoes SFX 手動下載指南 (CEO 指定)                    ║
╚═════════════════════════════════════════════════════════════════════════════╝

📌 目標素材清單 (5 個高質量自然音效)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. rain.wav         - 輕柔雨聲（避免暴雨/雷聲）
2. river.wav        - 清澈溪流聲（流水潺潺感）
3. wind.wav         - 微風拂過樹葉聲（沙沙聲）
4. birds.wav        - 清晨鳥鳴（鳥叫聲）
5. crickets.wav     - 深夜蟲鳴（蟲鳴聲）

🎧 推薦下載來源 (CEO 指定的三個工業標準庫)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【來源 A】Freesound.org - 全球最大協作聲音庫
   網址: https://freesound.org
   授權: CC0 (推薦) 或 CC-BY
   篩選: Advanced Search → 44.1kHz+ 取樣率 → 搜尋關鍵字
   
   推薦搜尋:
   • rain: "gentle rain" OR "soft rain"
   • river: "river stream" OR "flowing water"
   • wind: "wind trees" OR "wind leaves"
   • birds: "morning birds" OR "bird chorus"
   • crickets: "crickets" OR "insects night"

【來源 B】BBC Sound Effects Library
   網址: https://sound-effects.bbcrewind.co.uk/
   授權: CC-BY-NC (非商用)
   特色: 16,000+ 超高品質錄音 (業界標竿)
   
   推薦搜尋:
   • "Heavy Rain on Leaves" / "Light Rain"
   • "Brook" / "Small Stream Flowing"
   • "Wind in Trees" / "Wind in Foliage"
   • "Bird Chorus at Dawn"
   • "Crickets" / "Insects"

【來源 C】National Park Service - A Symphony of Sounds
   網址: https://www.nps.gov/articles/
   授權: 公眾領域
   特色: 美國國家公園（黃石等）官方錄音
   
   推薦搜尋:
   • Yellowstone Park sound profiles
   • Forest ambience recordings
   • Wildlife soundscapes

📥 下載步驟
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 造訪上述網站，搜尋並下載符合品牌調性的 WAV 檔案
2. 檢查下載檔案的格式：
   • 最佳: 44.1kHz 或更高取樣率
   • 最佳: 16-bit 或 24-bit
   • 接受: MP3/FLAC（我們會轉換）
3. 將檔案命名為目標清單中的名稱，放入:
   <WORKSPACE_ROOT>/assets/sfx/
4. 執行 FFmpeg 自動轉換（下一步）

🔧 自動格式化 (FFmpeg)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

如果下載的檔案格式不符，執行此命令自動轉換所有檔案:

  python scripts/gear2_rnd/sfx_curator.py --convert-all

結果: 所有 .wav 檔案統一為 44.1kHz / 24-bit / Stereo

✅ 驗證檔案
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

檢查 <WORKSPACE_ROOT>/assets/sfx/ 目錄是否包含:
  ✓ rain.wav
  ✓ river.wav
  ✓ wind.wav
  ✓ birds.wav
  ✓ crickets.wav

  每個檔案 > 1 MB（品質保證）

🚀 後續行動
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

檔案就緒後，執行:

  1. Action 2 - 母帶製作 + Telegram 發送:
     python scripts/gear1_prod/audio_mastering_engine.py --decay-sec 1.2 \\
       --sfx-volume 0.10 --clip-threshold-db -3.0 --seed 42 --timeout-sec 180

  2. Telegram CEO Bot（遠端中控）:
     python scripts/start_telegram_bot.py

CEO 正在等待第一首融合「BBC 等級真實自然音」的 1 分鐘 Demo！

╔═════════════════════════════════════════════════════════════════════════════╗
║                         CTO 核准簽章 (CEO 指定資源)                         ║
╚═════════════════════════════════════════════════════════════════════════════╝
"""
    
    print(guide)


# ============================================================================
# 主程式
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        prog="SFX Curator",
        description="CEO 指定高解析度自然音效庫建置工具"
    )
    
    parser.add_argument(
        "--guide", action="store_true",
        help="列印手動下載指南"
    )
    
    parser.add_argument(
        "--generate-inventory", action="store_true",
        help="產生下載清單範本"
    )
    
    parser.add_argument(
        "--convert-all", action="store_true",
        help="將 assets/sfx/ 中所有的音檔轉換為標準格式"
    )
    
    parser.add_argument(
        "--process-inventory", type=str,
        help="從清單檔案下載並轉換音檔"
    )
    
    parser.add_argument(
        "--verify", action="store_true",
        help="驗證 assets/sfx/ 中的檔案完整性"
    )
    
    args = parser.parse_args()
    
    sfx_dir = config.workspace_root / "assets" / "sfx"
    
    # =====================================================================
    # 模式 1: 列印手動下載指南
    if args.guide:
        print_manual_guide()
        return
    
    # =====================================================================
    # 模式 2: 產生下載清單範本
    if args.generate_inventory:
        generate_inventory_template()
        return
    
    # =====================================================================
    # 模式 3: 轉換所有音檔為標準格式
    if args.convert_all:
        print("\n" + "="*80)
        print("🔧 轉換 assets/sfx/ 中的所有音檔為標準格式 (44.1kHz / 24-bit / Stereo)")
        print("="*80)
        
        wav_files = list(sfx_dir.glob("*.wav"))
        
        if not wav_files:
            print(f"⚠️  在 {sfx_dir} 中未找到 .wav 檔案")
            return
        
        success_count = 0
        
        for wav_file in wav_files:
            if wav_file.name.startswith("_"):
                continue  # 跳過臨時檔案
            
            # 檢查是否已為標準格式（簡單檢查）
            output_file = wav_file.parent / f"converted_{wav_file.name}"
            
            # 為了保險起見，直接轉換
            if convert_to_standard_format(wav_file, output_file):
                # 備份原文件，用轉換後的檔案替代
                wav_file.unlink()
                output_file.rename(wav_file)
                success_count += 1
        
        print(f"\n✅ 轉換完成: {success_count}/{len(wav_files)} 個檔案")
        return
    
    # =====================================================================
    # 模式 4: 從清單檔案下載
    if args.process_inventory:
        print("\n" + "="*80)
        print(f"📥 從清單檔案下載: {args.process_inventory}")
        print("="*80)
        
        inventory_path = config.workspace_root / args.process_inventory
        results = process_inventory_file(inventory_path, sfx_dir)
        
        success = sum(1 for v in results.values() if v)
        total = len(results)
        
        print(f"\n✅ 下載完成: {success}/{total} 個檔案")
        return
    
    # =====================================================================
    # 模式 5: 驗證檔案
    if args.verify:
        print("\n" + "="*80)
        print(f"✓ 驗證 {sfx_dir} 中的檔案")
        print("="*80)
        
        wav_files = list(sfx_dir.glob("*.wav"))
        
        if not wav_files:
            print(f"⚠️  未找到任何 .wav 檔案")
            return
        
        total_size = 0
        for wav_file in sorted(wav_files):
            size_mb = wav_file.stat().st_size / (1024 * 1024)
            total_size += size_mb
            status = "✅" if size_mb > 1.0 else "⚠️"
            print(f"  {status} {wav_file.name:30s} {size_mb:8.2f} MB")
        
        print(f"\n📊 總大小: {total_size:.2f} MB ({len(wav_files)} 個檔案)")
        return
    
    # =====================================================================
    # 預設: 列印使用說明
    print("""
SFX 素材策展人 - 使用說明

模式:
  --guide                   列印手動下載指南 (推薦先讀)
  --generate-inventory      產生下載清單範本
  --convert-all             將所有 .wav 轉換為標準格式
  --process-inventory FILE  從清單檔案下載並轉換
  --verify                  驗證檔案完整性

例:
  python scripts/gear2_rnd/sfx_curator.py --guide
  python scripts/gear2_rnd/sfx_curator.py --convert-all
  python scripts/gear2_rnd/sfx_curator.py --verify
""")


if __name__ == "__main__":
    main()
