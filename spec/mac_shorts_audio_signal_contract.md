# Shorts Audio Signal Contract (Windows ↔ Mac mini)

本文件定義 `cloud_archiver.py` 在 Windows 端遷移/刪除完成後，如何通知 Mac mini 有新批次可處理。

## 1) 路徑對照（重點）

- Windows 整理目標：`Y:\Shorts_audio\{channel}`
- Mac 掛載對應：`/Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/{channel}`

即：

- `Y:\Shorts_audio\light_music` = `/Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/light_music`
- `Y:\Shorts_audio\lofi` = `/Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/lofi`

## 2) Signal 檔案位置

每次 Windows 執行 **execute** 模式整理後，會在每個 channel 寫入：

- `Y:\Shorts_audio\light_music\.signal.json`
- `Y:\Shorts_audio\lofi\.signal.json`

Mac 端對應：

- `/Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/light_music/.signal.json`
- `/Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/lofi/.signal.json`

## 3) Signal JSON 格式（v1）

```json
{
  "schema_version": "shorts-signal-v1",
  "batch_id": "20260427_134500",
  "timestamp": "2026-04-27 13:45:00",
  "channel": "light_music",
  "mode": "EXECUTE",
  "windows_path": "Y:\\Shorts_audio\\light_music",
  "mac_mount_path": "/Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/light_music",
  "stats": {
    "moved": 12,
    "deleted": 8,
    "missing": 1,
    "failed": 0,
    "dryrun": 0
  },
  "max_actions": 20,
  "auto_sync_enabled": true
}
```

## 4) 原子寫入保證

Windows 端會先寫 `.signal.json.tmp`，再 `replace` 成 `.signal.json`。  
Mac 端只需讀 `.signal.json`，即可避免半寫入風險。

## 5) Mac mini 對接建議

Mac 端監聽器建議流程：

1. 每 10~30 秒讀取兩個 channel 的 `.signal.json`。
2. 以 `batch_id` 去重（只處理新批次）。
3. 若 `stats.moved + stats.deleted + stats.missing > 0`，執行該 channel 的後續流程。
4. 處理完回寫 ack（建議）：
   - `.../{channel}/.ack.json`
   - 內容含 `batch_id`、`handled_at`、`status`。

## 6) 與目前流程的接點

- `pipeline_runner.py` 會在完工後呼叫 `cloud_archiver.py --execute ...`
- `scripts/ui/backend.py` 的 Tab5 發行流程在 SMB 傳輸前也會呼叫 `cloud_archiver.py --execute ...`

因此，Mac 端只需依 `.signal.json` 監聽，即可接上兩條主要自動流程。

## 7) Python watcher 範例

範例腳本：`scripts/streaming_steam/mac_shorts_signal_watcher.py`

常用啟動方式：

- 單次掃描（先驗證設定）
  - `python3 scripts/streaming_steam/mac_shorts_signal_watcher.py --once --dry-run`
- 常駐輪詢（每 15 秒）
  - `python3 scripts/streaming_steam/mac_shorts_signal_watcher.py --interval-sec 15`

可選參數：

- `--base-dir`：預設 `/Volumes/AI_Workspace/AI_Drama_Factory/Short_audio`
- `--channels`：預設 `light_music,lofi`
- `--state-path`：預設 `/Volumes/AI_Workspace/AI_Drama_Factory/Short_audio/.watcher_state.json`

watcher 行為：

1. 讀 `{channel}/.signal.json`
2. 用 `batch_id` 去重
3. 若有有效變化（`moved+deleted+missing>0`）則觸發 handler
4. 回寫 `{channel}/.ack.json`
