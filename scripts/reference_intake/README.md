# reference_intake — 素材攝取工作流（每日）

> **2026-09-14 改版（CEO 指示）**。權威文件：`架構說明書_v16.1.md` §4.7／§4.8。

> **2026-09-17 停用（CEO 指示）**：每日搜尋排程已取消（launchd `com.aidramafactory.reference.intake` 已 unload＋disable）。RCA 結論：**Pexels 金鑰有效**；403「error code: 1010」＝ Cloudflare 封鎖非瀏覽器 UA（瀏覽器 UA 實測 200）——已於 `stock_search.py` 全域修復 UA。工具保留供手動／日後重啟。重新啟用：`launchctl enable gui/$(id -u)/com.aidramafactory.reference.intake && launchctl load ~/Library/LaunchAgents/com.aidramafactory.reference.intake.plist`

## 一句話

Mac 每天 02:00 自動搜尋免費圖庫 → 下載到**固定資料夾** `inbox/` → CEO 檢視並把要用的圖移至 `CEO/02_素材與CP-D/VEO_download/Approved_material/` → **未移出者隔日 02:00 自動刪除**。

## 資料夾（Mac: `/Volumes/AI_Workspace/AI_Drama_Factory/assets/reference_intake/`）

| 路徑 | 用途 |
|---|---|
| `inbox/` | **唯一固定投遞夾**（不再有 `2026-Wxx/` 子夾）；含 `manifest.json`（逐檔 provenance＋sha256＋`run_date`） |
| `_state/seen_assets.json` | 跨日去重註冊表（曾下載過的 provider id；清 inbox 不會清它） |
| `cp_d/` | 世界草案審核包——**暫停產出**（待改版為以 Approved_material 為輸入） |

## 排程（Mac launchd）

- `com.aidramafactory.reference.intake` → **每日 02:00**（TZ Asia/Taipei）
- 入口：`daily_intake.py`（先清舊 → 跑 `stock_search.py` → Telegram 摘要）
- 日誌：`~/Library/Logs/AI_Drama_Factory/reference_intake.{out,err}.log`

## 清除規則

- `daily_intake.py` 啟動時刪除 `inbox/` 中**超過 18 小時**的檔案（先清後抓；同日手動重跑不會誤刪當日批次）；判準取 **max(mtime, 出生時間, ctime)**——複製進來但時間戳很舊的素材（CEO 上傳）不會被誤刪
- 清除範圍＝`inbox/` 全樹（含任何子夾）；清完自動移除空子夾；`_state/` 位於 inbox 之外、永不受影響
- CEO 已移至 `Approved_material/` 的檔案不受影響（已離開 inbox）

## CEO 審核交接（新流程）

1. **瀏覽**：`Y:\AI_Drama_Factory\assets\reference_intake\inbox\`（或 Mac 對應路徑）
2. **採用**：手動移動到 `F:\AI_DRAMA_FACTORY\CEO\02_素材與CP-D\VEO_download\Approved_material\`
3. **首幀素材池**＝`first_frames/`＋`VEO_download/`＋`VEO_download/Approved_material/`；索引重建工具：`python scripts/reference_intake/pool_manifest.py`

## 去重

- 下載前比對 `_state/seen_assets.json`（provider＋id）；命中即跳過並印 `[skip]`
- 下載成功後登記（原子寫入）；`--force` 只影響「同日已抓」守衛，不影響去重

## CLI

| 指令 | 用途 |
|---|---|
| `.venv/bin/python3 scripts/reference_intake/daily_intake.py --dry-run` | 驗證（不連網、不清除） |
| `daily_intake.py --force` | 略過「今日已抓」守衛（除錯用） |
| `stock_search.py --world 伸展台之夢 --limit 6` | 手動定向補抓（寫入固定夾） |
| `pool_manifest.py` | 重建首幀池 `manifest.json` |

## 金鑰

- Mac：`~/Library/Application Support/AI_Drama_Factory/reference_intake.env`（chmod 600）
- 傳輸工具：`stage_keys_for_transfer.py`／`install_keys_from_env.py`（值不入對話、不進版控）

## CEO 隨時增刪（韌性設計）

CEO 可隨時**上傳或刪除**下列資料夾內容，程式一律容錯、不需停機、不需預告：

| 資料夾 | 情境 | 行為 |
|---|---|---|
| `inbox/`（Y:） | 上傳（含舊時間戳拷貝） | **max(mtime, 出生時間, ctime)** 判準保護；18h 審核視窗照算 |
| `inbox/`（Y:） | 刪檔／刪整個資料夾 | 列舉／stat／寫入逐項防護；資料夾不存在時 `stock_search.py` 自動重建 |
| `VEO_download/`＋`Approved_material/`（F:） | 增刪 | `pool_manifest.py` 重建即反映現況；資料夾缺失→略過；半途消失→計入 `skipped` |
| `cp_d/`（Y:） | 增刪 | 目前無自動讀者（草案引擎暫停）；改版時比照同等容錯 |
| `manifest.json`（inbox／池） | 被刪或半寫 | 視為空並重建；seen 註冊表寫入採原子替換 |

> 重建索引：`python scripts/reference_intake/pool_manifest.py`（任何時候都可跑，反映當下實況）

## 已暫停

- `world_proposal.py`（世界草案引擎）：等待以 `Approved_material` 為輸入的改版設計；不再由 intake 自動觸發。
