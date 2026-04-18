#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 4 極速無損縫合引擎 (v8.3)

功能：
1. 讀取 assets/video_clips/<job_id>/shots 下所有 mp4（依檔名排序）。
2. 讀取 assets/audio/<job_id>/music_epic.mp3。
3. 建立 concat_list.txt（FFmpeg concat demuxer 規格）。
4. 無損合併視訊並掛入音訊，輸出 epic_movie.mp4。
"""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


def _log_fatal(error_code: str, details: str) -> None:
    """依規範將致命錯誤精簡 append 到 project_learning.md，並立即停機。"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_line = str(details).strip().splitlines()[-1][:240]
    entry = (
        f"\n### [{timestamp}] auto_editor.py: {error_code}\n"
        f"- Cause: {last_line}\n"
        "- Action: Pipeline halted.\n"
    )
    try:
        with open(Path(config.workspace_root) / "project_learning.md", "a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception:
        pass
    print(f"[AUTO_EDITOR][FATAL] {error_code}: {last_line}")
    sys.exit(1)


def _sorted_shot_files(shots_dir: Path) -> list[Path]:
    files = [p for p in shots_dir.glob("*.mp4") if p.is_file()]
    return sorted(files, key=lambda p: p.name.lower())


def _load_beats_json(job_id: str) -> dict | None:
    """讀取 beats.json。若不存在，回傳 None（向後相容）。"""
    import json
    beats_path = Path(config.workspace_root) / "assets" / "scripts" / job_id / "beats.json"
    if not beats_path.exists():
        print(f"[AUTO_EDITOR] beats.json not found (Phase B feature skipped)")
        return None
    try:
        with open(beats_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print(f"[AUTO_EDITOR] failed to load beats.json: {exc}")
        return None


def generate_setpts_expression(shot_duration_sec: float, target_beat_times: list[float]) -> str:
    """
    v8.4 Phase B：分段線性變速公式生成
    
    邏輯：將影片分為多個小段，每段對應一個節拍。在接近節拍點時減速，過後加速補回。
    使用分段線性變速（避免二次曲線的複雜 if/between 邏輯）。
    
    輸入：
    - shot_duration_sec: 原影片時長（通常 5.0s）
    - target_beat_times: 該影片應對齊的節拍時戳表 [t1, t2, ...]
    
    輸出：FFmpeg setpts 表達式字串
    """
    if not target_beat_times or len(target_beat_times) < 1:
        # 無節拍資訊，回傳恆等對應
        return "PTS"
    
    # 簡化邏輯：假設影片中點（2.5s）要對齊第一個強節拍
    # 使用分段線性變速：前一半減速抵達節拍，後一半加速補回
    mid_point = shot_duration_sec / 2.0
    first_beat = target_beat_times[0] if target_beat_times else mid_point
    
    # 分段線性變速矩陣
    # 前段（0 -> mid_point）: 線性對應至 (0 -> first_beat)
    # 後段（mid_point -> shot_duration_sec）: 補回至全程時長
    # setpts 中 PTS 是幀的時間戳，N 是幀編號
    # 公式：if(LT(PT,mid_point_in_100ths), ..., ...)
    
    # 轉換為百分之一秒級（FFmpeg 內部時間單位）
    mid_pts = int(mid_point * 100)
    target_pts = int(first_beat * 100) if first_beat else mid_pts
    
    # 分段公式：前段拉伸至目標節拍，後段加速補回
    # setpts: if(LT(PT,mid_pts), PT*ratio1, mid_pts_output + (PT-mid_pts)*ratio2)
    # ratio1 = target_pts / mid_pts （前段拉伸）
    # ratio2 = (shot_duration_sec*100 - target_pts) / (mid_pts) （後段加速）
    
    if mid_pts == 0:
        return "PTS"  # 防守無效輸入
    
    ratio1 = target_pts / mid_pts if mid_pts > 0 else 1.0
    ratio2 = ((shot_duration_sec * 100) - target_pts) / mid_pts if mid_pts > 0 else 1.0
    
    # 生成 FFmpeg setpts 字串
    # 簡化版：使用線性補間而非複雜 if
    # setpts='if(lt(N,mid_frame), N*ratio1, mid_frame_out + (N-mid_frame)*ratio2)'
    # 但 FFmpeg setpts 時間戳計算非常精細，我們用簡單降級版
    
    # 最終降級方案：使用分段幀速率變更
    # 前半用 fps 快速播放，後半用低 fps 慢速播放
    # setpts 表達式: if(lt(FRAME_NUM,total_frames/2), FRAME_NUM/fps1, ...)
    # 但這需要知道幀數，較複雜。
    
    # 更簡單的方案：使用 'select' + 'interpolate' 組合
    # 或直接回傳基礎線性公式用於測試
    
    # 實作快速版本：簡單的分段線性 PTS 轉換
    expr = f"if(lt(PT,{mid_pts}), PT*{ratio1:.3f}, {target_pts}+({mid_pts*ratio2:.2f})*((PT-{mid_pts})/{mid_pts}))"
    return expr


def apply_speed_ramping(input_video: Path, output_video: Path, beats_data: dict, shot_index: int) -> bool:
    """
    v8.4 Phase B 測試函式：對單一影片應用動態時間重映射
    
    邏輯：
    1. 計算該 shot 應對齊的節拍時戳
    2. 生成 setpts 表達式
    3. 組建 FFmpeg 指令，包括 setpts + minterpolate 補幀
    4. 執行並驗證輸出
    """
    if not input_video.exists():
        print(f"[SPEED_RAMP] input video missing: {input_video}")
        return False
    
    # 計算該 shot 在整體時間軸上的偏移
    # 假設每個 shot 5 秒，第 N 個 shot 時間範圍為 [N*5, (N+1)*5]
    shot_start_sec = shot_index * 5.0
    shot_end_sec = (shot_index + 1) * 5.0
    shot_duration = 5.0
    
    # 從 beats 中找出落在此 shot 時間範圍內的節拍
    beat_times = beats_data.get("beat_times", [])
    onset_times = beats_data.get("onset_times", [])
    
    # 取該 shot 應對齊的節拍（至少一個）
    relevant_beats = [b for b in beat_times if shot_start_sec <= b <= shot_end_sec]
    if not relevant_beats and onset_times:
        relevant_beats = [o for o in onset_times if shot_start_sec <= o <= shot_end_sec]
    
    # 轉換為相對時間（影片內部座標）
    target_beat_times_relative = [max(0.1, b - shot_start_sec) for b in relevant_beats]
    
    # 生成 setpts 表達式
    setpts_expr = generate_setpts_expression(shot_duration, target_beat_times_relative)
    
    print(f"[SPEED_RAMP] shot_{shot_index+1:02d}: setpts={setpts_expr[:60]}...")
    
    # 組建 FFmpeg 指令
    # 使用 setpts + minterpolate 的濾鏈
    filter_chain = f"setpts={setpts_expr},minterpolate=fps=60:mi_mode=mci"
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", str(input_video),
        "-vf", filter_chain,
        "-c:v", "libx264",  # 簡單編碼（可降級至 copy 若 setpts 無副作用）
        "-c:a", "copy",
        "-y",
        str(output_video),
    ]
    
    try:
        result = subprocess.run(
            ffmpeg_cmd,
            check=True,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
        )
        print(f"[SPEED_RAMP] success: {output_video.name}")
        return True
    except subprocess.CalledProcessError as exc:
        stderr_msg = (exc.stderr or "").split("\n")[-3] if exc.stderr else "unknown"
        print(f"[SPEED_RAMP] FFmpeg error: {stderr_msg}")
        return False
    except Exception as exc:
        print(f"[SPEED_RAMP] exception: {exc}")
        return False


def _write_concat_list(shots_dir: Path, shot_files: list[Path]) -> Path:
    """使用相對檔名建立 concat 清單，避免跨平台絕對路徑轉義差異。"""
    concat_list = shots_dir / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8", newline="\n") as fh:
        for shot in shot_files:
            safe_name = shot.name.replace("'", "'\\''")
            fh.write(f"file '{safe_name}'\n")
    return concat_list


def fast_concat(job_id: str) -> Path:
    workspace = Path(config.workspace_root)
    shots_dir = workspace / "assets" / "video_clips" / job_id / "shots"
    music_path = workspace / "assets" / "audio" / job_id / "music_epic.mp3"
    export_dir = workspace / "assets" / "final_exports" / job_id
    output_path = export_dir / "epic_movie.mp4"

    if not shots_dir.exists():
        _log_fatal("SHOTS_DIR_MISSING", f"shots dir not found: {shots_dir}")
    if not music_path.exists():
        _log_fatal("MUSIC_MISSING", f"music file not found: {music_path}")

    shot_files = _sorted_shot_files(shots_dir)
    if not shot_files:
        _log_fatal("NO_SHOTS_FOUND", f"no .mp4 files under: {shots_dir}")

    export_dir.mkdir(parents=True, exist_ok=True)
    concat_list = _write_concat_list(shots_dir, shot_files)

    # v8.4 Phase A：讀取 beats.json（用於 Phase B 動態對齊），當前版本先輸出資訊
    beats_data = _load_beats_json(job_id)
    if beats_data:
        print(f"[AUTO_EDITOR] BPM: {beats_data.get('bpm'):.1f}, beats: {len(beats_data.get('beat_times', []))}")

    # 複雜邏輯說明：必須切到 shots_dir 執行，讓 concat_list 內相對檔名可被 ffmpeg 正確解析。
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list.name),
        "-i",
        str(music_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]

    # v8.4 Phase A：集成 60fps 補幀濾鏈（預留 Phase B 時間重映射）
    # 複雜邏輯說明：minterpolate 是 FFmpeg 標準濾鏡，但需確保 libavfilter 編譯支援。
    # 降級備選：若 mci 模式無效，改用 fps=60 簡單升頻。
    try:
        video_filter = "minterpolate=fps=60:mi_mode=mci"
        ffmpeg_cmd_with_filter = (
            ffmpeg_cmd[:4]
            + ["-vf", video_filter]
            + ffmpeg_cmd[4:]
        )
        print(f"[AUTO_EDITOR] Phase A: 60fps 補幀濾鏈已集成")
        ffmpeg_cmd = ffmpeg_cmd_with_filter
    except Exception:
        print(f"[AUTO_EDITOR] Phase A: 降級至基礎縫合（無補幀）")

    try:
        subprocess.run(
            ffmpeg_cmd,
            cwd=str(shots_dir),
            check=True,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or "").strip().splitlines()
        _log_fatal("FFMPEG_CONCAT_FAILED", stderr_tail[-1] if stderr_tail else str(exc))

    if not output_path.exists() or output_path.stat().st_size == 0:
        _log_fatal("OUTPUT_EMPTY", f"output not generated: {output_path}")

    print(f"[AUTO_EDITOR] concat list: {concat_list}")
    print(f"[AUTO_EDITOR] output: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4/B 極速無損縫合 + 變速補幀引擎")
    parser.add_argument("--job-id", required=True, help="工作批次 ID，例如 zaouli_test_001")
    parser.add_argument("--enable-phase-b", action="store_true", help="啟用 Phase B 動態時間重映射")
    args = parser.parse_args()

    try:
        out = fast_concat(args.job_id, enable_speed_ramping=args.enable_phase_b)
        print(out)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _log_fatal("UNHANDLED_EXCEPTION", str(exc))


if __name__ == "__main__":
    main()