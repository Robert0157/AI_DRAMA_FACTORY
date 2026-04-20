# Windows 工作排程器：自動同步 `queue_staging` → Mac

目標：每隔幾分鐘執行 `sync_queue_staging_to_mac.ps1`，將本機新歌目錄同步到 Mac，**不需手動開終端**。

## 前置條件

1. **Git for Windows**（內含 `rsync.exe`），預設路徑之一存在：
   - `C:\Program Files\Git\usr\bin\rsync.exe`
2. **SSH 免密登入 Mac**（必須，否則 `BatchMode=yes` 會失敗）  
   - Windows 產生金鑰後，將公鑰加入 Mac `~/.ssh/authorized_keys`
3. **路徑已對齊**（腳本預設）  
   - 本機：`F:\AI_DRAMA_FACTORY\Streaming\queue_staging`  
   - Mac：`robert@192.168.1.111:/Volumes/AI_Workspace/AI_Drama_Factory/Streaming/queue_staging`  
   - 若你的 repo 不在 `F:\`，請改下面指令中的 `-File` 路徑，或改腳本參數。

---

## 方式 A：`schtasks` 一鍵建立（複製貼上）

以 **每 5 分鐘** 跑一次為例（請用「以系統管理員身分」開啟 PowerShell 或一般使用者皆可，視你環境）：

```powershell
schtasks /Create /F /TN "RS_Echoes_SyncQueueStaging" /SC MINUTE /MO 5 /RL LIMITED /RU "%USERNAME%" `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"F:\AI_DRAMA_FACTORY\scripts\streaming_steam\sync_queue_staging_to_mac.ps1\""
```

立即手動跑一次測試：

```powershell
schtasks /Run /TN "RS_Echoes_SyncQueueStaging"
```

查看上次結果（排程器 GUI 亦可）：

```powershell
schtasks /Query /TN "RS_Echoes_SyncQueueStaging" /V /FO LIST
```

刪除排程：

```powershell
schtasks /Delete /F /TN "RS_Echoes_SyncQueueStaging"
```

### 僅試跑（不寫入 Mac，dry-run）

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "F:\AI_DRAMA_FACTORY\scripts\streaming_steam\sync_queue_staging_to_mac.ps1" -DryRun
```

---

## 方式 B：工作排程器 GUI

1. `Win + R` → `taskschd.msc`
2. **建立基本工作** → 名稱：`RS_Echoes_SyncQueueStaging`
3. 觸發程序：**每天**或**一次**後，在內容裡改為「重複工作間隔」**5 分鐘**、持續時間「無限期」（依你需求）
4. 動作：**啟動程式**
   - 程式：`powershell.exe`
   - 引數：`-NoProfile -ExecutionPolicy Bypass -File "F:\AI_DRAMA_FACTORY\scripts\streaming_steam\sync_queue_staging_to_mac.ps1"`
5. 設定：可勾選「如果工作已在執行，則不啟動新執行個體」（避免 rsync 重疊）

---

## 與 Mac 上播流程

- 同步目標為 **`queue_staging`**，**不會自動上播**。
- 上線仍由 **`rotate_live_slot.sh`**（或你手動 `mv` + 改 manifest）負責，避免傳輸未完成就被 ffmpeg 讀取。
