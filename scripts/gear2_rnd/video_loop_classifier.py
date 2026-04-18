"""
video_loop_classifier.py
========================
v15.7 Loop 策略分類器 — 檔名即策略（CEO 命名制）

設計原則（v15.7 起正式採用）：
  CEO 在取得每支影片時，依判斷直接在檔名加上前綴：
    ping_原名.mp4  → Ping-Pong 策略（振盪/自然景觀，無人物）
    ford_原名.mp4  → Forward 策略（有人物，或 CEO 指定的循環播放）

  本模組僅負責讀取檔名前綴並返回策略，無任何 CV 或 ML 運算。

使用方法：
  from scripts.gear2_rnd.video_loop_classifier import get_loop_strategy

  strategy = get_loop_strategy(Path("ping_ocean01.mp4"))          # → "pingpong"
  strategy = get_loop_strategy(Path("ford_RS_lofi_gril_03.mp4"))  # → "forward"

命名規範（給 CEO）：
  取得新影片後，播放確認後依以下規則命名再存入 vault：
    無人物、振盪/自然景觀（海浪、雲、火焰等）→  ping_原名.mp4
    有人物，或 Forward 循環效果較佳            →  ford_原名.mp4
  未加前綴的檔案會觸發 WARNING 並預設為 pingpong。
"""

from pathlib import Path
import logging

log = logging.getLogger(__name__)

PREFIX_PINGPONG = "ping_"
PREFIX_FORWARD  = "ford_"


def get_loop_strategy(video_path: Path) -> str:
    """
    從檔名前綴讀取 loop 策略。

    Returns:
        "pingpong" — 使用 正向+反向+正向+... 播放
        "forward"  — 使用 正向+正向+正向+... 播放

    Examples:
        ping_ocean01.mp4          → "pingpong"
        ford_RS_lofi_gril_03.mp4  → "forward"
        unnamed_video.mp4         → "pingpong" (預設，含 WARNING)
    """
    name = video_path.name  # 含副檔名

    if name.startswith(PREFIX_PINGPONG):
        return "pingpong"
    elif name.startswith(PREFIX_FORWARD):
        return "forward"
    else:
        log.warning(
            f"[LoopClassifier] ⚠️ 檔名無 ping_/ford_ 前綴：{video_path.name}，"
            f"預設使用 pingpong。請 CEO 依命名規範重命名後重新入庫。"
        )
        return "pingpong"


def get_base_name(video_path: Path) -> str:
    """
    去除 ping_ / ford_ 前綴，返回原始基礎名稱（不含副檔名）。

    Examples:
        ping_ocean01.mp4          → "ocean01"
        ford_RS_lofi_gril_03.mp4  → "RS_lofi_gril_03"
        unnamed_video.mp4         → "unnamed_video"
    """
    stem = video_path.stem
    if stem.startswith(PREFIX_PINGPONG[:-1]):   # "ping"
        return stem[len(PREFIX_PINGPONG):]
    elif stem.startswith(PREFIX_FORWARD[:-1]):  # "ford"
        return stem[len(PREFIX_FORWARD):]
    return stem


def classify_vault(vault_dir: Path) -> dict[str, list[Path]]:
    """
    掃描 vault 目錄，按策略分組返回所有影片路徑。

    Returns:
        {
            "pingpong": [Path, ...],
            "forward":  [Path, ...],
            "unknown":  [Path, ...]   ← 未命名規範，需 CEO 處理
        }
    """
    result = {"pingpong": [], "forward": [], "unknown": []}

    for mp4 in sorted(vault_dir.rglob("*.mp4")):
        name = mp4.name
        if name.startswith(PREFIX_PINGPONG):
            result["pingpong"].append(mp4)
        elif name.startswith(PREFIX_FORWARD):
            result["forward"].append(mp4)
        else:
            result["unknown"].append(mp4)
            log.warning(f"[LoopClassifier] 未命名規範：{mp4.name}")

    return result


# ── 快速掃描工具（直接執行時使用）──
if __name__ == "__main__":
    import sys
    from pathlib import Path

    vault_root = Path(__file__).resolve().parents[2] / "assets" / "video_clips" / "vault"
    result = classify_vault(vault_root)

    print(f"\n{'='*60}")
    print(f"  Vault Loop Strategy Summary")
    print(f"{'='*60}")
    print(f"  🔄 PING-PONG (_ping): {len(result['pingpong'])} 支")
    for p in result["pingpong"]:
        print(f"      {p.parent.name}/{p.name}")
    print(f"\n  ▶️  FORWARD   (_ford): {len(result['forward'])} 支")
    for p in result["forward"]:
        print(f"      {p.parent.name}/{p.name}")
    if result["unknown"]:
        print(f"\n  ⚠️  未命名規範: {len(result['unknown'])} 支（需 CEO 處理）")
        for p in result["unknown"]:
            print(f"      {p.parent.name}/{p.name}")
    print(f"{'='*60}")
    print(f"  合計: {sum(len(v) for v in result.values())} 支")
    sys.exit(0 if not result["unknown"] else 1)
