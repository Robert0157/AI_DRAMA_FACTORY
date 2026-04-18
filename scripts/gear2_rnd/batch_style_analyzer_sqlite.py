#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SQLite 版本：YouTube 多模態風格批量分析工具
功能：從 video_input.txt 讀取多個 URL，進行智能去重，分析音頻和影片，直接累積到 SQLite 資料庫
"""

import os
import sys
import json
import sqlite3
import subprocess
import threading
import time
import re
import hashlib
import requests
import base64
import math
import numpy as np
import cv2
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Tuple
from urllib3.exceptions import InsecureRequestWarning
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed


# 禁用 SSL 警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# 導入共用基建與資料庫模塊
SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from common.env_manager import config
from common.atomic_io import atomic_write_text, atomic_write_json
from style_database import StyleDatabase

# ============= 配置 =============
API_KEY = config.ZHIPUAI_API_KEY

if not API_KEY:
    print(json.dumps({"status": "ERROR", "message": "無法獲取 ZHIPUAI_API_KEY（請檢查 env_manager / .env）"}))
    sys.exit(1)

ZHIPUAI_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL_NAME = "glm-4-flash"

# 文件路徑
WORKSPACE_ROOT = Path(config.workspace_root)
VIDEO_INPUT_FILE = WORKSPACE_ROOT / "video_input.txt"
TEMP_DIR = WORKSPACE_ROOT / ".temp"

TEMP_DIR.mkdir(exist_ok=True)

# 初始化資料庫
db = StyleDatabase()

# 🚀 並行處理鎖：防止日誌輸出混亂
print_lock = threading.Lock()


# ============= 工具函式 =============

def safe_print(*args, **kwargs):
    """執行緒安全的打印函式"""
    with print_lock:
        print(*args, **kwargs)

def extract_video_id_from_url(url: str) -> str:
    """從 YouTube 或 B 站 URL 提取影片 ID (CTO 修正版本)"""
    try:
        # YouTube 處理
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url:
            return url.split("youtu.be/")[1].split("?")[0]
        # B 站處理 (支援 av 號與 BV 號)
        elif "bilibili.com/video/" in url:
            video_id = url.split("bilibili.com/video/")[1].split("/")[0].split("?")[0]
            return video_id
    except:
        pass
    return None


def _extract_prefixed_value(line: str, prefix: str) -> str:
    """從一行中擷取 Keyword= 或 URL= 的值"""
    patterns = [
        rf'{prefix}\s*=\s*"([^"]+)"',
        rf"{prefix}\s*=\s*'([^']+)'",
        rf'{prefix}\s*=\s*(\S+)'
    ]
    for pattern in patterns:
        match = re.match(pattern, line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def parse_video_input(file_path: str) -> Tuple[List[str], List[str]]:
    """解析 video_input.txt，回傳去重後的 Keywords 與 URL"""
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"未找到文件: {file_path}")

    keywords = []
    urls = []
    seen_keywords = set()
    seen_urls = set()
    duplicate_kw = 0
    duplicate_url = 0

    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            kw = _extract_prefixed_value(line, "Keyword")
            if kw:
                normalized_kw = kw.lower()
                if normalized_kw in seen_keywords:
                    safe_print(f"⚠️ 重複關鍵字 (line {line_no}): {kw}")
                    duplicate_kw += 1
                    continue
                seen_keywords.add(normalized_kw)
                keywords.append(kw)
                continue

            url = _extract_prefixed_value(line, "URL")
            if url:
                normalized_url = url.lower()
                if normalized_url in seen_urls:
                    safe_print(f"⚠️ 重複 URL (line {line_no}): {url}")
                    duplicate_url += 1
                    continue
                seen_urls.add(normalized_url)
                urls.append(url)
                continue

            safe_print(f"⚠️ 無法解析的行 (line {line_no}): {line}")

    safe_print(f"✅ video_input.txt 解析完成：{len(keywords)} 個關鍵字，{len(urls)} 個 URL")
    if duplicate_kw:
        safe_print(f"⚠️ 偵測到 {duplicate_kw} 個重複關鍵字，僅保留第一筆")
    if duplicate_url:
        safe_print(f"⚠️ 偵測到 {duplicate_url} 個重複 URL，僅保留第一筆")
    return keywords, urls


def read_keywords_from_file(file_path: str) -> list:
    """從文件讀取關鍵字清單"""
    keywords, _ = parse_video_input(file_path)
    return keywords


def search_youtube_videos(keyword: str, max_results: int = 10) -> list:
    """用 yt-dlp 搜尋 YouTube 影片"""
    urls = []
    try:
        print(f"  🔍 搜尋 YouTube: '{keyword}'")
        cmd = [
            "yt-dlp",
            f"ytsearch{max_results}:{keyword}",
            "--dump-json",
            "--no-warnings"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            # yt-dlp 會輸出 jsonlines 格式（每行一個 JSON 對象）
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    
                    # 跳過播放列表元數據行，只取視頻條目
                    if data.get('_type') == 'playlist':
                        continue
                    
                    # 提取 URL（優先用 webpage_url，否則用 url）
                    video_url = data.get('webpage_url') or data.get('url')
                    if video_url and ('youtube.com' in video_url or 'youtu.be' in video_url):
                        urls.append(video_url)
                        title = data.get('title', 'Unknown')[:50]
                        print(f"    ✓ {title}...")
                except json.JSONDecodeError:
                    continue
        
        print(f"  ✅ 找到 {len(urls)} 個 YouTube 影片")
    except Exception as e:
        print(f"  ⚠️  YouTube 搜尋失敗: {e}")
    
    return urls[:max_results]


def search_bilibili_videos(keyword: str, max_results: int = 10) -> list:
    """搜尋 B 站影片（使用官方 API）"""
    urls = []
    try:
        print(f"  🔍 搜尋 B 站: '{keyword}'")
        
        # B 站搜尋 API
        search_url = "https://api.bilibili.com/x/web-interface/search/type"
        params = {
            "search_type": "video",
            "keyword": keyword,
            "page": 1,
            "pagesize": max_results,
            "order": "totalrank",
            "duration": 0,
            "tids": 0
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(search_url, params=params, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0 and data.get("data", {}).get("result"):
                for item in data["data"]["result"][:max_results]:
                    video_id = item.get("aid") or item.get("id")
                    if video_id:
                        url = f"https://www.bilibili.com/video/av{video_id}"
                        urls.append(url)
                        print(f"    ✓ {item.get('title', 'Unknown')[:50]}...")
        
        print(f"  ✅ 找到 {len(urls)} 個 B 站影片")
    except Exception as e:
        print(f"  ⚠️  B 站搜尋失敗: {e}")
    
    return urls[:max_results]


def read_urls_from_keywords(file_path: str, yt_per_keyword: int = 10, bili_per_keyword: int = 10) -> list:
    """從 video_input.txt 讀取關鍵字並搜尋, 同時保留直接提供的 URL"""
    keywords, direct_urls = parse_video_input(file_path)

    if not keywords and not direct_urls:
        safe_print("❌ 未找到關鍵字或 URL")
        return []

    total_sources = len(keywords) + len(direct_urls)
    safe_print(f"\n📋 來源總數: {total_sources}（關鍵字 {len(keywords)}，URL {len(direct_urls)}）")
    safe_print("===============================")

    all_urls = list(direct_urls)

    for idx, keyword in enumerate(keywords, 1):
        safe_print(f"\n🎯 關鍵字 {idx}/{len(keywords)}: '{keyword}'")

        yt_urls = search_youtube_videos(keyword, yt_per_keyword)
        all_urls.extend(yt_urls)

        bili_urls = search_bilibili_videos(keyword, bili_per_keyword)
        all_urls.extend(bili_urls)

    safe_print("\n===============================")
    safe_print(f"✅ 總共找到 {len(all_urls)} 個 URL")
    return all_urls


def remove_url_from_file(file_path: str, url_to_remove: str) -> bool:
    """從 video_input.txt 中移除失敗的 URL"""
    try:
        if not os.path.exists(file_path):
            return False
        
        # 讀取文件內容
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        
        # 分割 URL
        urls = content.split()
        
        # 找到並移除失敗的 URL
        if url_to_remove not in urls:
            return False
        
        urls.remove(url_to_remove)
        
        # 添加 end 終止符
        if urls and urls[-1].lower() != "end":
            urls.append("end")
        
        # 寫回文件（原子寫入）
        atomic_write_text(file_path, " ".join(urls))
        
        print(f"  ℹ️  已從 video_input.txt 中移除: {url_to_remove}")
        return True
    except Exception as e:
        print(f"  ⚠️  移除 URL 失敗: {e}")
        return False


def fetch_video_metadata_with_ytdlp(url: str) -> dict:
    """使用 yt-dlp 獲取影片元數據 (支援 B 站 Cookie，拒絕播放清單)"""
    try:
        cookies_path = WORKSPACE_ROOT / "cookies.txt"
        is_bilibili = "bilibili.com" in url
        
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-warnings",
            "--no-playlist",  # 🚀 CTO 鐵律：拒絕下載整個播放清單，只抓單集！
            url
        ]
        
        if is_bilibili and cookies_path.exists():
            cmd.insert(1, "--cookies")
            cmd.insert(2, str(cookies_path))
            
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True)
        
        # 🚀 CTO 防噎死：只抓取第一行有效的 JSON，無視多餘輸出
        valid_lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip().startswith('{')]
        if not valid_lines:
            raise Exception("yt-dlp 沒有返回有效的 JSON")
            
        data = json.loads(valid_lines[0])
        
        return {
            "title": data.get("title", "Unknown Title"),
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
            "duration": data.get("duration", 0)
        }
    except Exception as e:
        print(f"❌ 元數據抓取失敗: {e}")
        return None

def download_first_180_seconds(url: str, video_id: str) -> str:
    """從 YouTube 或 B 站下載前 180 秒影片 (無差別副檔名吞噬版)"""
    output_path = TEMP_DIR / f"batch_video_{video_id}.mp4"
    
    if output_path.exists() and output_path.stat().st_size > 102400:
        return str(output_path)
        
    import shutil
    ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"
    
    try:
        cookies_path = WORKSPACE_ROOT / "cookies.txt"
        is_bilibili = "bilibili.com" in url
        
        # 🚀 CTO 修正：不寫死 .mp4，讓 yt-dlp 自由發揮 %(ext)s
        dl_template = str(TEMP_DIR / f"batch_video_{video_id}.%(ext)s")
        
        cmd = [
            "yt-dlp",
            "-S", "res:480",  
            "--no-playlist",      # 🚀 嚴禁下載播放清單
            "--ffmpeg-location", ffmpeg_exe,
            "-o", dl_template,
        ]
        
        if is_bilibili and cookies_path.exists():
            cmd.insert(1, "--cookies")
            cmd.insert(2, str(cookies_path))
            
        cmd.append(url)
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
        
        # 🚀 CTO 智能尋標：尋找剛才到底下載了什麼副檔名 (.webm, .mkv, .mp4 等)
        downloaded_files = list(TEMP_DIR.glob(f"batch_video_{video_id}.*"))
        valid_files = [f for f in downloaded_files if not f.name.endswith(('.part', '.ytdl', '.mp4'))]
        
        # 如果有抓到其他格式的原始檔，或者是直接生成了 .mp4
        source_file = valid_files[0] if valid_files else (output_path if output_path.exists() else None)
        
        if source_file and source_file.exists() and source_file.stat().st_size > 0:
            temp_trimmed = TEMP_DIR / f"batch_video_{video_id}_trimmed.mp4"
            cmd_trim = [
                ffmpeg_exe,
                "-i", str(source_file),
                "-t", "180",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-c:a", "aac",
                str(temp_trimmed),
                "-y"
            ]
            subprocess.run(cmd_trim, capture_output=True, timeout=180, check=True)
            
            # 刪除原始雜亂檔案 (如 .webm)
            if source_file != output_path:
                source_file.unlink()
            if output_path.exists():
                output_path.unlink()
                
            temp_trimmed.rename(output_path)
            return str(output_path)
        else:
            raise Exception("下載完成但找不到實體檔案，或檔案為 0KB")
            
    except Exception as e:
        print(f"  ❌ 影片下載失敗: {e}")
        return None
    
def extract_keyframes_with_ffmpeg(video_path: str, video_id: str, num_frames: int = 25) -> list:
    """
    【CTO 修復版】從前 180 秒影片中均勻提取候選影格
    自帶 FFmpeg 動態尋標、容錯機制與極限解析度壓縮。
    """
    import shutil
    # 🚀 動態尋找，找不到就退回預設字串讓系統報錯
    ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"
    
    frames = []
    try:
        # 假設影片最長處理 180 秒，安全範圍取 170 秒，避免抓到結尾黑畫面
        duration_to_sample = 170 
        
        print(f"  🎬 開始使用 FFmpeg 提取 {num_frames} 張候選影格...")
        
        for i in range(1, num_frames + 1):
            timestamp = i * (duration_to_sample // num_frames)
            output_file = TEMP_DIR / f"frame_{video_id}_{timestamp}.jpg"
            
            # 刪除舊文件避免干擾
            if output_file.exists():
                output_file.unlink()
            
            success = False
            # 容錯機制：如果該時間點剛好是壞幀或黑屏，嘗試相鄰時間點 (-1s, +1s, -2s, +2s)
            for ts_offset in [0, -1, 1, -2, 2]:
                try_timestamp = max(0, timestamp + ts_offset)
                output_file = TEMP_DIR / f"frame_{video_id}_{try_timestamp}.jpg"
                
                try:
                    # FFmpeg 極速截圖指令 (軍規動態版)
                    # FFmpeg 極速截圖指令 (軍規簡化版)
                    cmd = [
                        ffmpeg_exe,
                        "-ss", str(try_timestamp),
                        "-i", video_path,
                        "-frames:v", "1",      # 現代寫法，取代 -vframes
                        "-q:v", "2",           # 提高 JPG 截圖容錯率
                        "-s", "384x216",
                        "-y",
                        str(output_file)
                    ]
                    # 執行指令，超時設定 30 秒
                    result = subprocess.run(cmd, capture_output=True, timeout=30, check=False)
                    
                    if result.returncode == 0 and output_file.exists():
                        # 檢查檔案是否有效 (避免生成 0KB 的壞檔)
                        if output_file.stat().st_size > 0:
                            frames.append(str(output_file))
                            success = True
                            break
                        else:
                            output_file.unlink()  # 刪除壞檔
                except Exception as e:
                    pass # 忽略單次嘗試失敗，繼續迴圈嘗試下一個 ts_offset
            
            if not success:
                print(f"  ⚠️  第 {i} 張幀提取失敗（時間戳 {timestamp}s），已跳過")
        
        print(f"  ✅ 已成功提取 {len(frames)} 張候選影格，準備進入去重階段")
        return frames
        
    except Exception as e:
        print(f"  ❌ 幀提取過程發生嚴重錯誤: {e}")
        return frames
    
def filter_frames_by_ssim(frame_paths: List[str], target_frames: int = 12, similarity_threshold: float = 0.90) -> List[str]:
    """
    【CTO 修復版】使用純 OpenCV (MSE) 進行極速影格去重
    """
    if not frame_paths or len(frame_paths) <= target_frames:
        return frame_paths

    valid_frames = []
    for p in frame_paths:
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                # 轉為灰階並大幅縮小尺寸，極大化運算速度
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, (192, 108))
                valid_frames.append((p, gray))

    if not valid_frames:
        return []

    # 永遠保留第一張
    selected_paths = [valid_frames[0][0]]
    last_selected_gray = valid_frames[0][1]

    # 挑出視覺變化夠大的影格
    for path, gray in valid_frames[1:]:
        # 計算 MSE (均方誤差)，值越大代表畫面變化越大
        err = np.sum((last_selected_gray.astype("float") - gray.astype("float")) ** 2)
        err /= float(gray.shape[0] * gray.shape[1])
        
        # MSE 閾值 (經驗值)：大於 300 通常代表畫面有明顯切換或大動作
        if err > 300: 
            selected_paths.append(path)
            last_selected_gray = gray

    print(f"  🔍 經 MSE 變化偵測，過濾後剩餘 {len(selected_paths)} 張高變化影格")

    # 如果去重後還是太多，均勻抽樣到目標張數 (12張)
    if len(selected_paths) > target_frames:
        indices = np.linspace(0, len(selected_paths) - 1, target_frames, dtype=int)
        selected_paths = [selected_paths[i] for i in indices]
        
    # 如果去重後太少（比如整支影片都是定格畫面），為了填滿十二宮格，將丟棄的補回來
    elif len(selected_paths) < target_frames:
        needed = target_frames - len(selected_paths)
        remaining = [p for p in frame_paths if p not in selected_paths]
        selected_paths.extend(remaining[:needed])

    return selected_paths[:target_frames]

def create_contact_sheet(image_paths: list, video_id: str) -> str:
    """
    【CTO 視覺駭客完整流程】從候選影格到十二宮格電影縮圖表
    
    三階段流程：
    1. 接收 25 張候選影格
    2. 利用 SSIM 去重，過濾冗餘靜態幀，精選 12 張關鍵影格
    3. 用 Pillow 拼接成「單張」電影縮圖表，送給大模型多模態分析
    
    與舊版本的差異：
    - 舊版：直接用全部 10 張幀拼接（Token 浪費）
    - 新版：SSIM 去重 25→12 張（只保留視覺變化最大的關鍵幀）
    """
    if not image_paths:
        return None
    
    print(f"  📸 開始視覺駭客流程：{len(image_paths)} 張候選 → SSIM 去重 → 12 張關鍵 → 十二宮格")
    
    try:
        # ========== 第 1 階段：SSIM 去重與精選 ==========
        # 呼叫 SSIM 去重函式，將 25 張候選精選為 12 張高變化影格
        filtered_frames = filter_frames_by_ssim(image_paths, target_frames=12, similarity_threshold=0.90)
        
        if not filtered_frames:
            print(f"  ❌ SSIM 去重後無影格，使用原始影格")
            filtered_frames = image_paths
        
        # ========== 第 2 階段：讀取與調整尺寸 ==========
        images = [Image.open(p) for p in filtered_frames if os.path.exists(p)]
        if not images:
            return None
        
        print(f"  ✅ 已讀取 {len(images)} 張去重後的影格")
        
        # 統一調整尺寸 (寬 384, 高 216)
        w, h = 384, 216
        images = [img.convert('RGB').resize((w, h)) for img in images]
        
        # ========== 第 3 階段：拼接成十二宮格 ==========
        # 計算網格 (例如 12 張圖 = 4列 x 3行)
        cols = 4
        rows = math.ceil(len(images) / cols)
        
        print(f"  📐 拼接配置：{len(images)} 張 → {cols}×{rows} 網格")
        
        # 建立黑色底圖
        grid = Image.new('RGB', (cols * w, rows * h), color='black')
        
        # 貼上圖片
        for i, img in enumerate(images):
            grid.paste(img, (i % cols * w, i // cols * h))
        
        # ========== 第 4 階段：輸出並驗證 ==========
        # 輸出拼接後的大圖
        output_path = TEMP_DIR / f"contact_sheet_{video_id}.jpg"
        grid.save(str(output_path), 'JPEG', quality=85)  # 保持良好畫質
        
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  ✅ 十二宮格拼接完成！")
        print(f"    原始候選：{len(image_paths)} 張")
        print(f"    去重後：{len(filtered_frames)} 張")
        print(f"    最終拼接：{len(images)} 張 → 1 張大圖")
        print(f"    檔案大小：{file_size_mb:.2f}MB")
        print(f"    Token 節省率估計：~60% (相比直接送全部幀)")
        
        return str(output_path)
    except Exception as e:
        print(f"  ❌ 圖片拼接失敗: {e}")
        return None


def clean_json_response(response_text: str) -> str:
    """清理 GLM 回應中的 Markdown 代碼塊"""
    response_text = response_text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    return response_text.strip()


def analyze_with_glm4v_multimodal(images: list, title: str, description: str, tags: str) -> dict:
    """用 GLM-4.1v-thinking 分析截圖 + 文字元數據 (CTO 終極修復版)"""
    try:
        # [CTO 修復 1] 強制限制最多只看 4 張圖，避免超過 Zhipu 多圖負載上限
        images_to_process = images[:4]
        print(f"🧠 正在調用 GLM-4.1v-thinking 進行多模態分析（{len(images_to_process)} 張圖）...")
        
        # 步驟 1: 將圖片編碼為 Base64
        image_contents = []
        for idx, img_path in enumerate(images_to_process, 1):
            try:
                with open(img_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                image_contents.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                })
            except Exception as e:
                print(f"  ⚠️  第 {idx} 張圖讀取失敗: {e}")
        
        # 步驟 2: 組合文字上下文
        context_text = f"""Title: {title}
Description: {description}
Tags: {tags}
You are analyzing the contact sheet which encodes the emotional rhythm inside the first 180 seconds of the video. Return ONLY a valid JSON matching the schema below, honoring every constraint.
{{
    "video_prompt": "visual style in English",
    "audio_prompt": "instrumental music style in English",
    "video_genes": {{"visual_style": "", "color_palette": ""}},
    "audio_genes": {{
        "genre": "",
        "instruments": "",
        "story_backbone": "",
        "foley_array": []
    }}
}}
Rules:
1. "story_backbone" must be a concise ~50-character Chinese description of the emotional arc (e.g., "前段壓抑沉悶 -> 中段機械式重複 -> 結尾詭異釋懷").
2. "foley_array" must list 2~3 entries selected from ["keyboard.wav", "clock_tick.wav", "rain.wav", "paper_flip.wav"], picking the noise textures that best match the atmosphere.
3. Focus on the contact sheet when reasoning; the captions should assist future music generation.
"""
        
        # [CTO 修復 2] 致命關鍵：Text 必須放在 content 陣列的第一位！
        messages_content = [{"type": "text", "text": context_text}] + image_contents
        
        # 步驟 3: 組建 API 請求
        payload = {
            "model": "glm-4.1v-thinking-flashx", 
            "messages": [
                {
                    "role": "user",
                    "content": messages_content
                }
            ]
        }
        
        # 步驟 4: 呼叫 API
        # 🚀 CTO 補丁：確實定義 headers 變數
        req_headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        # 發送請求（v8.3 合規：429/500 + 網路瞬斷 指數退避）
        last_exc = None
        response = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(
                    ZHIPUAI_API_URL,
                    headers=req_headers,
                    json=payload,
                    verify=False,
                    timeout=(30, 300)
                )

                # 可重試錯誤：429 或 5xx
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    raise requests.HTTPError(f"HTTP {response.status_code}: {response.text[:200]}")
                break
            except (requests.RequestException, requests.Timeout) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    _backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
                    print(f"  ⚠️ GLM API 重試 {attempt}/{MAX_RETRIES}：{exc}，{_backoff:.1f}s 後再試")
                    time.sleep(_backoff)
                    continue
                raise Exception(f"GLM API 最終失敗: {exc}") from exc
        if response is None and last_exc:
            raise Exception(f"GLM API 無回應: {last_exc}")
        
        # [CTO 修復 3] 拆除遮罩！印出智譜伺服器真實的報錯訊息
        if response.status_code != 200:
            error_detail = response.text
            print(f"\n❌ [智譜原生報錯攔截] HTTP {response.status_code}")
            print(f"❌ 錯誤詳情: {error_detail}\n")
            raise Exception(f"API 拒絕請求 (請看上方紅字真實死因)")
        
        result = response.json()
        response_text = result['choices'][0]['message']['content']
        
        # 清理 Markdown 代碼塊
        response_text = clean_json_response(response_text)
        response_json = json.loads(response_text)
        audio_genes = response_json.get("audio_genes", {})
        if not isinstance(audio_genes, dict):
            audio_genes = {}
        story_backbone = audio_genes.get("story_backbone", "")
        if not isinstance(story_backbone, str):
            story_backbone = str(story_backbone)
        audio_genes["story_backbone"] = story_backbone.strip()

        foley_array = audio_genes.get("foley_array", [])
        if isinstance(foley_array, str):
            foley_array = [foley_array]
        foley_array = [item for item in (foley_array or []) if isinstance(item, str) and item]
        audio_genes["foley_array"] = foley_array

        video_genes = response_json.get("video_genes", {})
        if not isinstance(video_genes, dict):
            video_genes = {}
        
        return {
            "video_prompt": response_json.get("video_prompt", ""),
            "audio_prompt": response_json.get("audio_prompt", ""),
            "video_genes": video_genes,
            "audio_genes": audio_genes
        }
    
    except Exception as e:
        print(f"❌ GLM-4V 多模態分析失敗: {e}")
        return {"video_prompt": "", "audio_prompt": "", "video_genes": {}, "audio_genes": {}}


def cleanup_temp_files(frame_files: list, video_file: Path):
    """清理臨時檔案"""
    for frame_file in frame_files:
        if frame_file and Path(frame_file).exists():
            try:
                Path(frame_file).unlink()
            except:
                pass
    if video_file and video_file.exists():
        try:
            video_file.unlink()
        except:
            pass


def process_single_url(url: str, index: int, total: int) -> dict:
    """處理單個 URL 並存儲到資料庫"""
    video_id = extract_video_id_from_url(url)
    if not video_id:
        print(f"❌ 無效的 URL: {url}")
        db.log_processing(url, "", "FAILED", "無效的 URL")
        return {"status": "FAILED", "url": url, "reason": "無效的 URL"}
    
    # ============= 去重檢查 =============
    print(f"\n{'='*60}")
    print(f"🎬 YouTube 批量風格分析工具 [第 {index}/{total} 個]")
    print(f"{'='*60}")
    print(f"🔗 處理 URL: {url}")
    print(f"📌 Video ID: {video_id}")
    
    # 檢查 1: 是否已在資料庫中
    if db.video_id_exists(video_id):
        print(f"⏭️  已在資料庫中，跳過處理")
        db.log_processing(url, video_id, "SKIPPED", "已在資料庫中")
        return {"status": "SKIPPED", "url": url, "video_id": video_id, "reason": "已在資料庫中"}
    
    # 檢查 2: 本次會話中是否已處理過
    already_processed, existing_id = db.url_already_processed(url)
    if already_processed:
        print(f"⏭️  本次會話已處理過，跳過")
        db.log_processing(url, video_id, "SKIPPED", "本次會話已處理")
        return {"status": "SKIPPED", "url": url, "video_id": video_id, "reason": "本次會話已處理"}
    
    # ============= CTO 工程駭客方案 =============
    print("\n【步驟 1/4】抓取元數據...")
    metadata = fetch_video_metadata_with_ytdlp(url)
    if not metadata:
        db.log_processing(url, video_id, "FAILED", "元數據抓取失敗")
        return {"status": "FAILED", "url": url, "reason": "元數據抓取失敗"}
    print(f"  ✅ 標題: {metadata['title'][:60]}...")
    
    print("\n【步驟 2/4】下載前 180 秒（3 分鐘）影片...")
    video_path = download_first_180_seconds(url, video_id)
    if not video_path:
        db.log_processing(url, video_id, "FAILED", "影片下載失敗")
        return {"status": "FAILED", "url": url, "reason": "影片下載失敗"}
    print(f"  ✅ 已下載: {Path(video_path).name}")
    
    print("\n【步驟 3/4】提取 12 張關鍵截圖（支援 3 分鐘 MV 完整節奏）...")
    frames = extract_keyframes_with_ffmpeg(video_path, video_id, num_frames=25)  # CTO 視覺駭客：從 6 → 12 張
    if not frames or len(frames) < 6:
        cleanup_temp_files(frames, Path(video_path))
        db.log_processing(url, video_id, "FAILED", f"幀提取失敗（只獲得 {len(frames)} 張，需要 6 張以上）")
        return {"status": "FAILED", "url": url, "reason": f"幀提取失敗（只獲得 {len(frames)} 張）"}
    
    # 🚀 [CTO 視覺駭客啟動：電影縮圖表戰術] 將 12 張圖片合體為 1 張大圖！
    contact_sheet_path = create_contact_sheet(frames, video_id)
    if not contact_sheet_path:
        cleanup_temp_files(frames, Path(video_path))
        db.log_processing(url, video_id, "FAILED", "圖片拼接失敗")
        return {"status": "FAILED", "url": url, "reason": "圖片拼接失敗"}
    
    print("\n【步驟 4/4】調用 GLM-4V-Plus 進行『縮圖表』多模態分析...")
    # ⚡ 現在只傳遞拼接後的「1 張大圖」，100% 繞過 API 多圖限制！
    analysis_result = analyze_with_glm4v_multimodal(
        [contact_sheet_path],  # 陣列裡只有一張拼接後的大圖
        metadata['title'],
        metadata['description'],
        metadata['tags']
    )
    
    if not analysis_result.get("video_prompt") or not analysis_result.get("audio_prompt"):
        print(f"❌ 分析結果不完整")
        cleanup_temp_files(frames + [contact_sheet_path], Path(video_path))
        db.log_processing(url, video_id, "FAILED", "分析結果不完整")
        return {"status": "FAILED", "url": url, "reason": "分析結果不完整"}
    
    # 插入到資料庫
    print("\n【步驟 5/5】存入 SQLite...")
    theme_name = f"Theme_{video_id}"
    
    # 提取潘朵拉基因（新增）
    video_genes_str = json.dumps(analysis_result.get("video_genes", {}), ensure_ascii=False)
    audio_genes_str = json.dumps(analysis_result.get("audio_genes", {}), ensure_ascii=False)
    
    if db.insert_entry(video_id, theme_name, analysis_result["audio_prompt"], analysis_result["video_prompt"], video_genes_str, audio_genes_str):
        print(f"✅ 已添加到資料庫: {video_id}")
        print(f"   音樂: {analysis_result['audio_prompt'][:80]}...")
        print(f"   視覺: {analysis_result['video_prompt'][:80]}...")
        print(f"   基因: 視覺={video_genes_str[:50]}... 音樂={audio_genes_str[:50]}...")
        db.log_processing(url, video_id, "SUCCESS")
        # 📍 [CTO 視覺駭客清理] 包括原始 12 張截圖 + 拼接後的大圖
        cleanup_temp_files(frames + [contact_sheet_path], Path(video_path))
        time.sleep(3)  # CTO 速率限制防護：避免 HTTP 429
        return {"status": "SUCCESS", "url": url, "video_id": video_id}
    else:
        print(f"❌ 資料庫插入失敗: {video_id}")
        db.log_processing(url, video_id, "FAILED", "資料庫插入失敗")
        cleanup_temp_files(frames + [contact_sheet_path], Path(video_path))
        time.sleep(3)  # CTO 速率限制防護：避免 HTTP 429
        return {"status": "FAILED", "url": url, "reason": "資料庫插入失敗"}


def _compute_file_hash(file_path: str) -> str:
    """計算檔案內容的 SHA256 雜湊值"""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except:
        return ""


def _get_stored_input_hash() -> str:
    """從快取檔案中讀取 video_input.txt 的雜湊值"""
    hash_file = WORKSPACE_ROOT / ".video_input_hash"
    try:
        if hash_file.exists():
            with open(hash_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
    except:
        pass
    return ""


def _save_input_hash(hash_value: str):
    """保存 video_input.txt 的雜湊值"""
    hash_file = WORKSPACE_ROOT / ".video_input_hash"
    try:
        atomic_write_text(hash_file, hash_value)
    except Exception as exc:
        safe_print(f"⚠️  無法保存 hash 檔案: {exc}")


def load_or_build_url_pool() -> List[str]:
    """載入 URL 池，若 video_input.txt 有變動則自動更新
    
    工作流程：
    1. 計算 video_input.txt 的內容雜湊值
    2. 與快取的雜湊值比對
    3. 若相同 → 直接使用舊 URL 池
    4. 若不同 → 重新搜尋新內容，與舊池合併去重後保存
    """
    url_pool_file = WORKSPACE_ROOT / ".url_pool.json"
    current_hash = _compute_file_hash(str(VIDEO_INPUT_FILE))
    stored_hash = _get_stored_input_hash()

    # 【情況 1】首次執行或檔案無內容
    if not current_hash or not VIDEO_INPUT_FILE.exists():
        safe_print("⚠️  video_input.txt 不存在或為空")
        return []

    # 【情況 2】檔案內容未變動，直接使用快取
    if current_hash == stored_hash and url_pool_file.exists():
        try:
            with open(url_pool_file, 'r', encoding='utf-8') as f:
                urls = json.load(f)
            if isinstance(urls, list) and urls:
                safe_print(f"✅ 已載入快取 URL 池，共 {len(urls)} 個 URL")
                return urls
        except Exception as exc:
            safe_print(f"⚠️  URL 池讀取失敗: {exc}")

    # 【情況 3】檔案有變動，需要更新 URL 池
    if current_hash != stored_hash:
        safe_print("🔄 偵測到 video_input.txt 有變動，正在更新 URL 池...")
        
        # 讀取舊 URL 池（如果存在）
        old_urls = set()
        if url_pool_file.exists():
            try:
                with open(url_pool_file, 'r', encoding='utf-8') as f:
                    old_urls = set(json.load(f) or [])
                safe_print(f"   舊 URL 池: {len(old_urls)} 個")
            except:
                pass
        
        # 搜尋新內容中的 URL
        safe_print("   正在搜尋新的 URL...")
        new_urls = read_urls_from_keywords(str(VIDEO_INPUT_FILE), yt_per_keyword=10, bili_per_keyword=10)
        
        # 合併去重
        merged_urls = list(dict.fromkeys(old_urls | set(new_urls)))  # 去重並保持順序
        added_count = len(merged_urls) - len(old_urls)
        
        safe_print(f"   舊 + 新: {len(merged_urls)} 個 ({added_count:+d})")
        
        # 保存更新後的 URL 池
        try:
            atomic_write_json(url_pool_file, merged_urls, indent=2)
            _save_input_hash(current_hash)
            safe_print(f"✅ URL 池已更新並保存\n")
            return merged_urls
        except Exception as exc:
            safe_print(f"⚠️  無法保存 URL 池: {exc}")
            return list(old_urls)

    # 【情況 4】首次建立 URL 池
    safe_print("💾 首次建立 URL 池，正在搜尋...")
    urls = read_urls_from_keywords(str(VIDEO_INPUT_FILE), yt_per_keyword=10, bili_per_keyword=10)
    if urls:
        try:
            atomic_write_json(url_pool_file, urls, indent=2)
            _save_input_hash(current_hash)
            safe_print(f"✅ URL 池已建立: {len(urls)} 個 URL\n")
        except Exception as exc:
            safe_print(f"⚠️  無法保存 URL 池: {exc}")
    else:
        safe_print("❌ 無法從 video_input.txt 搜尋到任何 URL")
    return urls


def load_processed_urls() -> Set[str]:
    """從 processing_log 讀取已完成的 URL"""
    processed = set()
    try:
        conn = sqlite3.connect(str(WORKSPACE_ROOT / "assets/data/style_vault.db"))
        c = conn.cursor()
        c.execute("SELECT DISTINCT url FROM processing_log")
        processed = {row[0] for row in c.fetchall() if row[0]}
        conn.close()
        safe_print(f"📊 processing_log 已記錄 {len(processed)} 個 URL")
    except Exception as exc:
        safe_print(f"⚠️  無法讀取 processing_log: {exc}")
    return processed


def build_todo_urls(url_pool: List[str], processed: Set[str]) -> List[str]:
    """過濾掉已處理的 URL"""
    if not url_pool:
        return []
    todo = [url for url in url_pool if url not in processed]
    skipped = len(url_pool) - len(todo)
    if skipped > 0:
        safe_print(f"⏭️  跳過已處理的 {skipped} 個 URL")
    return todo


def main():
    """主程式"""
    try:
        safe_print("\n" + "="*70)
        safe_print("🚀 【素材基因資料庫採集 - 單一主控腳本】")
        safe_print("="*70)

        url_pool = load_or_build_url_pool()
        if not url_pool:
            return

        processed_urls = load_processed_urls()
        todo_urls = build_todo_urls(url_pool, processed_urls)

        if not todo_urls:
            safe_print("\n⚠️  所有 URL 均已處理完畢！")
            safe_print(f"📊 資料庫現有: {db.count_entries()} 個條目")
            safe_print(f"📊 已處理記錄: {len(processed_urls)} 個\n")
            safe_print("💡 系統將自動監控 video_input.txt 的變動：")
            safe_print("   • 若要新增關鍵字，編輯 video_input.txt 後直接執行腳本")
            safe_print("   • 若要新增 URL，編輯 video_input.txt 後直接執行腳本")
            safe_print("   • 系統會自動偵測變動並重新搜尋 → 無需手動操作\n")
            return

        safe_print(f"\n✅ 待處理 URL 數量: {len(todo_urls)}")
        safe_print(f"📊 資料庫現有: {db.count_entries()} 個條目\n")

        start_time = time.time()
        results = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_map = {
                executor.submit(process_single_url, url, idx, len(todo_urls)): (idx, url)
                for idx, url in enumerate(todo_urls, 1)
            }

            for future in as_completed(future_map):
                idx, url = future_map[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    safe_print(f"❌ [{idx}/{len(todo_urls)}] 例外: {exc}")
                    results.append({"status": "FAILED", "url": url, "reason": str(exc)})

        elapsed_time = time.time() - start_time
        successful = sum(1 for r in results if r["status"] == "SUCCESS")
        failed = sum(1 for r in results if r["status"] == "FAILED")
        skipped = sum(1 for r in results if r["status"] == "SKIPPED")

        safe_print(f"\n{'='*60}")
        safe_print("🎉 批量分析已完成！")
        safe_print(f"{'='*60}")
        safe_print(f"✅ 成功: {successful} 個")
        safe_print(f"❌ 失敗: {failed} 個")
        safe_print(f"⏭️  跳過: {skipped} 個（重複或已入庫）")
        safe_print(f"📊 資料庫條目: {db.count_entries()}")
        safe_print(f"⏱️  總耗時: {elapsed_time:.1f} 秒 ({elapsed_time/60:.1f} 分鐘)")
        safe_print(f"🚀 使用 3-worker ThreadPoolExecutor")

        stats = db.get_statistics()
        safe_print(f"\n【資料庫統計】")
        safe_print(f"  • 總條目: {stats['total_entries']}")
        safe_print(f"  • 成功處理: {stats['success_processed']}")
        safe_print(f"  • 失敗處理: {stats['failed_processed']}")
        safe_print(f"  • 資料庫大小: {stats['database_size_mb']} MB")
        safe_print(f"  • 路徑: {stats['database_path']}")
        safe_print(f"{'='*60}\n")

        final_result = {
            "status": "COMPLETED",
            "total_urls": len(todo_urls),
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "total_entries": db.count_entries(),
            "elapsed_time_seconds": elapsed_time,
            "throughput_secs_per_url": elapsed_time / len(todo_urls) if todo_urls else 0,
            "parallelization": "3-worker ThreadPoolExecutor",
            "database_path": str(db.db_path),
            "timestamp": datetime.now().isoformat()
        }

        safe_print(json.dumps(final_result, ensure_ascii=False, indent=2))

    except Exception as e:
        safe_print(json.dumps({"status": "ERROR", "message": str(e)}))
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
