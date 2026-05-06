# Streaming／OBC：多支 1 小時 MP4 + 純 FFmpeg RTMP（Mac mini 24/7）

**與白皮書對齊**：請以 **`架構說明書_v15.10.md`** 之 `Streaming/` 小節與 Mac 兩階段部署為準；本檔為操作細節補充。

`Streaming/` 目錄在 repo 根 `.gitignore` 內（大檔、金鑰不進版控）。本資料夾提供**可進 git 的腳本與約定**，複製到 Mac 後與 `$WORKSPACE_ROOT/Streaming/` 搭配使用（Mac 正式根目錄：`/Volumes/AI_Workspace/AI_Drama_Factory`）。**舊名 `Steam/` 已廢止**，請將本機資料夾更名為 `Streaming/`（若仍見 `Steam`，請手動改名並更新環境變數 `STREAMING_ROOT`；相容：`STEAM_ROOT`）。

## `build_concat_playlist.sh` 優先順序（opt-in manifest）

| 優先 | 條件 | 行為 |
|------|------|------|
| **1** | `Streaming/config/live_manifest.json` **存在** | 呼叫 `emit_concat_from_manifest.py`：依 `entries[].slot` 排序，檢查 `queue/<file>` 皆存在，輸出 concat 行。需 **python3**。 |
| **2** | 無 manifest，但有 `Streaming/queue/order.txt` | 依 `order.txt` 一行一檔名（同舊行為）。 |
| **3** | 兩者皆無 | 掃 `queue/*.mp4` 依檔名字串排序。 |

若要停用 manifest：暫時將 `live_manifest.json` **移出** `config/`（或改名），再跑 `build_concat_playlist.sh` 即可回到 order／排序模式。

## `live_manifest.json` 格式（schema_version 1）

- **`expected_slots`**（選用）：若填 **24**，則 `entries` 必須剛好 24 筆；營運上可做「24 小時一輪」硬把關。未填則只要求 `entries` 非空。
- **`entries`**：每筆 `{ "slot": 整數 ≥1, "file": "僅檔名.mp4" [, "added_at": "ISO-8601"] }`；`file` **不可**含 `/`、`\`（禁止路徑穿越）；實體檔必須在 `Streaming/queue/`。
- **`added_at`**（選用於 concat，**輪換必填**）：例如 `2026-04-19` 或 `2026-04-19T12:00:00Z`。`emit_concat_from_manifest.py` 會忽略此欄；`rotate_live_manifest.py` 若缺則報錯。
- **排序**：輸出 concat 時依 `slot` **遞增**（與 JSON 陣列順序無關）。

範本：**`live_manifest.example.json`**（24 槽占位檔名 `live_slot_01.mp4`…）。複製到 Mac：

```bash
cp scripts/streaming_steam/live_manifest.example.json "$STREAMING_ROOT/config/live_manifest.json"
# 編輯 file 為真實檔名，並確保 queue/ 內有對應 MP4
```

## 為什麼用 concat，而不是每首重開 ffmpeg？

- **一支 ffmpeg、一路 RTMP**：concat demuxer 把多個 MP4 串成**一條連續時間軸**，接縫處仍為同一個 ingest 連線。
- **若每播完一首就重開 ffmpeg**：YouTube 端會視為**斷線重連／新段**，不利「單一直播間 24/7」體感與後台統計。
- **與顧問方案一致**：仍可用 **`-c:v copy -c:a copy`**（各檔編碼參數需一致，你們產線輸出通常已一致）。

## 營運策略（CEO 已定案）：**方案乙** — 24/7 連播優先

- **目標**：頻道 **長時間在線、不中斷 ingest**；**不**以「關播後是否留下一支完整 VOD」為 KPI。
- **因此**：**不必**為了 YouTube 常見的 **DVR／封存時間窗**（顧問提及約 **12 小時**量級）而實施 **定時斷流、重開 ffmpeg、硬切成 12 小時 unique 輪**；維持 **`concat` + `-stream_loop -1`** 單一 RTMP 無限循環即可。
- **`expected_slots`（例如 24）**：仍代表「一輪不重複時間軸要多長」的**營運與排程語意**（例如 24 支 × 1h），**不是**強迫對齊 YouTube 的封存上限；日後若改追求 VOD 長尾，再另評估「分段 ingest」等做法。
- **仍建議**：母帶在本地與冷備 **自行留存**；YouTube 後台行為以官方說明為準。

## 建議目錄（在 Mac 上，與 `WORKSPACE_ROOT` 同碟，例如外接 SSD）

```
Streaming/
├── queue/                 # 當前輪播用 1hr MP4（檔名須與 manifest 或 order.txt 一致）
├── queue_staging/         # 新片先放此，校驗完再一次 mv 進 queue/（勿 in-place 覆寫正在播的檔）
├── config/
│   ├── live_manifest.json     # 選用：存在則優先驅動 concat 順序（24 槽等）
│   └── concat_playlist.txt    # 由 build_concat_playlist.sh 產生
├── secrets/
│   └── rtmp.env           # YOUTUBE_RTMP_URL="rtmp://..."（勿提交 git）
├── frozen_broadcast/      # 選用：播出退役檔（勿與金庫 dc≥3「冷凍」混名）
└── logs/
```

## 實際流程（與製片產線的銜接）

1. **Windows 產線**：照常輸出 1hr 母帶 MP4。
2. **上架到直播夾**：複製到 Mac 的 `Streaming/queue_staging/`，確認可播放。
3. **進線／輪換**：手動可 `mv` 進 `queue/` 並手改 manifest；若用 **manifest 輪換策略**，請跑 **`rotate_live_slot.sh <新檔名>`**（自 staging 搬入並更新 `added_at`）。無 manifest 時則維護 `order.txt`。
4. **重產 concat**：維護視窗內執行 `build_concat_playlist.sh`；必要時**重啟** `run_youtube_rtmp.sh` 讓 ffmpeg 讀新清單。
5. **推流**：`run_youtube_rtmp.sh`（見腳本內註解）。

## `rotate_live_slot.sh` — 固定替換 **added_at 最小** 槽位

- **規則**：在所有 `entries` 中找 **`added_at` 最小** 者；若同分則 **`slot` 較小** 者勝出。
- **動作**（非 `--dry-run` 時，預設 `deferred`）：
  1. 將 `queue_staging/<新檔純檔名>` **移入** `queue/<新檔>`。
  2. **原子寫回** `config/live_manifest.json`：該槽 `file` 改為新檔名、`added_at` 改為當下 UTC（`...Z`）。
  3. 舊檔預設先留在 `queue/`（避免熱抽換碰到 ffmpeg 讀檔）；後續由 `cleanup_retired_queue.py` 依檔齡清理。
  4. 若在維護窗且接受風險，可加 `--retire-mode immediate` 立即搬舊檔到 `frozen_broadcast/`。
- **前置**：每筆 `entries` 必須已有 **`added_at`**；新歌已在 **`queue_staging/`**；`queue/` 內舊檔存在；新檔名未被其他槽位占用。

```bash
export STREAMING_ROOT="/Volumes/AI_Workspace/AI_Drama_Factory/Streaming"
# 先放入 staging
cp ./MyNew1Hr.mp4 "$STREAMING_ROOT/queue_staging/MyNew1Hr.mp4"
./scripts/streaming_steam/rotate_live_slot.sh --dry-run MyNew1Hr.mp4   # 確認將替換哪一格
./scripts/streaming_steam/rotate_live_slot.sh MyNew1Hr.mp4
# 可選：立即退役舊檔（維護窗使用）
# ./scripts/streaming_steam/rotate_live_slot.sh --retire-mode immediate MyNew1Hr.mp4
# deferred retire 清理（例如每日排程）
python3 ./scripts/streaming_steam/cleanup_retired_queue.py --streaming-root "$STREAMING_ROOT" --min-age-hours 24
./scripts/streaming_steam/build_concat_playlist.sh
# 維護視窗內視需要重啟 run_youtube_rtmp.sh
```

- **兩日一換**：由 Mac **`launchd` 每兩天呼叫** 上述指令（或包一層你自己的 shell），本 repo 不強制 cron 表；屬 **內容代謝節拍**，**不是**為滿足 YouTube 約 12 小時 DVR／封存傳聞而「定時斷流」（方案乙下無此需求）。
- **90／100 冷凍水位告警**：仍建議另用小型檢查腳本／Reporter；未內建於 `rotate_live_slot.sh`。
- **產線 Python**：不必為輪播修改；若日後要「產線收尾自動 copy 到 staging」再另開需求。

## Windows -> SSH/scp -> Mac 正式根目錄（可直接貼上）

> Mac mini 正式根目錄固定為：`/Volumes/AI_Workspace/AI_Drama_Factory`

### 1) 建立目錄與驗證掛載（從 Windows PowerShell）

```powershell
ssh robert@192.168.1.111 "mkdir -p /Volumes/AI_Workspace/AI_Drama_Factory/Streaming/{queue,queue_staging,config,secrets,logs} && ls -la /Volumes/AI_Workspace/AI_Drama_Factory/Streaming"
```

### 2) 同步腳本（Windows -> Mac）

```powershell
scp -r .\scripts\streaming_steam robert@192.168.1.111:/Volumes/AI_Workspace/AI_Drama_Factory/scripts/
```

### 3) 同步測試 MP4（第一輪/第二輪）

```powershell
scp .\Streaming\queue\steam_round12_test_01.mp4 robert@192.168.1.111:/Volumes/AI_Workspace/AI_Drama_Factory/Streaming/queue/
scp .\Streaming\queue\steam_round12_test_02.mp4 robert@192.168.1.111:/Volumes/AI_Workspace/AI_Drama_Factory/Streaming/queue/
```

### 4) 在 Mac 端執行第一輪/第二輪（SSH 一次跑完）

```powershell
ssh robert@192.168.1.111 "cd /Volumes/AI_Workspace/AI_Drama_Factory && export STREAMING_ROOT=/Volumes/AI_Workspace/AI_Drama_Factory/Streaming && cp scripts/streaming_steam/live_manifest.example.json \$STREAMING_ROOT/config/live_manifest.json && bash scripts/streaming_steam/build_concat_playlist.sh && cd \$STREAMING_ROOT/config && ffmpeg -hide_banner -loglevel warning -t 15 -re -f concat -safe 0 -stream_loop -1 -i concat_playlist.txt -c copy -f null -"
```

### 5) 快速檢查結果

```powershell
ssh robert@192.168.1.111 "ls -la /Volumes/AI_Workspace/AI_Drama_Factory/Streaming/config && tail -n 20 /Volumes/AI_Workspace/AI_Drama_Factory/Streaming/config/concat_playlist.txt"
```

## 驗證建議

- **第一輪 + 第二輪（本機、不連 YouTube）**：在 repo 根目錄執行  
  `.\scripts\streaming_steam\validate_local_round12.ps1`（Windows）  
  會依 `live_manifest.json` 產生 `concat_playlist.txt`，再以 ffmpeg **約 15 秒** `copy` 解到 `null` 驗證 concat。  
  Mac／Linux 可：`export STREAMING_ROOT=...`（相容 `STEAM_ROOT`）後執行 `build_concat_playlist.sh`，再於 `Streaming/config/` 手動跑第二輪 ffmpeg 指令（見腳本內註解）。
- **第三輪（RTMP → YouTube，建議先用測試金鑰）**：  
  - **Windows**：`Streaming/secrets/rtmp.env`（可自 `scripts/streaming_steam/rtmp.env.template` 複製），或先設 `$env:YOUTUBE_RTMP_URL='rtmp://...'`（優先於檔案）；再執行 `.\scripts\streaming_steam\run_youtube_rtmp.ps1`（可加 `-Once` 只做單次 ffmpeg、不迴圈重試）。  
  - **Mac／Linux**：`./scripts/streaming_steam/run_youtube_rtmp.sh`（行為與上對齊：concat + copy、退出後 5 秒重試）。  
  先用**測試直播**金鑰觀察 concat 接縫與 YouTube 後台丟幀，再換正式金鑰。
- **`.sh` 換行**：請維持 **LF**；repo 已對 `scripts/streaming_steam/*.sh` 設 `.gitattributes`；若本機仍見 `bash\r`，請 `git checkout --` 該檔或重新存成 LF。
- 變更 manifest 後務必重新執行 `build_concat_playlist.sh` 並視情況重啟 ffmpeg。

## 腳本一覽

| 檔案 | 用途 |
|------|------|
| `build_concat_playlist.sh` | 產出 `Streaming/config/concat_playlist.txt`（manifest → order → 排序） |
| `emit_concat_from_manifest.py` | 讀 manifest，驗證後印出 concat 行 |
| `rotate_live_slot.sh` | 呼叫 `rotate_live_manifest.py`（`--dry-run` / `--retire-mode`） |
| `rotate_live_manifest.py` | **added_at 最小**槽位：預設 deferred retire，staging→`queue/`、原子寫 manifest |
| `cleanup_retired_queue.py` | 清理 queue 中已不在 manifest 的舊檔（按檔齡門檻移入 `frozen_broadcast/`） |
| `live_manifest.example.json` | 24 槽 JSON 範本（含 `added_at`） |
| `run_youtube_rtmp.sh` | 讀 `rtmp.env`，ffmpeg 推流（外層自動重啟；Mac／Linux） |
| `run_youtube_rtmp.ps1` | 同上（第三輪；Windows PowerShell） |
| `normalize_to_staging.sh` | Ingest Gatekeeper：48k/簽名直通，否則音訊正規化（`-c:v copy -ar 48000`） |
| `sync_queue_staging_to_mac.ps1` | Windows → Mac：`queue_staging` rsync（可加 `-RunMacGatekeeper` 落地即淨化） |
| `WINDOWS_TASK_SCHEDULER_queue_staging.md` | 工作排程器 `schtasks` 複製貼上說明 |
| `order.example.txt` | 無 manifest 時 order.txt 格式範例 |

用法見各腳本內註解。

