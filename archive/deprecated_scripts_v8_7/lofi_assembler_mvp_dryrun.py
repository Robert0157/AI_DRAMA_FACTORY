#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.atomic_io import atomic_write_json
from scripts.common.env_manager import config
from scripts.common.path_sanitize import safe_join


@dataclass
class AssembleManifest:
    source_video: str
    mastered_tracks: list[str]
    audio_sequence: list[str]
    crossfades_sec: list[float]
    target_sec: int
    pingpong_video_path: str
    audio_bed_path: str
    output_path: str
    generated_at: str


def _fatal_exit(message: str) -> None:
    print(f"[ASSEMBLER][FATAL] {message}")
    sys.exit(1)


def _collect_mastered_tracks(workspace_root: Path) -> list[Path]:
    mastered_dir = safe_join(workspace_root, "assets", "audio", "mastered_tracks")
    return sorted([p for p in mastered_dir.glob("*_YT_-14LUFS.wav") if p.is_file()])


def _pick_source_video(workspace_root: Path, video_name: str | None) -> Path:
    video_dir = safe_join(workspace_root, "assets", "video_clips")

    if video_name:
        if "/" in video_name or "\\" in video_name:
            _fatal_exit("--video-name 僅接受檔名，不可包含路徑")
        picked = video_dir / video_name
        if not picked.exists() or not picked.is_file():
            _fatal_exit(f"指定影片不存在: {picked}")
        return picked

    rs_candidates = sorted([p for p in video_dir.glob("RS_lofi_gril*.mp4") if p.is_file()])
    if rs_candidates:
        return rs_candidates[0]

    all_candidates = sorted([p for p in video_dir.glob("*.mp4") if p.is_file()])
    if not all_candidates:
        _fatal_exit("assets/video_clips/ 找不到可用 MP4")
    return all_candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="R&S Echoes 1 小時無縫縫合機 v8.7 (MVP DRY-RUN)")
    parser.add_argument("--target-sec", type=int, default=3600)
    parser.add_argument("--seed", type=int, default=87)
    args = parser.parse_args()

    workspace_root = Path(config.workspace_root)

    source_video = _pick_source_video(workspace_root, None)
    mastered_tracks = _collect_mastered_tracks(workspace_root)

    if not mastered_tracks:
        print("[LOFI_ASSEMBLER][WARN] mastered_tracks 資料夾內未見音軌，請先執行 audio_mastering_engine.py 產生 *_YT_-14LUFS.wav")
        _fatal_exit("assets/audio/mastered_tracks/ 找不到 *_YT_-14LUFS.wav")

    print(f"[LOFI_ASSEMBLER][MVP-DRY-RUN] 找到 {len(mastered_tracks)} 個音軌")
    print(f"[LOFI_ASSEMBLER][MVP-DRY-RUN] 來源影片: {source_video.name}")
    print("[LOFI_ASSEMBLER][MVP-DRY-RUN] 啟動模擬模式（無需 FFmpeg）")

    random.seed(args.seed)
    
    # 模擬音軌序列與 crossfade
    sequence = []
    fades = []
    for _ in range(min(10, len(mastered_tracks) * 3)):
        sequence.append(random.choice(mastered_tracks))
        if len(sequence) > 1:
            fades.append(round(random.uniform(5.0, 10.0), 3))

    export_dir = safe_join(workspace_root, "assets", "final_exports")
    tmp_dir = export_dir / "_tmp_lofi_assembler"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    pingpong_video = tmp_dir / "pingpong_1h_video.mp4"
    audio_bed = tmp_dir / "crossfade_1h_audio.wav"
    output_path = export_dir / "R_S_Echoes_VolX_1Hour.mp4"

    manifest = AssembleManifest(
        source_video=str(source_video),
        mastered_tracks=[str(p) for p in mastered_tracks],
        audio_sequence=[str(p) for p in sequence],
        crossfades_sec=fades,
        target_sec=args.target_sec,
        pingpong_video_path=str(pingpong_video),
        audio_bed_path=str(audio_bed),
        output_path=str(output_path),
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )

    manifest_path = export_dir / "lofi_assembler_manifest.json"
    atomic_write_json(manifest_path, asdict(manifest), indent=2)

    print(f"[LOFI_ASSEMBLER][DRY-RUN] 音軌序列: {len(sequence)} 個，交叉淡化: {len(fades)} 次")
    print(f"[LOFI_ASSEMBLER] ✅ manifest 已生成: {manifest_path}")
    print(f"[LOFI_ASSEMBLER] 理論輸出: {output_path}")


if __name__ == "__main__":
    main()
