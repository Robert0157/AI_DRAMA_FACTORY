#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【v15.9】UI 非同步後端引擎（新鮮度鐵律儀表與 pipeline_runner Phase 4.6 對齊）
"""
import atexit
import datetime
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────
# 路徑強制校準
# ─────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.common.long_queue_sidecar_v1 import (
    build_long_upload_sidecar_v1,
    validate_long_upload_v1,
)
from scripts.common.youtube_longform_tags import merge_longform_tags
from scripts.common.tracklist_pick import pick_tracklist_txt_for_mp4
from scripts.common.youtube_cheatsheet_builder import generate_youtube_cheatsheet_file, glob_youtube_sheet_paths
from scripts.gear1_prod.music_metadata_engine import (
    compose_light_music_youtube_seo,
    compose_lofi_youtube_seo,
)
from scripts.gear2_rnd.vault_database import VaultDatabase
from scripts.common.ui_audit_logger import get_audit_logger  # v15.11 P3#13

# Mac mini 端預期路徑（相對於 Mac 上 Streaming 專案根目錄，供 CEO／Mac 工程對齊）
MAC_MINI_UPLOAD_LOG_REL = "Streaming/logs/long_video_upload.log"
MAC_MINI_VIDEO_ID_TRACK_REL = "Streaming/logs/long_video_video_ids.json"


def _merge_distrokid_with_stem_metadata(
    metadata: Dict, export_dir: Path, mp4_stem: str
) -> Dict:
    """
    以「與本次長片 MP4 同檔名 stem」之 *_metadata_distrokid.json 覆寫通用 metadata。

    RCA：若僅讀 metadata_distrokid_{channel}.json，track_list / youtube_seo_description 常為
    上一版企劃或 LLM 均分表；產線另寫入 R&S_Echoes_*_{run}_metadata_distrokid.json，內容才與該支
    1hr 母帶／Tracklist 一致。發行投遞 Long_Queue 須以 stem 檔為準覆寫後再寫 SMB。
    """
    stem_path = export_dir / f"{mp4_stem}_metadata_distrokid.json"
    if not stem_path.is_file():
        return metadata
    try:
        with open(stem_path, "r", encoding="utf-8") as f:
            stem = json.load(f)
    except (OSError, json.JSONDecodeError):
        return metadata
    if not isinstance(stem, dict):
        return metadata
    out = dict(metadata)
    out.update(stem)
    return out


class UIBackend:
    def _run_shorts_audio_cleanup(self, channel: Optional[str] = None) -> Tuple[bool, str]:
        """在發行前執行高使用次數歌曲整理（遷移/刪除）。"""
        ch = str(channel or self.current_channel).strip().lower()
        script_path = Path(self.config.workspace_root) / "scripts" / "gear1_prod" / "cloud_archiver.py"
        if not script_path.exists():
            return False, f"找不到整理腳本：{script_path}"
        cmd = [
            sys.executable,
            str(script_path),
            "--channel",
            ch,
            "--execute",
            "--max-actions",
            "20",
            "--log-path",
            str(Path(self.config.workspace_root) / "assets" / ".logs" / "shorts_audio_cleanup.log"),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
            if proc.returncode == 0:
                return True, f"Shorts 音檔整理已執行（channel={ch}）"
            err = (proc.stderr or proc.stdout or "").strip()
            return False, f"Shorts 音檔整理失敗（Exit {proc.returncode}）：{err[:300]}"
        except Exception as e:
            return False, f"Shorts 音檔整理異常：{e}"

    def _write_publish_status_json(
        self, check_res: dict, channel: Optional[str] = None
    ) -> None:
        """將目前檢查結果即時寫入 publish_status.json（原子寫入）。"""
        ch = str(channel or self.current_channel).strip().lower()
        export_dir = self._export_dir_for_channel(ch)
        status_path = export_dir / "publish_status.json"
        data = {
            "ok": bool(check_res.get("all_passed")),
            "msg": (
                "發行前檢查通過"
                if check_res.get("all_passed")
                else f"發行前檢查未通過：{', '.join(check_res.get('status', {}).get('missing_list', []))}"
            ),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "channel": ch,
        }
        try:
            export_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = status_path.with_name(status_path.name + ".tmp")
            tmp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(status_path)
        except Exception:
            # 預檢本身不應因狀態檔寫入失敗而拋錯，避免 UI 被中斷。
            pass

    def _export_dir_for_channel(self, channel: Optional[str]) -> Path:
        """與 get_channel_export_dir 相同規則，但可指定頻道（不變更 self.current_channel）。"""
        ch = str(channel or self.current_channel).strip().lower()
        primary = Path(self.config.workspace_root) / "assets" / "final_exports" / ch
        if primary.exists():
            return primary
        return _PROJECT_ROOT / "assets" / "final_exports" / ch

    def verify_export_files(self, channel: Optional[str] = None) -> dict:
        """自動檢驗 4 大核心發行檔案是否齊全（metadata、DistroKid Sheet、youtube_sheet、長片 MP4）。"""
        ch = str(channel or self.current_channel).strip().lower()
        export_dir = self._export_dir_for_channel(ch)
        status: Dict[str, List[str]] = {"missing_list": []}

        if not export_dir.exists():
            status["missing_list"].append(f"產出資料夾不存在: {export_dir.name}")
            check_result = {"all_passed": False, "status": status}
            self._write_publish_status_json(check_result, ch)
            return check_result

        if not (
            list(export_dir.glob(f"metadata_distrokid_{ch}.json"))
            or list(export_dir.glob("metadata_distrokid*.json"))
        ):
            status["missing_list"].append(f"metadata_distrokid_{ch}.json")

        if not list(export_dir.glob("DistroKid_Sheet_*.txt")):
            status["missing_list"].append("DistroKid_Sheet_*.txt")

        if not glob_youtube_sheet_paths(export_dir):
            status["missing_list"].append("youtube_sheet_*.txt")

        if not list(export_dir.glob("*.mp4")):
            status["missing_list"].append("*.mp4 (1小時長片)")

        check_result = {"all_passed": len(status["missing_list"]) == 0, "status": status}
        self._write_publish_status_json(check_result, ch)
        return check_result

    @staticmethod
    def _check_smb_access(max_retries: int = 2) -> bool:
        """v15.10: SMB 連線 + 寫入權限驗證，含指數退避重試"""
        import time
        for attempt in range(max_retries + 1):
            try:
                # v15.10 P3#15: 改用 config.smb_shorts_root 避免磁碟代號硬編碼
                test_file = config.smb_shorts_root / ".smb_rw_test"
                test_file.write_text("ok")
                test_file.unlink()
                return True
            except Exception:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
        return False

    def publish_final_exports(self, channel: Optional[str] = None, mode: str = "auto") -> dict:
        """
        發行產出與 SMB 邊車傳輸 (Sidecar Pattern)
        mode="auto"：Sidecar 標示 Mac 端可自動上傳
        mode="manual"：Sidecar 標示僅備份／手動上傳
        傳輸順序：先完整複製 MP4 → 原子寫入 `{stem}.json` 邊車（Mac 上傳觸發信號）。

        `{stem}_metadata_distrokid.json` **僅保留於 Windows** `final_exports`（含 stem 覆寫後之企劃書），
        **不**複製至 Y:/Long_Queue — Mac 端以上傳邊車內嵌之 title/description/tags 為準。
        """
        ch = str(channel or self.current_channel).strip().lower()
        export_dir = self._export_dir_for_channel(ch)
        result: Dict = {
            "ok": False,
            "msg": "",
            "cleaned_metadata": None,
            "cheatsheet": None,
            "video_path": None,
            "log": "",
            "mac_mini_upload_log": None,
            "mac_mini_video_id_track": None,
        }

        if mode not in ("auto", "manual"):
            result["msg"] = f"未知 mode: {mode}（僅支援 auto / manual）"
            return result

        # v15.10: 驗證有效頻道
        if ch not in ("lofi", "light_music"):
            result["msg"] = f"無效頻道: {ch}"
            return result

        cleanup_ok, cleanup_msg = self._run_shorts_audio_cleanup(ch)
        if not cleanup_ok:
            result["msg"] = cleanup_msg
            return result

        check = self.verify_export_files(ch)
        if not check["all_passed"]:
            missing = "；".join(check["status"]["missing_list"])
            result["msg"] = f"發行前檢查未通過：{missing}"
            return result

        mp4s = sorted(export_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        if not mp4s:
            result["msg"] = "找不到 MP4 影片檔案進行傳輸"
            return result
        vid_src = mp4s[-1]

        meta_path = export_dir / f"metadata_distrokid_{ch}.json"
        if not meta_path.exists():
            # v15.10: 優先頻道限定 glob，避免跨頻道混淆
            fallback = list(export_dir.glob(f"metadata_distrokid_{ch}_*.json"))
            if not fallback:
                fallback = list(export_dir.glob(f"metadata_distrokid_{ch}*.json"))
            if not fallback:
                fallback = list(export_dir.glob("metadata_distrokid*.json"))
            if fallback:
                meta_path = sorted(fallback, key=lambda p: p.stat().st_mtime)[-1]
            else:
                result["msg"] = f"找不到 metadata_distrokid_{ch}.json"
                return result
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            result["msg"] = f"讀取 metadata 失敗: {e}"
            return result

        metadata = _merge_distrokid_with_stem_metadata(metadata, export_dir, vid_src.stem)

        def remove_shorts_tags(tags):
            if isinstance(tags, str):
                raw = [t.strip() for t in re.split(r"[#,]", tags) if t.strip()]
            elif isinstance(tags, list):
                raw = [str(t).strip() for t in tags if str(t).strip()]
            else:
                raw = []
            shorts_pattern = re.compile(r"shorts?", re.IGNORECASE)
            return [t for t in raw if not shorts_pattern.search(t)]

        for key in ("tags", "hashtags", "youtube_tags", "yt_tags"):
            if key in metadata:
                tags = metadata[key]
                filtered = remove_shorts_tags(tags)
                metadata[key] = filtered if isinstance(tags, list) else ", ".join(filtered)

        cheatsheet = None
        cs_files = glob_youtube_sheet_paths(export_dir)
        if cs_files:
            cheatsheet = cs_files[-1].read_text(encoding="utf-8")

        video_path = str(vid_src)
        master_tracklist_text: Optional[str] = None
        tl_for_sidecar = pick_tracklist_txt_for_mp4(export_dir, vid_src)
        if tl_for_sidecar and tl_for_sidecar.is_file():
            try:
                master_tracklist_text = tl_for_sidecar.read_text(encoding="utf-8")
            except OSError:
                master_tracklist_text = None

        # v15.10: SMB 連線檢查含寫入權限驗證 + 重試
        if not self._check_smb_access():
            result["msg"] = "⚠️ SMB 連線中斷或無寫入權限：請確認已掛載 Mac mini 磁碟機為 Y 槽"
            return result

        smb_target_dir = self.config.smb_long_queue / ch
        try:
            smb_target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            if not self._check_smb_access():
                result["msg"] = "⚠️ SMB 連線中斷：請確認已掛載 Mac mini 磁碟機為 Y 槽"
            else:
                result["msg"] = f"無法存取 Mac mini 彈藥庫 ({smb_target_dir})，請確認網路與 SMB 連線: {e}"
            return result

        vid_dst = smb_target_dir / vid_src.name

        tags_list = merge_longform_tags(ch, metadata.get("tags", []))
        tags_list = remove_shorts_tags(tags_list)

        title_for_upload = (
            metadata.get("title")
            or metadata.get("album_title")
            or f"R&S Echoes {ch.upper()} Mix"
        )
        # 長片 Sidecar：YouTube description 須為「上架 SEO 正文」（與 metadata_engine 之 compose_* 一致），
        # 不可使用整份 youtube_sheet（含企劃書表頭／重複標題），以免與實際上線文案不符。
        tl_for_desc = metadata.get("track_list") or []
        if not isinstance(tl_for_desc, list):
            tl_for_desc = []
        album_for_desc = str(metadata.get("album_title", "") or "").strip()

        stem_meta_path = export_dir / f"{vid_src.stem}_metadata_distrokid.json"
        has_stem_meta = stem_meta_path.is_file()

        if ch == "light_music":
            # 優先採用「同 stem」metadata 內已對齊母帶的 youtube_seo_description（產線寫入之檔）。
            pref = str(metadata.get("youtube_seo_description", "") or "").strip()
            if has_stem_meta and pref and "【⏱️ TRACKLIST】" in pref:
                desc_for_upload = pref
            else:
                desc_for_upload = compose_light_music_youtube_seo(
                    album_for_desc or str(title_for_upload).strip(),
                    [str(x).strip() for x in tl_for_desc if str(x).strip()],
                    master_tracklist_file_text=master_tracklist_text,
                )
            metadata["youtube_seo_description"] = desc_for_upload
        elif ch == "lofi":
            pref = str(metadata.get("youtube_seo_description", "") or "").strip()
            if has_stem_meta and pref and "【⏱️ TRACKLIST】" in pref:
                desc_for_upload = pref
            else:
                desc_for_upload = compose_lofi_youtube_seo(
                    album_for_desc or str(title_for_upload).strip(),
                    [str(x).strip() for x in tl_for_desc if str(x).strip()],
                    master_tracklist_file_text=master_tracklist_text,
                )
            metadata["youtube_seo_description"] = desc_for_upload
        else:
            desc_for_upload = cheatsheet if cheatsheet else metadata.get("description", "")
        mode_auto = mode == "auto"
        privacy = "public" if mode_auto else "unlisted"

        yt_meta = build_long_upload_sidecar_v1(
            mp4_filename=vid_src.name,
            title=str(title_for_upload).strip(),
            description=desc_for_upload if isinstance(desc_for_upload, str) else "",
            tags=tags_list,
            privacy=privacy,
            category_id="10",
            mode_auto=mode_auto,
            # YouTube：變造／合成內容必須申報「是」；本專案一律為 true（不受 metadata 覆寫）
            contains_synthetic_media=True,
            # 非兒童導向（非「兒童專屬」影片）
            self_declared_made_for_kids=False,
            playlist_id=metadata.get("playlistId") or metadata.get("youtube_playlist_id"),
        )

        ok_sidecar, sidecar_err = validate_long_upload_v1(yt_meta, vid_src.name)
        if not ok_sidecar:
            result["msg"] = f"Sidecar preflight 失敗（已中止投遞，未寫入 Long_Queue/{ch}）：{sidecar_err}"
            return result

        try:
            shutil.copy2(vid_src, vid_dst)

            sidecar_path = smb_target_dir / f"{vid_src.stem}.json"
            tmp_path = sidecar_path.with_name(sidecar_path.name + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(yt_meta, f, ensure_ascii=False, indent=2)
            tmp_path.replace(sidecar_path)

            # 與 Mac 端同源：在 Windows export 目錄保留一份邊車，避免僅 SMB 有 truth、本地檔過期。
            local_sidecar = export_dir / f"{vid_src.stem}.json"
            tmp_local = local_sidecar.with_name(local_sidecar.name + ".tmp")
            with open(tmp_local, "w", encoding="utf-8") as f:
                json.dump(yt_meta, f, ensure_ascii=False, indent=2)
            tmp_local.replace(local_sidecar)
        except Exception as e:
            try:
                if vid_dst.exists():
                    vid_dst.unlink()
            except OSError:
                pass
            if not Path("Y:/").exists():
                result["msg"] = "⚠️ SMB 連線中斷：請確認已掛載 Mac mini 磁碟機為 Y 槽"
            else:
                result["msg"] = f"SMB 傳輸失敗: {e}"
            return result

        mode_text = "自動" if mode == "auto" else "人工"
        result.update(
            {
                "ok": True,
                "msg": (
                    f"✅ {mode_text}發行指令已下達！已傳送 MP4 與上傳邊車（{vid_src.stem}.json）至 Mac mini ({smb_target_dir})。"
                    f"（metadata 僅留在本機 final_exports，不投遞 *_metadata_distrokid.json。）"
                ),
                "cleaned_metadata": metadata,
                "cheatsheet": cheatsheet,
                "video_path": str(vid_dst),
                "mac_long_queue_metadata_path": None,
                "log": f"{cleanup_msg}；已成功推播 {vid_src.name} 與邊車至 Mac 暫存倉",
                "mac_mini_upload_log": MAC_MINI_UPLOAD_LOG_REL,
                "mac_mini_video_id_track": MAC_MINI_VIDEO_ID_TRACK_REL,
            }
        )
        # v15.11 P3#13：審計日誌
        get_audit_logger().log(
            action="publish_final_exports",
            channel=ch,
            result="success",
            params={"mode": mode, "video": vid_src.name},
        )
        return result
    def run_shorts_pool_with_log(self, batch_size: int = 30, channel: str = "lofi", sub_style: str | None = None) -> Tuple[bool, str, str]:
        """
        以即時 log 方式執行 generate_shorts_pool.py，供 UI 顯示產線日誌。
        v15.11: 傳遞 --channel + --sub-style 以寫入 shorts_meta_pool_{channel}_{style}.json
        """
        root = Path(self.config.workspace_root)
        script_path = root / "scripts" / "marketing" / "generate_shorts_pool.py"
        if not script_path.exists():
            return False, f"找不到腳本：{script_path}", ""
        cmd = [sys.executable, str(script_path), str(batch_size), "--channel", str(channel).lower()]
        if sub_style:
            cmd.extend(["--sub-style", str(sub_style).lower()])
        returncode, log_path = self._run_with_log("shorts_pool", cmd)
        tail = self.get_latest_log_lines(log_path, 30)
        if returncode == 0:
            return True, "Shorts 雙語標題彈藥庫生成完成", log_path
        fatal = self._extract_fatal(tail)
        return False, f"Shorts 彈藥庫生成失敗 (Exit {returncode})\n{fatal}", log_path
    def __init__(self):
        self.config = config
        self.current_channel = "lofi"
        self.db = VaultDatabase()
        self._job_lock = threading.Lock()
        self._bg: Dict = {"state": "idle", "label": "", "result": None}

        # ── 殭屍行程防護 ────────────────────────────────────────────
        # 追蹤所有由 _run_with_log 啟動的 Popen 子程序，
        # 確保 Streamlit 意外終止時能透過 atexit 清理孤兒程序。
        self._proc_lock   = threading.Lock()
        self._active_procs: List[subprocess.Popen] = []
        self._active_log_path: Optional[str] = None
        self._last_completed_log_path: Optional[str] = None  # 任務完成後持久保留，供 Tab2 顯示完整結果
        atexit.register(self._cleanup_procs)

    def set_channel(self, channel: str):
        self.current_channel = str(channel).strip()

    def get_freshness_quota_report(self, target_tracks: int = 20, *, quiet: bool = True) -> Dict:
        """【v15.9】與 `pipeline_runner._check_freshness_quota` 相同邏輯，供 Tab1 儀表卡。"""
        from scripts.gear1_prod.pipeline_runner import _check_freshness_quota

        return _check_freshness_quota(
            channel=self.current_channel,
            target_tracks=target_tracks,
            quiet=quiet,
        )

    def freshness_gate_blocks_full_pipeline(
        self, *, ttapi_fill_fresh: bool, target_tracks: int = 20
    ) -> Tuple[bool, Dict]:
        """
        strict + 新鮮度啟用 + 未達標 且未允許 TTAPI 補彈時，應鎖定「CEO 全自動產線」按鈕。
        回傳 (should_block, report)。
        """
        r = self.get_freshness_quota_report(target_tracks=target_tracks, quiet=True)
        if not r.get("enabled", True):
            return False, r
        if r.get("passed", True):
            return False, r
        if str(r.get("enforcement", "strict")).lower() == "warn":
            return False, r
        if ttapi_fill_fresh:
            return False, r
        return True, r

    def get_channel_info(self) -> dict:
        ch = self.current_channel
        return {
            "channel": ch,
            "display_name": "🌙 Lofi 模式" if ch == "lofi" else "☀️ Light Music 模式",
            "icon": "🌙" if ch == "lofi" else "☀️"
        }

    def get_channel_export_dir(self) -> Path:
        """取得當前頻道的最終匯出目錄（統一路徑來源）"""
        primary = Path(self.config.workspace_root) / "assets" / "final_exports" / self.current_channel
        if primary.exists():
            return primary
        fallback = _PROJECT_ROOT / "assets" / "final_exports" / self.current_channel
        return fallback

    def get_master_tapes(self) -> List[str]:
        """【CTO 核心修復】強化路徑防禦，確保 Windows 環境下 100% 掃描檔案"""
        base_path = self.get_channel_export_dir()
        if not base_path.exists():
            return []
            
        # 掃描 WAV 檔案並按修改時間排序
        files = sorted(base_path.glob("*.wav"), key=lambda x: x.stat().st_mtime, reverse=True)
        return [f.name for f in files]

    def resolve_master_tape_path(self, tape_name: str) -> Path:
        """依照掃描目錄解析母帶檔案絕對路徑"""
        return self.get_channel_export_dir() / tape_name

    # ─────────────────────────────────────────────────────────────
    # 日誌目錄管理
    # ─────────────────────────────────────────────────────────────
    def _get_log_dir(self) -> Path:
        d = Path(self.config.workspace_root) / "assets" / ".logs"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"建立 log 目錄失敗: {d}，錯誤: {e}")
        return d

    def get_latest_log_lines(self, log_path: str, n: int = 80) -> str:
        """讀取最後 n 行日誌供 UI 顯示。"""
        p = Path(log_path)
        if not p.exists():
            return "(日誌檔案不存在)"
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-n:])
        except Exception as e:
            return f"(讀取日誌失敗: {e})"

    def run_pipeline_proxy(self, script_name: str, args: List[str] = None) -> Tuple[bool, str]:
        """同步執行（僅一次），stdout/stderr 即時寫入 .logs/。"""
        script_path = Path(self.config.workspace_root) / "scripts" / "gear1_prod" / script_name
        if not script_path.exists():
            return False, f"找不到腳本：{script_path}"
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)
        returncode, log_path = self._run_with_log(script_name, cmd)
        if returncode == 0:
            return True, f"{script_name} 執行成功 | 日誌：{log_path}"
        tail = self.get_latest_log_lines(log_path, 48)
        err = self._extract_fatal(tail)
        return False, f"{script_name} 失敗 (Exit {returncode})\n{err}\n日誌：{log_path}"

    def _run_with_log(self, label: str, cmd: List[str]) -> Tuple[int, str]:
        """以 Popen 執行並持續寫入日誌，回傳 (returncode, log_path)。
        【v15.3 殭屍行程防護】追蹤 Popen 物件，確保 atexit 能清理孤兒程序。
        【v15.3 即時日誌】更新 _active_log_path 讓 UI 可即時讀取進度。
        【v15.3 緩衝修復】PYTHONUNBUFFERED=1 強制子程序 stdout 即時寫入 log 檔，
        解決 Python block-buffer 導致 log 長期為 0 bytes 的問題。
        """
        import datetime, os
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", label)
        log_path = self._get_log_dir() / f"{safe}_{ts}.log"

        # 強制子程序使用無緩衝輸出（等同於 python -u）
        unbuf_env = os.environ.copy()
        unbuf_env["PYTHONUNBUFFERED"] = "1"

        try:
            with open(log_path, "w", encoding="utf-8") as lf:
                proc = subprocess.Popen(
                    cmd, stdout=lf, stderr=subprocess.STDOUT,
                    text=True, shell=False, env=unbuf_env
                )
                with self._proc_lock:
                    self._active_procs.append(proc)
                    self._active_log_path = str(log_path)
                try:
                    returncode = proc.wait()
                finally:
                    with self._proc_lock:
                        if proc in self._active_procs:
                            self._active_procs.remove(proc)
                        if not self._active_procs:
                            self._last_completed_log_path = str(log_path)  # 完成後先記錄再清空
                            self._active_log_path = None
            return returncode, str(log_path)
        except Exception:
            return -1, str(log_path)

    def _cleanup_procs(self) -> None:
        """atexit 保險機制：強制終止所有仍在執行的子程序，防止殭屍行程。"""
        with self._proc_lock:
            for proc in list(self._active_procs):
                try:
                    if proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            self._active_procs.clear()
            self._active_log_path = None

    def get_active_log_path(self) -> Optional[str]:
        """回傳當前執行中子程序的日誌路徑；無背景任務時回傳 None。
        供 UI 即時讀取進度（每次 rerun 呼叫 get_latest_log_lines）。
        """
        with self._proc_lock:
            return self._active_log_path

    def get_last_completed_log_path(self) -> Optional[str]:
        """回傳最後一次完成任務的日誌路徑（任務結束後仍保留）。
        供 Tab2 供彈區塊在任務完成後顯示完整結果 log。
        """
        with self._proc_lock:
            return self._last_completed_log_path

    def run_pipeline_with_log(self, script_name: str, args: List[str] = None) -> Tuple[bool, str, str]:
        """Popen 版（白皮書規範）：stdout/stderr 即時寫入日誌，回傳 (ok, msg, log_path)。"""
        script_path = Path(self.config.workspace_root) / "scripts" / "gear1_prod" / script_name
        if not script_path.exists():
            return False, f"找不到腳本：{script_path}", ""
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)
        returncode, log_path = self._run_with_log(script_name, cmd)
        tail = self.get_latest_log_lines(log_path, 30)
        if returncode == 0:
            return True, f"{script_name} 完成", log_path
        fatal = self._extract_fatal(tail)
        return False, f"{script_name} 失敗 (Exit {returncode})\n{fatal}", log_path

    @staticmethod
    def _extract_fatal(text: str) -> str:
        """從輸出中摘取 FATAL / Error / 失敗 等關鍵行（最多 20 行），降低噪音。"""
        lines = text.splitlines()
        keywords = ("fatal", "error", "失敗", "exception", "traceback", "exit", "critical")
        key_lines = [l for l in lines if any(k in l.lower() for k in keywords)]
        if key_lines:
            return "\n".join(key_lines[-20:])
        return "\n".join(lines[-20:])

    def run_mastering_only(self) -> Tuple[bool, str, str]:
        """Tab3：僅執行 Phase 1+2（母帶壓制），跳過 assembler / metadata / backup / publish。"""
        # v15.10: 加入 --skip-publish，因僅母帶模式無 MP4 產出
        return self.run_pipeline_with_log(
            "pipeline_runner.py",
            ["--channel", self.current_channel,
             "--skip-assembler", "--skip-metadata", "--skip-backup",
             "--skip-publish"],
        )

    def get_final_exports(self) -> Dict:
        """回傳 final_exports/{channel} 下所有可交付成品的清單及概覽。"""
        d = self.get_channel_export_dir()
        if not d.exists():
            return {"wav": [], "mp4": [], "tracklist": [], "yt_cheatsheet": [],
                    "dk_cheatsheet": [], "dk_upload_csv": [], "metadata": [], "dir": str(d)}
        return {
            "wav":          sorted([f.name for f in d.glob("*.wav")]),
            "mp4":          sorted([f.name for f in d.glob("*.mp4")]),
            "tracklist":    sorted([f.name for f in d.glob("Tracklist_*.txt")]),
            "yt_cheatsheet": sorted([p.name for p in glob_youtube_sheet_paths(d)]),
            "dk_cheatsheet": sorted([f.name for f in d.glob("DistroKid_Sheet_*.txt")]),
            "dk_upload_csv": sorted([f.name for f in d.glob("DistroKid_Upload_*.csv")]),  # v15.12 Phase 3.5
            "metadata":     sorted([f.name for f in d.glob("metadata_distrokid*.json")]),
            "dir": str(d),
        }

    def get_ceo_approved_mastering_checklist(self, channel: Optional[str] = None) -> Dict:
        """
        列出 ceo_approved_beats/{channel}/ 中尚未在 mastered_tracks/{channel}/ 有對應
        `{safe_stem}_YT_*.wav` 的檔案。比對規則與 audio_mastering_engine._collect_inputs 一致。
        """
        from datetime import datetime

        from scripts.common.path_sanitize import sanitize_filename

        ch = (channel or self.current_channel).lower()
        root = Path(self.config.workspace_root)
        beat_dir = root / "assets" / "audio" / "ceo_approved_beats" / ch
        master_dir = root / "assets" / "audio" / "mastered_tracks" / ch

        pending: List[Dict] = []
        already_mastered: List[Dict] = []

        if beat_dir.exists():
            beats: List[Path] = []
            for pat in ("*.mp3", "*.wav"):
                beats.extend(sorted(beat_dir.glob(pat), key=lambda p: p.stat().st_mtime, reverse=True))
            seen: set[str] = set()
            for beat in beats:
                if beat.name in seen:
                    continue
                seen.add(beat.name)
                safe_stem = sanitize_filename(beat.stem)
                if master_dir.exists():
                    masters = sorted(
                        master_dir.glob(f"{safe_stem}_YT_*.wav"), key=lambda p: p.stat().st_mtime
                    )
                else:
                    masters = []
                try:
                    st = beat.stat()
                    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    size_mb = round(st.st_size / (1024 * 1024), 2)
                except OSError:
                    mtime, size_mb = "?", 0.0
                if masters:
                    lm = masters[-1]
                    already_mastered.append(
                        {
                            "filename": beat.name,
                            "matched_master": lm.name,
                            "mtime": mtime,
                        }
                    )
                else:
                    pending.append(
                        {
                            "filename": beat.name,
                            "safe_stem": safe_stem,
                            "mtime": mtime,
                            "size_mb": size_mb,
                        }
                    )

        return {
            "pending": pending,
            "already_mastered": already_mastered,
            "pending_count": len(pending),
            "mastered_count": len(already_mastered),
            "beat_dir": str(beat_dir),
            "master_dir": str(master_dir),
            "hint": "待母帶 = 尚無對應 *_YT_*.wav；與母帶引擎掃描邏輯一致。",
        }

    # ─────────────────────────────────────────────────────────────
    # 文件補生成（WAV 已存在，只缺 CheatSheet / Metadata）
    # ─────────────────────────────────────────────────────────────
    def generate_distrokid_docs(self, provider: str = "minimax") -> Tuple[bool, str, str]:
        """
        單獨補跑 music_metadata_engine.py：
        產出 metadata_distrokid_{channel}.json + DistroKid_Sheet_{datetime}.txt。
        WAV 母帶必須已存在於 final_exports/{channel}/，否則腳本會回報警告。

        Args:
            provider: "zhipu"（預設，智譜省錢）或 "gemini"
        """
        ch = self.current_channel
        root = Path(self.config.workspace_root)
        metadata_script = root / "scripts" / "gear1_prod" / "music_metadata_engine.py"
        if not metadata_script.exists():
            return False, f"找不到腳本：{metadata_script}", ""
        return self.run_pipeline_with_log(
            "music_metadata_engine.py", ["--channel", ch, "--provider", provider]
        )

    def generate_placeholder_tracklist(self, channel: Optional[str] = None) -> Tuple[bool, str]:
        """
        WAV 母帶存在但 Tracklist 遺失時，掃描 vault_ready_for_mix 的 WAV 檔名
        補生成「曲目名稱版 Tracklist」（無真實時間戳，僅供 YouTube CheatSheet 引用）。
        真實時間戳版本需重新執行「縫合長軌」。
        """
        import datetime
        ch = (channel or self.current_channel).lower()
        vault_dir = Path(self.config.workspace_root) / "assets" / "audio" / "vault_ready_for_mix" / ch
        export_dir = self.get_channel_export_dir()
        export_dir.mkdir(parents=True, exist_ok=True)

        wav_files = sorted(vault_dir.glob("*.wav")) if vault_dir.exists() else []
        if not wav_files:
            return False, f"vault_ready_for_mix/{ch}/ 下無 WAV 檔案，無法補生成 Tracklist"

        lines = ["【R&S Echoes 1 小時無縫混音 - Tracklist（補生成版，無時間戳）】", ""]
        for i, f in enumerate(wav_files, 1):
            lines.append(f"{i:02d}. {f.stem}")
        lines.append("")
        lines.append(f"⚠️  此 Tracklist 為補生成版，不含真實時間戳記。")
        lines.append(f"   如需精確時間戳，請重新執行「縫合長軌 & 雙語企劃（Step 1）」。")

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = export_dir / f"Tracklist_{ts}_placeholder.txt"
        try:
            out_path.write_text("\n".join(lines), encoding="utf-8")
            return True, f"補生成 Tracklist（{len(wav_files)} 首）→ {out_path.name}"
        except Exception as e:
            return False, f"寫入失敗：{e}"

    def regenerate_all_missing_docs(self) -> Tuple[bool, str]:
        """
        一鍵補生成全套文件（適用於 WAV 已存在但三份文件均缺失的情況）：
        1. music_metadata_engine → DistroKid CheatSheet + metadata JSON
        2. generate_youtube_cheatsheet → YouTube CheatSheet
        若 Tracklist 不存在，先補生成佔位版再帶入 YouTube CheatSheet。
        """
        export_dir = self.get_channel_export_dir()
        summary: List[str] = []

        # 1. DistroKid CS + metadata JSON
        ch = self.current_channel
        root = Path(self.config.workspace_root)
        meta_script = root / "scripts" / "gear1_prod" / "music_metadata_engine.py"
        if meta_script.exists():
            rc, log_p = self._run_with_log("music_metadata_engine",
                                           [sys.executable, str(meta_script),
                                            "--channel", ch, "--provider", "minimax"])
            if rc == 0:
                summary.append("✅ DistroKid CheatSheet + Metadata JSON 已補生成")
            else:
                tail = self.get_latest_log_lines(log_p, 20)
                summary.append(f"⚠️ music_metadata_engine 失敗 (Exit {rc})\n{self._extract_fatal(tail)}")
        else:
            summary.append("⚠️ 找不到 music_metadata_engine.py，跳過")

        # 2. Tracklist 佔位版（若 Tracklist 完全不存在）
        tracklist_files = list(export_dir.glob("Tracklist_*.txt")) if export_dir.exists() else []
        if not tracklist_files:
            tl_ok, tl_msg = self.generate_placeholder_tracklist(ch)
            summary.append(f"{'✅' if tl_ok else '⚠️'} {tl_msg}")

        # 3. YouTube CheatSheet
        yt_ok, yt_msg = self.generate_youtube_cheatsheet(ch)
        summary.append(f"{'✅' if yt_ok else '⚠️'} {yt_msg}")

        all_ok = all(s.startswith("✅") for s in summary)
        return all_ok, "\n".join(summary)

    # ─────────────────────────────────────────────────────────────
    # 衍生次數預覽（給側邊欄即時顯示「入池 / 退出」統計）
    # ─────────────────────────────────────────────────────────────
    def get_audio_deriv_preview(self, max_deriv: int, channel: Optional[str] = None) -> Dict:
        """
        依聽覺重複上限預覽：入池 (derivation_count < max_deriv) 與移出 (>= max_deriv) 的曲目數。
        同時回傳每個衍生次數的分布，供側邊欄繪製迷你長條。

        Returns:
            {channel, included, excluded, total, distribution: {dc: count}, max_deriv}
        """
        ch = channel or self.current_channel
        distribution: Dict[int, int] = {}
        try:
            db_p = self.config.music_db_path
            if db_p.exists():
                with sqlite3.connect(str(db_p)) as conn:
                    rows = conn.execute(
                        "SELECT derivation_count, COUNT(*) FROM audio_assets "
                        "WHERE is_archived=0 AND channel=? GROUP BY derivation_count",
                        (ch,),
                    ).fetchall()
                    for dc, cnt in rows:
                        distribution[int(dc or 0)] = cnt
        except Exception:
            pass
        included = sum(cnt for dc, cnt in distribution.items() if dc < max_deriv)
        excluded = sum(cnt for dc, cnt in distribution.items() if dc >= max_deriv)
        return {
            "channel": ch, "max_deriv": max_deriv,
            "included": included, "excluded": excluded,
            "total": included + excluded, "distribution": distribution,
        }

    def get_visual_deriv_preview(self, max_deriv: int, channel: Optional[str] = None) -> Dict:
        """
        依視覺重複上限預覽：入池 / 移出的影片片段數。

        Returns:
            {channel, included, excluded, total, distribution: {dc: count}, max_deriv}
        """
        ch = channel or self.current_channel
        distribution: Dict[int, int] = {}
        try:
            db_p = self.config.visual_db_path
            if db_p.exists():
                with sqlite3.connect(str(db_p)) as conn:
                    rows = conn.execute(
                        "SELECT derivation_count, COUNT(*) FROM video_assets "
                        "WHERE is_archived=0 AND channel=? GROUP BY derivation_count",
                        (ch,),
                    ).fetchall()
                    for dc, cnt in rows:
                        distribution[int(dc or 0)] = cnt
        except Exception:
            pass
        included = sum(cnt for dc, cnt in distribution.items() if dc < max_deriv)
        excluded = sum(cnt for dc, cnt in distribution.items() if dc >= max_deriv)
        return {
            "channel": ch, "max_deriv": max_deriv,
            "included": included, "excluded": excluded,
            "total": included + excluded, "distribution": distribution,
        }

    def generate_youtube_cheatsheet(self, channel: Optional[str] = None) -> Tuple[bool, str]:
        """
        Phase 4.5 移植版：讀取 Tracklist + metadata JSON → 輸出 youtube_sheet_{YYYYMMDD_HHMMSS}.txt。
        對應 pipeline_runner._finalize_youtube_cheatsheet()，供 run_phase4_sequence() 獨立呼叫。
        """
        ch = (channel or self.current_channel).lower()
        export_dir = self.get_channel_export_dir()
        try:
            res = generate_youtube_cheatsheet_file(export_dir, ch)
            out_path = res["output_path"]
            return True, f"YouTube CheatSheet 已生成：{out_path.name}"
        except Exception as e:
            return False, f"寫入 YouTube CheatSheet 失敗：{e}"

    # ─────────────────────────────────────────────────────────────
    # TTAPI 自動供彈備援（Tab4 Step1 前置檢查）
    # ─────────────────────────────────────────────────────────────
    MIN_VAULT_SONGS = 6   # 1 小時 mix 最低需要的曲目（以 10 分鐘/首估算）

    def _count_usable_vault_songs(self, max_deriv: int) -> int:
        """計算 vault_ready_for_mix/{channel}/ 中衍生次數未超標的可用曲目數。"""
        ch = self.current_channel
        vault_dir = Path(self.config.workspace_root) / "assets" / "audio" / "vault_ready_for_mix" / ch
        if not vault_dir.exists():
            return 0
        try:
            from scripts.gear2_rnd.vault_database import VaultDatabase
            db = VaultDatabase()
            tracks = db.get_all_tracks()
            usable = [t for t in tracks
                      if t.get("channel") == ch and t.get("derivation_count", 0) < max_deriv]
            return len(usable)
        except Exception:
            # DB 查不到時退回掃描實體檔案
            exts = {".wav", ".mp3", ".flac"}
            return sum(1 for f in vault_dir.iterdir() if f.suffix.lower() in exts)

    def _run_ttapi_backup(self, needed: int) -> Tuple[bool, str]:
        """
        【v15.4 Tab4 TTAPI 備援】
        透過 pipeline_runner.py 的供彈 + 母帶化流程補充曲目：
          --skip-assembler --skip-metadata  → 只跑 Phase 1+2+備援，不做縫合
        這等同於執行「掃描 ceo_approved_beats → 母帶化 → TTAPI 補足 → 同步 vault」。
        """
        ch = self.current_channel
        root = Path(self.config.workspace_root)
        runner = root / "scripts" / "gear1_prod" / "pipeline_runner.py"
        if not runner.exists():
            return False, f"找不到 pipeline_runner.py：{runner}"
        print(f"[BACKEND] 偵測到 vault 可用曲目不足，啟動 TTAPI 自動備援（需要補充 {needed} 首）...")
        rc, log_path = self._run_with_log(
            "ttapi_backup",
            [sys.executable, str(runner),
             "--channel", ch,
             "--skip-assembler",   # 不縫合，只補歌
             "--skip-metadata"],   # 不生成 metadata
        )
        tail = self.get_latest_log_lines(log_path, 20)
        if rc == 0:
            return True, "✅ TTAPI 備援完成，vault 已補充新曲目"
        return False, f"⚠️ TTAPI 備援失敗 (Exit {rc})\n{self._extract_fatal(tail)}"

    def run_phase4_sequence(self, max_audio_deriv: int = 3) -> Tuple[bool, str]:
        """
        【v15.4 完整發行鏈路】（v15.9：聽覺衍生預設上限 3，與全專案一致）
        前置檢查 vault 可用曲目 → 若不足自動觸發 TTAPI 備援
        → lofi_assembler (WAV + Tracklist)  ← 支援 max_audio_deriv 聽覺重複次數上限
        → music_metadata_engine (DistroKid CheatSheet + metadata JSON)
        → generate_youtube_cheatsheet (YouTube CheatSheet)  ← Phase 4.5 補足

        Args:
            max_audio_deriv: 曲目最大允許衍生次數（預設 3 = 允許 0/1/2 次），傳入 lofi_assembler
        """
        ch = self.current_channel
        root = Path(self.config.workspace_root)
        assembler_script = root / "scripts" / "gear1_prod" / "lofi_assembler.py"
        metadata_script  = root / "scripts" / "gear1_prod" / "music_metadata_engine.py"
        if not assembler_script.exists():
            return False, f"找不到腳本：{assembler_script}"
        if not metadata_script.exists():
            return False, f"找不到腳本：{metadata_script}"

        export_dir = self.get_channel_export_dir()
        try:
            # ── Phase 4-PRE: 檢查 vault 可用曲目，不足則 TTAPI 備援 ──
            usable = self._count_usable_vault_songs(max_audio_deriv)
            print(f"[BACKEND] vault_ready_for_mix/{ch}/ 可用曲目：{usable} 首（上限 {max_audio_deriv} 次衍生）")
            if usable < self.MIN_VAULT_SONGS:
                needed = self.MIN_VAULT_SONGS - usable
                backup_ok, backup_msg = self._run_ttapi_backup(needed)
                if not backup_ok:
                    return False, (
                        f"vault 曲目不足（僅 {usable} 首 < 最低 {self.MIN_VAULT_SONGS} 首），"
                        f"TTAPI 自動備援亦失敗：\n{backup_msg}\n"
                        "請手動補充音樂或確認 TTAPI_KEY 是否有效。"
                    )
                print(f"[BACKEND] {backup_msg}")
            else:
                print(f"[BACKEND] ✅ vault 曲目充足（{usable} 首），直接進入縫合")

            # ── Phase 4a: lofi_assembler → WAV + Tracklist ──
            rc_a, log_a = self._run_with_log(
                "lofi_assembler",
                [sys.executable, str(assembler_script),
                 "--channel", ch,
                 "--max-derivation-limit", str(max_audio_deriv)],
            )
            if rc_a != 0:
                tail = self.get_latest_log_lines(log_a, 30)
                return False, f"lofi_assembler 失敗 (Exit {rc_a})\n{self._extract_fatal(tail)}"

            wavs = list(export_dir.glob("*.wav")) if export_dir.exists() else []
            if not wavs:
                return False, (
                    "金庫曲目不足或選曲被跳過，未寫入 1 小時母帶 WAV。\n"
                    "請補足 vault_ready_for_mix 或改跑完整 pipeline_runner。\n"
                    f"匯出目錄仍無 WAV：{export_dir}"
                )

            # ── Phase 4b: music_metadata_engine → DistroKid CheatSheet + JSON ──
            rc_m, log_m = self._run_with_log(
                "music_metadata_engine",
                [sys.executable, str(metadata_script), "--channel", ch,
                 "--provider", "minimax"],  # v15.3 預設 MiniMax M2.7 (NVIDIA NIM)
            )
            if rc_m != 0:
                tail = self.get_latest_log_lines(log_m, 30)
                return False, f"music_metadata_engine 失敗 (Exit {rc_m})\n{self._extract_fatal(tail)}"

            # ── Phase 4.5: generate_youtube_cheatsheet → YouTube CheatSheet ──
            yt_ok, yt_msg = self.generate_youtube_cheatsheet(ch)

            result_parts = [
                f"✅ WAV 母帶縫合完成（聽覺衍生上限：{max_audio_deriv} 次）",
                "✅ DistroKid CheatSheet + Metadata JSON 已產出",
                f"{'✅' if yt_ok else '⚠️ '} {yt_msg}",
            ]
            # v15.11 P3#13：審計日誌
            get_audit_logger().log(
                action="run_phase4_sequence",
                channel=ch,
                result="success",
                params={"max_audio_deriv": max_audio_deriv},
            )
            return True, "\n".join(result_parts)

        except Exception as e:
            get_audit_logger().log(
                action="run_phase4_sequence",
                channel=ch,
                result=f"failed:{type(e).__name__}:{str(e)[:200]}",
            )
            return False, f"Phase 4 發行鏈路異常: {e}"

    def reset_hearing_vault_derivations(self) -> tuple[bool, str]:
        """聽覺金庫重置：僅 rs_music_vault / audio_assets，當前頻道 derivation_count → 0。"""
        return self.reset_derivation_counts("audio")

    def reset_visual_vault_derivations(self) -> tuple[bool, str]:
        """視覺金庫重置：僅 veo_visual_vault / video_assets，當前頻道 derivation_count → 0。"""
        return self.reset_derivation_counts("visual")

    def reset_derivation_counts(self, target: str = "both") -> tuple[bool, str]:
        channel = self.current_channel
        try:
            db_map = {"audio": self.config.music_db_path, "visual": self.config.visual_db_path}
            table_map = {"audio": "audio_assets", "visual": "video_assets"}
            targets = [target] if target != "both" else ["audio", "visual"]
            msgs = []
            for t in targets:
                db_p = db_map[t]
                if db_p.exists():
                    with sqlite3.connect(db_p) as conn:
                        tbl = table_map[t]
                        col_check = conn.execute(f"PRAGMA table_info({tbl})").fetchall()
                        cols = {row[1] for row in col_check}
                        if not col_check:
                            msgs.append(f"{t.upper()} 跳過：缺少資料表 {tbl}")
                            continue
                        if "derivation_count" not in cols:
                            msgs.append(f"{t.upper()} 跳過：{tbl} 無 derivation_count 欄位")
                            continue
                        if "channel" not in cols:
                            msgs.append(f"{t.upper()} 跳過：{tbl} 無 channel 欄位")
                            continue
                        res = conn.execute(f"UPDATE {tbl} SET derivation_count = 0 WHERE channel = ?", (channel,))
                        conn.commit()
                        msgs.append(f"{t.upper()} 重置成功 ({res.rowcount} 筆)")
                else:
                    msgs.append(f"{t.upper()} 跳過：找不到資料庫 {db_p.name}")
            if not msgs:
                return False, "未找到可重置目標"
            return True, " / ".join(msgs)
        except Exception as e:
            return False, str(e)

    def get_library_stats(self) -> Dict:
        """與 rs_manager 庫存戰報一致：CEO 區計 .mp3，金庫計 .wav。"""
        def _scan_ceo():
            p = Path(self.config.workspace_root) / "assets" / "audio" / "ceo_approved_beats" / self.current_channel
            if not p.exists():
                return 0, 0.0
            files = list(p.glob("*.mp3")) + list(p.glob("*.wav"))
            mb = round(sum(f.stat().st_size for f in files) / (1024 * 1024), 1) if files else 0.0
            return len(files), mb

        def _scan_vault():
            p = Path(self.config.workspace_root) / "assets" / "audio" / "vault_ready_for_mix" / self.current_channel
            files = list(p.glob("*.wav")) if p.exists() else []
            mb = round(sum(f.stat().st_size for f in files) / (1024 * 1024), 1) if files else 0.0
            return len(files), mb

        c1, s1 = _scan_ceo()
        c2, s2 = _scan_vault()
        return {"approved_count": c1, "vault_count": c2, "approved_mb": s1, "vault_mb": s2}

    def get_dual_channel_inventory(self) -> Dict:
        """雙頻道庫存快照（對應 rs_manager [0] 戰報，供儀表板用）。"""
        base = Path(self.config.workspace_root) / "assets" / "audio"
        out = {}
        for ch in ("lofi", "light_music"):
            ceo = base / "ceo_approved_beats" / ch
            vault = base / "vault_ready_for_mix" / ch
            n_mp3 = len(list(ceo.glob("*.mp3"))) if ceo.exists() else 0
            n_ceo_wav = len(list(ceo.glob("*.wav"))) if ceo.exists() else 0
            n_vault = len(list(vault.glob("*.wav"))) if vault.exists() else 0
            out[ch] = {
                "ceo_tracks": n_mp3 + n_ceo_wav,
                "ceo_mp3": n_mp3,
                "vault_wav": n_vault,
                "vault_ok": n_vault >= 10,
            }
        return out

    def get_ceo_prompts_dir(self) -> Path:
        """assets/.ceo_prompts — generate_ceo_prompts.py 輸出目錄。"""
        d = Path(self.config.workspace_root) / "assets" / ".ceo_prompts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_ceo_prompt_files(self, limit: int = 12) -> List[str]:
        """目前頻道最新提示詞檔名（daily_prompts_{CHANNEL}_*.txt），新→舊。"""
        ch = self.current_channel.upper().replace(" ", "_")
        d = self.get_ceo_prompts_dir()
        if not d.exists():
            return []
        files = sorted(
            d.glob(f"daily_prompts_{ch}_*.txt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [f.name for f in files[:limit]]

    def start_ceo_prompts_supply(
        self,
        *,
        provider: str,
        batch_size: int,
        max_retries: int = 3,
    ) -> Tuple[bool, str]:
        """
        【架構說明書_v15.10 §4.1 Tab2】背景執行 generate_ceo_prompts.py（threading + Popen 日誌）。
        與 content_assembly_workflow Protocol A：`--provider` + `--batch-size`。
        """
        ch = self.current_channel
        args = [
            "--channel",
            ch,
            "--provider",
            str(provider).strip().lower(),
            "--batch-size",
            str(int(batch_size)),
            "--max-retries",
            str(int(max_retries)),
        ]

        def _job() -> Tuple[bool, str]:
            ok, msg, _log = self.run_pipeline_with_log("generate_ceo_prompts.py", args)
            return ok, msg

        label = f"CEO 提示詞供彈 ({provider}, {batch_size} 組)"
        return self.start_background(label, _job)

    def start_full_pipeline(self, args: List[str]) -> Tuple[bool, str]:
        """
        【Tab5】背景執行 pipeline_runner.py（Phase 1–5），與 Tab2 供彈相同模式：
        threading 子執行緒 + Popen 日誌 → 主執行緒可 rerun，fragment 可每 ~1.25s 讀取 log 尾端。
        切勿在主執行緒同步呼叫 run_pipeline_proxy（會阻塞整個 Streamlit run，畫面無法即時刷新）。
        """
        if not args:
            return False, "缺少 pipeline_runner 參數。"

        def _job() -> Tuple[bool, str]:
            ok, msg, _log = self.run_pipeline_with_log("pipeline_runner.py", args)
            return ok, msg

        ch = self.current_channel
        label = f"CEO 全自動產線 ({ch})"
        return self.start_background(label, _job)

    # ─────────────────────────────────────────────────────────────
    # 背景任務（白皮書：非阻塞 UI）
    # ─────────────────────────────────────────────────────────────
    def start_background(self, label: str, fn: Callable[[], Tuple[bool, str]]) -> Tuple[bool, str]:
        with self._job_lock:
            if self._bg["state"] == "busy":
                return False, "已有背景任務執行中，請稍候再試。"
            self._bg = {"state": "busy", "label": label, "result": None}

        def worker() -> None:
            try:
                out = fn()
            except Exception as e:
                out = (False, str(e))
            with self._job_lock:
                self._bg["state"] = "done"
                self._bg["result"] = out

        threading.Thread(target=worker, daemon=True).start()
        return True, f"已於背景啟動：{label}"

    def poll_background(self) -> Optional[Dict]:
        """若上一輪背景任務已完成，回傳 {ok, msg, label} 並清空狀態；否則 None。"""
        with self._job_lock:
            if self._bg["state"] == "busy":
                return None
            if self._bg["state"] == "done":
                ok, msg = self._bg["result"]
                label = self._bg.get("label", "")
                self._bg = {"state": "idle", "label": "", "result": None}
                return {"ok": ok, "msg": msg, "label": label}
        return None

    def background_busy(self) -> bool:
        with self._job_lock:
            return self._bg["state"] == "busy"

    def get_background_job_status(self) -> Dict[str, object]:
        """供 UI 顯示目前背景任務標題（與 start_background 的 label 一致）。"""
        with self._job_lock:
            if self._bg["state"] != "busy":
                return {"busy": False, "label": ""}
            return {"busy": True, "label": str(self._bg.get("label") or "")}

    # ─────────────────────────────────────────────────────────────
    # Protocol L（聽覺金庫）+ 視覺金庫摘要
    # ─────────────────────────────────────────────────────────────
    def get_protocol_l_snapshot(self) -> Dict:
        """對應 rs_manager [6]：Protocol L 音樂保鮮庫統計 + 視覺筆數。"""
        stats = self.db.get_statistics()
        tracks = self.db.get_all_tracks()
        by_ch: Dict[str, Dict[str, int]] = {}
        for ch in ("lofi", "light_music"):
            ct = [t for t in tracks if t.get("channel") == ch]
            by_ch[ch] = {
                "tracks": len(ct),
                "ready_new": sum(1 for t in ct if t.get("derivation_count", 0) == 0),
                "in_use": sum(1 for t in ct if t.get("derivation_count", 0) > 0),
            }
        vis_total = 0
        vis_db = self.config.visual_db_path
        if vis_db.exists():
            try:
                with sqlite3.connect(vis_db) as conn:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM video_assets WHERE is_archived = 0"
                    ).fetchone()
                    vis_total = int(row[0]) if row else 0
            except Exception:
                vis_total = -1
        return {
            "audio": stats,
            "by_channel": by_ch,
            "visual_active_clips": vis_total,
            "visual_db": str(vis_db),
        }

    def get_asset_audit_for_channel(self, channel: Optional[str] = None) -> Dict:
        """對應 rs_manager [8]：待命部隊 / 已服役 / 功勳榜（資料結構供 UI 表格）。"""
        ch = channel or self.current_channel
        tracks = self.db.get_all_tracks()
        ct = [t for t in tracks if t.get("channel") == ch]
        ready = [t for t in ct if t.get("derivation_count", 0) == 0]
        in_service = [t for t in ct if t.get("derivation_count", 0) > 0]
        ready_sorted = sorted(ready, key=lambda t: t.get("created_at", ""), reverse=True)[:5]
        heroes = self.db.get_most_used_tracks(limit=10)
        heroes = [t for t in heroes if t.get("track_id")]
        return {
            "channel": ch,
            "ready_count": len(ready),
            "in_service_count": len(in_service),
            "ready_top5": [
                {"track_id": t.get("track_id"), "created_at": t.get("created_at")}
                for t in ready_sorted
            ],
            "heroes": [
                {"track_id": t.get("track_id"), "derivation_count": t.get("derivation_count", 0)}
                for t in heroes
            ],
        }

    # ─────────────────────────────────────────────────────────────
    # 自訂視覺發行（對應 rs_manager [5] 之 pipeline 分支）
    # ─────────────────────────────────────────────────────────────
    def list_background_videos(self) -> List[str]:
        root = Path(self.config.workspace_root) / "assets" / "video_clips"
        if not root.exists():
            return []
        return sorted([p.name for p in root.glob("*.mp4") if p.is_file()])

    def list_sfx_files(self) -> List[str]:
        root = Path(self.config.workspace_root) / "assets" / "sfx"
        if not root.exists():
            return []
        return sorted(
            [p.name for p in root.iterdir() if p.suffix.lower() in {".wav", ".mp3", ".flac", ".aiff", ".m4a"} and p.is_file()]
        )

    def resolve_bg_video_path(self, filename: str) -> Path:
        return Path(self.config.workspace_root) / "assets" / "video_clips" / filename

    def resolve_sfx_path(self, filename: str) -> Path:
        return Path(self.config.workspace_root) / "assets" / "sfx" / filename

    def run_custom_visual_pipeline(self, video_name: str, sfx_name: Optional[str] = None) -> Tuple[bool, str]:
        """以自選背景影片啟動 pipeline_runner（完整產線含新母帶路徑）。"""
        vpath = self.resolve_bg_video_path(video_name)
        if not vpath.exists():
            return False, f"找不到背景影片：{vpath}"
        args = ["--channel", self.current_channel, "--bg-video", str(vpath)]
        if sfx_name and sfx_name.strip():
            sp = self.resolve_sfx_path(sfx_name.strip())
            if not sp.exists():
                return False, f"找不到環境音：{sp}"
            args.extend(["--sfx", str(sp), "--sfx-mode", "global"])
        return self.run_pipeline_proxy("pipeline_runner.py", args)

    # ─────────────────────────────────────────────────────────────
    # 依檔名 LUFS 歸檔（-16 → lofi、-18 → light_music，對齊 audio_mastering_engine）
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def infer_channel_from_audio_filename(filename: str) -> Optional[str]:
        """
        由檔名推斷頻道。母帶慣例：*_YT_-16.0LUFS.wav / *_YT_-18.0LUFS.wav
        （見 audio_mastering_engine.py、pipeline_runner 碎檔歸位邏輯）
        """
        name = Path(filename).name
        if re.search(r"-18(?:\.0)?LUFS", name, re.IGNORECASE):
            return "light_music"
        if re.search(r"-16(?:\.0)?LUFS", name, re.IGNORECASE):
            return "lofi"
        return None

    def apply_db_lufs_channel_rules(self) -> Tuple[bool, str]:
        """與 scripts/gear2_rnd/fix_db_channels.py 相同規則，校正 DB channel。"""
        db_p = Path(self.db.db_path)
        if not db_p.exists():
            return False, f"找不到資料庫：{db_p}"
        try:
            with sqlite3.connect(str(db_p)) as conn:
                c = conn.cursor()
                c.execute(
                    """
                    UPDATE audio_assets
                    SET channel = 'light_music'
                    WHERE track_id LIKE '%-18.0LUFS%'
                    """
                )
                n_light = c.rowcount
                c.execute(
                    """
                    UPDATE audio_assets
                    SET channel = 'lofi'
                    WHERE channel IS NULL OR channel = ''
                    """
                )
                n_lofi = c.rowcount
                conn.commit()
            return (
                True,
                f"DB 已校正：含 -18.0LUFS 的 track_id → light_music ({n_light} 筆)；"
                f"空 channel → lofi ({n_lofi} 筆)。",
            )
        except Exception as e:
            return False, str(e)

    def reconcile_misplaced_audio_by_lufs(self, dry_run: bool = True) -> Tuple[bool, str]:
        """
        掃描各頻道子目錄，若檔名 LUFS 與所在資料夾不一致，移至正確頻道資料夾，
        並嘗試更新 Vault DB 的 channel / original_path。
        """
        audio_root = Path(self.config.workspace_root) / "assets" / "audio"
        subroots = ("ceo_approved_beats", "vault_ready_for_mix", "mastered_tracks", "ceo_archived_beats")
        audio_ext = {".wav", ".mp3", ".flac", ".m4a", ".aiff"}
        lines: List[str] = []
        moved_n = 0
        for sub in subroots:
            for folder_ch in ("lofi", "light_music"):
                d = audio_root / sub / folder_ch
                if not d.is_dir():
                    continue
                for f in d.iterdir():
                    if not f.is_file() or f.suffix.lower() not in audio_ext:
                        continue
                    inferred = self.infer_channel_from_audio_filename(f.name)
                    if inferred is None:
                        continue
                    if inferred == folder_ch:
                        continue
                    dest_dir = audio_root / sub / inferred
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest = dest_dir / f.name
                    if dest.exists():
                        moved_n += 1
                        dest = dest_dir / f"{f.stem}__moved{moved_n}{f.suffix}"
                    rel = f"{sub}/{folder_ch}/ → {sub}/{inferred}/"
                    if dry_run:
                        lines.append(f"[預覽] {f.name} | {rel} → {dest.name}")
                    else:
                        shutil.move(str(f), str(dest))
                        tid = f.stem
                        self.db.update_track_channel_path(tid, inferred, str(dest))
                        lines.append(f"[已移動] {dest}")
        if not lines:
            msg = "無需歸檔：未發現 LUFS 檔名與資料夾頻道不一致的音檔。"
            if not dry_run:
                db_ok, db_msg = self.apply_db_lufs_channel_rules()
                return db_ok, f"{msg} {db_msg}"
            return True, msg
        head = "【預覽】" if dry_run else "【已執行】"
        body = "\n".join(lines[:200])
        if len(lines) > 200:
            body += f"\n… 其餘 {len(lines) - 200} 筆省略"
        if not dry_run:
            db_ok, db_msg = self.apply_db_lufs_channel_rules()
            body += f"\n\n{db_msg}"
            return db_ok, f"{head} 共 {len(lines)} 項。\n{body}"
        return True, f"{head} 共 {len(lines)} 項。\n{body}"

    # ─────────────────────────────────────────────────────────────
    # 頻道靶場封存（對應 rs_manager [7]）
    # ─────────────────────────────────────────────────────────────
    def archive_channel_workspace(self, channel: str) -> Tuple[bool, str]:
        """將 ceo_approved_beats/channel 與 vault_ready_for_mix/channel 檔案移至 ceo_archived_beats/channel/。"""
        ch = str(channel).strip()
        if ch not in ("lofi", "light_music"):
            return False, "無效頻道"
        base = Path(self.config.workspace_root) / "assets" / "audio"
        targets = [
            base / "ceo_approved_beats" / ch,
            base / "vault_ready_for_mix" / ch,
        ]
        archived_root = base / "ceo_archived_beats" / ch
        archived_root.mkdir(parents=True, exist_ok=True)
        moved = 0
        errors: List[str] = []
        dedupe = 0
        for d in targets:
            if not d.exists():
                continue
            for item in d.iterdir():
                try:
                    dest = archived_root / item.name
                    if dest.exists():
                        dedupe += 1
                        dest = archived_root / f"{item.stem}__dup{dedupe}{item.suffix}"
                    shutil.move(str(item), str(dest))
                    moved += 1
                except Exception as e:
                    errors.append(f"{item.name}: {e}")
        if errors:
            return False, f"已移動 {moved} 個項目，但有錯誤：{' / '.join(errors[:5])}"
        if moved == 0:
            return True, "無需封存（目標目錄為空或不存在）。"
        return True, f"已封存 {moved} 個檔案/目錄至 assets/audio/ceo_archived_beats/{ch}/"


_instance = None


def get_ui_backend():
    global _instance
    if _instance is None:
        _instance = UIBackend()
    return _instance