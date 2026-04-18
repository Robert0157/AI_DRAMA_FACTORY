#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【v15.0 視覺金庫管理器】scripts/gear2_rnd/visual_vault_db.py
獨立管理 Veo 影視資產，支援多頻道隔離與無重複隨機抽取
✅ Schema：video_id, file_path, channel, scene_tags, duration_sec, derivation_count, is_archived
✅ 功能：隨機抽取時確保連續兩個場景 scene_tags 不重複
✅ 路徑解析：依賴 env_manager.py 的 WORKSPACE_ROOT，嚴禁硬編碼
"""

import sqlite3
import json
import sys
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 【CTO 強制執行】確保腳本能找到專案根目錄
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import EnvConfig

config = EnvConfig()


class VisualVaultDB:
    """【v15.0】Veo 影視資產金庫 - SQLite 資料庫管理器
    
    支援：
    - 多頻道隔離 (lofi, light_music, 等)
    - 無重複隨機抽取 (scene_tags 防重複)
    - 衍生計數與歸檔協議
    """
    
    def __init__(self, db_path=None):
        """初始化資料庫連接
        
        Args:
            db_path: 資料庫文件路徑，默認為 veo_visual_vault.db
        """
        if db_path is None:
            self.db_path = config.visual_db_path
        else:
            self.db_path = Path(db_path)
        
        # 確保父目錄存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 建立資料庫連接
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        
        # 初始化資料庫結構
        self._initialize_database()
        
        print(f"✅ Visual Vault DB 初始化: {self.db_path}")
    
    def _initialize_database(self):
        """初始化全量資料表與索引"""
        cursor = self.conn.cursor()
        
        # 防護機制：WAL 模式
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous = FULL;")
        
        print(f"🛠️  正在初始化【v15.0 視覺金庫】Schema...")
        
        # 建立核心資料表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_assets (
                video_id TEXT PRIMARY KEY NOT NULL,
                channel TEXT DEFAULT 'lofi',              -- 頻道標籤（lofi, light_music）
                file_path TEXT NOT NULL,                  -- 完整檔案路徑
                scene_tags TEXT NOT NULL,                 -- JSON 格式場景標籤（用於防重複）
                duration_sec REAL NOT NULL,               -- 影片時長（秒）
                derivation_count INTEGER DEFAULT 0,       -- 衍生次數
                is_archived BOOLEAN DEFAULT 0,            -- 是否已歸檔
                metadata JSON,                            -- 額外 metadata (fps, resolution, 等)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 建立所有必要的索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_id ON video_assets(video_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_channel ON video_assets(channel)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_derivation_count ON video_assets(derivation_count)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_archived ON video_assets(is_archived)")
        
        # 建立借調記錄表（用於追蹤金庫借調）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS borrow_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                project_id TEXT NOT NULL,                 -- 關聯的多場景製作項目
                borrowed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES video_assets(video_id)
            )
        """)
        
        self.conn.commit()
        print("✅ Schema 初始化完成")
    
    def add_video(self, video_id: str, file_path: str, channel: str, scene_tags: List[str], 
                  duration_sec: float, metadata: Optional[Dict] = None) -> bool:
        """添加影視资产到資料庫
        
        Args:
            video_id: 唯一識別符（通常為檔名去副檔名）
            file_path: 完整檔案路徑
            channel: 頻道名稱 (lofi, light_music)
            scene_tags: 場景標籤列表 (e.g., ["water", "sunset"])
            duration_sec: 影片時長
            metadata: 額外 metadata 字典
        
        Returns:
            是否成功添加
        """
        try:
            cursor = self.conn.cursor()
            scene_tags_json = json.dumps(scene_tags)
            metadata_json = json.dumps(metadata) if metadata else "{}"
            
            cursor.execute("""
                INSERT OR REPLACE INTO video_assets 
                (video_id, channel, file_path, scene_tags, duration_sec, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (video_id, channel, file_path, scene_tags_json, duration_sec, metadata_json))
            
            self.conn.commit()
            print(f"  ✓ 添加影視資產: {video_id} ({channel})")
            return True
        except Exception as e:
            print(f"  ✗ 添加失敗 {video_id}: {e}")
            return False
    
    def get_random_videos(self, count: int, channel: str, avoid_scene_tags: Optional[List[str]] = None) -> List[Dict]:
        """隨機抽取指定數量的影視資產，確保場景標籤不連續重複
        
        Args:
            count: 抽取數量
            channel: 頻道名稱
            avoid_scene_tags: 上次抽取的場景標籤列表（用於防重複）
        
        Returns:
            資產字典列表
        """
        # 【CTO 熱修復 - 任務二】取出該頻道前先自動掃描，確保新增 .mp4 入庫
        scanned_count = self.auto_scan_vault(channel)
        if scanned_count > 0:
            print(f"  📍 自動掃描完成，新增 {scanned_count} 個視覺資產")
        
        try:
            cursor = self.conn.cursor()
            
            # 查詢該頻道的可用資產
            cursor.execute("""
                SELECT * FROM video_assets 
                WHERE channel = ? AND is_archived = 0
                ORDER BY RANDOM()
            """, (channel,))
            
            all_videos = cursor.fetchall()
            
            if not all_videos:
                print(f"⚠️  頻道 {channel} 中無可用影視資產")
                return []
            
            # 防重複邏輯：過濾掉與 avoid_scene_tags 重疊的資產
            selected = []
            avoid_tags_set = set(avoid_scene_tags) if avoid_scene_tags else set()
            
            for video_row in all_videos:
                if len(selected) >= count:
                    break
                
                scene_tags = json.loads(video_row['scene_tags'])
                scene_tags_set = set(scene_tags)
                
                # 如果沒有重疊，則納入
                if not (scene_tags_set & avoid_tags_set):
                    selected.append({
                        'video_id': video_row['video_id'],
                        'channel': video_row['channel'],
                        'file_path': video_row['file_path'],
                        'scene_tags': scene_tags,
                        'duration_sec': video_row['duration_sec'],
                        'derivation_count': video_row['derivation_count']
                    })
            
            if len(selected) < count:
                print(f"⚠️  頻道 {channel} 中只找到 {len(selected)} 個無重複資產（需求 {count} 個）")
            
            return selected
        
        except Exception as e:
            print(f"✗ 隨機抽取失敗: {e}")
            return []
    
    def get_pyramid_videos(self, channel: str, needed_count: int = 6, max_derivation_limit: int = 2) -> List[Dict]:
        """【v15.1 金字塔抽樣】50% 全新 + 25% 二手 + 25% 三手
        
        延遲扣款原則：此處只讀取，不修改 derivation_count。
        扣款由 Stage 3 在成片完成後統一執行。
        
        Args:
            channel: 頻道名稱
            needed_count: 需要的素材數量
            max_derivation_limit: 最大允許衍生次數（UI 控制）
        
        Returns:
            素材字典列表
        """
        # 先自動掃描入庫（與 get_random_videos 一致）
        scanned_count = self.auto_scan_vault(channel)
        if scanned_count > 0:
            print(f"  📍 自動掃描完成，新增 {scanned_count} 個視覺資產")
        
        quota_new = max(1, needed_count // 2)       # 50%
        quota_used1 = max(0, needed_count // 4)      # 25%
        quota_used2 = needed_count - quota_new - quota_used1  # 25%
        
        selected_videos = []
        selected_ids = set()
        
        def fetch_quota(target_count: int, derivation_level: int) -> List[Dict]:
            """從指定衍生層級中抽取素材"""
            fetched = []
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT * FROM video_assets 
                    WHERE channel = ? AND derivation_count = ? AND is_archived = 0 AND derivation_count <= ?
                    ORDER BY RANDOM()
                """, (channel, derivation_level, max_derivation_limit))
                
                for row in cursor.fetchall():
                    if len(fetched) >= target_count:
                        break
                    vid_id = row['video_id']
                    if vid_id in selected_ids:
                        continue
                    # 驗證物理檔案存在
                    if not Path(row['file_path']).exists():
                        continue
                    fetched.append({
                        'video_id': vid_id,
                        'channel': row['channel'],
                        'file_path': row['file_path'],
                        'scene_tags': json.loads(row['scene_tags']),
                        'duration_sec': row['duration_sec'],
                        'derivation_count': row['derivation_count']
                    })
                    selected_ids.add(vid_id)
            except Exception as e:
                print(f"  ⚠️ 金字塔抽樣 deriv={derivation_level} 查詢異常: {e}")
            return fetched
        
        # 依序滿足配額
        selected_videos.extend(fetch_quota(quota_new, 0))
        selected_videos.extend(fetch_quota(quota_used1, 1))
        selected_videos.extend(fetch_quota(quota_used2, 2))
        
        # Fallback: 若二手/三手庫存不足，用全新素材補齊
        if len(selected_videos) < needed_count:
            shortage = needed_count - len(selected_videos)
            selected_videos.extend(fetch_quota(shortage, 0))
        
        # 第二層 Fallback: 若全新也不夠，放寬到任意 deriv 層級（仍受 max_derivation_limit 約束）
        if len(selected_videos) < needed_count:
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT * FROM video_assets 
                    WHERE channel = ? AND is_archived = 0 AND derivation_count <= ?
                    ORDER BY derivation_count ASC, RANDOM()
                """, (channel, max_derivation_limit))
                for row in cursor.fetchall():
                    if len(selected_videos) >= needed_count:
                        break
                    if row['video_id'] in selected_ids:
                        continue
                    if not Path(row['file_path']).exists():
                        continue
                    selected_videos.append({
                        'video_id': row['video_id'],
                        'channel': row['channel'],
                        'file_path': row['file_path'],
                        'scene_tags': json.loads(row['scene_tags']),
                        'duration_sec': row['duration_sec'],
                        'derivation_count': row['derivation_count']
                    })
                    selected_ids.add(row['video_id'])
            except Exception as e:
                print(f"  ⚠️ 金字塔 Fallback 查詢異常: {e}")

        # 【v15.3 修復】第三層 Fallback：完全拿掉衍生次數限制，補滿剩餘名額
        # 觸發條件：視覺金庫在 max_derivation_limit 範圍內的唯一素材已耗盡
        if len(selected_videos) < needed_count:
            print(f"  ⚠️ [第三層 Fallback] 衍生上限內素材不足，放寬至無限次數補位（金庫擴充警告）")
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT * FROM video_assets
                    WHERE channel = ? AND is_archived = 0
                    ORDER BY derivation_count ASC, RANDOM()
                """, (channel,))
                for row in cursor.fetchall():
                    if len(selected_videos) >= needed_count:
                        break
                    if row['video_id'] in selected_ids:
                        continue
                    if not Path(row['file_path']).exists():
                        continue
                    selected_videos.append({
                        'video_id': row['video_id'],
                        'channel': row['channel'],
                        'file_path': row['file_path'],
                        'scene_tags': json.loads(row['scene_tags']),
                        'duration_sec': row['duration_sec'],
                        'derivation_count': row['derivation_count']
                    })
                    selected_ids.add(row['video_id'])
            except Exception as e:
                print(f"  ⚠️ 金字塔 第三層 Fallback 查詢異常: {e}")

        # 打亂順序避免固定排列
        random.shuffle(selected_videos)
        
        print(f"  🔺 金字塔抽樣結果: {len(selected_videos)}/{needed_count} "
              f"(new={sum(1 for v in selected_videos if v['derivation_count']==0)}, "
              f"used1={sum(1 for v in selected_videos if v['derivation_count']==1)}, "
              f"used2={sum(1 for v in selected_videos if v['derivation_count']==2)}, "
              f"other={sum(1 for v in selected_videos if v['derivation_count']>=3)})")
        
        return selected_videos

    def reset_derivation_counts(self, channel: Optional[str] = None) -> int:
        """將指定頻道（或全頻道）所有資產的 derivation_count 歸零
        Args:
            channel: 頻道名稱（None = 全頻道）
        Returns:
            受影響的資產數
        """
        try:
            cursor = self.conn.cursor()
            if channel:
                cursor.execute("""
                    UPDATE video_assets SET derivation_count = 0, updated_at = CURRENT_TIMESTAMP WHERE channel = ?
                """, (channel,))
                affected = cursor.rowcount
            else:
                cursor.execute("""
                    UPDATE video_assets SET derivation_count = 0, updated_at = CURRENT_TIMESTAMP
                """)
                affected = cursor.rowcount
            self.conn.commit()
            print(f"✅ 已重置 {affected} 筆資產的 derivation_count (channel={channel})")
            return affected
        except Exception as e:
            print(f"❌ 重置 derivation_count 失敗: {e}")
            return 0
    
    def increment_derivation_count(self, video_id: str) -> bool:
        """增加影視資產的衍生計數
        
        Args:
            video_id: 影視資產 ID
        
        Returns:
            是否成功
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE video_assets 
                SET derivation_count = derivation_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE video_id = ?
            """, (video_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"✗ 增加衍生計數失敗 {video_id}: {e}")
            return False
    
    def auto_scan_vault(self, channel: str) -> int:
        """自動掃描對應頻道目錄，將新發現的 .mp4 文件入庫
        
        Args:
            channel: 頻道名稱 (lofi, light_music)
        
        Returns:
            新增的資產數量
        """
        try:
            vault_dir = config.workspace_root / "assets" / "video_clips" / "vault" / channel
            
            if not vault_dir.exists():
                print(f"⚠️  金庫目錄不存在: {vault_dir}")
                return 0
            
            cursor = self.conn.cursor()
            added_count = 0
            
            for mp4_file in vault_dir.glob("*.mp4"):
                video_id = mp4_file.stem
                
                # 檢查是否已存在
                cursor.execute("SELECT COUNT(*) FROM video_assets WHERE video_id = ?", (video_id,))
                if cursor.fetchone()[0] > 0:
                    continue
                
                # 讀取基本元數據
                # 注意：實際應使用 ffprobe 讀取精確時長，這裡簡化為預設值
                duration_sec = 10.0  # 預設 10 秒，實際應調用 ffprobe
                scene_tags = [channel]  # 基本標籤
                
                self.add_video(
                    video_id=video_id,
                    file_path=str(mp4_file),
                    channel=channel,
                    scene_tags=scene_tags,
                    duration_sec=duration_sec
                )
                added_count += 1
            
            print(f"✅ 頻道 {channel} 自動掃描完成，新增 {added_count} 個資產")
            return added_count
        
        except Exception as e:
            print(f"✗ 自動掃描失敗: {e}")
            return 0
    
    def list_videos_by_channel(self, channel: str) -> List[Dict]:
        """列出指定頻道的所有影視資產
        
        Args:
            channel: 頻道名稱
        
        Returns:
            資產列表
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM video_assets 
                WHERE channel = ? AND is_archived = 0
                ORDER BY created_at DESC
            """, (channel,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'video_id': row['video_id'],
                    'file_path': row['file_path'],
                    'scene_tags': json.loads(row['scene_tags']),
                    'duration_sec': row['duration_sec'],
                    'derivation_count': row['derivation_count']
                })
            
            return results
        
        except Exception as e:
            print(f"✗ 列表查詢失敗: {e}")
            return []
    
    def cleanup_orphaned_records(self, channel: Optional[str] = None) -> int:
        """【資料庫淨化】刪除指向不存在物理文件的所有孤立記錄
        
        Args:
            channel: 指定頻道 (None = 全頻道)
        
        Returns:
            刪除的記錄數
        """
        try:
            cursor = self.conn.cursor()
            
            if channel:
                cursor.execute(
                    "SELECT * FROM video_assets WHERE channel = ? AND is_archived = 0",
                    (channel,)
                )
                scope = f"頻道 {channel}"
            else:
                cursor.execute("SELECT * FROM video_assets WHERE is_archived = 0")
                scope = "全頻道"
            
            orphaned_records = cursor.fetchall()
            orphaned_count = 0
            
            for row in orphaned_records:
                file_path = Path(row['file_path'])
                if not file_path.exists():
                    cursor.execute("DELETE FROM video_assets WHERE video_id = ?", (row['video_id'],))
                    orphaned_count += 1
                    print(f"  🗑️  已刪除孤立記錄: {row['video_id']} ({file_path})")
            
            self.conn.commit()
            print(f"\n✅ {scope} 資料庫淨化完成，共移除 {orphaned_count} 個孤立記錄")
            return orphaned_count
        
        except Exception as e:
            print(f"❌ 資料庫淨化失敗: {e}")
            return 0
    
    def close(self):
        """關閉資料庫連接"""
        if self.conn:
            self.conn.close()


# ─────────────────────────────────────────────────────────────
# 【CLI 測試介面】
# ─────────────────────────────────────────────────────────────

# ====== 【測試代碼已閹割】下列代碼僅供歷史參考，已完全禁用 ======
# if __name__ == "__main__":
#     # 初始化資料庫
#     vault = VisualVaultDB()
#     
#     # 測試：添加樣本影視資產（已禁用 - 防止重複污染資料庫）
#     # print("\n【測試一】添加樣本資產...")
#     # vault.add_video(
#     #     video_id="lofi_water_01",
#     #     file_path=str(config.workspace_root / "assets/video_clips/vault/lofi/water_01.mp4"),
#     #     channel="lofi",
#     #     scene_tags=["water", "flow"],
#     #     duration_sec=10.0
#     # )
#     # vault.add_video(
#     #     video_id="lofi_sunset_01",
#     #     file_path=str(config.workspace_root / "assets/video_clips/vault/lofi/sunset_01.mp4"),
#     #     channel="lofi",
#     #     scene_tags=["sunset", "sky"],
#     #     duration_sec=10.0
#     # )
#     
#     # 測試：隨機抽取
#     # print("\n【測試二】隨機抽取...")
#     # videos = vault.get_random_videos(2, "lofi")
#     # for v in videos:
#     #     print(f"  - {v['video_id']}: {v['scene_tags']}")
#     
#     # 測試：自動掃描
#     # print("\n【測試三】自動掃描 v15_sandbox...")
#     # sandbox_dir = config.workspace_root / "assets/video_clips/v15_sandbox"
#     # 注意：實際測試需先在 v15_sandbox 中放入 .mp4 文件
#     
#     # print("\n✅ Visual Vault DB 初始化完成")
#     # vault.close()
# ====== 測試代碼結尾 ======
