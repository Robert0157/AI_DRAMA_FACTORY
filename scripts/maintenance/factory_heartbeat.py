#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【工廠心跳守護程序】factory_heartbeat.py (v12.2 CTO 最終衝刺版)
================================================

🌟 商業級自動化心跳守護程序

使用 Python schedule 套件實現密集排程，確保：
• 週期性提示詞供彈（週日 01:00）
• 每日垃圾回收（03:00）
• 每日財務統計（08:00）✅ 【v12.2 新增】Telegram 推播
• 每日庫存檢查（10:00）✅ 【v12.2 新增】預警推播
• 數據備份與自檢（每6小時）

🔄 預期運行環境：Mac mini M4 (pm2 或 launchd 背景常駐)
💓 系統脈搏：此程式是整個自動化工廠的生命線
🚀 【v12.2】遠端推播：每日財報與庫存預警直達 CEO Telegram
"""

import schedule
import time
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# 強制獲取專案根目錄
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.gear2_rnd.vault_database import VaultDatabase
from scripts.common.env_manager import config
from scripts.telegram_reporter_bot import (
    send_telegram_report,
    generate_daily_financial_report,
    generate_inventory_warning
)


class FactoryHeartbeat:
    """工廠心跳守護程序 - 集中所有排程任務"""
    
    def __init__(self):
        """初始化守護程序"""
        self.db = VaultDatabase()
        self.config = config
        self.execution_log = []
        print("[HEARTBEAT] 初始化工廠心跳守護程序 v12.2 (含 Telegram 推播)...")
    
    def log_event(self, job_name: str, status: str, details: str = ""):
        """記錄執行事件到記憶體"""
        timestamp = datetime.now().isoformat()
        event = {
            "timestamp": timestamp,
            "job": job_name,
            "status": status,
            "details": details
        }
        self.execution_log.append(event)
        
        status_icon = "✅" if status == "success" else "❌" if status == "failed" else "⏳"
        print(f"[{timestamp}] {status_icon} {job_name}: {status} {details}")
    
    # ========== 任務一：週期提示詞供彈 ==========
    
    def job_generate_prompts_lofi(self):
        """每週日 01:00 - Lofi 頻道提示詞供彈"""
        try:
            print("\n[HEARTBEAT] 執行 CW_Generate_CEO_Prompts_Lofi (週日 01:00)")
            result = subprocess.run(
                [sys.executable, "scripts/gear1_prod/generate_ceo_prompts.py", 
                 "--channel", "lofi", "--batch-size", "5"],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(_PROJECT_ROOT)
            )
            
            if result.returncode == 0:
                self.log_event("Generate_Prompts_Lofi", "success", "✅ 5 組 Lofi 提示詞已生成")
            else:
                self.log_event("Generate_Prompts_Lofi", "failed", f"Exit Code {result.returncode}")
        
        except subprocess.TimeoutExpired:
            self.log_event("Generate_Prompts_Lofi", "failed", "超時 (600s)")
        except Exception as e:
            self.log_event("Generate_Prompts_Lofi", "failed", str(e))
    
    def job_generate_prompts_light_music(self):
        """每週一 01:30 - Light Music 頻道提示詞供彈"""
        try:
            print("\n[HEARTBEAT] 執行 CW_Generate_CEO_Prompts_LightMusic (週一 01:30)")
            result = subprocess.run(
                [sys.executable, "scripts/gear1_prod/generate_ceo_prompts.py",
                 "--channel", "light_music", "--batch-size", "5"],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(_PROJECT_ROOT)
            )
            
            if result.returncode == 0:
                self.log_event("Generate_Prompts_LightMusic", "success", "✅ 5 組 Light Music 提示詞已生成")
            else:
                self.log_event("Generate_Prompts_LightMusic", "failed", f"Exit Code {result.returncode}")
        
        except subprocess.TimeoutExpired:
            self.log_event("Generate_Prompts_LightMusic", "failed", "超時 (600s)")
        except Exception as e:
            self.log_event("Generate_Prompts_LightMusic", "failed", str(e))
    
    # ========== 任務二：每日垃圾回收 ==========
    
    def job_garbage_collection(self):
        """每日 03:00 - 深度垃圾回收"""
        try:
            print("\n[HEARTBEAT] 執行 SYS_Garbage_Collection (每日 03:00)")
            # v15.10 P3#14: 加入 PYTHONUNBUFFERED + 日誌輸出，避免 capture_output 盲盒化錯誤
            _env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            _log_dir = _PROJECT_ROOT / "logs"
            _log_dir.mkdir(exist_ok=True)
            _log_path = _log_dir / "workspace_sweeper.log"
            with open(_log_path, "a", encoding="utf-8") as _lf:
                # 清理 Lofi 頻道
                result_lofi = subprocess.run(
                    [sys.executable, "scripts/maintenance/workspace_sweeper.py", "--channel", "lofi"],
                    stdout=_lf, stderr=_lf,
                    timeout=300,
                    cwd=str(_PROJECT_ROOT),
                    env=_env,
                )
                # 清理 Light Music 頻道
                result_light = subprocess.run(
                    [sys.executable, "scripts/maintenance/workspace_sweeper.py", "--channel", "light_music"],
                    stdout=_lf, stderr=_lf,
                    timeout=300,
                    cwd=str(_PROJECT_ROOT),
                    env=_env,
                )
            
            if result_lofi.returncode == 0 and result_light.returncode == 0:
                self.log_event("Garbage_Collection", "success", "✅ 兩個頻道已清理完畢")
            else:
                self.log_event("Garbage_Collection", "failed", f"Lofi: {result_lofi.returncode}, Light: {result_light.returncode}")
        
        except subprocess.TimeoutExpired:
            self.log_event("Garbage_Collection", "failed", "超時 (300s)")
        except Exception as e:
            self.log_event("Garbage_Collection", "failed", str(e))
    
    # ========== 任務三：每日財務統計 ==========
    
    def job_financial_report(self):
        """
        【v12.2 新增】每日 08:00 - 產生每日財務統計報告
        + 推播至 CEO Telegram (如有配置)
        """
        try:
            print("\n[HEARTBEAT] 執行 PM_Daily_Financial_Report (每日 08:00)")
            
            # 【第一步】從資料庫撈取統計數據
            stats = self.db.get_statistics()
            all_tracks = self.db.get_all_tracks()
            
            # 計算庫存價值
            total_tracks = stats.get('total_tracks', 0)
            total_derivations = stats.get('total_derivations', 0)
            
            # 分頻道統計
            lofi_tracks = len([t for t in all_tracks if t.get("channel") == "lofi"])
            light_music_tracks = len([t for t in all_tracks if t.get("channel") == "light_music"])
            
            # 【第二步】構建財務報告 JSON
            report = {
                "timestamp": datetime.now().isoformat(),
                "total_capital_tracks": total_tracks,
                "total_value_derivations": total_derivations,
                "lofi_inventory": lofi_tracks,
                "light_music_inventory": light_music_tracks,
                "database_size_mb": stats.get('database_size_mb', 0),
                "avg_derivations_per_track": stats.get('avg_derivations', 0)
            }
            
            # 保存財務報告至本地
            report_dir = _PROJECT_ROOT / "assets" / "financial_reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_file = report_dir / f"daily_report_{datetime.now().strftime('%Y%m%d')}.json"
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            self.log_event(
                "Financial_Report",
                "success",
                f"✅ 資本結構: {total_tracks} 首母帶, 衍生 {total_derivations} 次"
            )
            
            # 【第三步】準備 Telegram 推播 (v12.2 新增)
            try:
                # 獲取完整審計數據
                audit_data = {
                    "global_stats": {
                        "total_tracks": total_tracks,
                        "total_derivations": total_derivations,
                        "avg_derivations": stats.get('avg_derivations', 0),
                        "database_size_mb": stats.get('database_size_mb', 0)
                    },
                    "channels": {
                        "lofi": {"ready_to_work_count": lofi_tracks, "in_service_count": 0},
                        "light_music": {"ready_to_work_count": light_music_tracks, "in_service_count": 0}
                    },
                    "hall_of_fame": self.db.get_most_used_tracks(limit=3)
                }
                
                # 生成美化的財務報表
                financial_report_text = generate_daily_financial_report(audit_data)
                
                # 【推播至 Telegram】非阻塞執行
                print("[HEARTBEAT] 📤 正在推播每日財報至 Telegram...")
                telegram_result = send_telegram_report(
                    message_title=f"每日財務報表 - {datetime.now().strftime('%Y-%m-%d')}",
                    message_body=financial_report_text,
                    message_type="daily_report",
                    emoji="💰"
                )
                
                if telegram_result.get("success"):
                    print(f"[HEARTBEAT] ✅ Telegram 推播成功")
                else:
                    print(f"[HEARTBEAT] ⚠️ Telegram 推播失敗: {telegram_result.get('error', '未知錯誤')}")
            
            except ImportError:
                print("[HEARTBEAT] ℹ️ Telegram Reporter 未配置，跳過推播")
            except Exception as e:
                print(f"[HEARTBEAT] ⚠️ Telegram 推播異常: {str(e)}")
        
        except Exception as e:
            self.log_event("Financial_Report", "failed", str(e))
    
    # ========== 任務四：每日庫存檢查 ==========
    
    def job_inventory_check(self):
        """
        【v12.2 新增】每日 10:00 - 庫存健康檢查與預警
        + 推播至 CEO Telegram (如有配置)
        """
        try:
            print("\n[HEARTBEAT] 執行 PM_Daily_Inventory_Check (每日 10:00)")
            
            all_tracks = self.db.get_all_tracks()
            
            # 檢查待命部隊
            lofi_tracks = [t for t in all_tracks if t.get("channel") == "lofi"]
            light_music_tracks = [t for t in all_tracks if t.get("channel") == "light_music"]
            
            lofi_ready = len([t for t in lofi_tracks if t.get("derivation_count", 0) == 0])
            light_ready = len([t for t in light_music_tracks if t.get("derivation_count", 0) == 0])
            
            warnings = []
            low_channels = {}
            
            if lofi_ready < 20:
                warnings.append(f"⚠️ Lofi 待命部隊不足: {lofi_ready} 首 (建議補充)")
                low_channels["lofi"] = lofi_ready
            
            if light_ready < 20:
                warnings.append(f"⚠️ Light Music 待命部隊不足: {light_ready} 首 (建議補充)")
                low_channels["light_music"] = light_ready
            
            if warnings:
                details = " | ".join(warnings)
                self.log_event("Inventory_Check", "warning", details)
                
                # 【推播預警至 Telegram】v12.2 新增
                try:
                    print("[HEARTBEAT] 🚨 庫存不足，正在推播預警至 Telegram...")
                    warning_message = generate_inventory_warning(low_channels)
                    
                    telegram_result = send_telegram_report(
                        message_title=f"庫存預警 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        message_body=warning_message,
                        message_type="inventory_warning",
                        emoji="🚨"
                    )
                    
                    if telegram_result.get("success"):
                        print(f"[HEARTBEAT] ✅ 預警推播成功")
                    else:
                        print(f"[HEARTBEAT] ⚠️ 預警推播失敗: {telegram_result.get('error', '未知錯誤')}")
                
                except Exception as e:
                    print(f"[HEARTBEAT] ⚠️ 預警推播異常: {str(e)}")
            else:
                self.log_event("Inventory_Check", "success", f"✅ 庫存充足 (Lofi: {lofi_ready}, Light: {light_ready})")
        
        except Exception as e:
            self.log_event("Inventory_Check", "failed", str(e))
    
    # ========== 任務五：數據備份 ==========
    
    def job_database_backup(self):
        """每 6 小時 - 資料庫備份與自檢"""
        try:
            print("\n[HEARTBEAT] 執行 INF_Database_Backup_Health_Check (每 6 小時)")
            
            # 簡歷詢查資料庫元數據
            stats = self.db.get_statistics()
            db_size = stats.get('database_size_mb', 0)
            
            # 創建備份目錄
            backup_dir = _PROJECT_ROOT / "assets" / "database_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # 複製資料庫檔
            db_path = self.db.db_path
            backup_file = backup_dir / f"rs_music_vault_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            
            if db_path.exists():
                import shutil
                shutil.copy2(db_path, backup_file)
                self.log_event(
                    "Database_Backup",
                    "success",
                    f"✅ 備份成功 ({db_size:.2f} MB) → {backup_file.name}"
                )
            else:
                self.log_event("Database_Backup", "failed", "資料庫檔案不存在")
        
        except Exception as e:
            self.log_event("Database_Backup", "failed", str(e))
    
    # ========== 主排程設定 ==========
    
    def setup_schedule(self):
        """設定所有定時任務"""
        print("[HEARTBEAT] 設定排程任務...")
        
        # 週期提示詞供彈
        schedule.every().sunday.at("01:00").do(self.job_generate_prompts_lofi)
        schedule.every().monday.at("01:30").do(self.job_generate_prompts_light_music)
        
        # 每日任務
        schedule.every().day.at("03:00").do(self.job_garbage_collection)
        schedule.every().day.at("08:00").do(self.job_financial_report)
        schedule.every().day.at("10:00").do(self.job_inventory_check)
        
        # 每 6 小時執行一次備份
        schedule.every(6).hours.do(self.job_database_backup)
        
        print("[HEARTBEAT] ✅ 排程已設定，就緒待命...")
    
    def run(self):
        """啟動心跳守護程序（無限迴圈）"""
        self.setup_schedule()
        
        print("\n" + "=" * 70)
        print("💓 R&S Echoes Factory Heartbeat Daemon 啟動完成")
        print("=" * 70)
        print("\n【排程時間表】")
        print("  • 週日 01:00   → CW_Generate_CEO_Prompts_Lofi")
        print("  • 週一 01:30   → CW_Generate_CEO_Prompts_LightMusic")
        print("  • 每日 03:00   → SYS_Garbage_Collection")
        print("  • 每日 08:00   → PM_Daily_Financial_Report")
        print("  • 每日 10:00   → PM_Daily_Inventory_Check")
        print("  • 每 6小時     → INF_Database_Backup_Health_Check")
        print("\n【運行狀態】")
        print("  🟢 背景常駐進程已啟動")
        print("  💓 工廠心臟正常跳動...")
        print("=" * 70 + "\n")
        
        # 無限迴圈
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分鐘檢查一次是否需要執行任務
            except KeyboardInterrupt:
                print("\n[HEARTBEAT] 收到中斷信號，準備優雅關閉...")
                self.log_event("Daemon", "shutdown", "✅ 守護程序已停止")
                break
            except Exception as e:
                print(f"\n[HEARTBEAT] 執行迴圈錯誤: {e}")
                self.log_event("Daemon", "error", str(e))
                time.sleep(60)


if __name__ == "__main__":
    try:
        heartbeat = FactoryHeartbeat()
        heartbeat.run()
    except Exception as e:
        print(f"[FATAL] 心跳守護程序啟動失敗: {e}", file=sys.stderr)
        sys.exit(1)
