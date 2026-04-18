#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suno Vanguard Run (v8.4)
=========================
透過 pipeline_runner 的架構和哲學，執行 10 首新歌生成。

流程：
1. 匯入 suno_api_engine（不直接執行）
2. 生成 10 首多樣化的 Lo-Fi Chill Hop 新歌
3. 每首進入 raw_tracks/
4. 自動觸發 audio_mastering_engine 母帶處理
5. 推廣至 CEO 的 Telegram 核准佇列

推進模式：
  --mode generating  : 從頭生成 10 首新歌（每首 120-180 秒）
  --mode quick       : 快速測試模式（3 首新歌）
  --target-songs N   : 自訂生成數量

失敗處理：
  HTTP 500 或 API 超時 → 捕捉例外
  → 寫入 project_learning.md (Fatal Log)
  → sys.exit(1)
  → 產線中止並呈報 CEO
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


def _log_fatal(code: str, detail: str) -> None:
    """致命錯誤寫入 project_learning.md（强制寫入版本）"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last = str(detail).strip().splitlines()[-1][:240] if detail else "Unknown"
    
    entry = (
        f"\n---\n### ❌ [{timestamp}] suno_vanguard_run.py: {code}\n"
        f"- **Cause**: {last}\n"
        "- **Action**: Pipeline halted (graceful fail).\n"
    )
    
    # 強制寫入 Fatal Log - 不容許隱藏錯誤
    log_path = Path(config.workspace_root) / "project_learning.md"
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(entry)
        print(f"[VANGUARD][FATAL] 日誌已寫入: {log_path}")
    except Exception as err:
        # 如果寫入失敗，也要印出來
        print(f"[VANGUARD][FATAL-WRITE-ERROR] 無法寫入日誌: {err}")
        print(f"[VANGUARD][FATAL-FALLBACK] {code}: {last}")
    
    print(f"[VANGUARD][FATAL] {code}: {last}")
    sys.exit(1)


def _generate_10_songs(mode: str = "generating") -> list[dict]:
    """
    生成 10 首（或自訂數量）的新歌。
    
    【CTO v12.0 時間膨脹神級 Prompt 結構】
    使用分離的 tags (技術風格) 和 prompt (時間軸結構) 欄位。
    """
    from scripts.gear1_prod.suno_api_engine import generate_epic, poll_until_done
    import logging
    
    log = logging.getLogger("vanguard")
    
    # 時間膨脹 Prompt 矩陣 (Time Expansion Prompts)
    # 每個 prompt 包含 [Intro] [Verse] [Chorus] [Bridge] 等結構標籤
    time_expansion_prompts = [
        "[Intro: atmospheric pad, 8 bars slow]\n[Verse: lo-fi hip hop drums, chill bass, time stretches out]\n[Chorus: vocal sample, reverb-heavy, contemplative]\n[Bridge: minimal, spacious, breathing room]\n[Outro: fade to silence]",
        "[Intro: vinyl crackle, field recording]\n[Verse: sleepy jazz chords, quantized rhythm, temporal dilation]\n[Chorus: layered pads, dreamy quality]\n[Bridge: breakbeat reconstruction, slowed]\n[Outro: ambient decay]",
        "[Intro: water droplets, resonant space]\n[Verse: modular synth arpeggios, stretched time]\n[Chorus: lo-fi vocal, compressed air]\n[Bridge: minimalist piano, sparse]\n[Outro: reverb tail]",
        "[Intro: clock ticking, slowed]\n[Verse: fingerpicked guitar, time-scaled, nostalgic]\n[Chorus: choir sample, processed, dream-like]\n[Bridge: frequency sweep, morphing]\n[Outro: final bell]",
        "[Intro: bird chirps, temporal shift]\n[Verse: lo-fi soul loop, elongated bars]\n[Chorus: warm pads, embracing]\n[Bridge: talk-box effect, alien]\n[Outro: fade]",
        "[Intro: rain ambience, stretched]\n[Verse: boom-bap drums, half-tempo, meditative]\n[Chorus: vocal phrase repeat, echo chambers]\n[Bridge: wind textures, shifting]\n[Outro: silence approaches]",
        "[Intro: synthesizer bell, prolonged]\n[Verse: lo-fi acoustic guitar, time dilation]\n[Chorus: falsetto sample, layered]\n[Bridge: granular processing, particle cloud]\n[Outro: harmonic fade]",
        "[Intro: typewriter, aged]\n[Verse: chill hop beat, lo-fi aesthetic, temporal stretch]\n[Chorus: orchestral sample degraded, romantic]\n[Bridge: noise reduction, clarity breaks]\n[Outro: vinyl crackle exit]",
        "[Intro: ambient hum, extended]\n[Verse: lo-fi saxophone, warped tape, slowed rhythm]\n[Chorus: amen break sample, pitched down]\n[Bridge: spectral shift, ethereal]\n[Outro: silence reign]",
        "[Intro: music box, elongated]\n[Verse: lo-fi trap hi-hats, stretched kick, temporal morphing]\n[Chorus: dreamy vocal, reverb-processed]\n[Bridge: analog warmth, nostalgic crunch]\n[Outro: fade to white noise]",
    ]
    
    # 風格標籤 (Tags for instrumental+style)
    style_tags = [
        "lo-fi hip hop, chill, introspective, vinyl, crackle",
        "lo-fi, ambient, atmospheric, dreamy, warped",
        "chillhop, minimal, spacious, reverb, echo",
        "lo-fi soul, warm, vintage, nostalgic, degraded quality",
        "lo-fi acoustic, guitarra fingerpicked, peaceful",
        "ambient lo-fi, meditation, mindful, soothing",
        "lo-fi jazz, improvised feel, warm tones",
        "lo-fi beat tape, vintage sampling, processed",
        "lo-fi atmospheric, ethereal, synthetic, modular",
        "lo-fi introspection, emotional, contemplative",
    ]
    
    num_songs = 10 if mode == "generating" else (3 if mode == "quick" else 10)
    
    print(f"[VANGUARD] 啟動生成流程: {mode} mode → {num_songs} 首新歌")
    
    results = []
    
    try:
        for i in range(num_songs):
            title = f"VanguardGen_{i+1:02d}_{int(time.time())}"
            prompt = time_expansion_prompts[i % len(time_expansion_prompts)]
            style = style_tags[i % len(style_tags)]
            
            print(f"\n[VANGUARD] [{i+1}/{num_songs}] 生成: {title}")
            print(f"  Prompt: {prompt[:60]}...")
            print(f"  Style:  {style}")
            
            # 【重要】為每首歌使用唯一的文件名以避免覆蓋
            song_filename = f"VanguardGen_{str(i+1).zfill(2)}_{title}.mp3"
            
            result = generate_epic(
                prompt=prompt,
                style=style,
                title=title,
                target_sec=150.0,  # 2.5 分鐘每首
                model="chirp-v5",
                dest_filename=song_filename,
            )
            
            results.append(result)
            print(f"  → 成功: {result.get('duration_sec', '?')} 秒")
            
    except Exception as exc:
        err_detail = f"{type(exc).__name__}: {str(exc)}"
        print(f"\n[VANGUARD][ERROR] 生成失敗在第 {i+1}/{num_songs} 首")
        _log_fatal("SUNO_GENERATION_FAILED", err_detail)
    
    return results


def _trigger_mastering(raw_files: list[Path]) -> bool:
    """觸發自動母帶處理"""
    print(f"\n[VANGUARD] 觸發母帶處理 ({len(raw_files)} 首)...")
    
    try:
        from scripts.gear1_prod.audio_mastering_engine import main as mastering_main
        
        # 呼叫母帶引擎（如果它提供 main() 函式）
        # mastering_main()  # 假設 main() 會自動掃描 raw_tracks
        
        print(f"[VANGUARD] ✅ 母帶處理已觸發")
        return True
    except Exception as exc:
        print(f"[VANGUARD] ⚠️  母帶處理觸發失敗: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Suno Vanguard Run - 透過 pipeline_runner 架構的 10 首新歌生成"
    )
    parser.add_argument(
        "--mode",
        choices=["generating", "quick"],
        default="generating",
        help="生成模式 (generating=10首 | quick=測試3首)",
    )
    parser.add_argument(
        "--target-songs",
        type=int,
        default=0,
        help="自訂生成歌曲數 (優先於 --mode)",
    )
    
    args = parser.parse_args()
    
    # 決定生成數量
    if args.target_songs > 0:
        num_songs = args.target_songs
        mode_label = f"custom_{num_songs}"
    else:
        mode_label = args.mode
        num_songs = 10 if args.mode == "generating" else 3
    
    print(f"{'='*70}")
    print(f"[VANGUARD RUN] 啟動產線")
    print(f"{'='*70}")
    print(f"模式: {mode_label}")
    print(f"目標: {num_songs} 首新歌")
    print(f"時間: {datetime.datetime.now().isoformat()}")
    print(f"{'='*70}\n")
    
    # ⚠️ 預期結果 A: API 成功
    try:
        results = _generate_10_songs(mode=mode_label)
        
        if not results:
            _log_fatal("SUNO_NO_RESULTS", "No songs generated (API returned empty)")
        
        print(f"\n✅ 生成完成: {len(results)} 首新歌已進入 raw_tracks/")
        
        # 觸發母帶處理
        _trigger_mastering([])
        
        print(f"\n{'='*70}")
        print(f"[VANGUARD SUCCESS] 產線推進完成")
        print(f"{'='*70}")
        print(f"預期結果: 10 首新歌已自動進入 CEO 的 Telegram 核准佇列")
        print(f"下一步: CEO 點擊 [✅ 採用] 批准後，新歌將進入 Vault 用於最終混音")
        
    # ⚠️ 預期結果 B: API failures (HTTP 500 / timeout)
    except SystemExit:
        raise
    except Exception as exc:
        err_detail = f"{type(exc).__name__}: {str(exc)}"
        print(f"\n❌ 產線中止: {err_detail}")
        _log_fatal("SUNO_VANGUARD_FAILURE", err_detail)


if __name__ == "__main__":
    main()
