#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# 讓腳本可直接以檔案路徑執行（python scripts/gear1_prod/xxx.py）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.atomic_io import atomic_write_json, atomic_write_text
from scripts.common.env_manager import config
from scripts.common.path_sanitize import sanitize_filename


DEFAULT_TIMEOUT_SEC = 600
AUTHOR_NAME = "R&S Echoes"
# v15.10 P1#3: MAC_SHORT_AUDIO_ROOT 常數已废止，統一由 config.mac_short_audio_root 派發
REMIX_KEYWORDS = ("tempo_up", "tempo_down", "pitch_up", "pitch_down")


@dataclass
class MasteringRecord:
    input_beat: str
    title: str
    author: str
    output_spotify_wav: str | None
    status: str
    fail_reason: str | None
    processed_at: str


class ProtocolBError(Exception):
    """已廢除 - 保留以相容舊代碼"""
    def __init__(self, message: str, peak_db: float | None = None) -> None:
        super().__init__(message)
        self.peak_db = peak_db


def _export_loudnorm_direct(
    ffmpeg_bin: str,
    input_mp3: Path,
    output_wav: Path,
    track_title: str,
    track_author: str,
    target_lufs: int,
    timeout_sec: int,
    dry_run: bool = False,
) -> None:
    """【純淨工業流程】直接將 Suno MP3 轉為 loudnorm 標準化 WAV
    
    此流程完全移除 SoX 混響、SFX 混音、防爆音檢測。
    僅保留 FFmpeg 響度標準化，符合 Spotify (-16 LUFS) 發行標準。
    """
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    
    if dry_run:
        print(f"[DRY-RUN] loudnorm 轉檔: {input_mp3.name} → {output_wav.name}")
        output_wav.write_text("DRY_RUN_WAV")
        return
    
    # FFmpeg 終極指令：MP3 → loudnorm (-16 LUFS) → WAV
    loudnorm_filter = f"loudnorm=I={target_lufs}:TP=-2.0:LRA=11"
    cmd = [
        ffmpeg_bin,
        "-i", str(input_mp3),
        "-af", loudnorm_filter,
        "-metadata", f"title={track_title}",
        "-metadata", f"artist={track_author}",
        "-metadata", f"album_artist={track_author}",
        "-ar", "44100",
        "-ac", "2",
        "-c:a", "pcm_s24le",
        "-y",
        str(output_wav),
    ]
    _run_command(cmd, timeout_sec)


def _extract_industrial_title(stem: str) -> str:
    """從檔名抽取工業級標題格式 [16字母]_[MMDDYY]_[00X]。"""
    match = re.search(r"([A-Za-z]{16}_\d{6}_\d{3})", stem)
    if match:
        return match.group(1)
    return sanitize_filename(stem)


def _append_project_learning(entry: str) -> None:
    learning_path = Path(config.workspace_root) / "project_learning.md"
    if learning_path.exists():
        existing = learning_path.read_text(encoding="utf-8")
    else:
        existing = ""
    atomic_write_text(learning_path, existing + entry, encoding="utf-8")


def _fatal_exit(context: str, message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        "\n\n"
        f"## [{stamp}] Fatal: {context}\n"
        f"- 錯誤訊息: {message}\n"
        "- 處置: 已中斷產線，請人工檢查後重啟。\n"
    )
    _append_project_learning(entry)
    sys.exit(1)


def _find_binary(name: str, dry_run: bool = False) -> str:
    if dry_run:
        print(f"[DRY-RUN] 跳過 {name} 檢查")
        return f"DRY_RUN_{name}"
    path = shutil.which(name)
    if not path:
        _fatal_exit("Binary Missing", f"找不到必要執行檔: {name}")
    return path


def _run_command(cmd: list[str], timeout_sec: int, dry_run: bool = False) -> None:
    if dry_run:
        print(f"[DRY-RUN] 跳過命令: {' '.join(cmd[:3])}...")
        return
    result = subprocess.run(
        cmd,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if result.returncode != 0:
        error_line = (result.stderr or "").strip().splitlines()
        reason = error_line[-1] if error_line else "unknown subprocess error"
        raise RuntimeError(reason)


def _is_remix_name(name: str) -> bool:
    lowered = str(name).lower()
    return any(k in lowered for k in REMIX_KEYWORDS)


def _shorts_publish_windows_hint(workspace_root: Path) -> dict:
    """自 configs/shorts_publish_windows.json 讀取摘要，寫入 Shorts signal 供 Mac／營運對齊檔期。"""
    p = workspace_root / "configs" / "shorts_publish_windows.json"
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        slots = data.get("slots") or []
        return {
            "timezone_label": data.get("timezone_label", ""),
            "slot_times_local": [
                s.get("local_time") for s in slots if isinstance(s, dict) and s.get("local_time")
            ],
            "config_ref": "configs/shorts_publish_windows.json",
        }
    except Exception:
        return {}


def _sync_new_masters_to_shorts_and_signal(
    *,
    channel: str,
    mastered_paths: list[Path],
) -> dict:
    """
    固定流程：每輪母帶完成後，增量同步非 remix 檔到 Y:/Shorts_audio/{channel} 並寫 signal。
    """
    shorts_dir = config.smb_shorts_root / channel.lower()
    stats = {
        "copied": 0,
        "skipped_exists": 0,
        "skipped_remix": 0,
        "failed": 0,
        "batch_selected": 0,
        "available_in_target": 0,
    }
    selected: list[Path] = []
    for p in mastered_paths:
        if _is_remix_name(p.name):
            stats["skipped_remix"] += 1
            continue
        selected.append(p)
    stats["batch_selected"] = len(selected)

    signal_path = shorts_dir / ".signal.json"
    try:
        shorts_dir.mkdir(parents=True, exist_ok=True)
        for src in selected:
            dst = shorts_dir / src.name
            if dst.exists():
                stats["skipped_exists"] += 1
                continue
            try:
                shutil.copy2(str(src), str(dst))
                stats["copied"] += 1
            except Exception as e:
                stats["failed"] += 1
                print(f"[SHORTS_SYNC] copy_failed::{src.name}::{e}")

        stats["available_in_target"] = len([p for p in selected if (shorts_dir / p.name).exists()])
        now = datetime.now()
        workspace_root = Path(config.workspace_root)
        payload = {
            "schema_version": "shorts-signal-v1",
            "batch_id": now.strftime("%Y%m%d_%H%M%S"),
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": channel.lower(),
            "mode": "AUTO_MASTERING_SYNC",
            "windows_path": str(shorts_dir),
            "mac_mount_path": str(config.mac_short_audio_root / channel.lower()),  # v15.10 P1#3
            "stats": stats,
            "auto_sync_enabled": True,
            "note": "Incremental sync after mastering completion.",
            "publish_windows_hint": _shorts_publish_windows_hint(workspace_root),
        }
        atomic_write_json(signal_path, payload, indent=2)
        print(f"[SHORTS_SYNC] signal: {signal_path}")
    except Exception as e:
        # v15.10: 不中斷母帶主流程，但記錄同步錯誤供診斷
        print(f"[SHORTS_SYNC] ⚠️ sync/signal failed: {e}")
        stats["sync_error"] = str(e)[:200]

    # v15.10: 若 failed > 0 輸出警告
    if stats.get("failed", 0) > 0:
        print(f"[SHORTS_SYNC] ⚠️ {stats['failed']} 個檔案同步失敗，請檢查 SMB 連線與權限")
        # v15.11 P3#14：寫入重試清單供後續補同步
        _write_shorts_sync_retry(channel=channel, failed_sources=selected, stats=stats)

    return {
        "shorts_dir": str(shorts_dir),
        "signal_path": str(signal_path),
        "stats": stats,
    }


def _write_shorts_sync_retry(
    *,
    channel: str,
    failed_sources: list[Path],
    stats: dict,
) -> None:
    """
    v15.11 P3#14 — 將 Shorts 同步失敗的檔案清單寫入 assets/data/shorts_sync_retry.json。

    格式（合併而非覆寫，以保留跨批次失敗記錄）：
        {
            "channel": {
                "pending": [
                    {"src": "...", "name": "...", "batch_ts": "..."},
                    ...
                ]
            }
        }
    """
    retry_path = Path(config.workspace_root) / "assets" / "data" / "shorts_sync_retry.json"
    try:
        retry_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing: dict = json.loads(retry_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            existing = {}
        ch_key = str(channel).lower()
        ch_pending: list = existing.get(ch_key, {}).get("pending", [])
        batch_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for src in failed_sources:
            dst_path = config.smb_shorts_root / ch_key / src.name
            if not dst_path.exists():
                ch_pending.append({
                    "src": str(src),
                    "name": src.name,
                    "batch_ts": batch_ts,
                })
        existing[ch_key] = {"pending": ch_pending}
        from scripts.common.atomic_io import atomic_write_json as _awj
        _awj(retry_path, existing, indent=2)
        print(f"[SHORTS_SYNC] 📋 重試清單已更新：{retry_path} ({len(ch_pending)} 筆)")
    except Exception as e:
        print(f"[SHORTS_SYNC] ⚠️ 重試清單寫入失敗: {e}")


def _probe_duration_sec(ffprobe_bin: str, audio_path: Path, timeout_sec: int) -> float:
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(
        cmd,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {audio_path.name}")
    try:
        return float((result.stdout or "0").strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe duration parse failed: {audio_path.name}") from exc


def _validate_wav_spec(ffprobe_bin: str, wav_path: Path, timeout_sec: int) -> bool:
    """驗證 WAV 是否符合 Spotify 規格 (44.1kHz, 24-bit, stereo)。"""
    try:
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels,codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1:noinvalidatetime=1",
            str(wav_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 3:
            sr, channels, codec = int(lines[0]), int(lines[1]), lines[2]
            return sr == 44100 and channels == 2 and codec in ["pcm_s24le", "pcm_s16le"]
    except Exception:
        pass
    return False


def _prepare_audio_for_sox(src_audio: Path, out_dir: Path, ffmpeg_bin: str, ffprobe_bin: str, timeout_sec: int) -> Path:
    """智慧準備音聲檔案供 SoX 使用。支援 MP3 與 WAV 格式。
    
    - WAV 規格相符 → 直接返回（快速路徑，節省 25-75 秒）
    - WAV 規格不符 → FFmpeg 重新編碼
    - MP3 → FFmpeg 轉換 + 預衰減（-12dB 基礎 / -15dB 針對 maiden_voyage）
    """
    src_ext = str(src_audio).lower().split(".")[-1]
    
    if src_ext == "wav":
        # WAV 快速路徑：驗證規格
        if _validate_wav_spec(ffprobe_bin, src_audio, timeout_sec):
            print(f"[AUDIO-PREP] WAV 規格正確，跳過轉檔: {src_audio.name}")
            return src_audio  # ← 直接返回，節省 25-75 秒
        else:
            print(f"[AUDIO-PREP] WAV 規格不符，重新編碼: {src_audio.name}")
            # 規格不符，進行重新編碼
            temp_wav = out_dir / f"{src_audio.stem}_recoded.wav"
    else:
        # MP3 路徑：標準轉換 + 預衰減
        temp_wav = out_dir / f"{src_audio.stem}_temp.wav"
    
    # 【CTO 激進預衰減】Suno MP3 峰值過高。
    # 普通歌曲：-12dB；maiden_voyage_suno_001（特熱）：-15dB
    volume_filter = "-15dB" if "maiden_voyage_suno_001" in str(src_audio) else "-12dB" if src_ext == "mp3" else "0dB"
    
    ffmpeg_cmd = [
        ffmpeg_bin,
        "-i",
        str(src_audio),
        "-filter:a",
        f"volume={volume_filter}",
        "-acodec",
        "pcm_s24le",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-y",
        str(temp_wav),
    ]
    try:
        _run_command(ffmpeg_cmd, timeout_sec)
        print(f"[AUDIO-PREP] 轉檔完成: {src_audio.name} → {temp_wav.name}")
        return temp_wav
    except Exception as e:
        raise RuntimeError(f"[CRITICAL] 音聲準備失敗 ({src_ext.upper()}): {e}")


def _sox_reverb(sox_bin: str, src_audio: Path, out_wav: Path, decay_sec: float, timeout_sec: int, dry_run: bool = False) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"[DRY-RUN] 生成 SoX reverb: {out_wav.name}")
        out_wav.write_text("DRY_RUN_WAV_PLACEHOLDER")
        return
    
    # 智慧準備音聲 (MP3/WAV 混合支援)
    ffmpeg_bin = _find_binary("ffmpeg")
    ffprobe_bin = _find_binary("ffprobe")
    src_for_sox = _prepare_audio_for_sox(src_audio, out_wav.parent, ffmpeg_bin, ffprobe_bin, timeout_sec)
    
    # 標記是否需要後續清理臨時檔案
    is_temp = src_for_sox != src_audio
    
    wet_gain = round(max(-2.0, min(0.0, (decay_sec - 3.0) * 3.0)), 2)
    # 【Spotify 規範】SoX 需要 -b 24 來保持 24-bit 輸出
    cmd = [
        sox_bin,
        "-b",
        "24",
        str(src_for_sox),
        str(out_wav),
        "reverb",
        "50",
        "50",
        "100",
        "100",
        "0",
        str(wet_gain),
    ]
    try:
        _run_command(cmd, timeout_sec)
    finally:
        # 清理臨時 WAV（如果源檔案是 MP3 或 WAV 規格不符）
        if is_temp:
            try:
                src_for_sox.unlink()
            except OSError:
                pass


def _mix_ambience(
    ffmpeg_bin: str,
    ffprobe_bin: str,
    reverb_wav: Path,
    sfx_audio: Path,
    out_wav: Path,
    sfx_volume: float,
    timeout_sec: int,
) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    duration = _probe_duration_sec(ffprobe_bin, reverb_wav, timeout_sec)

    # 【CTO 修正】開始 0~10 秒 & 結尾最後 10 秒不混 SFX
    # 只在 10 秒 ~ (duration-10 秒) 的區間混音
    trim_start = 10.0
    trim_end = max(trim_start + 0.1, duration - 10.0)  # 確保至少有 0.1s 的混音區間
    
    filter_complex = (
        f"[0:a]volume=if(between(t\\,{trim_start}\\,{trim_end:.3f}),{sfx_volume},0),"
        f"atrim=0:{duration:.3f}[amb];"
        "[1:a]volume=1.0[music];"
        "[music][amb]amix=inputs=2:duration=first:dropout_transition=3[aout]"
    )
    cmd = [
        ffmpeg_bin,
        "-stream_loop",
        "-1",
        "-i",
        str(sfx_audio),
        "-i",
        str(reverb_wav),
        "-filter_complex",
        filter_complex,
        "-map",
        "[aout]",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-c:a",
        "pcm_s24le",
        "-y",
        str(out_wav),
    ]
    _run_command(cmd, timeout_sec)


def _detect_peak_db(ffmpeg_bin: str, audio_path: Path, timeout_sec: int) -> float:
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-i",
        str(audio_path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        cmd,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    stderr_text = (result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(f"volumedetect failed: {audio_path.name}")

    match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", stderr_text)
    if not match:
        raise RuntimeError(f"volumedetect parse failed: {audio_path.name}")
    return float(match.group(1))


def _cleanup_files(paths: list[Path]) -> None:
    for p in paths:
        try:
            if p.exists():
                p.unlink()
        except OSError:
            continue


def _export_loudnorm(
    ffmpeg_bin: str,
    mixed_wav: Path,
    out_wav: Path,
    target_lufs: int,
    timeout_sec: int,
) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    # 【CTO 商業規格】綜合響度 I=-14/-16 + 真實峰值 TP=-2.0（防止耳機破音）
    loudnorm = f"loudnorm=I={target_lufs}:TP=-2.0:LRA=11"
    cmd = [
        ffmpeg_bin,
        "-i",
        str(mixed_wav),
        "-af",
        loudnorm,
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "pcm_s24le",
        "-y",
        str(out_wav),
    ]
    _run_command(cmd, timeout_sec)


def _collect_inputs(workspace_root: Path, channel: str = "lofi") -> tuple[list[Path], list[Path]]:
    beat_dir = workspace_root / "assets" / "audio" / "ceo_approved_beats" / channel.lower()

    # 【CTO 修復 v8.8.4】改進衍生音檔的母帶檢查邏輯
    # 【v12.0 頻道隔離】支援 lofi / light_music 通道
    # 【v12.11 物理隔離】母帶按頻道存放到 mastered_tracks/{channel}/
    # 關鍵：任何存在於 ceo_approved_beats/{channel}/ 且未在 mastered_tracks/{channel}/ 中對應的檔案
    # 都應進入母帶化佇列，無論是 MP3 還是 WAV
    
    output_root = workspace_root / "assets" / "audio" / "mastered_tracks" / channel.lower()
    output_root.mkdir(parents=True, exist_ok=True)
    beats: list[Path] = []
    
    # 同時掃描 *.mp3 和 *.wav
    source_beats_mp3 = sorted(
        [p for p in beat_dir.glob("*.mp3") if p.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    source_beats_wav = sorted(
        [p for p in beat_dir.glob("*.wav") if p.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    
    # 合併兩份列表
    source_beats = sorted(
        source_beats_mp3 + source_beats_wav,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    
    for beat in source_beats:
        safe_stem = sanitize_filename(beat.stem)
        # 【CTO 修復任務三】廢除硬編碼 LUFS，改用 glob 匹配
        # 只要找到 {safe_stem}_YT_*.wav（不管 LUFS 值是多少），就視為已處理
        # 防止 Light Music 頻道在 -18LUFS 下無限重複處理相同檔案
        existing_masters = list(output_root.glob(f"{safe_stem}_YT_*.wav"))
        
        if existing_masters:
            # 取最新的檔案（通常只有一個，但以防萬一）
            latest_master = sorted(existing_masters, key=lambda p: p.stat().st_mtime)[-1]
            print(f"[MASTERING] skip already processed: {beat.name} → {latest_master.name}")
            continue
        
        # 未被處理的檔案進入佇列
        beats.append(beat)

    return beats, []  # SFX 列表返回空


def _extract_demo_60sec(wav_path: Path, demo_path: Path, ffmpeg_bin: str, timeout_sec: int = 60) -> bool:
    """
    擷取 WAV 檔案的前 60 秒作為 Demo
    
    Args:
        wav_path: 輸入 WAV 檔路徑
        demo_path: 輸出 MP3 Demo 路徑
        ffmpeg_bin: FFmpeg 執行檔路徑
        timeout_sec: 超時時間（秒）
    
    Returns:
        True if successful, False otherwise
    """
    try:
        cmd = [
            ffmpeg_bin,
            "-i", str(wav_path),
            "-t", "60",  # 60 秒
            "-ar", "44100",
            "-acodec", "libmp3lame",
            "-q:a", "5",  # 高品質 MP3
            "-y",
            str(demo_path),
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        
        if result.returncode == 0 and demo_path.exists():
            print(f"✅ Demo 已擷取: {demo_path.name}")
            return True
        else:
            print(f"❌ Demo 擷取失敗 (FFmpeg return code {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        print(f"❌ Demo 擷取超時 ({timeout_sec}s)")
        return False
    except Exception as e:
        print(f"❌ Demo 擷取異常: {e}")
        return False


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R&S Echoes 純淨母帶處理引擎 - FFmpeg loudnorm only")
    parser.add_argument("--seed", type=int, default=87)
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--dry-run", action="store_true", help="僅驗證流程，跳過實際音頻處理")
    parser.add_argument("--channel", type=str, default="lofi", choices=["lofi", "light_music"], help="目標頻道 (lofi 或 light_music)")
    parser.add_argument("--lufs", type=float, default=-16.0, help="【v12.9】目標 LUFS 值（預設: -16，Light Music 通常 -18）")
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    
    # ==================== 【CTO 極簡化】純淨母帶流程 ====================
    # 流程：Suno MP3 → FFmpeg loudnorm (Spotify標準) → 擷取 60s Demo → Telegram
    # 完全廢除 SoX 混響、SFX 混音、防爆音檢測
    
    workspace_root = Path(config.workspace_root)
    beats, _ = _collect_inputs(workspace_root, channel=args.channel)

    # 【CTO v8.9.1 修復】當沒有新檔案時的防呆邏輯
    if not beats:
        print("[MASTERING] skip: no new files to process")
        sys.exit(0)  # ✅ 安全退出，不視為失敗

    ffmpeg_bin = _find_binary("ffmpeg", args.dry_run)
    random.seed(args.seed)

    # 【v12.22 頻道強行錨定】禁止使用任何不帶頻道參數的預設路徑
    output_root = workspace_root / "assets" / "audio" / "mastered_tracks" / args.channel.lower()
    output_root.mkdir(parents=True, exist_ok=True)

    records: list[MasteringRecord] = []
    success_count = 0
    failed_count = 0
    failed_tracks: list[str] = []
    success_outputs: list[Path] = []

    # 【v12.9 LUFS 參數傳遞】使用 --lufs 參數或默認值
    print(f"【v12.9 LUFS 設定】正在應用 {args.lufs} LUFS 標準 (頻道: {args.channel})")

    for beat in beats:
        try:
            industrial_title = _extract_industrial_title(beat.stem)
            
            # 【工業命名】最終母帶檔名使用工業標題加上清晰的質量標記
            sp_out = output_root / f"{industrial_title}_YT_{args.lufs}LUFS.wav"
            
            # 【純淨】直接用 FFmpeg loudnorm，無 SoX、無 SFX、無混響
            _export_loudnorm_direct(
                ffmpeg_bin,
                beat,
                sp_out,
                track_title=industrial_title,
                track_author=AUTHOR_NAME,
                target_lufs=int(args.lufs),  # 轉換為整數 (e.g., -16, -18)
                timeout_sec=args.timeout_sec,
                dry_run=args.dry_run,
            )
            
            if not args.dry_run and not sp_out.exists():
                raise RuntimeError(f"[ERROR] 母帶生成失敗: {sp_out.name}")
            
            records.append(
                MasteringRecord(
                    input_beat=str(beat),
                    title=industrial_title,
                    author=AUTHOR_NAME,
                    output_spotify_wav=str(sp_out),
                    status="SUCCESS",
                    fail_reason=None,
                    processed_at=datetime.now().isoformat(timespec="seconds"),
                )
            )
            success_count += 1
            success_outputs.append(sp_out)
            print(f"[MASTERING] done: {beat.name}")
        except Exception as exc:
            failed_count += 1
            failed_tracks.append(f"{beat.name}: {exc}")
            records.append(
                MasteringRecord(
                    input_beat=str(beat),
                    title=_extract_industrial_title(beat.stem),
                    author=AUTHOR_NAME,
                    output_spotify_wav=None,
                    status="FAILED",
                    fail_reason=str(exc),
                    processed_at=datetime.now().isoformat(timespec="seconds"),
                )
            )
            print(f"[MASTERING] failed: {beat.name} - {exc}")
            continue

    if success_count == 0:
        _fatal_exit("Audio Mastering Pipeline", "所有音軌皆未成功處理")

    manifest_path = output_root / "mastering_manifest.json"
    manifest_data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workspace_root": str(workspace_root),
        "record_count": len(records),
        "success_count": success_count,
        "failed_count": failed_count,
        "author": AUTHOR_NAME,
        "method": "FFmpeg loudnorm only (no SoX, no SFX, no reverb)",
        "records": [asdict(r) for r in records],
    }
    atomic_write_json(manifest_path, manifest_data, indent=2)
    print(f"[MASTERING] manifest: {manifest_path}")

    # 固定流程：每輪母帶完成後自動增量同步到 Mac mini Shorts 倉並發送 signal
    shorts_sync = _sync_new_masters_to_shorts_and_signal(
        channel=args.channel,
        mastered_paths=success_outputs,
    )
    print(
        "[SHORTS_SYNC] "
        f"copied={shorts_sync['stats']['copied']}, "
        f"skipped_exists={shorts_sync['stats']['skipped_exists']}, "
        f"skipped_remix={shorts_sync['stats']['skipped_remix']}, "
        f"failed={shorts_sync['stats']['failed']}, "
        f"batch_selected={shorts_sync['stats']['batch_selected']}, "
        f"available_in_target={shorts_sync['stats']['available_in_target']}"
    )

    if failed_tracks:
        error_entry = (
            f"\n\n## [{datetime.now().isoformat()}] Audio Mastering Partial Failure\n"
            + "\n".join(f"- {item}" for item in failed_tracks)
            + "\n"
        )
        _append_project_learning(error_entry)
    
    # ==================== Phase B: 母帤完成，直接上架 ====================
    # 【CTO 營運升級】禁用舊版 telegram_approval_gate，改用 telegram_manager_bot 遠端中控
    print("\n[MASTERING] 母帤完成！所有品質檔案已存儲至金庫。")
    print("[MASTERING] 🎛️  CEO 可透過 Telegram /build 指令遠端啟動進階後製流程。")
    
    print("[MASTERING] all tracks completed.")


if __name__ == "__main__":
    # 【PIPELINE_MANIFESTO】允許 pipeline_runner.py 透過環境變數授權呼叫
    import os
    if os.environ.get("PIPELINE_RUNNER_AUTHORIZED") != "1":
        sys.exit("Error: Must be run via pipeline_runner.py per PIPELINE_MANIFESTO")
    # 若有授權，正常執行
    main()