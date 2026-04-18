#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v8.5 Telegram 哨兵 - 生產線審批中樞
角色：實時通知 CEO，確保 Vol_1 首映關鍵節點均已上報
"""

import sys
from pathlib import Path
import telebot
from telebot.util import quick_markup

# 設定項目根目錄
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


class TelegramApprover:
    """CEO Telegram 通訊中樞"""
    
    def __init__(self):
        # 從 .env 安全讀取 Bot Token 和 Chat ID
        bot_token = config.__dict__.get('telegram_bot_token') or \
                    getattr(config, 'telegram_bot_token', None)
        
        # 如果 config 沒有直接提供，從環境變數讀取
        import os
        if not bot_token:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        
        chat_id_str = config.__dict__.get('telegram_chat_id') or \
                      getattr(config, 'telegram_chat_id', None)
        
        if not chat_id_str:
            chat_id_str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        
        if not bot_token or not chat_id_str:
            raise ValueError(
                "❌ TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未設定\n"
                "   請確保 .env 檔案包含正確的金鑰"
            )
        
        self.bot = telebot.TeleBot(bot_token, parse_mode="HTML")
        self.chat_id = chat_id_str
        
        print(f"✅ Telegram 機器人已初始化")
        print(f"   Chat ID: {self.chat_id}")
    
    def send_test_message(self) -> bool:
        """
        發送文字測試訊息給 CEO
        """
        try:
            message = (
                "🤖 <b>報告 CEO</b>\n\n"
                "萬物生靈產線 <b>Telegram 哨兵</b>已上線！\n"
                "Vol_1 縫合處理中...\n\n"
                "📊 <b>Phase B 狀態：</b>\n"
                "✓ 12 顆鏡頭異步 API 生成完畢\n"
                "✓ 節拍 JSON 同步完備\n"
                "📍 epic_movie_ramped.mp4 合併中..."
            )
            
            result = self.bot.send_message(
                self.chat_id,
                message
            )
            
            print(f"✅ 文字訊息已發送")
            print(f"   Message ID: {result.message_id}")
            return True
            
        except Exception as exc:
            print(f"❌ 發送文字訊息失敗: {exc}")
            return False
    
    def send_image_test(self, image_path: str | Path) -> bool:
        """
        發送圖片測試給 CEO（anchor_01.jpg）
        """
        try:
            image_path = Path(image_path)
            
            if not image_path.exists():
                print(f"❌ 圖片不存在: {image_path}")
                return False
            
            with open(image_path, "rb") as photo:
                result = self.bot.send_photo(
                    self.chat_id,
                    photo,
                    caption="📷 <b>Vol_1 首映錨點圖</b>\n"
                           "This is the anchor frame for shot_01 generation."
                )
            
            print(f"✅ 圖片已發送")
            print(f"   File: {image_path.name}")
            print(f"   Message ID: {result.message_id}")
            return True
            
        except Exception as exc:
            print(f"❌ 發送圖片失敗: {exc}")
            return False


def main():
    """主程序：完整測試流程"""
    print("=" * 70)
    print("📡 AI_DRAMA_FACTORY v8.5 Telegram 哨兵 - 初始化測試")
    print("=" * 70)
    
    try:
        # 初始化機器人
        approver = TelegramApprover()
        
        # 測試一：發送文字訊息
        print("\n【Phase 1】發送文字訊息...")
        text_success = approver.send_test_message()
        
        if not text_success:
            print("⚠️  文字訊息發送失敗，但繼續圖片測試...")
        
        # 測試二：發送圖片
        print("\n【Phase 2】發送圖片訊息...")
        anchor_path = (
            Path(config.workspace_root) / 
            "assets" / "image_anchors" / "zaouli_test_002_vol1_premiere" / 
            "anchor_01.jpg"
        )
        
        image_success = approver.send_image_test(anchor_path)
        
        if not image_success:
            print("⚠️  圖片訊息發送失敗")
        
        # 總結
        print("\n" + "=" * 70)
        print("📊 Telegram 通訊測試結果：")
        print(f"   ✓ 文字訊息: {'成功' if text_success else '失敗'}")
        print(f"   ✓ 圖片訊息: {'成功' if image_success else '失敗'}")
        print("=" * 70)
        
        # 返回成功狀態
        if text_success or image_success:
            print("✅ Telegram 哨兵運作正常！CEO 應已收到通知。")
            return 0
        else:
            print("❌ Telegram 哨兵測試完全失敗")
            return 1
    
    except Exception as exc:
        print(f"\n❌ 致命錯誤: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
