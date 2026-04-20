# 🎛️ Telegram CEO 遠端遙控儀表板 - 快速啟動指南 (v15.4)

## 📋 概覽

`telegram_bot_manager.py` 是一個功能完整的 Telegram Bot，為 Mac mini (無頭伺服器) 提供遠端控制能力：

- ✅ **全自動產線啟動** - 遠端一鍵啟動 `pipeline_runner.py`
- ✅ **動態素材選擇** - 即時選擇背景影片 + 環境音效
- ✅ **金庫查詢** - 實時顯示 Protocol L 音樂庫存狀態
- ✅ **成品交付** - 自動發送 YouTube CheatSheet 和 MP4 影片
- ✅ **安全驗證** - 基於 Telegram User ID 的身份認證
- ✅ **併發防護** - Asyncio.Lock 防止重複觸發

---

## 🚀 快速啟動

### 1️⃣ 前置要求

```bash
# ✅ 已滿足的依賴
- python-telegram-bot >= 22.7
- aiohttp (自動安裝)
- 現有的 AI Drama Factory 環境

# ✅ 檢查安裝
python -m pip list | grep telegram
```

### 2️⃣ 環境配置 (.env)

在 `.env` 文件中確保已設定以下變數：

```env
# CEO Bot 授權（請向 @BotFather 取得真實 Token，勿將實值提交 Git）
TELEGRAM_BOT_TOKEN="123456789:ABCDefGhiJklmnoPqRstuvWxyz"
TELEGRAM_ALLOWED_USER_ID="your-telegram-user-id"

# 可選：Protocol L 配置 (金庫查詢)
TTAPI_KEY="your-ttapi-master-key"
TT_BASE_URL="https://api.ttapi.io"
```

### 3️⃣ 啟動 Bot

**方式 A：直接執行啟動腳本**

```bash
python scripts/start_telegram_bot.py
```

**方式 B：在 Mac mini 後臺常駐**

```bash
# 使用 nohup 在後臺運行
nohup python scripts/start_telegram_bot.py > logs/telegram_bot.log 2>&1 &

# 使用 systemd (生產推薦)
# 詳見下方 [部署到 systemd]
```

### 4️⃣ 在 Telegram 中與 Bot 互動

添加 Bot 為聯絡人，然後：

```
/start          # 顯示主菜單
/menu           # 重新顯示主菜單
/status         # 查看系統狀態
```

---

## 📊 主菜單功能詳解

```
🎛️ CEO 遠端遙控儀表板

┌─────────────────────────────┐
│ 🚀 啟動全自動產線            │  ← 執行 pipeline_runner.py
├─────────────────────────────┤
│ 🧠 獲取明日靈感              │  ← 調用 GLM 生成提示詞
├─────────────────────────────┤
│ 🎬 自訂視覺發行              │  ← 選擇視頻 + SFX 組合
├─────────────────────────────┤
│ 💰 查詢音樂金庫              │  ← 顯示 Protocol L 統計
├─────────────────────────────┤
│ 🧹 靶場重置                  │  ← 清空庫存 (確認)
└─────────────────────────────┘
```

### 核心功能流程

#### **🚀 啟動全自動產線**

1. 檢查 Mutex Lock (防止重複運行)
2. 啟動 `pipeline_runner.py`：
   - Suno/DistroKid 生圖生音
   - FFmpeg 混音 (+ SFX 4% 音量)
   - 自動入庫 Protocol L
3. 等待完成，發送成品

#### **🎬 自訂視覺發行**

1. 掃描 `assets/video_clips/` 動態生成視頻選擇菜單
2. 掃描 `assets/sfx/` 動態生成音效選擇菜單
3. 確認選擇後執行：
   ```bash
   python pipeline_runner.py \
     --bg-video assets/video_clips/YOUR_VIDEO.mp4 \
     --sfx assets/sfx/YOUR_SFX.wav
   ```

#### **💰 查詢音樂金庫**

顯示 Protocol L 統計：
- 總音檔數
- 總衍生次數
- 平均衍生次數
- 最常使用的音檔排行

#### **🧠 獲取明日靈感**

調用 GLM-4-Plus 生成 5 組創意提示詞：
```
prompt_000.txt → 暖心居家 + 下雨聲
prompt_001.txt → 夜深人靜 + 窗外流量
...
```

---

## 🔒 安全機制

### User ID 驗證

```python
ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID"))

# 只有授權的 CEO User ID 可以操作
if user_id != ALLOWED_USER_ID:
    await message.reply_text("❌ 無授權的訪問")
```

### Mutex Lock (產線防撞)

```python
PIPELINE_LOCK = asyncio.Lock()

async with PIPELINE_LOCK:
    if PIPELINE_RUNNING:
        return "⏳ 產線運轉中..."
    PIPELINE_RUNNING = True
    # 執行產線...
    PIPELINE_RUNNING = False
```

### 非同步執行 (無阻塞)

```python
# 使用 asyncio.create_subprocess_exec 避免阻塞 Bot
process = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE
)
stdout, stderr = await process.communicate()
```

---

## 📁 文件結構

```
scripts/
├── common/
│   └── telegram_bot_manager.py     ← ✨ Bot 核心邏輯 (500+ 行)
├── start_telegram_bot.py           ← ✨ 啟動腳本與環境檢查
└── gear1_prod/
    └── pipeline_runner.py          ← 已整合 Telegram 指令參數

.env                                ← ✅ 已更新 TELEGRAM_ALLOWED_USER_ID
```

---

## 🧪 測試與除錯

### 測試 Bot 連線

```bash
# 驗證 Token 有效性
python -c "
from telegram import Bot
import asyncio
import os

async def test():
    bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
    me = await bot.get_me()
    print(f'✅ Bot 連線成功: @{me.username}')

asyncio.run(test())
"
```

### 即時日誌

```bash
# 監控 Bot 運行日誌
tail -f logs/telegram_bot.log

# 格式範例
[TELEGRAM_BOT][2025-04-04 14:30:45][INFO] 🤖 Telegram Bot Manager 啟動中...
[TELEGRAM_BOT][2025-04-04 14:30:47][INFO] ✅ Bot 已連接，等待 CEO 指令...
[TELEGRAM_BOT][2025-04-04 14:31:02][INFO] 🚀 產線已啟動，開始執行全自動流程...
```

### 常見問題排查

| 問題 | 原因 | 解決方案 |
|------|------|---------|
| `ImportError: No module named 'telegram'` | python-telegram-bot 未安裝 | `pip install python-telegram-bot` |
| `❌ 無授權的訪問` | User ID 不匹配 | 確認 .env 中的 TELEGRAM_ALLOWED_USER_ID |
| `⏳ 產線正在運轉` | Mutex Lock 防護作用 | 等待前一個任務完成 |
| `Bot 無回應` | Token 失效或網路問題 | 從 BotFather 獲取新 Token |

---

## 🌐 部署到 systemd (Mac mini 推薦)

### 1. 建立 systemd service 檔案

```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

### 2. 粘貼以下內容

```ini
[Unit]
Description=AI Drama Factory - Telegram CEO Bot Manager
After=network.target

[Service]
Type=simple
User=ai_user
WorkingDirectory=/Volumes/AI_Workspace/AI_Drama_Factory
Environment="PATH=/Volumes/AI_Workspace/envs/openclaw_project/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/Volumes/AI_Workspace/envs/openclaw_project/bin/python scripts/start_telegram_bot.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 3. 啟動服務

```bash
# 重新加載配置
sudo systemctl daemon-reload

# 啟動 Bot
sudo systemctl start telegram-bot

# 設定開機自啟
sudo systemctl enable telegram-bot

# 檢查狀態
sudo systemctl status telegram-bot

# 實時日誌
sudo journalctl -u telegram-bot -f
```

---

## 📈 效能指標

| 項目 | 數值 | 備註 |
|------|------|------|
| **Bot 啟動時間** | ~2-3 秒 | 首次必要依賴載入 |
| **菜單響應延遲** | <100ms | 純按鈕交互 |
| **產線執行時間** | ~2-3 分鐘 | 依賴影片長度和 FFmpeg 性能 |
| **成品上傳速度** | 50MB/分鐘 | Telegram 伺服器限制 |
| **併發防護** | 即時 | Asyncio.Lock 零延遲判定 |

---

---

## 🌐 Webhook 模式（v15.4 新增）

> **為什麼要用 Webhook？**  
> Polling 模式每隔數秒向 Telegram 詢問「有新訊息嗎？」，浪費 CPU 與網路。  
> Webhook 模式讓 **Telegram 主動 POST 更新給 Bot**，延遲更低（<100ms）、資源更省。

### Webhook 與 Polling 對比

| 指標 | Polling（舊）| Webhook（新）|
|------|------------|------------|
| 訊息延遲 | 1-3 秒 | <100ms |
| CPU 佔用 | 持續輪詢 | 只在有訊息時喚醒 |
| 需要公網 IP | 否 | 是（或 ngrok 隧道）|
| 適用環境 | 本地開發 | 生產伺服器 / ngrok |

---

### 🚇 方式 A：ngrok 隧道（Windows 開發機推薦）

```bash
# 第 1 步：安裝 pyngrok（自動管理 ngrok）
pip install pyngrok

# 第 2 步：一鍵啟動（自動建立隧道 + 啟動 Webhook Bot）
python scripts/start_telegram_bot.py --ngrok
```

> pyngrok 會自動下載 ngrok 執行檔並建立 HTTPS 隧道，無需手動設定。  
> 每次重啟會取得新的隨機 URL（免費版限制），重啟後 Telegram 會自動更新 Webhook。

若需使用固定 ngrok 域名（ngrok 付費功能），在 `.env` 設定後直接用 `--webhook`：
```bash
# .env
TELEGRAM_WEBHOOK_URL=https://your-static-domain.ngrok-free.app
TELEGRAM_WEBHOOK_PORT=8443

# 啟動
python scripts/start_telegram_bot.py --webhook
```

---

### 🖥️ 方式 B：Mac mini 生產伺服器（固定 IP / 自定域名）

**前提**：Mac mini 有公網 IP 或已設定 DDNS，以及有效的 HTTPS 憑證。

```bash
# .env（Mac mini 設定）
TARGET_ENV=MAC_M4
WORKSPACE_ROOT=/Volumes/AI_Workspace/AI_Drama_Factory
# 建議：獨立虛擬環境放在 /Volumes/AI_Workspace/envs/openclaw_project
TELEGRAM_WEBHOOK_URL=https://rs-echoes.yourdomain.com
TELEGRAM_WEBHOOK_PORT=8443
TELEGRAM_WEBHOOK_SECRET=your-random-secret-string
```

```bash
# 直接啟動 Webhook 模式
python scripts/start_telegram_bot.py --webhook

# 或背景常駐（nohup）
nohup python scripts/start_telegram_bot.py --webhook \
  > /var/log/rs_telegram_bot.log 2>&1 &
```

**若無域名但有固定公網 IP**，可使用 Let's Encrypt 免費 SSL：
```bash
# 安裝 certbot 後取得憑證
sudo certbot certonly --standalone -d YOUR_IP_AS_DOMAIN
```

---

### 🔄 自動模式（預設）

不加任何旗標時，啟動器會自動判斷：
```
.env 中有 TELEGRAM_WEBHOOK_URL → Webhook 模式
.env 中無 TELEGRAM_WEBHOOK_URL → Polling 模式（安全降級）
```

```bash
python scripts/start_telegram_bot.py   # 自動決定
```

---

### 🧪 驗證 Webhook 是否成功

啟動後可透過 Telegram Bot API 確認：
```bash
# 替換 YOUR_TOKEN
curl https://api.telegram.org/botYOUR_TOKEN/getWebhookInfo
```

預期回應：
```json
{
  "ok": true,
  "result": {
    "url": "https://abc123.ngrok-free.app/YOUR_TOKEN",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "last_error_date": null
  }
}
```

---

## 🎯 開發計畫

- [x] **Webhook 支援** ✅ v15.4 已實作（polling/webhook/ngrok 三模式）
- [ ] **進度條** - 顯示產線執行進度（Upload Video Queue）
- [ ] **多用戶支援** - 允許多個授權的 CEO 帳號
- [ ] **定時任務** - 支持排隊執行（如「明天早上 8 點執行」）
- [ ] **人工審核集成** - 從 Telegram 直接審核音樂 + 上傳

---

## 📞 技術支援

若遇到問題，請檢查：

1. ✅ `.env` 檔案是否正確設定
2. ✅ `python-telegram-bot` 是否已安裝
3. ✅ Telegram Bot Token 是否有效
4. ✅ User ID 是否正確
5. ✅ 網路連線是否穩定

查看日誌：

```bash
# 即時監控
tail -f logs/telegram_bot.log

# 完整日誌
cat logs/telegram_bot.log | grep ERROR
```

---

**🚀 系統就緒！CEO 可以開始通過 Telegram 遠端控制 Mac mini 了！**

