#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
【狀態檢查】Telegram CEO Bot 環境與依賴驗證工具

用途：在啟動 Bot 前檢查所有必要的環境配置是否正確

使用：
  python scripts/telegram_health_check.py
"""

import os
import sys
from pathlib import Path

# 添加專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 從 .env 加載環境變數
from dotenv import load_dotenv
env_file = PROJECT_ROOT / ".env"
load_dotenv(env_file)

def check_environment():
    """進行全面的環境檢查"""
    
    print("=" * 70)
    print("🏥 Telegram CEO Bot 環境健康檢查")
    print("=" * 70)
    print()
    
    checks = {
        "✅ 通過": [],
        "⚠️  警告": [],
        "❌ 失敗": []
    }
    
    # ========== 檢查 1: .env 檔案 ==========
    print("【1】檢查 .env 檔案...")
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        print("  ✅ .env 檔案存在")
        checks["✅ 通過"].append(".env 檔案存在")
    else:
        print("  ❌ .env 檔案不存在")
        checks["❌ 失敗"].append(".env 檔案不存在")
        return checks
    
    # ========== 檢查 2: 必要的環境變數 ==========
    print("\n【2】檢查環境變數...")
    
    required_vars = {
        "TELEGRAM_BOT_TOKEN": "Telegram Bot Token",
        "TELEGRAM_ALLOWED_USER_ID": "CEO 用戶 ID",
    }
    
    for var_name, var_desc in required_vars.items():
        value = os.getenv(var_name)
        if value:
            masked_value = f"{value[:10]}...{value[-10:]}" if len(str(value)) > 20 else value
            print(f"  ✅ {var_desc}: {masked_value}")
            checks["✅ 通過"].append(f"{var_name} 已設定")
        else:
            print(f"  ❌ {var_desc}: 未設定")
            checks["❌ 失敗"].append(f"{var_name} 未設定")
    
    # ========== 檢查 3: Python 依賴 ==========
    print("\n【3】檢查 Python 依賴...")
    
    dependencies = {
        "telegram": "python-telegram-bot",
        "aiohttp": "aiohttp",
    }
    
    for module_name, package_name in dependencies.items():
        try:
            __import__(module_name)
            # 試著獲取版本
            version = None
            try:
                if module_name == "telegram":
                    import telegram
                    version = telegram.__version__
                elif module_name == "aiohttp":
                    import aiohttp
                    version = aiohttp.__version__
            except:
                version = "已安裝"
            
            print(f"  ✅ {package_name}: {version}")
            checks["✅ 通過"].append(f"{package_name} 已安裝")
        except ImportError:
            print(f"  ❌ {package_name}: 未安裝")
            checks["❌ 失敗"].append(f"{package_name} 未安裝")
    
    # ========== 檢查 4: AI Drama Factory 核心模組 ==========
    print("\n【4】檢查 AI Drama Factory 核心模組...")
    
    core_modules = {
        "scripts.common.env_manager": "環境管理器",
        "scripts.gear1_prod.pipeline_runner": "產線執行器",
    }
    
    for module_path, module_desc in core_modules.items():
        try:
            __import__(module_path)
            print(f"  ✅ {module_desc}: {module_path}")
            checks["✅ 通過"].append(f"{module_desc} 可導入")
        except ImportError as e:
            print(f"  ⚠️  {module_desc}: 導入失敗 ({str(e)[:50]}...)")
            checks["⚠️  警告"].append(f"{module_desc} 導入失敗")
    
    # ========== 檢查 5: Protocol L 模組 (可選) ==========
    print("\n【5】檢查 Protocol L 模組 (可選)...")
    
    try:
        from scripts.gear2_rnd.vault_database import VaultDatabase
        print("  ✅ VaultDatabase: 已就緒")
        checks["✅ 通過"].append("Protocol L 完全就緒")
    except ImportError:
        print("  ⚠️  VaultDatabase: 未安裝 (可選功能，Bot 仍可運行)")
        checks["⚠️  警告"].append("Protocol L 未安裝")
    
    # ========== 檢查 6: 核心目錄 ==========
    print("\n【6】檢查核心目錄...")
    
    required_dirs = {
        "assets/video_clips": "視頻素材",
        "assets/sfx": "音效素材",
        "assets/final_exports": "成品輸出",
        "logs": "日誌目錄",
    }
    
    for dir_path, dir_desc in required_dirs.items():
        full_path = PROJECT_ROOT / dir_path
        if full_path.exists():
            print(f"  ✅ {dir_desc}: {dir_path}")
            checks["✅ 通過"].append(f"目錄存在: {dir_path}")
        else:
            print(f"  ⚠️  {dir_desc}: 缺失 ({dir_path})")
            print(f"     嘗試建立...")
            full_path.mkdir(parents=True, exist_ok=True)
            checks["⚠️  警告"].append(f"目錄已建立: {dir_path}")
    
    # ========== 檢查 7: 可選檢查 - Telegram Bot Token 有效性 ==========
    print("\n【7】驗證 Telegram Bot Token [選擇性]...")
    
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token:
        try:
            import asyncio
            from telegram import Bot
            
            async def verify_token():
                try:
                    bot = Bot(token=telegram_token)
                    me = await bot.get_me()
                    return True, me.username
                except Exception as e:
                    return False, str(e)
            
            result, info = asyncio.run(verify_token())
            if result:
                print(f"  ✅ Bot Token 有效: @{info}")
                checks["✅ 通過"].append("Telegram Bot Token 有效")
            else:
                print(f"  ❌ Bot Token 無效: {info}")
                checks["❌ 失敗"].append("Telegram Bot Token 無效")
        except Exception as e:
            print(f"  ⚠️  無法驗證 Token: {str(e)[:50]}...")
            checks["⚠️  警告"].append("Token 驗證失敗")
    
    return checks


def print_summary(checks):
    """打印摘要"""
    print("\n" + "=" * 70)
    print("📊 檢查摘要")
    print("=" * 70)
    
    total = sum(len(v) for v in checks.values())
    passed = len(checks["✅ 通過"])
    warnings = len(checks["⚠️  警告"])
    failed = len(checks["❌ 失敗"])
    
    print(f"\n✅ 通過: {passed} 項")
    for item in checks["✅ 通過"]:
        print(f"   • {item}")
    
    if warnings > 0:
        print(f"\n⚠️  警告: {warnings} 項")
        for item in checks["⚠️  警告"]:
            print(f"   • {item}")
    
    if failed > 0:
        print(f"\n❌ 失敗: {failed} 項")
        for item in checks["❌ 失敗"]:
            print(f"   • {item}")
    
    print("\n" + "-" * 70)
    
    if failed > 0:
        print("❌ **環境檢查失敗** - Bot 無法啟動")
        print("   請修復上述失敗項目後重試")
        return False
    elif warnings > 0:
        print("⚠️  **環境檢查通過（帶警告）** - Bot 可啟動")
        print("   若功能異常，請檢查警告項目")
        return True
    else:
        print("✅ **環境檢查完成** - Bot 已就緒！")
        print("   可以安全地啟動 Telegram Bot")
        return True


def main():
    """主程式"""
    try:
        checks = check_environment()
        success = print_summary(checks)
        
        print("\n" + "=" * 70)
        if success:
            print("\n🚀 啟動 Bot:")
            print("   python scripts/start_telegram_bot.py")
        else:
            print("\n🔧 修復建議:")
            print("   1. 檢查 .env 文件中的環境變數")
            print("   2. 執行 pip install -r requirements.txt")
            print("   3. 確認所有必要目錄已建立")
        
        print("\n" + "=" * 70)
        
        sys.exit(0 if success else 1)
    
    except Exception as e:
        print(f"\n❌ 檢查過程出錯: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
