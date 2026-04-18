#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 幻影輪播緊急發射控制台
CTO 最終命令：馬上執行 Stage 1 + Stage 2
"""

import sys
from pathlib import Path

# 添加路徑
sys.path.insert(0, str(Path.cwd()))

from scripts.gear1_prod.multi_scene_processor import MultiSceneProcessor
import logging

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

log = logging.getLogger(__name__)

def main():
    log.info("=" * 80)
    log.info("🚀 【總指揮官最終命令】啟動雙棲企劃與幻影輪播發射序列...")
    log.info("=" * 80)
    
    try:
        processor = MultiSceneProcessor()
        log.info("✅ 處理器初始化完成")
        
        # 發射 (Lofi channel)
        result = processor.process_full_pipeline(
            channel='lofi',
            target_duration=3600,
            scene_dwell_time=300
        )
        
        if result:
            log.info("=" * 80)
            log.info(f"✅ 【發射成功】最終輸出: {result}")
            log.info("=" * 80)
        else:
            log.error("=" * 80)
            log.error("❌ 【發射失敗】process_full_pipeline 返回 None")
            log.error("=" * 80)
            sys.exit(1)
            
    except Exception as e:
        log.error("=" * 80)
        log.error(f"❌ 【發射異常】{type(e).__name__}: {str(e)}")
        log.error("=" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
