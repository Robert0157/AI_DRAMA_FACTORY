# Mac mini 長片上傳器 — Sidecar 通訊契約（Windows 發射台 → `Y:/Long_Queue`）

本文與 `scripts/ui/backend.py` 中 `publish_final_exports()` 行為對齊；Sidecar 使用 **`schema_version: long-upload-v1`**（Mac 工程規格）。

---

## 1. 目錄與檔名

| 項目 | 值 |
|------|-----|
| 佇列根目錄 | `Y:/Long_Queue`（Windows 掛載 SMB 後與 Mac 共享之同一資料夾） |
| 影片 | `*.mp4`，檔名由產線決定 |
| 邊車（上傳用、綠燈） | 與影片**同主檔名**、副檔名 `.json`（`long-upload-v1`） |
| metadata 副本（可選存檔／核對） | `{同主檔名}_metadata_distrokid.json`：與 Windows `final_exports` 內讀入之中繼資料相同內容（已做 Shorts 標籤清理），**不**作為上傳觸發；觸發仍以**僅**邊車 `.json` 為準。 |

---

## 2. 傳輸完成語意（綠燈）

Windows 端**保證順序**：

1. **Preflight**：先在記憶體組好邊車 JSON 並通過 `validate_long_upload_v1`；失敗則**不複製** MP4、**不寫**任一路徑之檔案（fail-closed）。
2. `shutil.copy2` 將完整 MP4 寫入 `Long_Queue`。
3. **原子寫入** `{stem}_metadata_distrokid.json`（與上傳邊車同源之已清理 metadata，供 Mac 存檔／人類核對；**非**觸發檔）。
4. **原子寫入**上傳邊車：先寫 `{stem}.json.tmp`，完成後 `replace` 為 `{stem}.json`（**綠燈**；觸發上傳以本檔為準）。

Mac 端應**僅在 `.json` 存在且可完整解析**後才視為可上傳；不應在僅有 MP4 或僅有 `.tmp` 時觸發。

若步驟 3 或 4 失敗，Windows 會嘗試刪除已複製之 MP4 及已寫入之 metadata 副本，避免半套檔案（尽力而為）。

---

## 3. Sidecar JSON — `long-upload-v1`

### 必填（規格）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `schema_version` | string | 固定 `"long-upload-v1"` |
| `video_file` | string | **必須**與同批 `.mp4` 檔名一致 |
| `title` | string | 影片標題（沿用 metadata `title`，缺則 `album_title`） |
| `description` | string | 優先為最新 `youtube_sheet_*.txt` 全文；否則 metadata `description` |
| `privacy` | string | `public` \| `unlisted` \| `private` |
| `categoryId` | string | 音樂類為 `"10"` |

### 選填（規格）

| 欄位 | 型別 |
|------|------|
| `tags` | string[] |
| `playlistId` | string |
| `notifySubscribers` | boolean |
| `idempotency_key` | string |
| `source_system` | string |
| `created_at` | ISO8601 字串（含時區） |

### Windows 額外欄位（相容／營運）

| 欄位 | 說明 |
|------|------|
| `auto_publish_enabled` | `mode=auto` → `true`；`manual` → `false` |
| `containsSyntheticMedia` | **固定 `true`**：變造／合成內容於 YouTube 申報為「是」（不受 metadata 覆寫） |
| `selfDeclaredMadeForKids` | **固定 `false`**：非兒童導向／非兒童專屬影片（對應 API `status.selfDeclaredMadeForKids`） |
| `privacyStatus` | 與 `privacy` **相同字串**，供舊讀者過渡 |

### `privacy` / `notifySubscribers` 對應 CEO 模式

| `publish_final_exports` mode | `privacy` | `notifySubscribers` |
|-------------------------------|-----------|---------------------|
| `auto` | `public` | `true` |
| `manual` | `unlisted` | `false` |

---

## 4. Preflight（Windows 端）

實作：`scripts/common/long_queue_sidecar_v1.py` 之 `validate_long_upload_v1`。

主要檢查：`schema_version`、`video_file` 檔名一致、`privacy` 合法、`categoryId` 為數字字串、`tags` 若存在則為字串陣列等。

---

## 5. Mac 端路徑約定（相對 Streaming 專案根）

- 上傳日誌：`Streaming/logs/long_video_upload.log`（`MAC_MINI_UPLOAD_LOG_REL`）
- Video ID 追蹤：`Streaming/logs/long_video_video_ids.json`（`MAC_MINI_VIDEO_ID_TRACK_REL`）

---

## 6. 壓力測試

```powershell
python scripts/ui/stress_publish_sidecar.py --runs 5 --channel lofi
```

須通過 preflight，且不得殘留 `.json.tmp`。

---

## 7. 單元測試

`tests/test_long_queue_sidecar_v1.py`
