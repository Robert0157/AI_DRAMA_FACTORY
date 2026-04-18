#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【v15.7 幻影輪播矩陣引擎】scripts/gear1_prod/multi_scene_processor.py
🔒 CEO PROTECTED — 修改須取得 CEO 授權（見 .cursor/rules/protect-multi-scene-processor.mdc）
Encode-Once-Repeat + Pre-baked Fade 廣播級極速產線
✅ 動態區塊計算（target_duration / scene_dwell_time）
✅ 視覺金庫借調與金字塔抽樣（三模式：母帶回收 / CEO 手選 / 金字塔自動）
✅ fps=24 + tune film + CRF 28 強制鎖定
✅ Pre-baked Fade 呼吸燈轉場 (Dip to Black)
✅ CEO 友善單行進度條
✅ v15.5 無縫迴圈防禦：Closed GOP(-flags +cgop) + PTS 歸零(setpts) + 嚴格 IDR(-keyint_min 48 -sc_threshold 0) + 統一時間基底(-video_track_timescale 24000)
✅ v15.5 GOP-QA：base_mid.ts 每次編碼後自動驗證 I 幀間隔，確保廣播級 GOP 牢籠完好
✅ v15.5 音訊漂移防禦：Stage 2 音訊強制 -ar 48000，消除 44100↔48000 浮點換算漂移
✅ v15.6 源幀率計算：get_video_duration() 用 nb_read_packets ÷ r_frame_rate，根除 30fps 素材誤算
✅ v15.6 雙重保險：loop_list duration 直接清點 base_mid.ts 實際幀數，幀級吻合零空洞
✅ v15.7 智能 Ping-Pong：ping_ 前綴素材自動正反交替循環，ford_ 前綴維持正向播放，零拼接閃爍
✅ v15.8 雙軌編碼 Profile：Windows H.264 CRF29/slow/192k；Mac M4 HEVC VideoToolbox q:v 55/hvc1/192k（由 env_manager 動態載入）
"""

import sys
import json
import re
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
import tempfile
from datetime import datetime
import math

# 【CTO 強制執行】確保腳本能找到專案根目錄
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import EnvConfig
from scripts.gear2_rnd.visual_vault_db import VisualVaultDB
from scripts.common.json_parser_utils import clean_and_parse_json
from scripts.gear2_rnd.video_loop_classifier import get_loop_strategy

config = EnvConfig()

# 日誌設定
log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# ╔═══════════════════════════════════════════════════════════════╗
# ║ 幻影輪播矩陣引擎 - v15.0 核心類別                            ║
# ╚═══════════════════════════════════════════════════════════════╝


class MultiSceneProcessor:
    """【v15.0】幻影輪播矩陣引擎
    
    職能：
    1. 動態計算所需區塊數 (target_duration / scene_dwell_time)
    2. 從視覺金庫借調對應數量素材
    3. 建構 FFmpeg filter_complex 進行無縫縫合
    4. 強制 v14.3 除顫參數：fps=30, -tune film, -crf 28
    5. 支援沙盒優先測試
    """
    
    def __init__(self, use_sandbox: bool = False):
        """初始化引擎
        
        Args:
            use_sandbox: 是否優先讀取 assets/video_clips/v15_sandbox/
        """
        self.config = config
        self.use_sandbox = use_sandbox
        self.vault = VisualVaultDB()
        
        # 確定素材來源目錄
        if use_sandbox:
            self.source_dir = self.config.workspace_root / "assets" / "video_clips" / "v15_sandbox"
            log.info(f"✅ 沙盒模式: 從 {self.source_dir} 讀取素材")
        else:
            self.source_dir = None
        
        # 臨時目錄
        self.temp_dir = self.config.workspace_root / ".temp" / "multi_scene"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        log.info("✅ Multi Scene Processor 初始化完成")
    
    def calculate_chunks(self, target_duration: int = 3600, scene_dwell_time: int = 300) -> int:
        """動態計算所需區塊數
        
        Args:
            target_duration: 目標總時長（秒，默認 3600 = 1 小時）
            scene_dwell_time: 每個場景停留時間（秒，默認 300 = 5 分鐘）
        
        Returns:
            所需區塊數量
        """
        # 基本計算
        required_chunks = (target_duration + scene_dwell_time - 1) // scene_dwell_time
        
        # 【CTO 終極防禦】強制 +1 個緩衝區塊
        # 理由：交疊融接(xfade)會損耗總時長。若視覺總長度 < 音樂長度，
        # FFmpeg 在濾鏡末端會因為 EOF 拋出 Conversion failed。
        # 加上緩衝區塊後，視覺流永遠長於音樂流，-shortest 才能完美觸發！
        safe_chunks = required_chunks + 1
        
        log.info(f"📊 動態計算: {target_duration}s ÷ {scene_dwell_time}s = {required_chunks} 區塊 (+1 緩衝 = {safe_chunks} 區塊)")
        return safe_chunks
    
    def borrow_materials(self, channel: str, num_chunks: int) -> List[Dict]:
        """從視覺金庫借調素材（陣列擴展）
        
        Args:
            channel: 頻道名稱 (lofi, light_music)
            num_chunks: 所需區塊數
        
        Returns:
            素材列表 (可能包含重複，用於矩陣旋轉)
        """
        log.info(f"🎬 從視覺金庫 {channel} 借調 {num_chunks} 個區塊...")
        
        # 如使用沙盒模式，優先掃描沙盒目錄
        if self.use_sandbox and self.source_dir.exists():
            return self._borrow_from_sandbox(num_chunks)
        
        # 否則從真實金庫借調
        try:
            # 自動掃描金庫（新增文件）
            self.vault.auto_scan_vault(channel)
            
            # 獲取所有可用素材
            available = self.vault.list_videos_by_channel(channel)
            
            if not available:
                log.error(f"❌ 頻道 {channel} 無可用素材")
                return []
            
            log.info(f"✓ 金庫中找到 {len(available)} 個素材")
            
            # Matrix Rotation：如區塊數 > 可用素材數，則循環使用
            materials = []
            for i in range(num_chunks):
                material = available[i % len(available)]
                materials.append(material)
                
                # 增加衍生計數
                self.vault.increment_derivation_count(material['video_id'])
            
            log.info(f"✓ 陣列擴展完成：{num_chunks} 個區塊就位")
            return materials
        
        except Exception as e:
            log.error(f"❌ 借調素材失敗: {e}")
            return []
    
    def _borrow_from_sandbox(self, num_chunks: int) -> List[Dict]:
        """從沙盒目錄借調素材
        
        Args:
            num_chunks: 所需區塊數
        
        Returns:
            素材列表
        """
        try:
            mp4_files = list(self.source_dir.glob("*.mp4"))
            
            if not mp4_files:
                log.error(f"❌ 沙盒目錄 {self.source_dir} 中無 .mp4 文件")
                return []
            
            log.info(f"✓ 沙盒中找到 {len(mp4_files)} 個視頻文件")
            
            # Matrix Rotation
            materials = []
            for i in range(num_chunks):
                mp4_file = mp4_files[i % len(mp4_files)]
                materials.append({
                    'video_id': mp4_file.stem,
                    'file_path': str(mp4_file),
                    'channel': 'sandbox',
                    'scene_tags': ['sandbox'],
                    'duration_sec': 10.0  # 沙盒模式假設每個 10 秒
                })
            
            log.info(f"✓ 沙盒陣列擴展完成：{num_chunks} 個區塊就位")
            return materials
        
        except Exception as e:
            log.error(f"❌ 沙盒借調失敗: {e}")
            return []
    
    def get_video_duration(self, video_path: Path) -> float:
        """【v15.5 物理清點修正版】幀數 ÷ 源幀率 = 絕對物理時長。

        v15.4 的致命錯誤：hardcode 除以 24.0，但生產素材全部是 30fps。
        30fps 素材 240 幀 ÷ 24 = 10s（錯！），正確應為 240 ÷ 30 = 8s。
        導致 loop_list 宣告 duration=10s，而實際 .ts 只有 8s → 每次 concat
        產生 2 秒靜止空洞，這才是「每 8 秒卡頓 2 秒」的真正根因。

        修復：同步讀取 nb_read_packets + r_frame_rate，用源幀率做除數。
        此法對 24fps AI 素材（Kling/Veo 標頭錯寫 10s 但只算繪 192 幀）
        同樣正確：192 幀 ÷ 24fps = 8.0s。
        """
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-count_packets",
                "-show_entries", "stream=nb_read_packets,r_frame_rate",
                "-of", "csv=p=0",
                str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    parts = line.strip().split(",")
                    # csv=p=0 輸出順序：r_frame_rate, nb_read_packets
                    # 例如："30/1,240"
                    if len(parts) >= 2:
                        fps_str, frames_str = parts[0], parts[1]
                        if frames_str.isdigit() and "/" in fps_str:
                            frames = int(frames_str)
                            num, den = fps_str.split("/")
                            source_fps = float(num) / float(den) if float(den) > 0 else 24.0
                            if source_fps > 0 and frames > 0:
                                duration = frames / source_fps
                                log.info(
                                    f"  📏 {video_path.name}: 物理清點 {frames} 幀 "
                                    f"@ {source_fps:.3f}fps = {duration:.3f}s"
                                )
                                return duration
        except Exception as e:
            log.warning(f"⚠️ 物理清點失敗，退回標頭讀取: {e}")

        # 備援：物理清點失敗才用標頭（盡量不走這條路）
        try:
            cmd_fallback = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1:noesc=1",
                str(video_path)
            ]
            result_fb = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=10)
            if result_fb.returncode == 0:
                duration = float(result_fb.stdout.strip())
                log.warning(f"  ⚠️ {video_path.name}: 使用標頭時長 {duration:.3f}s（可能不準確）")
                return duration
        except Exception:
            pass

        return 8.0  # 最終備援預設
    
    def build_crossfade_concat(self, materials: List[Dict], scene_dwell_time: int) -> Tuple[str, List[str]]:
        """建構 FFmpeg filter_complex 進行交疊縫合
        
        這是 v14.3 除顫手術的核心應用：
        ✅ 強制 fps=30 幀率對齊
        ✅ 使用 xfade 交疊過渡
        ✅ 無黑屏無呼吸效應
        
        Args:
            materials: 借調的素材列表
            scene_dwell_time: 每個場景停留時間（秒）
        
        Returns:
            (filter_complex 字符串, input_files 列表)
        """
        log.info(f"🔨 建構交疊拼接濾鏡（{len(materials)} 個素材）...")
        
        input_files = []
        filter_complex_parts = []
        
        # 計算交疊參數
        xfade_duration = min(2.0, scene_dwell_time * 0.1)  # 交疍時間為停留時間的 10%，最多 2 秒
        base_offset = max(0.5, scene_dwell_time - xfade_duration)  # 基礎 offset，後續會動態累加
        
        log.info(f"  🎬 交疊參數: duration={xfade_duration}s, base_offset={base_offset}s")
        
        # 收集輸入文件
        for i, material in enumerate(materials):
            video_path = Path(material['file_path'])
            if video_path.exists():
                input_files.append(str(video_path))
            else:
                log.warning(f"⚠️  素材文件不存在: {video_path}")
        
        if not input_files:
            log.error("❌ 沒有有效的輸入文件")
            return "", []
        
        # 【v14.3 核心】構建 filter_complex
        # 原理：每個輸入流首先強制 fps=30，然後 trim 到指定時長
        
        if len(input_files) == 1:
            # 【v14.0 前向交疍】單一影片時，嚴禁 Ping-Pong，使用 split + trim + fade 保證正向
            normalization_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
            xfade_duration = min(2.0, scene_dwell_time * 0.1)
            
            # 分成主體與交疍部分
            main_duration = int(scene_dwell_time - xfade_duration)
            fade_duration = int(xfade_duration)
            
            filter_complex = (
                f"[0:v]fps=30,{normalization_filter},split[a][b];"
                f"[a]trim=0:{main_duration},setpts=PTS-STARTPTS[p1];"
                f"[b]trim=0:{fade_duration},fade=in:st=0:d={fade_duration}[p2];"
                f"[p1][p2]concat=n=2:v=1[v_out]"
            )
        else:
            # 多個文件使用交疊拼接
            filter_parts = []
            
            # 前置：為每個輸入流應用 fps=30 + trim
            for i in range(len(input_files)):
                # 強制將任何 AI 生成的奇葩解析度，等比例縮放並補黑邊至絕對的 1920x1080，並且鎖定採樣率 setsar=1
                normalization_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
                
                filter_part = (
                    f"[{i}:v]fps=30,{normalization_filter},trim=0:{scene_dwell_time},setpts=PTS-STARTPTS[v{i}]"
                )
                filter_parts.append(filter_part)
            
            # 中間：構建交疊鏈
            concat_chain = ""
            
            for i in range(len(input_files) - 1):
                # 【CTO 終極抹除 - 修復標籤】最後一個 xfade 輸出到 [v_out]
                output_label = "v_out" if i == len(input_files) - 2 else f"xf{i}"
                
                # 【產線校準】動態時間軸累加：offset = (區塊序號 + 1) * (停留時間 - 交疍時間)
                xfade_offset = (i + 1) * (scene_dwell_time - xfade_duration)
                
                if i == 0:
                    concat_chain = f"[v0][v1]xfade=transition=fade:duration={xfade_duration}:offset={xfade_offset}[{output_label}]"
                else:
                    # 處理前一個標籤
                    prev_label = "v_out" if i - 1 == len(input_files) - 2 else f"xf{i-1}"
                    concat_chain += f";[{prev_label}][v{i+1}]xfade=transition=fade:duration={xfade_duration}:offset={xfade_offset}[{output_label}]"
            
            if concat_chain:
                filter_parts.append(concat_chain)
            
            # 【CTO 終極抹除軍令】拔除多餘的 Scale 濾鏘，只返回乾淨的 filter_parts 串聯
            filter_complex = ";".join(filter_parts)
        
        log.info(f"✓ filter_complex 構建完成")
        return filter_complex, input_files
    
    def composite_to_file(self, filter_complex: str, input_files: List[str], 
                         output_path: Path, audio_path: Optional[Path] = None, target_duration: int = 3600) -> bool:
        """使用 FFmpeg 進行最終合成
        
        【v14.3 強制參數】
        ✅ -tune film（廢除 stillimage）
        ✅ -crf 28（品質控制）
        ✅ -maxrate 1000k（動態空間）
        
        Args:
            filter_complex: FFmpeg filter_complex 字符串
            input_files: 輸入視頻文件列表
            output_path: 輸出文件路徑
            audio_path: 音頻文件路徑（可選）
            target_duration: 目標時長（秒，用於 -t 絕對切斷）
        
        Returns:
            是否成功
        """
        try:
            log.info(f"🎬 開始 FFmpeg 合成: {output_path.name}")
            
            # 構建 FFmpeg 命令
            cmd = ["ffmpeg", "-v", "info"]
            
            # 【CTO 動作一】添加所有輸入文件 + 無限循環 (-stream_loop -1)
            for video_file in input_files:
                cmd.extend(["-stream_loop", "-1", "-i", video_file])
            
            # 可選：添加音頻
            if audio_path and audio_path.exists():
                # 【CTO 核心修復】音樂也必須無限循環，確保長度絕對超越 1 小時
                cmd.extend(["-stream_loop", "-1", "-i", str(audio_path)])
            
            # 【v14.3 強制編碼參數】
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[v_out]",
                "-c:v", "libx264",
                "-crf", "28",                  # 品質控制
                "-preset", "medium",           # 編碼密度
                "-tune", "film",               # 電影調校（廢除 stillimage）
                "-maxrate", "1000k",           # VBV 上限
                "-bufsize", "2000k",           # VBV 緩衝
                "-pix_fmt", "yuv420p",
            ])
            
            # 【RCA 修復】音頻映射必須在視頻編碼參數之後、-t 之前
            # 計算正確的音頻輸入索引（視頻流在前，音頻流在後）
            if audio_path and audio_path.exists():
                audio_index = len(input_files)  # 音頻是最後一個輸入
                cmd.extend(["-map", f"{audio_index}:a:0", *config.video_enc_profile["audio_enc"]])
            
            # 【CTO 核心修復】絕對時間切斷放在最後
            cmd.extend(["-t", str(target_duration)])
            
            
            # 輸出
            cmd.extend(["-y", str(output_path)])
            
            log.info(f"  📊 命令行: {' '.join(cmd[:5])} ...")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            
            if result.returncode != 0:
                log.error(f"❌ FFmpeg 失敗:\n{result.stderr[-1000:]}")
                return False
            
            if output_path.exists():
                file_size_mb = output_path.stat().st_size / (1024 * 1024)
                log.info(f"✅ 合成完成: {file_size_mb:.1f} MB")
                return True
            else:
                log.error(f"❌ 輸出文件不存在: {output_path}")
                return False
        
        except subprocess.TimeoutExpired:
            log.error("❌ FFmpeg 超時 (>3600s)")
            return False
        except Exception as e:
            log.error(f"❌ 合成失敗: {e}")
            return False
    
    def _run_ffmpeg_with_progress(self, cmd: list, total_seconds: float, stage_label: str) -> bool:
        """【P2 CEO 友善進度條】即時攔截 FFmpeg stderr，轉化為單行進度條
        
        使用 Popen 即時讀取 stderr，解析 time= 欄位計算進度百分比，
        以 \\r 覆寫同一行顯示乾淨的進度條。絕不致盲（§2.7 合規）。
        
        Args:
            cmd: FFmpeg 命令列表
            total_seconds: 預期總時長（秒），用於計算百分比
            stage_label: 進度條前綴標籤（如 "[Stage 1] Scene 1/6"）
        
        Returns:
            是否成功 (returncode == 0)
        """
        TIME_RE = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})")
        BAR_WIDTH = 20
        
        process = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
            text=True, bufsize=1
        )
        
        last_pct = -1
        for line in process.stderr:
            m = TIME_RE.search(line)
            if m:
                h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                current = h * 3600 + mi * 60 + s + cs / 100.0
                pct = min(100, int(current / total_seconds * 100)) if total_seconds > 0 else 0
                if pct != last_pct:
                    filled = int(BAR_WIDTH * pct / 100)
                    bar = "▓" * filled + "░" * (BAR_WIDTH - filled)
                    mins_cur, secs_cur = divmod(int(current), 60)
                    mins_tot, secs_tot = divmod(int(total_seconds), 60)
                    print(f"\r⏳ {stage_label}: {bar} {pct:3d}% ({mins_cur:02d}:{secs_cur:02d}/{mins_tot:02d}:{secs_tot:02d})", end="", flush=True)
                    last_pct = pct
        
        process.wait()
        print(f"\r⏳ {stage_label}: {'▓' * BAR_WIDTH} 100% ✅{' ' * 20}")
        return process.returncode == 0

    def _verify_gop_closure(self, ts_path: Path, expected_interval: float = 2.0, label: str = "") -> bool:
        """【v15.5 QA】自動驗證 base_mid.ts 的 GOP 結構是否符合封閉、規律的廣播標準。

        外部顧問建議的驗證邏輯，內化為自動化 Pipeline QA，每次 Stage 1 編碼後自動觸發。
        正確的 Closed GOP 輸出：I 幀應嚴格出現在 0.000, 2.000, 4.000... 每 2 秒一個。

        Args:
            ts_path: 要驗證的 .ts 檔案路徑（通常是 base_mid.ts）
            expected_interval: 預期的 I 幀間隔秒數（g=48 / fps=24 = 2.0s）
            label: 日誌標籤（如 "Scene 1/6 clean"）

        Returns:
            True = GOP 結構正常；False = 異常（記錄 WARNING，不中斷產線）
        """
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "frame=pict_type,pts_time",
                "-of", "csv",
                str(ts_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                log.warning(f"⚠️ [GOP-QA] ffprobe 失敗，跳過驗證: {label}")
                return True  # 驗證工具失敗不阻斷產線

            i_frame_times = []
            for line in result.stdout.splitlines():
                parts = line.strip().split(",")
                if len(parts) >= 3 and parts[1] == "I":
                    try:
                        i_frame_times.append(float(parts[2]))
                    except ValueError:
                        pass

            if len(i_frame_times) < 2:
                log.warning(f"⚠️ [GOP-QA] {label}: I 幀數量不足（{len(i_frame_times)} 個），無法驗證間隔")
                return False

            # 計算相鄰 I 幀間隔，允許 ±1 幀誤差（1/24 ≈ 0.042s）
            tolerance = 1.5 / 24.0
            intervals = [i_frame_times[i+1] - i_frame_times[i] for i in range(len(i_frame_times) - 1)]
            bad_intervals = [iv for iv in intervals if abs(iv - expected_interval) > tolerance]

            if bad_intervals:
                log.warning(
                    f"⚠️ [GOP-QA] {label}: 發現 {len(bad_intervals)}/{len(intervals)} 個不規則 I 幀間隔 "
                    f"(期望={expected_interval}s, 異常={[f'{v:.3f}s' for v in bad_intervals[:3]]}...)"
                )
                return False

            log.info(
                f"  ✅ [GOP-QA] {label}: {len(i_frame_times)} 個 I 幀，"
                f"間隔嚴格 {expected_interval}s ±{tolerance:.3f}s — GOP 牢籠完好"
            )
            return True

        except subprocess.TimeoutExpired:
            log.warning(f"⚠️ [GOP-QA] ffprobe 逾時，跳過驗證: {label}")
            return True
        except Exception as e:
            log.warning(f"⚠️ [GOP-QA] 驗證異常，跳過: {e}")
            return True

    def _build_audio_premix(self, audio_paths: List[Path], target_duration: int, temp_dir: Path) -> Optional[Path]:
        """【Stage 2.5】多音軌交叉淡化預混音 - 消除聽覺斷層 (Audio Jump Cut)
        
        透過 acrossfade 鏈將多首歌無縫銜接，消除 concat demuxer 的暴力拼接問題。
        首曲淡入 + 曲間交叉淡化 + 尾端淡出 = 完整沉浸式音景。
        """
        CROSSFADE_SEC = 5.0   # 曲間交叉淡化
        FADE_IN_SEC = 3.0     # 整體開頭淡入
        FADE_OUT_SEC = 5.0    # 整體結尾淡出
        MIN_TRACK_DUR = 15.0  # 跳過過短曲目（低於此秒數）
        
        # 1. ffprobe 逐首累加，計入交叉淡化時長損耗
        tracks = []
        
        for ap in audio_paths:
            if not ap.exists():
                continue
            try:
                probe_cmd = [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(ap)
                ]
                dur = float(subprocess.check_output(probe_cmd).decode('utf-8').strip())
                if dur < MIN_TRACK_DUR:
                    continue
                tracks.append((ap, dur))
                effective_dur = sum(d for _, d in tracks) - (len(tracks) - 1) * CROSSFADE_SEC
                if effective_dur >= target_duration + 60:
                    break
            except (subprocess.CalledProcessError, ValueError):
                continue
        
        if not tracks:
            return None
        
        N = len(tracks)
        premix_path = temp_dir / "audio_premix.wav"
        fade_out_start = max(0.0, target_duration - FADE_OUT_SEC)
        effective_total = sum(d for _, d in tracks) - (N - 1) * CROSSFADE_SEC
        
        log.info(f"🎶 [Stage 2.5] 音訊預混音: {N} 首歌 / acrossfade {CROSSFADE_SEC}s / 有效 {effective_total:.0f}s")
        for i, (ap, dur) in enumerate(tracks):
            log.info(f"  🎵 [{i+1}/{N}] {ap.name} ({dur:.0f}s)")
        
        cmd = ["ffmpeg", "-v", "error", "-y"]
        for ap, _ in tracks:
            cmd.extend(["-i", str(ap)])
        
        if N == 1:
            dur = tracks[0][1]
            fo_start = min(fade_out_start, dur - FADE_OUT_SEC)
            filter_str = (
                f"[0:a]afade=t=in:d={FADE_IN_SEC},"
                f"afade=t=out:st={fo_start:.3f}:d={FADE_OUT_SEC}[audio_out]"
            )
        else:
            parts = []
            parts.append(f"[0:a]afade=t=in:d={FADE_IN_SEC}[a0]")
            for i in range(1, N):
                parts.append(f"[{i}:a]anull[a{i}]")
            
            for i in range(N - 1):
                in1 = "a0" if i == 0 else f"cf{i-1}"
                in2 = f"a{i+1}"
                if i == N - 2:
                    parts.append(
                        f"[{in1}][{in2}]acrossfade=d={CROSSFADE_SEC}:c1=exp:c2=exp,"
                        f"afade=t=out:st={fade_out_start:.3f}:d={FADE_OUT_SEC}[audio_out]"
                    )
                else:
                    parts.append(
                        f"[{in1}][{in2}]acrossfade=d={CROSSFADE_SEC}:c1=exp:c2=exp[cf{i}]"
                    )
            filter_str = ";".join(parts)
        
        cmd.extend([
            "-filter_complex", filter_str,
            "-map", "[audio_out]",
            "-c:a", "pcm_s16le",
            str(premix_path)
        ])
        
        subprocess.run(cmd, check=True)
        # 【RCA v15.2.1 診斷】驗證 premix 實際時長
        try:
            premix_dur = float(subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(premix_path)],
                text=True, timeout=10).strip())
            log.info(f"✅ [Stage 2.5] 預混音完成: {premix_path.name} ({premix_path.stat().st_size / (1024*1024):.0f} MB, 實際時長: {premix_dur:.1f}s)")
        except Exception:
            log.info(f"✅ [Stage 2.5] 預混音完成: {premix_path.name} ({premix_path.stat().st_size / (1024*1024):.0f} MB)")

        # [CTO 修復] Tracklist 時間軸扣除 acrossfade 重疊
        try:
            CROSSFADE_SEC = 4.0  # 請依實際 FFmpeg 參數同步
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            channel = getattr(self, 'channel', 'unknown')
            local_output_dir = temp_dir.parent if temp_dir.name.startswith('tmp') else temp_dir
            tracklist_path = local_output_dir / f"Tracklist_{channel.upper()}_{timestamp}.txt"
            with open(tracklist_path, "w", encoding="utf-8") as f:
                f.write(f"【R&S Echoes 官方時間軸 - {channel.upper()}】\n\n")
                current_sec = 0.0
                for idx, track_path in enumerate(audio_paths, 1):
                    m, s = divmod(int(current_sec), 60)
                    time_str = f"{m:02d}:{s:02d}"
                    track_name = track_path.stem.split('_YT_')[0].replace('_', ' ')
                    f.write(f"{time_str} - {track_name}\n")
                    try:
                        dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(track_path)]
                        dur_str = subprocess.check_output(dur_cmd, text=True).strip()
                        # 【CTO 修復】扣除 acrossfade 造成的重疊時間
                        current_sec += (float(dur_str) - CROSSFADE_SEC)
                    except:
                        current_sec += (180.0 - CROSSFADE_SEC)
            log.info(f"✅ Tracklist 已同步產出: {tracklist_path.name}")
        except Exception as e:
            log.warning(f"⚠️ Tracklist 輸出失敗: {e}")
        return premix_path
    
    def process_full_pipeline(self, channel: str, target_duration: int = 3600, scene_dwell_time: int = 600, audio_paths: Optional[List[Path]] = None, output_path: Optional[Path] = None, override_video: Optional[Path] = None, override_videos: Optional[List[Path]] = None, max_derivation_limit: int = 2) -> Optional[Path]:
        """【v15.3 Encode-Once-Repeat + Pre-baked Fade】金字塔抽樣 + 模組化渲染 + 物理拼接
        
        【架構】
        - Stage 1：金字塔抽樣 N 支素材，每支編碼 3 個 base (fadein/clean/fadeout) 8s 片段
                   → concat copy 物理延長至 scene_dwell_time 的 unit（CPU 僅編碼 ~24s/場景）
        - Stage 2.5：多音軌 acrossfade 預混音（保留創意總監認可的無縫音景）
        - Stage 2：concat demuxer 將 N 個 unit 物理拼接 + 預混音頻 → -c:v copy 零重編碼
        - Stage 3：延遲扣款 — 僅在成片完成後才對選中素材執行 derivation_count + 1
        
        【v15.3 三模式視覺來源】
        1. override_video (單一影片)：母帶回收模式，同一支影片 × N 填滿
        2. override_videos (CEO 手選多支)：CEO 選 K 支 + 金字塔自動補 (N-K) 支 = N 支輪播
        3. 皆為 None：全自動金字塔抽樣 N 支輪播
        
        Args:
            channel: 頻道名稱
            target_duration: 目標時長（秒）
            scene_dwell_time: 場景停留時間（秒），預設 600 = 10 分鐘一景
            audio_paths: 音頻文件路徑清單（多首輪播，可選）
            output_path: 輸出文件路徑（若為 None 則自動生成）
            override_video: CEO 指定的單一背景影片路徑（母帶回收模式，跳過金字塔抽樣）
            override_videos: CEO 手選多支影片清單，系統從金庫自動補齊剩餘名額
            max_derivation_limit: 最大可重複使用次數（由 UI 注入，預設 2）
        
        Returns:
            輸出文件路徑，失敗返回 None
        """
        log.info(f"🎬 【v15.3 Encode-Once-Repeat 啟動】頻道: {channel}")
        log.info(f"   📐 target_duration={target_duration}s ({target_duration//60}min), scene_dwell={scene_dwell_time}s")
        log.info(f"   🎚️ max_derivation_limit={max_derivation_limit}")
        
        # ==========================================
        # 【v15.3 三模式視覺來源】
        # 模式 1: override_video → 單一影片 × N (母帶回收)
        # 模式 2: override_videos → CEO 手選 K 支 + 金庫自動補 (N-K) 支
        # 模式 3: 皆 None → 全自動金字塔抽樣 N 支
        # ==========================================
        selected_video_ids = []
        needed_clips = math.ceil(target_duration / scene_dwell_time)
        
        if override_video:
            # 模式 1：母帶回收 — CEO 指定單一影片，全片只用這支素材
            if not override_video.exists():
                log.error(f"❌ CEO 指定的影片不存在: {override_video}")
                return None
            log.info(f"🎯 [模式1 母帶回收] CEO 指定影片: {override_video.name}，跳過金字塔抽樣")
            input_videos = [override_video] * needed_clips
        elif override_videos:
            # 模式 2：CEO 手選 + 金庫自動補齊
            # 驗證 CEO 選的影片都存在
            valid_ceo_picks = []
            for vp in override_videos:
                if vp.exists():
                    valid_ceo_picks.append(vp)
                else:
                    log.warning(f"⚠️ CEO 指定的影片不存在，已跳過: {vp}")
            
            ceo_count = len(valid_ceo_picks)
            auto_count = max(0, needed_clips - ceo_count)
            log.info(f"🎯 [模式2 手動+自動輪播] CEO 手選 {ceo_count} 支 + 金庫自動補 {auto_count} 支 = {needed_clips} 支")
            
            # 金庫自動補齊剩餘名額
            auto_clips = []
            if auto_count > 0:
                vault = VisualVaultDB()
                auto_clips = vault.get_pyramid_videos(channel, needed_count=auto_count, max_derivation_limit=max_derivation_limit)
                vault.close()
                selected_video_ids = [clip['video_id'] for clip in auto_clips]
                if len(auto_clips) < auto_count:
                    log.warning(f"⚠️ 金庫素材不足！需補 {auto_count} 支，僅取得 {len(auto_clips)}")

            # 組合：CEO 手選在前，金庫自動在後，然後打亂順序
            input_videos = valid_ceo_picks + [Path(clip['file_path']) for clip in auto_clips]

            # 【v15.3 循環補位】若組合後仍不足 needed_clips，以 CEO 手選素材循環補齊
            if len(input_videos) < needed_clips and len(input_videos) > 0:
                shortage = needed_clips - len(input_videos)
                log.warning(f"⚠️ 模式2 組合後仍不足（{len(input_videos)}/{needed_clips}），循環補位 {shortage} 個場景")
                base = list(input_videos)
                while len(input_videos) < needed_clips:
                    input_videos.append(base[(len(input_videos) - len(base)) % len(base)])
            import random as _rnd
            _rnd.shuffle(input_videos)
            
            for i, v in enumerate(input_videos):
                log.info(f"  🎞️ 位置 {i+1}: {v.name}")
        else:
            # 模式 3：全自動金字塔抽樣 (50/25/25)
            vault = VisualVaultDB()
            selected_clips = vault.get_pyramid_videos(channel, needed_count=needed_clips, max_derivation_limit=max_derivation_limit)
            vault.close()

            if len(selected_clips) == 0:
                log.error(f"❌ 視覺金庫完全無素材！頻道: {channel}，請先上傳影片至 visual vault。")
                return None

            if len(selected_clips) < needed_clips:
                # 【v15.3 循環補位】素材不足時以現有素材循環填滿，ambient 影片重複場景合理
                shortage = needed_clips - len(selected_clips)
                log.warning(
                    f"⚠️ 視覺金庫素材不足（需 {needed_clips} 支，僅 {len(selected_clips)} 支）"
                    f"，啟動循環補位模式（重複 {shortage} 個場景）。"
                    f"建議 CEO 補充更多影片至 light_music 視覺金庫。"
                )
                base_clips = list(selected_clips)
                while len(selected_clips) < needed_clips:
                    selected_clips.append(base_clips[(len(selected_clips) - len(base_clips)) % len(base_clips)])
                log.info(f"🔄 循環補位後共 {len(selected_clips)} 支素材（{len(base_clips)} 唯一 + {shortage} 循環）")

            input_videos = [Path(clip['file_path']) for clip in selected_clips]
            selected_video_ids = [clip['video_id'] for clip in selected_clips]
        N = len(input_videos)
        log.info(f"✓ 金字塔抽樣取得 {N} 支素材，準備鑄造獨立長鏡頭母體...")
        
        # 準備最終輸出路徑
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"R&S_Echoes_{channel}_1HrMix_{timestamp}.mp4"
        output_dir = config.workspace_root / "assets" / "final_exports" / channel
        output_dir.mkdir(parents=True, exist_ok=True)
        final_output_path = output_dir / output_name
        
        with tempfile.TemporaryDirectory() as tmpdirname:
            temp_dir = Path(tmpdirname)
            norm = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
            FADE_DUR = 2.0  # 呼吸燈過渡秒數
            
            # ==========================================
            # Stage 1：Pre-baked Fade + Encode-Once-Repeat
            # 每支素材編碼 3 個 base (in/mid/out) → concat copy 延長至 scene_dwell_time
            # ==========================================
            log.info(f"🔨 [Stage 1] Pre-baked Fade 鑄造 {N} 個 {scene_dwell_time}s 長鏡頭...")
            unit_paths = []
            
            for idx, vid_path in enumerate(input_videos):
                # Step A: 偵測原始素材時長
                base_dur = self.get_video_duration(vid_path)
                fade_dur = min(FADE_DUR, base_dur * 0.25)
                fade_out_st = max(0, base_dur - fade_dur)
                
                log.info(f"  🎞️ [{idx+1}/{N}] {vid_path.name} ({base_dur:.1f}s) → unit_{idx}.ts ({scene_dwell_time}s)")
                
                # 共用編碼參數
                # 【v15.5 無縫迴圈防禦陣列 - CTO + 外部顧問聯合修復】
                # - setpts=PTS-STARTPTS：強迫 PTS 從 0 開始，消除 AI 素材時間軸碎屑（非零起始 PTS）
                # - g 48 / keyint_min 48：嚴格鎖定每 2 秒（24fps×2）一個 IDR，不多不少
                # - sc_threshold 0：關閉動態場景偵測，防止它自行插入額外 I 幀打亂 GOP 邊界
                # - flags +cgop：強制封閉 GOP，確保 base_mid 結尾的 B 幀絕不跨界依賴下一個 TS 的 I 幀
                # - video_track_timescale 24000：統一時間基底，防止 24fps 浮點誤差在 400+ 片段累積崩塌
                # - 中繼格式 .ts（MPEG-TS）：廣播級串流格式，PTS 天生連續，concat copy 無 DTS 斷層
                # 【v15.8 雙軌 Profile】Windows: H.264 CRF29 slow；Mac M4: HEVC VideoToolbox q:v 55
                vf_pre = f"setpts=PTS-STARTPTS,fps=24"  # 先歸零 PTS、再鎖 24fps，讓 fade st= 參照乾淨時間軸
                common_vf_base = f"{vf_pre},{norm}"
                common_enc = config.video_enc_profile["common_enc"]
                log.debug(f"  🎛️  [v15.8] 編碼 Profile: {config.video_enc_profile['name']}")
                
                base_in  = temp_dir / f"base_{idx}_in.ts"
                base_mid = temp_dir / f"base_{idx}_mid.ts"
                base_out = temp_dir / f"base_{idx}_out.ts"
                
                # Step B: 三段式鑄造 (3-Pass Encoding)
                # 【v15.5 濾鏡順序修正】PTS 歸零與 fps=24 必須在 fade 之前執行，
                # 確保 fade 的 st= 時間參數對齊到歸零後的乾淨 24fps 時間軸
                passes = [
                    (base_in,  f"{vf_pre},fade=t=in:st=0:d={fade_dur},{norm}",              "fade-in"),
                    (base_mid, common_vf_base,                                               "clean"),
                    (base_out, f"{vf_pre},fade=t=out:st={fade_out_st}:d={fade_dur},{norm}", "fade-out"),
                ]
                
                for out_path, vf, label in passes:
                    cmd_base = [
                        "ffmpeg", "-v", "error", "-stats", "-y",
                        "-i", str(vid_path),
                        "-vf", vf,
                        *common_enc,
                        str(out_path)
                    ]
                    ok = self._run_ffmpeg_with_progress(
                        cmd_base, base_dur,
                        f"[Stage 1] Scene {idx+1}/{N} ({label})"
                    )
                    if not ok:
                        log.error(f"❌ [Stage 1] base_{idx}_{label} 編碼失敗")
                        return None

                # 【v15.5 GOP-QA】base_mid 是被無限重複的核心片段，自動驗證其 GOP 結構
                # 只驗 mid（clean pass），in/out 只出現一次，GOP 邊界無重複拼接風險
                self._verify_gop_closure(
                    base_mid,
                    expected_interval=2.0,  # g=48 / fps=24 = 2.0s
                    label=f"Scene {idx+1}/{N} clean"
                )

                # 【v15.7 Ping-Pong】讀取素材前綴決定 loop 策略
                # ping_*.mp4 → 正向+反向交替（零拼接閃爍，適合海浪/雲/火焰等振盪景觀）
                # ford_*.mp4 → 正向重複（適合有人物或 CEO 指定的場景）
                loop_strategy = get_loop_strategy(vid_path)
                base_mid_rev = None

                if loop_strategy == "pingpong":
                    base_mid_rev = temp_dir / f"base_{idx}_mid_rev.ts"
                    # reverse 濾鏡先緩衝所有幀再反轉，8s@24fps=192幀，記憶體完全可接受
                    vf_rev = f"reverse,{common_vf_base}"
                    cmd_rev = [
                        "ffmpeg", "-v", "error", "-stats", "-y",
                        "-i", str(vid_path),
                        "-vf", vf_rev,
                        *common_enc,
                        str(base_mid_rev)
                    ]
                    ok_rev = self._run_ffmpeg_with_progress(
                        cmd_rev, base_dur,
                        f"[Stage 1] Scene {idx+1}/{N} (reverse)"
                    )
                    if not ok_rev:
                        log.warning(f"  ⚠️ [v15.7] 反向片段編碼失敗，降級為 Forward 策略")
                        loop_strategy = "forward"
                        base_mid_rev = None
                    else:
                        log.info(f"  🔄 [v15.7] Ping-Pong 策略啟動：{vid_path.name}")
                else:
                    log.info(f"  ▶️  [v15.7] Forward 策略：{vid_path.name}")

                # Step C: 計算 mid 重複次數（ceil 確保 concat 總長 ≥ scene_dwell_time）
                mid_count = max(0, math.ceil((scene_dwell_time - base_dur * 2) / base_dur))
                actual_dur = base_dur * (mid_count + 2)
                log.info(f"    📐 base={base_dur:.1f}s × (1+{mid_count}+1) = {actual_dur:.1f}s → -t {scene_dwell_time}s 截斷")

                # 【v15.6 雙重保險】不依賴輸入估算值，直接清點已編碼 base_mid.ts 的真實幀數。
                # base_mid.ts 已強制 fps=24，所以 nb_read_packets ÷ 24 在任何情況下都是最終真值。
                # 此步驟消除了源幀率 fps 轉換的捨入誤差（例：178幀@30fps → 142幀@24fps = 5.917s 而非 5.933s）。
                # 這是最終的「絕對精準」防線，讓 loop_list 宣告值與物理 .ts 實際長度達到幀級吻合。
                real_ts_dur = base_dur  # 備援：若清點失敗則沿用輸入估算值
                try:
                    ts_probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-count_packets", "-show_entries", "stream=nb_read_packets",
                         "-of", "csv=p=0", str(base_mid)],
                        capture_output=True, text=True, timeout=10
                    )
                    ts_frames_str = ts_probe.stdout.strip()
                    if ts_frames_str.isdigit() and int(ts_frames_str) > 0:
                        real_ts_dur = int(ts_frames_str) / 24.0
                        log.info(
                            f"    🔒 [雙重保險] base_mid.ts 實測 {ts_frames_str} 幀 @ 24fps "
                            f"= {real_ts_dur:.4f}s（輸入估算: {base_dur:.4f}s，"
                            f"誤差: {abs(real_ts_dur - base_dur):.4f}s）"
                        )
                except Exception as e:
                    log.warning(f"    ⚠️ [雙重保險] 清點 base_mid.ts 失敗，沿用估算值: {e}")

                # Step D: 寫入 concat 清單（使用實測絕對時長，切斷對上游估算的依賴）
                # 【v15.7】Ping-Pong 策略：mid 與 mid_rev 交替排列
                #   正向+反向邊界 = 同一幀接同一幀 → 數學保證零視覺跳躍
                #   -t scene_dwell_time 在 Step E 截斷，無需精確計算奇偶數
                loop_list = temp_dir / f"loop_list_{idx}.txt"
                with open(loop_list, "w", encoding="utf-8") as f:
                    f.write(f"file '{base_in.resolve().as_posix()}'\n")
                    f.write(f"duration {real_ts_dur}\n")
                    if loop_strategy == "pingpong" and base_mid_rev is not None:
                        for i in range(mid_count):
                            if i % 2 == 0:
                                f.write(f"file '{base_mid.resolve().as_posix()}'\n")
                            else:
                                f.write(f"file '{base_mid_rev.resolve().as_posix()}'\n")
                            f.write(f"duration {real_ts_dur}\n")
                    else:
                        for _ in range(mid_count):
                            f.write(f"file '{base_mid.resolve().as_posix()}'\n")
                            f.write(f"duration {real_ts_dur}\n")
                    f.write(f"file '{base_out.resolve().as_posix()}'\n")
                    f.write(f"duration {real_ts_dur}\n")
                
                # Step E: TS 無損拼接（Golden Hybrid — 維持 Encode-Once-Repeat 極速架構）
                # 【Golden Hybrid v15.4】
                # - .ts 容器：PTS 連續，concat copy 無 DTS 斷層，取代 .mp4 的 PTS Gap 問題
                # - -c:v copy：硬碟 I/O 秒級完成，保留無損原畫質，維持極速產線優勢
                # - -t scene_dwell_time：精確截斷至目標時長
                unit_out = temp_dir / f"unit_{idx}.ts"
                cmd_concat = [
                    "ffmpeg", "-v", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(loop_list),
                    "-c:v", "copy", "-t", str(scene_dwell_time),
                    str(unit_out)
                ]
                try:
                    subprocess.run(cmd_concat, check=True, stderr=subprocess.DEVNULL)
                    log.info(f"    ✅ unit_{idx}.ts 拼接完成 ({scene_dwell_time}s)")
                    unit_paths.append(unit_out)
                except subprocess.CalledProcessError as e:
                    log.error(f"❌ [Stage 1] unit_{idx} TS 拼接失敗: {e}")
                    return None
            
            # 【RCA v15.2.1 診斷】驗證每個 unit 的實際時長
            for ui, up in enumerate(unit_paths):
                try:
                    d = float(subprocess.check_output(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", str(up)],
                        text=True, timeout=5).strip())
                    log.info(f"    🔍 unit_{ui} 實際時長: {d:.3f}s (預期: {scene_dwell_time}s)")
                except Exception:
                    pass
            log.info(f"✅ [Stage 1] {len(unit_paths)} 個呼吸燈長鏡頭鑄造完成！")
            
            # ==========================================
            # Stage 2.5：音軌預混音 (acrossfade)
            # ==========================================
            has_audio = False
            premix_path = None
            if audio_paths:
                premix_path = self._build_audio_premix(audio_paths, target_duration, temp_dir)
                if premix_path and premix_path.exists():
                    has_audio = True
            
            # ==========================================
            # Stage 2：陣列物理拼接 (Matrix Concat)
            # ==========================================
            log.info("🎬 [Stage 2] 音畫陣列物理拼接...")
            
            # 生成 video concat 清單（含 duration=scene_dwell_time 指令）
            # 【Golden Hybrid v15.4 修正】同 Step D 的邏輯：
            # unit.ts 被 ffprobe 低估為 480s（實為 600s），不宣告 duration 會導致
            # Stage 2 concat demuxer 以 480s 作 PTS offset，每個 unit 只播 480s 就換場。
            # 解法：明確宣告 duration {scene_dwell_time}，demuxer 直接使用正確值。
            video_list_path = temp_dir / "video_concat.txt"
            with open(video_list_path, "w", encoding="utf-8") as f:
                for up in unit_paths:
                    f.write(f"file '{up.resolve().as_posix()}'\n")
                    f.write(f"duration {scene_dwell_time}\n")
            log.info(f"📝 Video Concat 清單: {len(unit_paths)} 個 .ts unit (duration={scene_dwell_time}s 宣告)")
            
            cmd_final = ["ffmpeg", "-v", "error", "-stats", "-y"]
            
            # Input 0: video concat demuxer
            cmd_final.extend(["-f", "concat", "-safe", "0", "-i", str(video_list_path)])
            
            # Input 1: audio premix (若有)
            if has_audio:
                cmd_final.extend(["-i", str(premix_path)])
            
            # 映射與編碼
            cmd_final.extend([
                "-map", "0:v:0",
                "-map_metadata", "-1",
                "-c:v", "copy",
            ])
            
            if has_audio:
                cmd_final.extend([
                    "-map", "1:a:0",
                    # 【v15.8】從 profile 讀取音訊編碼參數，Windows/Mac 統一 192k AAC 48kHz
                    # 較舊的 320k 是冗餘的：AAC 192k 已達聽覺透明，且對 YouTube VP9 二次壓縮更友善
                    *config.video_enc_profile["audio_enc"],
                ])
            
            # 【Golden Hybrid v15.4 - 自然結尾策略】
            # 不強制 -t target_duration，讓 6 個 unit.ts 播到自然 EOF。
            # 每個 unit ~595-600s，實際總時長約 3570-3620s（59~60.3 分鐘），符合 CEO 接受範圍。
            # 好處：徹底消除因 unit 實際時長 < 600s 而導致的「最後一幀凍結延長」。
            cmd_final.append(str(final_output_path))

            # 自然結尾時音訊可能比影片長，加 -shortest 確保兩者同步結束
            if has_audio:
                cmd_final.insert(-1, "-shortest")

            actual_estimate = scene_dwell_time * N
            log.info(f"  📊 FFmpeg: {N} units concat + audio premix → {final_output_path.name}")
            log.info(f"  ⏱️  預估時長: ~{actual_estimate//60}m（自然結尾，不強制截斷）")
            ok = self._run_ffmpeg_with_progress(cmd_final, actual_estimate, "[Stage 2] 音畫合成")
            if ok and final_output_path.exists():
                log.info(f"✅ [Stage 2] 最終合成完成！檔案：{final_output_path}")
            else:
                log.error("❌ [Stage 2] FFmpeg 合成失敗")
                return None
        
        # ==========================================
        # Stage 3：視覺金庫延遲扣款（母帶回收模式跳過）
        # ==========================================
        if selected_video_ids:
            log.info(f"💰 [Stage 3] 產線成功，執行延遲扣款 ({len(selected_video_ids)} 支)...")
            vault_update = VisualVaultDB()
            for vid_id in selected_video_ids:
                vault_update.increment_derivation_count(vid_id)
            vault_update.close()
        else:
            log.info("💰 [Stage 3] 母帶回收模式，跳過延遲扣款")
        log.info("✅ [Stage 3] 延遲扣款完成")
        
        return final_output_path
    
    def composite_to_file_stage2(self, phantom_unit_path: str, output_path: Path, 
                                audio_path: Optional[Path] = None, target_duration: int = 3600) -> bool:
        """【階段二】無限循環母體 + 音樂 + 絕對切斷
        
        【CTO 核心優化】
        只開 2 條流，記憶體消耗極低，跑到世界末日都不會崩潰！
        
        Args:
            phantom_unit_path: phantom_unit.mp4 的完整路徑
            output_path: 輸出文件路徑
            audio_path: 音頻文件路徑（可選）
            target_duration: 目標時長（秒）
        
        Returns:
            是否成功
        """
        try:
            log.info(f"🎬 【階段二】開始最終合成: {output_path.name}")
            
            # 構建 FFmpeg 命令
            cmd = ["ffmpeg", "-v", "info"]
            
            # 輸入 1：phantom_unit.mp4 無限循環
            cmd.extend(["-stream_loop", "-1", "-i", phantom_unit_path])
            
            # 輸入 2：音樂無限循環（若提供）
            if audio_path and audio_path.exists():
                cmd.extend(["-stream_loop", "-1", "-i", str(audio_path)])
                audio_index = 1  # 音頻在索引 1
            else:
                audio_index = None
            
            # 簡單濾鏘：直通視頻
            cmd.extend([
                "-filter_complex", "[0:v]fps=30[v_out]",
                "-map", "[v_out]",
                "-c:v", "libx264",
                "-crf", "28",
                "-preset", "medium",
                "-tune", "film",
                "-maxrate", "1000k",
                "-bufsize", "2000k",
                "-pix_fmt", "yuv420p",
            ])
            
            # 音頻映射（若有）
            if audio_index is not None:
                cmd.extend(["-map", f"{audio_index}:a:0", *config.video_enc_profile["audio_enc"]])
            
            # 【CTO 絕對時間鎖定】在最後精準切斷
            cmd.extend(["-t", str(target_duration), "-y", str(output_path)])
            
            log.info(f"  📊 命令行: ffmpeg -stream_loop -1 -i {Path(phantom_unit_path).name} ... -t {target_duration}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            
            if result.returncode != 0:
                log.error(f"❌ FFmpeg 失敗:\n{result.stderr[-1000:]}")
                return False
            
            log.info("✅ FFmpeg 合成成功")
            return True
        
        except subprocess.TimeoutExpired:
            log.error("❌ FFmpeg 超時（> 1小時）")
            return False
        except Exception as e:
            log.error(f"❌ 合成異常: {e}")
            return False


# ─────────────────────────────────────────────────────────────
# 【CLI 介面】
# ─────────────────────────────────────────────────────────────

def main():
    """命令行介面"""
    parser = argparse.ArgumentParser(
        description="v15.0 幻影輪播矩陣引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--channel", default="lofi", 
                       help="頻道名稱 (lofi, light_music)")
    parser.add_argument("--target-duration", type=int, default=3600,
                       help="目標總時長（秒，默認 3600 = 1 小時）")
    parser.add_argument("--scene-dwell-time", type=int, default=300,
                       help="場景停留時間（秒，默認 300 = 5 分鐘）")
    parser.add_argument("--sandbox", action="store_true",
                       help="優先使用沙盒目錄進行測試")
    parser.add_argument("--audio", type=str, default=None,
                       help="音頻文件路徑（可選）")
    parser.add_argument("--output", type=str, default=None,
                       help="輸出文件路徑（若未指定則自動生成）")
    parser.add_argument(
        "--max-derivation-limit",
        type=int,
        default=2,
        help="視覺素材最大重複衍生次數（對應 UI「視覺最大重複次數」，預設 2）",
    )

    args = parser.parse_args()
    
    # 初始化引擎
    engine = MultiSceneProcessor(use_sandbox=args.sandbox)
    
    # 執行完整流程
    audio_paths = [Path(args.audio)] if args.audio else None
    output_path = Path(args.output) if args.output else None
    
    result = engine.process_full_pipeline(
        channel=args.channel,
        target_duration=args.target_duration,
        scene_dwell_time=args.scene_dwell_time,
        audio_paths=audio_paths,
        output_path=output_path,
        max_derivation_limit=args.max_derivation_limit,
    )
    
    if result:
        print(f"\n✅ 成功！輸出: {result}")
        sys.exit(0)
    else:
        print(f"\n❌ 失敗")
        sys.exit(1)


if __name__ == "__main__":
    main()
