#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lofi_assembler.py — Phase 4 無縫縫合機 v15.9 (新鮮度鐵律版)
將存放於 vault_ready_for_mix/ 的多首單曲，以 FFmpeg acrossfade 濾鏡
融合成一首長達 1 小時的無縫長曲，並以平滑淡出收尾。
輸出格式：純音頻 .wav（無影片），用於 YouTube 頻道上傳。

【v15.9 變更】
  - 新增 NewSongsInsufficientException：dc=0 新歌配額不足時硬閘門阻擋
  - 廢除 v15.7 軟遞補（New 不足→Gen1 填補），保證每部作品 ≥50% 新鮮度
  - VaultSelection 支援 min_new_ratio 參數與分頻道 freshness_policy
"""
from __future__ import annotations
import argparse
import json
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path
# --- 路徑鐵律：引入動態 config，禁止硬編碼磁碟路徑 ---
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.common.env_manager import config
from scripts.gear2_rnd.vault_database import VaultDatabase
import math
import re

# ─────────────────────────────────────────────
#  自定義異常
# ─────────────────────────────────────────────
class VaultShortageException(Exception):
    """庫存不足異常：無法滿足最低選曲需求"""
    pass

class NewSongsInsufficientException(VaultShortageException):
    """
    【v15.9 新鮮度鐵律】dc=0 新歌配額不足，違反 50% 門檻。
    觸發條件：selected_new < ceil(target_tracks * min_new_ratio)
    解法：
      1) CEO 上傳更多新 MP3 至 ceo_approved_beats/{channel}/
      2) 啟用 --ttapi-fill-fresh 旗標，由 TTAPI Suno 自動補齊缺口
    """
    pass

# ─────────────────────────────────────────────
#  常數設定
# ─────────────────────────────────────────────
# 【v12.9 頻道路徑化】強制進入子目錄，禁止掃描根目錄
VAULT_DIR            = None  # 由 main() 根據 args.channel 動態設定，見下方
OUTPUT_DIR           = None  # 由 main() 根據 args.channel 動態設定，見下方【頻道隔離】
LEARNING_LOG         = config.workspace_root / "project_learning.md"
TARGET_DURATION_SEC  = 3600   # 目標輸出長度：1 小時
CROSSFADE_SEC        = 12     # acrossfade 交叉淡化秒數（雙向各 6 秒）
FINAL_FADEOUT_SEC    = 10     # 結尾 afade 淡出秒數
MIN_TRACK_DURATION   = 15     # 低於此秒數的音檔直接跳過，避免 acrossfade 出錯
SUPPORTED_EXTS = {".wav", ".mp3", ".flac", ".aiff", ".m4a"}
# ─────────────────────────────────────────────
#  致命錯誤處理器（全局鐵律：記錄 + sys.exit(1)）
# ─────────────────────────────────────────────
def _log_fatal(msg: str) -> None:
    """將致命錯誤 Append 寫入 project_learning.md，禁止靜默失敗。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n\n## [{timestamp}] lofi_assembler.py 致命錯誤\n{msg}\n"
    try:
        with open(LEARNING_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass
# ─────────────────────────────────────────────
#  ffprobe 取得音頻精確秒數
# ─────────────────────────────────────────────
def _get_duration(audio_path: Path) -> float:
    """使用 ffprobe 量測音頻精確秒數（符合「音樂先行」鐵律）。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(audio_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        raise RuntimeError(f"ffprobe 無法讀取 [{audio_path.name}]: {e}")
# ─────────────────────────────────────────────
#  掃描 Vault 資料夾
# ─────────────────────────────────────────────
def _scan_vault(vault_dir: Path) -> list[Path]:
    """掃描指定資料夾，回傳所有支援格式的音頻檔案（按修改時間倒序排列，最新優先）。【CTO v9.0 修復】確保新素材優先使用。"""
    vault_dir.mkdir(parents=True, exist_ok=True)
    valid_files = []
    try:
        for item in vault_dir.iterdir():
            try:
                # 只掃描檔案，不掃描目錄；檢查副檔名
                if item.is_file() and item.suffix.lower() in SUPPORTED_EXTS:
                    valid_files.append(item)
            except (OSError, PermissionError) as e:
                # 跳過無法讀取的項目，繼續掃描
                print(f"[VAULT_SCAN] ⚠️  無法讀取 {item.name}: {e}")
                continue
    except Exception as e:
        print(f"[VAULT_SCAN] 警告: 掃描 {vault_dir} 時遇到異常: {e}")
        # 繼續使用已收集的有效檔案
    
    # 【CTO v9.0 修復】按修改時間倒序排列（最新的檔案優先）
    valid_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    return valid_files
# ─────────────────────────────────────────────
#  建立播放清單（隨機選取 + 重複直到超過目標長度）
# ─────────────────────────────────────────────
def _build_playlist(
    all_tracks: list[Path],
    durations: dict[Path, float],
    target_sec: int,
) -> list[Path]:
    """
    隨機選取並重複拼接歌曲，直到考量 crossfade 重疊後的總長度 >= target_sec。
    每跑完一輪就重新洗牌，避免曲目順序過於重複。
    """
    playlist: list[Path] = []
    accumulated = 0.0
    shuffled = all_tracks[:]
    random.shuffle(shuffled)
    cycle_idx = 0
    while accumulated < target_sec:
        track = shuffled[cycle_idx % len(shuffled)]
        # 第一首全量累計；之後每首扣除 crossfade 重疊秒數
        accumulated += durations[track] if not playlist else (durations[track] - CROSSFADE_SEC)
        playlist.append(track)
        cycle_idx += 1
        # 每完整跑完一輪就重新洗牌
        if cycle_idx % len(shuffled) == 0:
            random.shuffle(shuffled)
    return playlist

# ─────────────────────────────────────────────
#  v9.5 智能選曲演算法：50/25/25 排播矩陣 + 同源排斥
# ─────────────────────────────────────────────
class VaultSelection:
    """v9.5 Vault 智能選曲引擎 (Bucketing + Anti-Collision + Channel Isolation)"""
    
    def __init__(self, target_tracks: int = 20, vault_dir: Path = None, channel: str = "lofi",
                 max_derivation_limit: int = 3, min_new_ratio: float = None):
        """
        初始化選曲引擎

        Args:
            target_tracks: 目標選曲數量（默認 20 首）
            vault_dir: Vault 目錄路徑（不指定則使用全局 VAULT_DIR）
            channel: 頻道標籤（lofi 或 light_music），用於資料庫層過濾
            max_derivation_limit: 曲目衍生次數嚴格上限（唯一標準 **3**）：僅 derivation_count < 3 入池
                                  （對應 Gen0/Gen1/Gen2；≥3 冷凍退役，與 Protocol L / 戰情表一致）
            min_new_ratio: 【v15.9 新鮮度鐵律】dc=0 新歌最低佔比（0.0~1.0）
                           None = 從 config.freshness_policy 按頻道讀取（預設 0.5）
        """
        self.target_tracks = target_tracks
        self.vault_dir = vault_dir if vault_dir else VAULT_DIR
        self.channel = channel
        self.max_derivation_limit = max_derivation_limit
        self.db = VaultDatabase()
        self.used_roots = set()
        self.playlist = []

        # 【v15.9】新鮮度配置：參數 > env config > 硬回退 0.5
        if min_new_ratio is None:
            try:
                policy = getattr(config, "freshness_policy", {}) or {}
                ch_cfg = (policy.get("channels") or {}).get(channel, {})
                self.min_new_ratio = float(ch_cfg.get("min_new_ratio", 0.5))
                self.freshness_enabled = bool(policy.get("enabled", True))
                self.freshness_enforcement = str(policy.get("enforcement", "strict")).lower()
            except Exception:
                self.min_new_ratio = 0.5
                self.freshness_enabled = True
                self.freshness_enforcement = "strict"
        else:
            self.min_new_ratio = float(min_new_ratio)
            self.freshness_enabled = True
            self.freshness_enforcement = "strict"
        
    @staticmethod
    def _extract_root_id(track_id: str) -> str:
        """
        從 track_id 中解析出基因 Root ID。
        核心策略：移除所有衍生後綴，保留基原 ID
        
        例如：
          - "R&S_Echoes_20260404_153000_tempo_up" → "R&S_Echoes_20260404_153000"
          - "original_track_pitch_down" → "original_track"
        """
        root = track_id
        
        # 列出所有可能的衍生後綴
        suffixes = [
            "_tempo_up", "_tempo_down", 
            "_pitch_up", "_pitch_down",
            "_reverb", "_chorus",
            "_speed_up", "_speed_down"
        ]
        
        for suffix in suffixes:
            if suffix in root:
                # 只移除最後一次出現
                parts = root.rsplit(suffix, 1)
                root = parts[0]
        
        return root.strip() if root else track_id
    
    def _extract_root_from_filename(self, filename: str) -> str:
        """從檔名中解析 Root ID（備用方法，以防 track_id 格式不一致）"""
        # 移除副檔名
        name = filename.rsplit('.', 1)[0] if '.' in filename else filename
        # 移除前綴序號
        name = re.sub(r'^\d+_', '', name)
        # 移除後綴
        name = re.sub(r'(_tempo_up|_tempo_down|_pitch_up|_pitch_down|_reverb|_chorus|_YT|-16LUFS).*$', '', name, flags=re.IGNORECASE)
        return name
    
    def _select_from_pool(self, pool: list[dict], quota: int) -> list[dict]:
        """
        從指定的 pool 中選取指定數量的曲目，實施同源排斥機制
        
        Args:
            pool: track 記錄列表 (含 track_id, original_path, derivation_count)
            quota: 需要選取的數量
            
        Returns:
            已選取的 track 記錄列表
        """
        selected = []
        pool_copy = pool[:]
        random.shuffle(pool_copy)
        
        for track_record in pool_copy:
            if len(selected) >= quota:
                break
                
            track_id = track_record.get("track_id", "")
            original_path = track_record.get("original_path", "")
            root = VaultSelection._extract_root_id(track_id)
            
            # 同源排斥檢查：若該基因已使用，跳過
            if root in self.used_roots:
                continue
            
            # 確認檔案存在
            file_path = self.vault_dir / Path(original_path).name
            if not file_path.exists():
                continue
            
            selected.append(track_record)
            self.used_roots.add(root)
        
        return selected
    
    def run(self) -> list[Path]:
        """
        執行 v9.5 50/25/25 選曲演算法（含頻道隔離）
        
        Returns:
            已選定的播放清單 (Path 列表)
            
        Raises:
            VaultShortageException: 庫存不足無法滿足選曲需求
        """
        # 第一步：從資料庫讀取所有 track，按 derivation_count 分組
        all_tracks = self.db.get_all_tracks()

        # 【修復 4】致命污染防護：嚴格過濾頻道，防止跨頻道基因污染
        all_tracks = [t for t in all_tracks if t.get("channel") == self.channel]

        # 【v15.3 UI 接管】依聽覺最大重複次數篩選：derivation_count < max_derivation_limit
        all_tracks = [t for t in all_tracks if t.get("derivation_count", 0) < self.max_derivation_limit]
        print(f"[VAULT_V95] 聽覺重複上限={self.max_derivation_limit}，過濾後可用曲目={len(all_tracks)}")

        # 若過濾後沒有歌曲，拋出異常
        if not all_tracks:
            raise VaultShortageException(f"資料庫中找不到頻道 [{self.channel}] 的可用歌曲")
        
        # 【CTO 熱修復】移除 -created_at 排序（字串負號地雷）
        # created_at 是字串格式，對其使用 - 操作符會拋出 TypeError
        # 且後續已有 random.shuffle() 打亂，此排序邏輯已冗餘
        all_tracks.sort(key=lambda t: t.get("derivation_count", 0))
        
        pool_new = [t for t in all_tracks if t.get("derivation_count", 0) == 0]
        pool_gen1 = [t for t in all_tracks if t.get("derivation_count", 0) == 1]
        pool_gen2 = [t for t in all_tracks if t.get("derivation_count", 0) == 2]
        
        print(f"\n[VAULT_V95] 庫存分佈：新歌={len(pool_new)}, Gen1={len(pool_gen1)}, Gen2={len(pool_gen2)}")
        
        # 第二步：計算配額
        # 【v15.9 新鮮度鐵律】quota_new 由頻道 min_new_ratio 動態決定（不再硬編碼 0.50）
        quota_new = math.ceil(self.target_tracks * self.min_new_ratio)
        # Gen1/Gen2 均分剩餘配額
        remaining = self.target_tracks - quota_new
        quota_gen1 = math.ceil(remaining * 0.5)
        quota_gen2 = remaining - quota_gen1

        print(f"[VAULT_V95] 配額目標（新鮮度 {self.min_new_ratio*100:.0f}%）："
              f"新歌={quota_new}, Gen1={quota_gen1}, Gen2={quota_gen2}")

        # 第三步：按配額從各 pool 選取（同源排斥）
        selected_new = self._select_from_pool(pool_new, quota_new)
        selected_gen1 = self._select_from_pool(pool_gen1, quota_gen1)
        selected_gen2 = self._select_from_pool(pool_gen2, quota_gen2)

        print(f"[VAULT_V95] 實際選取：新歌={len(selected_new)}, Gen1={len(selected_gen1)}, Gen2={len(selected_gen2)}")

        # 【v15.9 硬閘門】第四步a：新歌配額不足 → 拋 NewSongsInsufficientException（絕對不遞補）
        # ⚠️ v15.7 軟遞補已廢除！不允許用 Gen1 填補新歌缺口，以保障每部作品的原創新鮮度
        new_deficit = quota_new - len(selected_new)
        if new_deficit > 0 and self.freshness_enabled and self.freshness_enforcement == "strict":
            raise NewSongsInsufficientException(
                f"【v15.9 新鮮度鐵律】頻道 [{self.channel}] 新歌（dc=0）不足。\n"
                f"  需求：{quota_new} 首（= ceil({self.target_tracks} × {self.min_new_ratio*100:.0f}%)）\n"
                f"  池內：{len(pool_new)} 首 | 實選：{len(selected_new)} 首 | 缺：{new_deficit} 首\n"
                f"解法：\n"
                f"  (1) CEO 手動上傳 {new_deficit} 首新 MP3 到 ceo_approved_beats/{self.channel}/\n"
                f"  (2) 以 --ttapi-fill-fresh 旗標啟動 TTAPI Suno 自動補充（有費用）\n"
                f"  (3) 設定環境變數 FRESHNESS_ENFORCEMENT=warn 降級為警告模式（不建議）"
            )
        elif new_deficit > 0:
            # warn 模式：僅警告，不阻擋（CEO 顯式配置）
            print(f"[VAULT_V95] ⚠️  [warn 模式] New 缺 {new_deficit} 首，繼續執行（新鮮度未達標 {self.min_new_ratio*100:.0f}%）")

        # 第四步b：動態降級 - 若 Gen2 不足，從 Gen1 補足（不動 New 池，保持新鮮度乾淨）
        gen2_deficit = quota_gen2 - len(selected_gen2)
        if gen2_deficit > 0:
            print(f"[VAULT_V95] ⚠️  Gen2 缺少 {gen2_deficit} 首，從 Gen1 補足（新鮮度池不動用）...")
            additional_from_gen1 = self._select_from_pool(pool_gen1, gen2_deficit)
            selected_gen1.extend(additional_from_gen1)

        # 第五步：若 total >= 1 就繼續（_build_playlist 會自動重複填滿目標時長）
        total_selected = len(selected_new) + len(selected_gen1) + len(selected_gen2)
        if total_selected < 1:
            msg = f"庫存為空：頻道 [{self.channel}] 完全無可用曲目，無法混音"
            raise VaultShortageException(msg)
        if total_selected < self.target_tracks:
            shortage = self.target_tracks - total_selected
            print(f"[VAULT_V95] ⚠️  實際選取 {total_selected} 首 < 目標 {self.target_tracks}，"
                  f"缺少 {shortage} 首（_build_playlist 將以重複播放補足時長）")
        
        # 第六步：將 track 記錄轉換為 Path，打亂順序並回傳
        all_selected_records = selected_new + selected_gen1 + selected_gen2
        
        # 【CTO 修復 v13.2】延遲扣款防線：不在選曲時扣款，改由 assemble() 在確認最終播放清單後執行
        # 原因：提前扣款會導致過載縫合時浪費資產（例如選了25首，實際只用16首，多出9首也被扣款了）
        
        playlist = []
        for record in all_selected_records:
            original_path = record.get("original_path", "")
            file_path = self.vault_dir / Path(original_path).name
            playlist.append(file_path)
        
        random.shuffle(playlist)
        
        print(f"[VAULT_V95] ✅ 成功選取 {len(playlist)} 首，已實施同源排斥 (獨立基因={len(self.used_roots)})")
        print(f"[VAULT_V95] 💡 注意：此時未扣款，將於 assemble() 中精準修剪後再扣款")
        return playlist


def count_selectable_new_for_freshness_gate(
    channel: str,
    *,
    max_derivation_limit: int = 3,
    workspace_root: Path | None = None,
) -> tuple[int, int]:
    """
    【v15.9 對齊】與 VaultSelection.run() / _select_from_pool 一致的新歌「可選」數量。

    資料庫 dc=0 筆數可能大於實際可選首數，原因：
      - 同源排斥：同一基因 root 在單次混音最多只會選一首
      - 幽靈列：DB 有列但 vault_ready_for_mix 內無對應 WAV

    Returns:
        (raw_dc0_rows, unique_roots_with_existing_wav)
    """
    root_base = workspace_root or config.workspace_root
    vault_dir = root_base / "assets" / "audio" / "vault_ready_for_mix" / channel.lower()
    db = VaultDatabase()
    all_tracks = [t for t in db.get_all_tracks() if t.get("channel") == channel]
    all_tracks = [t for t in all_tracks if t.get("derivation_count", 0) < max_derivation_limit]
    pool_new = [t for t in all_tracks if t.get("derivation_count", 0) == 0]
    roots_ok: set[str] = set()
    for t in pool_new:
        op = t.get("original_path") or ""
        if not op:
            continue
        fp = vault_dir / Path(op).name
        if not fp.exists():
            continue
        roots_ok.add(VaultSelection._extract_root_id(t.get("track_id", "")))
    return len(pool_new), len(roots_ok)


def _scan_vault_v95(target_tracks: int = 20, vault_dir: Path = None, channel: str = "lofi",
                    max_derivation_limit: int = 3) -> list[Path]:
    """
    v9.5 新選曲引擎包裝函數（公用介面）

    Args:
        target_tracks: 目標選曲數量
        vault_dir: Vault 目錄路徑
        channel: 頻道標籤，向下傳遞給 VaultSelection
        max_derivation_limit: 最大允許衍生次數（v15.3 UI 接管新增，預設 3）

    Returns:
        已選定的播放清單

    Raises:
        VaultShortageException: 庫存不足
    """
    selection = VaultSelection(
        target_tracks=target_tracks, vault_dir=vault_dir,
        channel=channel, max_derivation_limit=max_derivation_limit,
    )
    return selection.run()

# ─────────────────────────────────────────────
#  計算 crossfade 後的精確輸出總秒數
# ─────────────────────────────────────────────
def _compute_output_duration(playlist: list[Path], durations: dict[Path, float]) -> float:
    """計算所有 acrossfade 重疊後的實際輸出長度（秒）。"""
    total = 0.0
    for i, track in enumerate(playlist):
        total += durations[track] if i == 0 else (durations[track] - CROSSFADE_SEC)
    return total

# ─────────────────────────────────────────────
#  提取乾淨的曲名（CTO v9.0 時間軸任務）
# ─────────────────────────────────────────────
def _extract_clean_title(filename: str) -> str:
    """
    【商業化升級】從檔名中剝離序號與後綴，還原真實曲名並標註效果標籤。
    
    範例：
      001_Midnight_Rain_YT_-16LUFS.wav → Midnight Rain
      002_Coffee_and_Code_tempo_up_YT_-16LUFS.mp3 → Coffee and Code [Remix 1]
      003_Neon_Solitude_pitch_down_YT_-16LUFS.wav → Neon Solitude [Remix 3]
    
    效果映射：
      - tempo_up → Remix 1 (加速)
      - tempo_down → Remix 2 (減速)
      - pitch_down → Remix 3 (降調)
      - pitch_up → Remix 4 (升調)
    """
    import re
    
    # 移除檔案副檔名
    name = filename.rsplit('.', 1)[0] if '.' in filename else filename
    
    # 偵測效果標籤
    remix_tags = {
        r'tempo_up': '[Remix 1]',
        r'tempo_down': '[Remix 2]',
        r'pitch_down': '[Remix 3]',
        r'pitch_up': '[Remix 4]',
    }
    
    remix_suffix = ""
    for pattern, tag in remix_tags.items():
        if re.search(pattern, name, re.IGNORECASE):
            remix_suffix = f" {tag}"
            # 移除效果標籤本身
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
            break
    
    # 移除前綴序號（例：001_ 或 01_ 或 1_）
    name = re.sub(r'^\d+_', '', name)
    
    # 移除後綴模式（例：_YT、-16LUFS、_YT_-16LUFS、_2026XXXX 等）
    name = re.sub(r'(_YT|_-16LUFS|-16LUFS|_YT_-16LUFS|_2026\d+).*$', '', name, flags=re.IGNORECASE)
    
    # 移除孤立的底線（由效果標籤移除後遺留）
    name = re.sub(r'_+$', '', name)
    
    # 將底線替換回空格
    name = name.replace('_', ' ')
    
    # 清理多個空格
    name = re.sub(r'\s+', ' ', name).strip()
    
    return (name if name else "Unknown Track") + remix_suffix

# ─────────────────────────────────────────────
#  生成 Tracklist（CTO v10.0 商業化升級）
# ─────────────────────────────────────────────
def _generate_tracklist(playlist: list[Path], durations: dict[Path, float]) -> str:
    """
    【商業化升級】生成 YouTube 相容的 Tracklist，自動標註重複曲目。
    
    計算公式：
    - 第 N 首歌起始時間 = 前 (N-1) 首歌的總秒數 - ((N-1) * CROSSFADE_SEC)
    
    重複處理：
    - 首次出現：如常 "Midnight Rain"
    - 第 2 次出現：添加 "Vol. 2" 標籤 → "Midnight Rain Vol. 2"
    - 第 3 次出現：添加 "Vol. 3" 標籤 → "Midnight Rain Vol. 3"
    
    範例輸出：
    00:00 - Midnight Rain
    02:45 - Neon Solitude [Remix 1]
    05:22 - Coffee and Code
    08:10 - Midnight Rain Vol. 2
    """
    tracklist_lines = []
    current_time = 0.0
    title_counts = {}  # 【商業化升級】追蹤曲目出現次數
    
    for idx, track in enumerate(playlist):
        # 提取乾淨的曲名（含效果標籤，如 [Remix 1]）
        clean_title = _extract_clean_title(track.name)
        
        # 【商業化升級】若曲名重複，添加 Vol. 標籤
        if clean_title in title_counts:
            title_counts[clean_title] += 1
            final_title = f"{clean_title} Vol. {title_counts[clean_title]}"
        else:
            title_counts[clean_title] = 1
            final_title = clean_title
        
        # 格式化時間戳記（MM:SS）
        minutes = int(current_time) // 60
        seconds = int(current_time) % 60
        timestamp = f"{minutes:02d}:{seconds:02d}"
        
        tracklist_lines.append(f"{timestamp} - {final_title}")
        
        # 計算下一首歌的起始時間
        if idx < len(playlist) - 1:
            track_duration = durations[track]
            if idx == 0:
                current_time += track_duration - CROSSFADE_SEC
            else:
                current_time += track_duration - CROSSFADE_SEC
    
    return "\n".join(tracklist_lines)

# ─────────────────────────────────────────────
#  保存 Tracklist 到檔案（CTO v9.0）
# ─────────────────────────────────────────────
def _save_tracklist(tracklist_content: str, output_dir: Path) -> Path:
    """
    將 Tracklist 保存為 Tracklist_[日期].txt。
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    tracklist_file = output_dir / f"Tracklist_{timestamp}.txt"
    
    try:
        with open(tracklist_file, "w", encoding="utf-8") as f:
            f.write("【R&S Echoes 1 小時無縫混音 - Tracklist】\n")
            f.write("=" * 60 + "\n")
            f.write(tracklist_content)
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        print(f"\n✅ Tracklist 已保存: {tracklist_file}")
        return tracklist_file
    except Exception as e:
        print(f"⚠️ 保存 Tracklist 失敗: {e}")
        return None
# ─────────────────────────────────────────────
#  【CTO SFX 過場橋樑】計算所有 Crossfade 時間戳記（毫秒）
# ─────────────────────────────────────────────
def _compute_crossfade_timestamps(playlist: list[Path], durations: dict[Path, float], cf_sec: int) -> list[int]:
    """
    計算每個 Crossfade 發生時的精確時間戳記（毫秒）。
    
    示例：
    - 歌1 (180s) → Crossfade @ 180-6=174s = 174000ms
    - 歌2 (120s, 扣除 crossfade) → Crossfade @ 174+120-6=288s = 288000ms
    ...
    """
    timestamps = []
    accumulated = 0.0
    
    for i in range(len(playlist) - 1):
        # 首首歌的結尾時間 = accumulated + 歌曲長度 - crossfade/2
        crossfade_point = accumulated + durations[playlist[i]] - (cf_sec / 2.0)
        timestamps.append(int(crossfade_point * 1000))  # 轉換為毫秒
        
        # 累計：加上當前歌曲長度，然後扣除 crossfade 重疊
        accumulated += durations[playlist[i]] - cf_sec
    
    return timestamps

# ─────────────────────────────────────────────
#  【CTO 鐵血軍令】重構 SFX 過場濾鏡 (O(1) 記憶體複雜度)
# ─────────────────────────────────────────────
def _build_sfx_overlay_filters(num_tracks: int, sfx_input_idx: int, cf_sec: int = 12) -> tuple[str, list[str]]:
    """
    【新架構 v9.0】 SFX 與軌道交叉淡化一體化設計
    
    核心策略：廢除多副本 + adelay 的記憶體浪費！
    取 SFX 的前 12 秒，直接與「每一首即將接續的 Track」的開頭進行 amix 混合。
    
    邏輯流程：
    1. 抽取 SFX 的前 CROSSFADE_SEC 秒，儲為 [sfx0]（單份，內存O(1)）
    2. 使用 asplit 分割為 (num_tracks - 1) 份副本（虛擬分割，不耗內存）
    3. 每份副本與對應高階Track的開頭進行 amix 混合
    4. 然後進行 acrossfade 交叉淡化
    
    返回值：
    - sfx_prefix：SFX 抽取 + asplit 的濾波器前綴
    - overlay_paths：每個軌道對應的 SFX 混合輸出標籤
    
    示例（num_tracks=3）：
    [3:a]atrim=0:12,volume=0.04,asplit=2[sfx0_0][sfx0_1];  # 4% 音量
    [1:a][sfx0_0]amix=inputs=2:duration=first[t1_sfx];
    [2:a][sfx0_1]amix=inputs=2:duration=first[t2_sfx];
    """
    # 邊界檢查：至少需要 2 首軌道才能有 SFX 過場
    if num_tracks < 2:
        return "", [f"[{i}:a]" for i in range(num_tracks)]
    
    n_copies = num_tracks - 1  # 【CTO 終極糾偏】SFX 副本數 = 軌道數 - 1（只有過場點需要 SFX）
    
    filters = []
    overlay_paths = []
    
    # 【第 1 步】抽取 SFX 的前 CROSSFADE_SEC 秒，添加 volume 調整
    # 使用 asplit 分割為(n-1)個副本供過場點使用
    sfx_labels = "".join([f"[sfx0_{i}]" for i in range(n_copies)])
    filters.append(f"[{sfx_input_idx}:a]atrim=0:{cf_sec},volume=0.04,asplit={n_copies}{sfx_labels}")
    
    # 軌道 0 保持原樣，直接加入overlay_paths
    overlay_paths.append(f"[0:a]")
    
    # 【第 2 步】將每份 SFX 副本與對應軌道進行 amix 混合（從軌道 1 開始）
    for i in range(1, num_tracks):
        sfx_label = f"sfx0_{i-1}"
        overlay_label = f"t{i}_with_sfx"
        
        # 軌道 i 與 SFX 副本 (i-1) 混合
        filters.append(f"[{i}:a][{sfx_label}]amix=inputs=2:duration=first[{overlay_label}]")
        overlay_paths.append(f"[{overlay_label}]")
    
    sfx_prefix = ";".join(filters)
    return sfx_prefix, overlay_paths

# ─────────────────────────────────────────────
#  建構 FFmpeg filter_complex 字串
# ─────────────────────────────────────────────
def _build_filter_complex(n: int, fade_start: float, has_sfx: bool = False, sfx_input_idx: int = None) -> str:
    """
    【CTO 鐵血軍令 v9.0】為 n 個輸入音軌建構 acrossfade 串接 filter_complex 字串。
    
    新架構（O(1) 記憶體複雜度）：
    - 如果 has_sfx=True，使用 _build_sfx_overlay_filters 生成 SFX amix 與 acrossfade 邏輯
    - 否則使用原本乾淨的 acrossfade 邏輯
    """
    cf    = CROSSFADE_SEC
    fo    = FINAL_FADEOUT_SEC
    
    parts = []
    
    if has_sfx and sfx_input_idx is not None:
        # 【有 SFX 的情況】：由 _build_sfx_overlay_filters 負責所有 SFX amix + acrossfade
        sfx_prefix, overlay_paths = _build_sfx_overlay_filters(n, sfx_input_idx, cf_sec=cf)
        parts.append(sfx_prefix)
        
        # 移除標籤的方括號進行串接
        inputs_no_brackets = [p.strip("[]") for p in overlay_paths]
        
        afade_out = f"afade=t=out:st={fade_start:.3f}:d={fo}[out]"
        
        if n == 1:
            # 單首軌道：直接淡出
            parts.append(f"[{inputs_no_brackets[0]}]{afade_out}")
        elif n == 2:
            # 兩首軌道：[0:a] 與 [t1_with_sfx] 進行 acrossfade + afade
            parts.append(f"[{inputs_no_brackets[0]}][{inputs_no_brackets[1]}]acrossfade=d={cf}:c1=exp:c2=exp,{afade_out}")
        else:
            # 多首軌道：逐一 crossfade
            # 第一個 crossfade：軌道 0 與軌道 1（已混好 SFX）
            parts.append(f"[{inputs_no_brackets[0]}][{inputs_no_brackets[1]}]acrossfade=d={cf}:c1=exp:c2=exp[cf0]")
            
            # 中間的 crossfades
            for i in range(2, n):
                parts.append(f"[cf{i - 2}][{inputs_no_brackets[i]}]acrossfade=d={cf}:c1=exp:c2=exp[cf{i - 1}]")
            
            # 最後的 crossfade + afade
            last_in = f"cf{n - 2}"
            parts.append(f"[{last_in}]{afade_out}")
    else:
        # 【無 SFX 的情況】：使用原本乾淨的 acrossfade 邏輯
        # 【v12.28 RCA 修復】添加 fade in 操作
        fade_in_dur = 3  # Fade in 時長 3 秒
        afade_out = f"afade=t=out:st={fade_start:.3f}:d={fo}[out]"
        
        if n == 1:
            # 單首軌道：fade in + fade out
            parts.append(f"[0:a]afade=t=in:st=0:d={fade_in_dur},afade=t=out:st={fade_start:.3f}:d={fo}[out]")
        elif n == 2:
            # 兩首軌道：第一首 fade in，然後 acrossfade，最後 fade out
            parts.append(f"[0:a]afade=t=in:st=0:d={fade_in_dur}[in0];[in0][1:a]acrossfade=d={cf}:c1=exp:c2=exp,{afade_out}")
        else:
            # 多首軌道：第一首 fade in，中間 acrossfade，最後 fade out
            parts.append(f"[0:a]afade=t=in:st=0:d={fade_in_dur}[in0];[in0][1:a]acrossfade=d={cf}:c1=exp:c2=exp[cf0]")
            
            # 中間的 crossfades
            for i in range(2, n):
                parts.append(f"[cf{i - 2}][{i}:a]acrossfade=d={cf}:c1=exp:c2=exp[cf{i - 1}]")
            
            # 最後的 crossfade + afade
            last_in = f"cf{n - 2}"
            parts.append(f"[{last_in}]{afade_out}")
    
    return ";".join(parts)
# ─────────────────────────────────────────────
#  【v12.26 物理檔案查驗】同步硬碟與資料庫
# ─────────────────────────────────────────────
def _refresh_orphans(vault_dir: Path, channel: str) -> int:
    """
    【v12.27 懶加載註冊機制】在選曲前執行物理檔案查驗，自動補辦入庫登記。
    
    邏輯：
    1. 掃描硬碟上 vault_dir 中的所有支援格式檔案
    2. 查詢資料庫中該頻道已紀錄的 track_id
    3. 識別「硬碟有但資料庫無」的檔案（孤兒檔）
    4. 對每個孤兒自動調用 db.add_track() 進行補辦登記
    5. 確保選曲引擎能夠識別所有實際檔案
    
    Returns:
        補辦登記的檔案數量（包含跳過的已存在檔案）
    """
    print(f"\n[v12.27] 【懶加載註冊】執行硬碟與資料庫同步檢查...")
    
    db = VaultDatabase()
    try:
        # 掃描硬碟上的所有支援格式檔案
        disk_files = {}
        for ext in SUPPORTED_EXTS:
            for item in vault_dir.glob(f"*{ext}"):
                filename = item.name
                track_id = item.stem  # 檔名去副檔名
                disk_files[track_id] = item
        
        if not disk_files:
            print(f"[v12.27] ℹ️ 硬碟上無可用檔案")
            return 0
        
        print(f"[v12.27] 硬碟掃描: 發現 {len(disk_files)} 個可用檔案")
        
        # 查詢資料庫中該頻道已紀錄的 track_id
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT track_id FROM audio_assets WHERE channel = ? AND is_archived = 0",
            (channel,)
        )
        db_records = cursor.fetchall()
        db_track_ids = set(row[0] for row in db_records)
        
        print(f"[v12.27] 資料庫查詢: 該頻道已有 {len(db_track_ids)} 筆活躍紀錄")
        
        # 識別孤兒檔（硬碟有但資料庫無）
        orphan_track_ids = set(disk_files.keys()) - db_track_ids
        
        if not orphan_track_ids:
            print(f"[v12.27] ✅ 硬碟與資料庫完全同步，無孤兒檔")
            return 0
        
        # 補辦登記孤兒檔
        print(f"[v12.27] ⚠️  發現 {len(orphan_track_ids)} 個孤兒檔，開始補辦入庫登記...")
        
        registered_count = 0
        for track_id in sorted(orphan_track_ids):
            file_path = disk_files[track_id]
            
            try:
                success = db.add_track(
                    track_id=track_id,
                    original_path=str(file_path),
                    root_id=track_id,
                    channel=channel,
                    mood=None,
                    genre=None,
                    bpm=None
                )
                
                if success:
                    print(f"  ✅ 已補辦: {file_path.name}")
                    registered_count += 1
                else:
                    print(f"  ℹ️ 已存在: {file_path.name}")
                    registered_count += 1
            except Exception as e:
                print(f"  ❌ 登記異常: {file_path.name} - {e}")
        
        print(f"[v12.27] 📝 完成補辦 {registered_count}/{len(orphan_track_ids)} 個孤兒檔")
        return registered_count
        
    finally:
        db.close()

# ─────────────────────────────────────────────
#  【v12.27 分段縫合架構】解決 Windows 8191 字元限制
# ─────────────────────────────────────────────
def _assemble_with_batching(
    playlist: list[Path],
    durations: dict[Path, float],
    output_dir: Path,
    output_duration: float,
) -> Path | None:
    """
    【v12.27 分段縫合】用 5 首一組的批次處理，解決 FFmpeg 命令行長度超限。
    
    邏輯：
    1. 將播放清單分組（每組 5 首）
    2. 對每組調用 FFmpeg acrossfade，生成 part1.wav, part2.wav...
    3. 使用 ffmpeg concat demuxer（文本清單模式）進行最終無損合併
    
    優勢：
    - ✅ 支持無限長播放清單（1 小時、10 小時都可以）
    - ✅ 每個 FFmpeg 命令行保持在 8191 字元限制以內
    - ✅ 中間件無損處理（全部 PCM s16le）
    - ✅ 進度透明（逐批次日誌輸出）
    
    Returns:
        最終合併後的 .wav 檔案路徑，或 None 表示失敗
    """
    n = len(playlist)
    batch_size = 5
    num_batches = (n + batch_size - 1) // batch_size  # 向上取整
    
    print(f"\n[v12.27 分段縫合] 啟動批次處理 ({n} 首曲目 → {num_batches} 批，每批 {batch_size} 首)")
    
    cf = CROSSFADE_SEC
    fo = FINAL_FADEOUT_SEC
    
    part_files = []
    
    # ───────────────────────────────────────────
    # 第一階段：逐批次縫合
    # ───────────────────────────────────────────
    for batch_idx in range(num_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, n)
        batch_tracks = playlist[start_idx:end_idx]
        batch_n = len(batch_tracks)
        
        print(f"\n[批次 {batch_idx + 1}/{num_batches}] 縫合曲目 #{start_idx + 1} - #{end_idx}...")
        
        # 【CTO 終極修復】精準計算批次長度，解決 st=0 導致的全域靜音 Bug
        fade_in_dur = 3
        # 計算此批次扣除 crossfade 重疊後的總真實時長
        batch_dur = sum(durations[t] for t in batch_tracks) - (batch_n - 1) * cf
        
        is_first_batch = (batch_idx == 0)
        is_last_batch = (batch_idx == num_batches - 1)
        
        filter_parts = []
        current_out = "0:a"
        
        # 1. 處理 Fade-in (僅限第一批次的第一首)
        if is_first_batch:
            filter_parts.append(f"[0:a]afade=t=in:st=0:d={fade_in_dur}[in0]")
            current_out = "in0"
            
        # 2. 處理 Acrossfade (曲目縫合)
        if batch_n > 1:
            filter_parts.append(f"[{current_out}][1:a]acrossfade=d={cf}:c1=exp:c2=exp[cf1]")
            current_out = "cf1"
            for i in range(2, batch_n):
                filter_parts.append(f"[{current_out}][{i}:a]acrossfade=d={cf}:c1=exp:c2=exp[cf{i}]")
                current_out = f"cf{i}"
                
        # 3. 處理 Fade-out (僅限最後一批次的結尾)
        if is_last_batch:
            # 精準計算淡出起始點：批次總時長 - 淡出時長
            fade_start = max(0.0, batch_dur - fo)
            filter_parts.append(f"[{current_out}]afade=t=out:st={fade_start:.3f}:d={fo}[out]")
        else:
            # 中間批次不淡出，使用 anull 濾鏡安全對接到 [out] 接口
            filter_parts.append(f"[{current_out}]anull[out]")
            
        batch_filter = ";".join(filter_parts)
        
        # 構建 FFmpeg 輸入列表
        ffmpeg_inputs = []
        for track in batch_tracks:
            ffmpeg_inputs.extend(["-i", str(track)])
        
        # 輸出檔案名
        batch_output = output_dir / f"_batch_{batch_idx:02d}_part{batch_idx + 1}.wav"
        
        cmd = (
            ["ffmpeg", "-y"]
            + ffmpeg_inputs
            + [
                "-filter_complex", batch_filter,
                "-map", "[out]",
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                str(batch_output),
            ]
        )
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                msg = f"批次 {batch_idx + 1} 縫合失敗：{result.stderr[-1000:]}"
                _log_fatal(msg)
                print(f"[FATAL] {msg}")
                return None
            
            part_files.append(batch_output)
            print(f"  ✅ 批次 {batch_idx + 1} 完成：{batch_output.name}")
        except Exception as e:
            _log_fatal(f"批次 {batch_idx + 1} 異常：{e}")
            return None
    
    # ───────────────────────────────────────────
    # 第二階段：concat demuxer 最終合併
    # ───────────────────────────────────────────
    if len(part_files) == 1:
        # 只有一批，直接使用
        print(f"\n[合併] 只有 1 批，直接使用...")
        return part_files[0]
    
    print(f"\n[合併] 使用 concat demuxer 進行 {len(part_files)} 批無損合併...")
    
    # 生成 concat 清單檔案
    concat_list_file = output_dir / f"_concat_list_{datetime.now().strftime('%H%M%S')}.txt"
    try:
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for part_file in part_files:
                # FFmpeg concat demuxer 格式：file '/path/to/file.wav'
                f.write(f"file '{part_file}'\n")
        
        print(f"  📝 Concat 清單已生成：{concat_list_file.name}")
    except Exception as e:
        _log_fatal(f"生成 concat 清單失敗：{e}")
        return None
    
    # 最終輸出檔案名稱
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    final_output = output_dir / f"R&S_Echoes_1HrMix_{ts}.wav"
    
    # 使用 concat demuxer
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",  # 無損複製（全部已是 PCM s16le）
        str(final_output),
    ]
    
    try:
        result = subprocess.run(cmd_concat, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            msg = f"Concat 合併失敗：{result.stderr[-1000:]}"
            _log_fatal(msg)
            print(f"[FATAL] {msg}")
            return None
        
        print(f"✅  Concat 合併完成：{final_output.name}")
        
        # 清理中間檔案和 concat 清單
        for part_file in part_files:
            try:
                part_file.unlink()
            except:
                pass
        try:
            concat_list_file.unlink()
        except:
            pass
        
        return final_output
        
    except Exception as e:
        _log_fatal(f"Concat 合併異常：{e}")
        return None

# ─────────────────────────────────────────────
#  主縫合函式
# ─────────────────────────────────────────────
def assemble(output_name: str | None = None, target_sec: int = TARGET_DURATION_SEC, sfx_path: str | None = None, sfx_mode: str = "global", channel: str = "lofi", output_dir: Path | None = None, max_derivation_limit: int = 3) -> Path | None:
    """
    【CTO v12.27 分段縫合重構 + 修復 2】支持無限長播放清單與多頻道隔離。
    
    新架構：
    1. 選曲前先執行 _refresh_orphans()，同步硬碟與資料庫
    2. 使用分段縫合（5首一組）進行 acrossfade 縫合
    3. 最後用 concat demuxer 無損合併
    4. 可選 SFX 疊加
    5. 【修復 2】頻道感知輸出檔名
    
    支援：
    - ✅ 無限長播放清單（1小時 / 10小時）
    - ✅ 手動改名/搬運檔案自動同步
    - ✅ 完整的音訊品質保留（PCM s16le 44.1kHz）
    - ✅ 多頻道隔離
    """
    # 【CTO 熱修復 v13.1】動態設定 output_dir，避免依賴全域變數
    if output_dir is None:
        output_dir = config.workspace_root / "assets" / "final_exports" / channel.lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 【CTO 修復 v13.1】使用全局 VAULT_DIR（已在 __main__ 中被設置為正確的頻道路徑）
    # 注意：global 宣告已移除，因為 VAULT_DIR 在模組層級初始化，並在 __main__ 中賦值
    
    # 【v12.27 懶加載】在選曲前同步硬碟與資料庫（補辦孤兒檔登記）
    try:
        _refresh_orphans(VAULT_DIR, channel)
    except Exception as e:
        _log_fatal(f"孤兒檔同步失敗: {e}")
        sys.exit(1)
    
    # === 【CTO 架構修正 v10.1】動態時長驅動選曲 ===
    print(f"\n[PHASE 1.5] 啟動動態時長驅動選曲引擎...")
    try:
        # 1. 掃描金庫，取得所有可用媒體檔案
        all_files = _scan_vault(VAULT_DIR)
        if not all_files:
            raise VaultShortageException("金庫為空，無可用媒體檔案")
        
        # 2. 隨機抽樣 5 首（或全部若少於 5 首），估算平均單曲時長
        sample_size = min(5, len(all_files))
        sample_files = random.sample(all_files, sample_size)
        total_sample_duration = sum(_get_duration(f) for f in sample_files)
        avg_duration = total_sample_duration / sample_size
        
        # 3. 計算動態目標首數
        estimated_tracks_needed = math.ceil(target_sec / avg_duration) + 2
        
        # 4. 日誌輸出
        print(f"[動態時長] 掃描結果: 金庫共 {len(all_files)} 首可用媒體")
        print(f"[動態時長] 抽樣樣本: {sample_size} 首，平均時長: {avg_duration:.1f} 秒")
        print(f"[動態時長] 計算公式: ceil({target_sec} / {avg_duration:.1f}) + 2 = {estimated_tracks_needed} 首")
        print(f"[動態時長] 系統決定動態抓取: {estimated_tracks_needed} 首媒體")
        
        # 5. 將動態計算出的首數與 channel 傳給 50/25/25 選曲演算法【修復 2】
        playlist = _scan_vault_v95(target_tracks=estimated_tracks_needed, vault_dir=VAULT_DIR,
                                   channel=channel, max_derivation_limit=max_derivation_limit)
        
    except NewSongsInsufficientException as e:
        # 【v15.9 硬閘門】新鮮度違規：不是「庫存不足→遞補」，而是「品質不足→中止」
        # 必須以 exit code 4 明確告知 pipeline_runner，區別於舊版庫存缺貨
        print(f"\n[FATAL][FRESHNESS_VIOLATION]\n{e}\n")
        _log_fatal(f"FRESHNESS_VIOLATION: {e}")
        sys.exit(4)
    except VaultShortageException as e:
        print(f"[STATUS] {e}。系統將觸發自動備援補充。")
        return None
    except Exception as e:
        _log_fatal(f"選曲引擎發生未知錯誤: {e}")
        sys.exit(1)

    # 【CTO 熱修復】動態決定 output_dir（避免依賴全域變數）
    if output_dir is None:
        output_dir = config.workspace_root / "assets" / "final_exports" / channel.lower()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 取得 durations 以供後續 crossfade 計算
    durations: dict[Path, float] = {}
    try:
        for track in playlist:
            try:
                durations[track] = _get_duration(track)
            except RuntimeError as e:
                _log_fatal(f"無法取得曲目時長 [{track.name}]: {e}")
                sys.exit(1)
    except Exception as e:
        _log_fatal(f"計算時長時發生未知錯誤: {e}")
        sys.exit(1)
        
    # === 【CTO 修復 v13.2：過載修剪防線 (Overshoot Defense)】 ===
    print(f"\n[VAULT_V95] 【精準修剪】分析播放清單...")
    trimmed_playlist = []
    output_duration = 0.0
    for track in playlist:
        trimmed_playlist.append(track)
        # 精確累加時長
        if len(trimmed_playlist) == 1:
            output_duration += durations[track]
        else:
            output_duration += (durations[track] - CROSSFADE_SEC)
        
        # 一旦達到或剛好超過 target_sec 秒，立刻停止加入後續歌曲
        if output_duration >= target_sec:
            print(f"[VAULT_V95] 🛑 已達目標時長 {output_duration:.1f}s >= {target_sec}s，停止加入後續歌曲")
            break
            
    playlist = trimmed_playlist  # 覆蓋為修剪後的精準播放清單
    unique_count = len(playlist)

    # === 【CTO 修復 v13.2：精準扣款 (Delayed DB Commit)】 ===
    print(f"\n[VAULT_V95] 📝 正在將最終確認的 {len(playlist)} 首曲目寫回資料庫...")
    db = VaultDatabase()
    if db.conn:
        cursor = db.conn.cursor()
        for track in playlist:
            track_id = track.stem  # 檔名即 track_id
            try:
                cursor.execute(
                    "UPDATE audio_assets SET derivation_count = derivation_count + 1 WHERE track_id = ?",
                    (track_id,)
                )
            except Exception as e:
                print(f"[VAULT_V95] ⚠️ 更新 {track_id} 計數失敗: {e}")
        db.conn.commit()
        db.close()
        print(f"[VAULT_V95] ✅ 成功扣款 {len(playlist)} 首曲目的使用次數")
    else:
        print(f"[VAULT_V95] ⚠️ 資料庫連接不可用，無法扣款")
    
    # 【CTO 絕對時長防線】確保真實時長必定 >= target_sec (處理極端短缺情況)
    cycle_idx = 0
    original_n = unique_count
    while output_duration < target_sec:
        # 若長度不足，從已選清單中循環提取曲目補足
        extra_track = playlist[cycle_idx % original_n]
        playlist.append(extra_track)
        # 累加時長 (因為是拼接，需扣除一次 crossfade 重疊時間)
        output_duration += (durations[extra_track] - CROSSFADE_SEC)
        cycle_idx += 1

    n = len(playlist)
    print(f"\n[PLAYLIST] 智能選曲與時長校正完成！")
    print(f"  • 實際消耗金庫基因: {unique_count} 首")
    print(f"  • 循環補足首數: {cycle_idx} 首 (總計 {n} 首)")
    print(f"  • 最終精準預估長度：{output_duration:.1f}s ({output_duration / 60:.1f} 分鐘)")
    
    # 輸出檔案名稱【修復 2】動態包含頻道名稱
    if output_name is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        # 【修復 2】檔名加入 channel，讓 Phase 5 與後續流程能識別頻道
        output_name = f"R&S_Echoes_{channel.lower()}_1HrMix_{ts}.wav"
    output_path = output_dir / output_name
    
    # ═══════════════════════════════════════════════════════════
    # 【v12.27 分段縫合】使用新架構進行無縫混音
    # ═══════════════════════════════════════════════════════════
    print(f"\n[PHASE 1] 開始纯音乐母帯縫合（分段批次架構）...")
    
    temp_music_path = _assemble_with_batching(playlist, durations, output_dir, output_duration)
    
    if temp_music_path is None:
        _log_fatal("分段縫合失敗")
        sys.exit(1)
    
    print(f"✅ Phase 1 完成：{temp_music_path.name}")
    
    # ═══════════════════════════════════════════════════════════
    # 【阶段二】後期 SFX 疊加
    # ═══════════════════════════════════════════════════════════
    if sfx_path:
        print(f"\n[PHASE 2] 開始後期 SFX 疊加（模式: {sfx_mode}）...")
        sfx_file = Path(sfx_path)
        if sfx_file.exists() and sfx_file.suffix.lower() in {'.wav', '.mp3', '.flac', '.aiff', '.m4a'}:
            # 【v12.28 RCA 修復】廢除 between() transition 邏輯，統一使用 Global 模式
            # 原因：between() 時間戳記與實際播放時間對應關係易出錯，導致 11:25~12:10 
            # 時段異常混入音樂。改為全程 Global 模式更安全。
            print(f"   [Global Mode] SFX 應用於全程（4% 音量，過場點滑順）")
            
            # Global 模式：簡單而安全
            sfx_mix_filter = (
                "[1:a]volume=0.04[sfx_vol];"
                "[0:a][sfx_vol]amix=inputs=2:duration=first[out]"
            )
            
            cmd_phase2 = [
                "ffmpeg", "-y",
                "-i", str(temp_music_path),
                "-stream_loop", "-1", "-i", str(sfx_file),
                "-filter_complex", sfx_mix_filter,
                "-t", str(int(output_duration)),  # 限制輸出長度
                "-map", "[out]",
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                str(output_path),
            ]
            
            print(f"[FFMPEG P2] 混合純音樂 + 循環 SFX（{sfx_file.name}，模式: {sfx_mode}）...")
            try:
                result = subprocess.run(cmd_phase2, capture_output=True, text=True, timeout=3600)
                if result.returncode != 0:
                    msg = f"Phase 2 失敗（returncode={result.returncode}）\n{result.stderr[-1500:]}"
                    _log_fatal(msg)
                    print(f"[FATAL] {msg}")
                    sys.exit(1)
                print(f"✅  Phase 2 完成：混合 SFX（{sfx_mode} 模式）")
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                _log_fatal(f"Phase 2 異常：{e}")
                sys.exit(1)
        else:
            print(f"⚠️  SFX 檔案無效，跳過 Phase 2，輸出純音樂...")
            try:
                import shutil
                shutil.move(str(temp_music_path), str(output_path))
            except Exception as e:
                _log_fatal(f"檔案搬運失敗: {e}")
                sys.exit(1)
    else:
        print(f"\n[PHASE 2] 跳過 SFX 疊加（未指定 SFX 檔案）")
        try:
            import shutil
            shutil.move(str(temp_music_path), str(output_path))
        except Exception as e:
            _log_fatal(f"檔案搬運失敗: {e}")
            sys.exit(1)
    
    # 清理臨時檔案
    try:
        temp_music_path.unlink(missing_ok=True)
    except:
        pass
    
    # 最後結果
    print("\n" + "=" * 80)
    print(f"✅  【完全完成】1 小時無縫 Lofi 音樂（v12.27 分段縫合架構）")
    print(f"    輸出檔案：{output_path}")
    print(f"    總長度：{output_duration / 60:.1f} 分鐘（{output_duration:.0f} 秒）")
    print(f"    使用曲目：{n} 首（含重複）")
    if sfx_path and Path(sfx_path).exists():
        print(f"    背景 SFX：{Path(sfx_path).name}（循環，4% 音量）")
    print("=" * 80)
    
    # 【CTO v9.0 時間軸任務】生成 Tracklist
    tracklist_content = _generate_tracklist(playlist, durations)
    _save_tracklist(tracklist_content, output_dir)
    
    return output_path
# ─────────────────────────────────────────────
#  CLI 入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="R&S Echoes 1 小時無縫縫合機 (lofi_assembler v2.0) + 頻道隔離"
    )
    # 【修復 1】新增 channel 參數，接收 pipeline_runner.py 傳來的 --channel 值
    parser.add_argument(
        "--channel",
        type=str,
        default="lofi",
        choices=["lofi", "light_music"],
        help="【修復 1】視覺頻道，用於對齊庫存目錄與資料庫標籤（lofi 或 light_music）",
    )
    parser.add_argument(
        "--vault",
        type=str,
        default=None,
        help="覆蓋預設 Vault 資料夾路徑（預設: assets/audio/vault_ready_for_mix/{channel}/）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="輸出檔案名稱（預設：R&S_Echoes_1HrMix_YYYYMMDD_HHMM.wav）",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=TARGET_DURATION_SEC,
        help=f"目標輸出秒數（預設: {TARGET_DURATION_SEC}）",
    )
    parser.add_argument(
        "--sfx",
        type=str,
        default=None,
        help="可選的環境音檔案路徑 (WAV/MP3/FLAC)，將以 4%% 音量疊加到混音中",
    )
    parser.add_argument(
        "--sfx-mode",
        type=str,
        choices=["transition", "global"],
        default="global",
        help="SFX 播放模式：transition (僅過場) 或 global (全程)",
    )
    parser.add_argument(
        "--max-derivation-limit",
        type=int,
        default=3,
        help="聽覺唯一上限：僅 derivation_count < N 入選曲池。預設 3 = Gen0/1/2（0/1/2 次衍生）；≥3 冷凍",
    )
    args = parser.parse_args()
    
    # 【修復 1】動態修正全局 VAULT_DIR，強制指向對應頻道的子目錄
    if args.vault:
        # 若使用者明確指定 --vault，則使用該路徑
        VAULT_DIR = Path(args.vault)
    else:
        # 【修復 1】精準路徑指向】根據 channel 參數動態設定 VAULT_DIR
        channel_lower = args.channel.lower()
        VAULT_DIR = config.workspace_root / "assets" / "audio" / "vault_ready_for_mix" / channel_lower
        
        # 驗證路徑是否存在
        if not VAULT_DIR.exists():
            print(f"[FATAL] Vault 目錄不存在: {VAULT_DIR}")
            print(f"【v12.23 路徑解析】頻道: {args.channel} → {channel_lower}")
            sys.exit(1)
        
        # 掃描母帶檔案計數
        wav_files = list(VAULT_DIR.glob("*.wav"))
        print(f"【v12.23 路徑解析】VAULT_DIR 已精準指向: {VAULT_DIR}")
        print(f"  頻道: {args.channel}")
        print(f"  母帶數: {len(wav_files)} 個")
        if not wav_files:
            print(f"[WARNING] Vault 目錄無 .wav 檔案，庫存為 0")
    
    # ✅ CTO 修復 3：徹底清理全域變數，改為區域變數傳入
    channel_lower = args.channel.lower()
    local_output_dir = config.workspace_root / "assets" / "final_exports" / channel_lower
    local_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"【頻道隔離 OUTPUT_DIR】已重定向至: {local_output_dir}")
    
    if args.target < 60:
        print("[FATAL] --target 至少需 60 秒")
        sys.exit(1)
    
    # 【修復 1 + v15.3】將 channel / output_dir / max_derivation_limit 傳遞給 assemble()
    result = assemble(output_name=args.output, target_sec=args.target, sfx_path=args.sfx, sfx_mode=args.sfx_mode,
                      channel=args.channel, output_dir=local_output_dir,
                      max_derivation_limit=args.max_derivation_limit)
    if result is None:
        print("[STATUS] 庫存為 0，混音已跳過。系統將觸發自動備援補充。")
        sys.exit(0)  # 安全退出，不視為失敗
