#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【v15.0 UI 中控台擴展】scripts/ui/v15_phantom_controller.py
為現有 Web 介面新增幻影輪播與雙棲企劃控制區塊
✅ 參數滑桿：【場景停留時間】與【啟用/停用金庫】
✅ API 路由：一鍵生成企劃 + 啟動幻影輪播
✅ Streamlit/FastAPI 相容
"""

import sys
import json
import random
from pathlib import Path
from typing import Dict, Any, Optional

# 【CTO 強制執行】
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import EnvConfig
from scripts.gear1_prod.gemini_genesis_engine import GeminiGenesisEngine
from scripts.gear1_prod.multi_scene_processor import MultiSceneProcessor

config = EnvConfig()


# ╔═══════════════════════════════════════════════════════════════╗
# ║ v15.0 Phantom Rotation 控制器 - 可複用的 API 層              ║
# ╚═══════════════════════════════════════════════════════════════╝

class PhantomController:
    """【v15.0】Web 中控台用的 Phantom Rotation 控制器"""
    
    def __init__(self):
        self.genesis_engine = GeminiGenesisEngine()
        self.scene_processor = MultiSceneProcessor(use_sandbox=False)
    
    def get_ui_config(self) -> Dict[str, Any]:
        """返回前端需要的 UI 配置"""
        return {
            "version": "v15.0",
            "features": [
                "dual_plan_generation",
                "phantom_rotation",
                "vault_management"
            ],
            "channels": ["lofi", "light_music"],
            "scene_dwell_options": [
                {"label": "3 分鐘", "value": 180},
                {"label": "5 分鐘", "value": 300},
                {"label": "10 分鐘", "value": 600}
            ],
            "target_durations": [
                {"label": "30 分鐘", "value": 1800},
                {"label": "1 小時", "value": 3600},
                {"label": "2 小時", "value": 7200}
            ]
        }
    
    def generate_plan(self, channel: str, context: Optional[str] = None) -> Dict[str, Any]:
        """生成雙棲企劃
        
        Args:
            channel: 頻道名稱
            context: 額外背景信息
        
        Returns:
            企劃 JSON
        """
        try:
            plan = self.genesis_engine.generate_dual_plan(channel, context)
            if plan:
                return {
                    "status": "success",
                    "plan": plan
                }
            else:
                return {
                    "status": "error",
                    "message": "Gemini 引擎返回空結果"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def start_phantom_rotation(self, 
                               channel: str,
                               target_duration: int = 3600,
                               scene_dwell_time: int = 600,
                               use_sandbox: bool = False) -> Dict[str, Any]:
        """啟動幻影輪播
        
        Args:
            channel: 頻道名稱
            target_duration: 目標時長（秒）
            scene_dwell_time: 場景停留時間（秒）
            use_sandbox: 是否使用沙盒
        
        Returns:
            狀態 + 輸出文件路徑
        """
        try:
            # 【CTO 修復】多音軌輪播注入：打亂全部 .wav 並傳遞清單給 FFmpeg concat demuxer
            audio_paths = []
            vault_audio_dir = config.workspace_root / "assets" / "audio" / "vault_ready_for_mix" / channel
            
            if vault_audio_dir.exists():
                wav_files = list(vault_audio_dir.glob("*.wav"))
                if wav_files:
                    random.shuffle(wav_files)
                    audio_paths = [Path(f) for f in wav_files]
                    print(f"  🎵 Multi-Track Soul Injection: {len(audio_paths)} tracks shuffled for rotation")
            
            # 【CTO 防禦增強】靈魂音樂強制檢查機制
            # 如果找不到音樂，拒絕啟動 FFmpeg，確保 100% 音軌品質
            if not audio_paths:
                return {
                    "status": "error",
                    "message": f"Startup Failed! Could not find any .wav master in {vault_audio_dir}. Please expand audio vault first!"
                }
            
            if use_sandbox:
                processor = MultiSceneProcessor(use_sandbox=True)
            else:
                processor = self.scene_processor
            
            output_path = processor.process_full_pipeline(
                channel=channel,
                target_duration=target_duration,
                scene_dwell_time=scene_dwell_time,
                audio_paths=audio_paths
            )
            
            if output_path:
                return {
                    "status": "success",
                    "output_path": str(output_path),
                    "file_size_mb": output_path.stat().st_size / (1024 * 1024)
                }
            else:
                return {
                    "status": "error",
                    "message": "幻影輪播處理失敗"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }


# ╔═══════════════════════════════════════════════════════════════╗
# ║ FastAPI 路由示例（用於 backend.py 整合）                    ║
# ╚═══════════════════════════════════════════════════════════════╝

"""
【集成到 backend.py 的示例】

在 backend.py 中添加以下路由：

---

from scripts.ui.v15_phantom_controller import PhantomController

phantom_controller = PhantomController()

@app.get("/api/v15/config")
async def get_phantom_config():
    \"\"\"取得 v15.0 UI 配置\"\"\"
    return phantom_controller.get_ui_config()

@app.post("/api/v15/generate-plan")
async def generate_dual_plan(request: dict):
    \"\"\"生成雙棲企劃
    
    Request JSON:
    {
        "channel": "lofi",
        "context": "深夜雨夜"
    }
    \"\"\"
    return phantom_controller.generate_plan(
        channel=request.get("channel", "lofi"),
        context=request.get("context")
    )

@app.post("/api/v15/phantom-rotation")
async def start_rotation(request: dict):
    \"\"\"啟動幻影輪播
    
    Request JSON:
    {
        "channel": "lofi",
        "target_duration": 3600,
        "scene_dwell_time": 300,
        "use_sandbox": false
    }
    \"\"\"
    return phantom_controller.start_phantom_rotation(
        channel=request.get("channel", "lofi"),
        target_duration=request.get("target_duration", 3600),
        scene_dwell_time=request.get("scene_dwell_time", 300),
        use_sandbox=request.get("use_sandbox", False)
    )

---
"""


# ╔═══════════════════════════════════════════════════════════════╗
# ║ Streamlit 整合示例（用於 app.py 擴展）                       ║
# ╚═══════════════════════════════════════════════════════════════╝

"""
【集成到 app.py (Streamlit) 的示例】

在 app.py 中添加新的選項卡或按鈕：

---

import streamlit as st
from scripts.ui.v15_phantom_controller import PhantomController

phantom = PhantomController()

# 新增導覽選項 (在現有選項卡中新增)
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎵 音樂生成",
    "🎬 視覺製作", 
    "🔄 幻影輪播 (v15.0 NEW)",
    "📊 資產管理",
    "⚙️ 設置"
])

# 幻影輪播選項卡
with tab3:
    st.header("🔄 Project Phantom Rotation (v15.0)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        channel = st.selectbox("頻道", ["lofi", "light_music"])
        target_duration = st.select_slider(
            "目標時長",
            options=[1800, 3600, 7200],
            value=3600,
            format_func=lambda x: f"{x//60} 分鐘"
        )
    
    with col2:
        scene_dwell_time = st.select_slider(
            "場景停留時間",
            options=[180, 300, 600],
            value=300,
            format_func=lambda x: f"{x//60} 分鐘"
        )
        use_sandbox = st.checkbox("使用沙盒模式", value=False)
    
    # 生成企劃
    if st.button("📝 生成雙棲企劃"):
        with st.spinner("Gemini 正在生成企劃..."):
            result = phantom.generate_plan(channel)
            if result["status"] == "success":
                st.success("✅ 企劃生成成功！")
                st.json(result["plan"])
            else:
                st.error(f"❌ 企劃生成失敗: {result.get('message')}")
    
    # 啟動幻影輪播
    if st.button("🚀 啟動幻影輪播"):
        with st.spinner("正在處理 FFmpeg 縫合..."):
            result = phantom.start_phantom_rotation(
                channel=channel,
                target_duration=target_duration,
                scene_dwell_time=scene_dwell_time,
                use_sandbox=use_sandbox
            )
            if result["status"] == "success":
                st.success(f"✅ 幻影輪播完成！")
                st.write(f"📁 輸出: {result['output_path']}")
                st.write(f"📊 檔案大小: {result['file_size_mb']:.1f} MB")
            else:
                st.error(f"❌ 幻影輪播失敗: {result.get('message')}")

---
"""


# ╔═══════════════════════════════════════════════════════════════╗
# ║ CLI 測試介面                                                  ║
# ╚═══════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    controller = PhantomController()
    
    # 測試一：取得 UI 配置
    print("\n【測試一】UI 配置:")
    config = controller.get_ui_config()
    print(json.dumps(config, ensure_ascii=False, indent=2))
    
    # 測試二：生成企劃（mock）
    print("\n【測試二】生成企劃:")
    result = controller.generate_plan("lofi", "深夜雨夜")
    print(f"Status: {result['status']}")
    
    # 測試三：幻影輪播（沙盒模式）
    print("\n【測試三】幻影輪播 (沙盒模式):")
    result = controller.start_phantom_rotation(
        channel="lofi",
        target_duration=600,  # 10 分鐘測試
        scene_dwell_time=300,  # 5 分鐘一個場景
        use_sandbox=True
    )
    print(f"Status: {result['status']}")
    
    print("\n✅ V15.0 UI 控制器測試完成")
