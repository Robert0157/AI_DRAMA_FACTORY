# Workflow: R&S Echoes AI Factory Assembly Line
# v15.7 — 智能 Ping-Pong 迴圈引擎 · LLM JSON 修復 · 選曲遞補 · 視覺 DB 遷移

**Target:** R&S Echoes 多頻道影音全自動封裝產線（Lofi / Light Music 雙頻道物理隔離）  
**Infrastructure:** Windows 10 開發機（現役）→ Mac mini M4（24/7 部署目標）  
**最後更新:** 2026-04-17  
　v15.5：Closed GOP · setpts 優先濾鏡順序 · 嚴格 IDR · GOP-QA 自動驗證 · -ar 48000 音訊漂移防禦  
　v15.6：get_video_duration 源幀率修正（根治 30fps 素材 2 秒凍結）· 雙重保險 re-probe · CEO 鎖定  
　v15.7：ping_/ford_ 前綴 Ping-Pong 策略 · LLM JSON 截斷修復 · lofi 偽短缺修復 · 視覺 DB 路徑遷移

---

## 1. 產線核心鐵律（Ironclad Disciplines）

| # | 鐵律 | 對應機制 |
|---|------|---------|
| 1 | **Streamlit UI 單一樞紐** | 廢除 `rs_manager.py`；所有操作走 `app.py` Web UI (Tab1-6) |
| 2 | **UI 非阻塞** | 耗時任務以 `threading.Thread(daemon=True)` 背景執行 |
| 3 | **絕對音畫同步** | Stage 2 自然 EOF 策略；音軌先在 Stage 2.5 以 acrossfade 預混音（-ar 48000）|
| 4 | **雙棲實體路徑隔離** | `.env` 的 `WORKSPACE_ROOT` + `env_manager.py` 跨平台解析，嚴禁硬編碼磁碟符號 |
| 5 | **零浪費延遲扣款** | 成片寫入後才執行 `derivation_count + 1`，絕不預扣款 |
| 6 | **多頻道物理隔離** | `--channel lofi / light_music` 嚴格隔離基因、DB 與目錄 |
| 7 | **零容忍靜默失敗** | 核心異常必須 `sys.exit(1)`；嚴禁空 `try-except` 假成功 |
| 8 | **原子寫入防護** | JSON / DB 狀態更新必須 `.tmp` → `os.replace()` 或 DB Commit |
| 9 | **殭屍行程防護** | `atexit` 追蹤所有 `Popen`，Streamlit 退出時自動清理 |
| 10 | **即時日誌流** | 子程序環境注入 `PYTHONUNBUFFERED=1`，log 即時落盤 |
| 11 | **DB 連線唯一入口** | 所有 SQLite 存取必須透過 `vault.conn`（threading.local property）；`_get_connection()` 已廢除 |
| 12 | **🔒 核心引擎 CEO 鎖定** | `multi_scene_processor.py` 任何修改須取得 CEO 書面授權；見 Protocol LOCK |
| 13 | **🎬 影片前綴命名強制規範** | 所有 vault 影片必須有 `ping_` 或 `ford_` 前綴；改名後必須同步更新 `veo_visual_vault.db`；見 Protocol VN |

---

## ⚙️ 齒輪二：R&D 逆向研發線（休眠模式）

### [Protocol RE: Multimodal Style Mining]（基因提煉與逆向工程）

- **Trigger:** CEO 手動下達指令，籌備新頻道或補充曲風基因時觸發
- **Actor:** `RE`（Reverse Engineer）
- **Action:** 生成關鍵字 → 抓取目標風格影音 → 提煉 `audio_genes` / `video_genes` → 寫入 `style_vault.db`
- **Constraint:** 執行期間嚴格監控 API 計費；任務完成後必須強制入庫，否則視為失敗
- **DoD:** 獲得 ≥ 20 組高品質新曲風基因，成功寫入 `style_vault.db`
- **Handoff:** 基因入庫後回報 CEO，系統立即休眠回歸主線

---

## ⚙️ 齒輪一：日常生產線（Daily Manufacturing Pipeline）

---

### [Protocol A: CEO Prompts Supply]（三引擎供彈與 UI 入庫）

- **Trigger:** CEO 於 `Tab2` 選擇 LLM 引擎、設定組數（預設 5），點擊「生成一週份提示詞」；或於 `Tab1` 拖曳音檔上傳
- **Actor:** `CW`（Copywriter）& `PM`（Project Manager）
- **Action:**
  1. **背景供彈（Tab2）：** `app.py` 呼叫 `generate_ceo_prompts.py --channel {ch} --provider {engine} --batch-size {n}`
     - 預設引擎：MiniMax M2.7（每組 ~100s）；批量建議改 Zhipu GLM-4（~7s/組）
     - 輸出：`assets/.ceo_prompts/daily_prompts_{CH}_{日期}.txt`
  2. **拖曳入庫（Tab1）：** Streamlit 上傳檔案由後端自動分類至 `ceo_approved_beats/{channel}/`
- **Constraint:**
  - MiniMax 不得超過 5 組（單次約 8-9 分鐘）；大批量改用 Zhipu
  - 頻道嚴格隔離：`lofi` 素材不可進入 `light_music/`，反之亦然
  - 背景任務注入 `PYTHONUNBUFFERED=1`，log 即時可見
- **DoD:** 提示詞檔案寫入完成，或音檔成功落入 `ceo_approved_beats/{channel}/`
- **Handoff:** 提示詞交 TTAPI（Protocol L），音檔交 `AD`（Protocol M）

---

### [Protocol M: Audio Mastering Engine]（母帶化）

- **Trigger:** `ceo_approved_beats/{channel}/` 偵測到新 MP3/WAV 素材（由 Tab3 手動觸發 或 pipeline_runner 自動串聯）
- **Actor:** `AD`（Audio & Mastering Engineer）
- **Action:**
  1. 執行 `audio_mastering_engine.py --channel {ch}`
  2. FFmpeg `-af loudnorm` 標準化至目標 LUFS，輸出 44.1kHz / 16-bit WAV
  3. `_sync_mastered_to_vault()`：新曲入庫 `rs_music_vault.db`（derivation_count=0）
- **Constraint:**
  - Lofi：`-16.0 LUFS`，檔名含 `_-16.0LUFS.wav`
  - Light Music：`-18.0 LUFS`，檔名含 `_-18.0LUFS.wav`
  - 成品存入隔離的 `vault_ready_for_mix/{channel}/`；DB 連線使用 `vault.conn`（threading.local）
- **DoD:** 新曲通過 LUFS 驗證，物理入庫並完成 DB 登記（derivation_count=0）
- **Handoff:** 狀態標記 Mastered → 交 `QA`（Protocol Q）並通知可進入 Protocol L 檢查

---

### [Protocol L: TTAPI Auto-Supply]（智能自動供彈備援）

- **Trigger:**
  - **Tab5（pipeline_runner）：** `ceo_approved_beats/{channel}/` 有效 MP3 < 5 首
  - **Tab4（backend）：** `vault_ready_for_mix/{channel}/` 衍生次數 < 上限的可用曲目 < 6 首
- **Actor:** `AD`（Audio Engineer）+ TTAPI Suno 代理
- **Action:**
  1. **Protocol L 衍生優先（省成本）：** 從 `rs_music_vault.db` 取 `derivation_count < 3` 的曲目，套用 tempo_up / tempo_down / pitch_up / pitch_down 變形
     - 成功 → `audio_mastering_engine.py` → 入庫 → 結束
  2. **TTAPI 新歌生成（衍生不足時）：**
     - 讀取 `assets/.ceo_prompts/daily_prompts_{CH}_*.txt`；若不存在 → 即時呼叫 `generate_ceo_prompts.py`
     - 呼叫 `suno_api_engine.py --prompt ... --channel {ch} --output-dir ceo_approved_beats/{ch}/`
     - TTAPI endpoint：`https://api.ttapi.io`，輪詢直至 status="success"（timeout 600s/首）
     - 下載 MP3 → `audio_mastering_engine.py` → `rs_music_vault.db` 入庫
- **Constraint:**
  - 衍生優先、外部 API 其次（先省成本）
  - 需要 `TTAPI_KEY` in `.env`；失敗時回傳明確錯誤訊息，絕不靜默失敗
  - Tab4 備援使用 `pipeline_runner.py --skip-assembler --skip-metadata`
- **DoD:**
  - Tab5：`ceo_approved_beats/{ch}/` ≥ 5 首
  - Tab4：`vault_ready_for_mix/{ch}/` 可用曲目 ≥ 6 首
- **Handoff:** 備援完成 → 回到 Protocol M → 再進 Protocol Q（縫合）

---

### [Protocol V: Visual Pyramid Vault]（金字塔視覺金庫調度）

- **Trigger:** CEO 於 Tab4 點擊「啟動幻影矩陣」或 Tab5 全自動產線的 Phase 5
- **Actor:** `VD`（Vision Director）
- **Action:**
  1. `visual_vault_db.get_pyramid_videos(channel, needed_count=6, max_derivation_limit={n})`
  2. **三層兜底策略：**
     - Level 1：50% 全新 / 25% 二手 / 25% 三手（嚴格抽樣）
     - Level 2：放寬至 `max_derivation_limit × 2`
     - Level 3：完全忽略衍生次數限制（確保產線不中斷）
  3. **Clip Cycling：** 若金庫素材不足但非零，自動循環複用填滿所需場景數
- **Constraint:**
  - 防重疊機制：連續場景的 `scene_tags` 絕對不可有交集
  - 延遲扣款：僅在成片成功後才執行 `derivation_count + 1`（絕不預扣）
  - DB 連線使用 `vault.conn`（threading.local）
  - **v15.7 前綴強制：** 所有 vault 影片必須具備 `ping_` 或 `ford_` 前綴；任何改名後需立即走 Protocol VN 更新 DB
- **DoD:** 鎖定 6 支不重複的視覺素材路徑清單（或 Clip Cycling 補足清單）
- **Handoff:** 素材路徑清單交 `QA`（Protocol Q）

---

### [Protocol VN: Video Naming & DB Sync]（影片前綴命名與資料庫同步）

> **v15.7 新增。所有 vault 影片的生命週期管理規範。**

- **Trigger:** CEO 取得新影片素材、或需要重新分類現有影片的迴圈策略時
- **Actor:** `VD`（Vision Director）+ CEO（人工審閱）
- **Action（新入庫 SOP）：**
  1. CEO 審閱素材，決定迴圈策略：
     - **Ping-Pong（正反交替）：** 適合海浪、雲朵、煙霧等振盪型場景 → 命名 `ping_[原始名稱].mp4`
     - **Forward（正向重複）：** 適合瀑布、城市、靜態美景、已完美無縫的素材 → 命名 `ford_[原始名稱].mp4`
  2. 將命名後的影片放入 `assets/video_clips/vault/{channel}/`
  3. 執行視覺金庫入庫指令：`visual_vault_db.py` 登記至 `veo_visual_vault.db`
- **Action（改名 / 重新分類 SOP）：**
  1. 在磁碟上重新命名檔案（`ping_xxx.mp4` ↔ `ford_xxx.mp4`）
  2. **立即** 在 `veo_visual_vault.db` 的 `video_assets` 表執行：
     ```sql
     UPDATE video_assets SET video_id = ?, file_path = ? WHERE video_id = ?
     ```
  3. 確認 DB 記錄與磁碟檔案完全一致（使用 `veo_visual_vault.db` 查詢驗證）
- **Constraint:**
  - **嚴禁** vault 內存在無前綴的影片（會導致 `get_loop_strategy()` 預設 forward，策略可能不正確）
  - **嚴禁** 只改磁碟名稱不更新 DB（會導致 `multi_scene_processor.py` FileNotFoundError）
  - 系統分類邏輯由 `scripts/gear2_rnd/video_loop_classifier.py` 的 `get_loop_strategy()` 實作，純前綴比對，無 CV 運算
- **DoD:** 磁碟檔名與 `veo_visual_vault.db.video_assets.file_path` 完全一致；所有檔案具備有效前綴
- **Handoff:** 入庫完成，新素材可立即被 Protocol V 調用

---

### [Protocol Q: Phantom Matrix Assembly v15.7]（幻影矩陣廣播級拼接）

> **⚠️ `multi_scene_processor.py` 受 CEO 鎖定（v15.7）。見 Protocol LOCK。**

- **Trigger:** Protocol V 素材清單就緒，或 CEO 指定 `--bg-video / --bg-videos / --auto-visual`
- **Actor:** `QA`（Phantom Rotation Expert）
- **Action:** 執行 `multi_scene_processor.py` v15.7：

  **Pre-Stage（v15.7 迴圈策略感知）：**
  > - 對每支素材呼叫 `get_loop_strategy(vid_path)`（`video_loop_classifier.py`）
  > - 讀取檔名前綴：`ping_` → `"pingpong"`；`ford_` → `"forward"`；無前綴 → 預設 `"forward"`（log 警告）

  **Stage 1（Encode-Once-Repeat + Pre-baked Fade + Pre-baked Reverse）— 四層廣播級防禦：**

  > **Layer 0 — Ping-Pong 反向鑄造（v15.7，消除振盪場景閃切）**
  > - `pingpong` 策略：額外編碼一個 `base_mid_rev.ts`，濾鏡：`reverse,setpts=PTS-STARTPTS,fps=24,{norm}`
  >   - **`reverse` 必須在 `setpts` 之前**：先物理倒轉幀序列，再歸零時間軸，否則倒轉後 PTS 仍為雜亂值
  > - `loop_list.txt` 寫入規則：
  >   - `pingpong`：`base_in → [base_mid → base_mid_rev] × N/2 → base_out`（交替正反）
  >   - `forward`：`base_in → base_mid × N → base_out`（全正向）
  > - 若 `base_mid_rev.ts` 編碼失敗：自動降級至 `forward`，記錄 `⚠️ [v15.7] 反向片段編碼失敗，降級為 Forward 策略`

  > **Layer 1 — 源幀率修正（v15.6，根治 2 秒凍結）**
  > - `get_video_duration()` 同步讀取 `nb_read_packets` + `r_frame_rate`，以 `frames / source_fps` 計算實際時長
  > - 30fps 素材（240 幀）→ 240 ÷ 30 = **8.0s**（正確）；舊版 240 ÷ 24 = 10.0s（錯誤，導致 2 秒空洞凍結）
  > - **雙重保險**：三段編碼完成後，re-probe `base_mid.ts` 實際幀數 ÷ 24 作為 loop_list 的 `duration` 宣告，幀級吻合零空洞

  > **Layer 2 — 廣播級 GOP 防禦（v15.5）**
  > - 濾鏡執行順序（鎖定）：`setpts=PTS-STARTPTS,fps=24` → `fade`（如有）→ `norm`
  >   - 先建立絕對 0-based 24fps 乾淨時間軸，fade 的 `st=` 才能幀級精準落點
  > - 編碼參數（鎖定，禁止修改）：
  >   ```
  >   -preset medium -tune film -crf 28 -pix_fmt yuv420p
  >   -g 48 -keyint_min 48        # 嚴格 IDR：最大 = 最小 = 48 幀
  >   -sc_threshold 0             # 關閉 libx264 動態場景偵測
  >   -flags +cgop                # 強制封閉 GOP，B 幀不跨 concat 邊界
  >   -video_track_timescale 24000 # 統一時間基底，防浮點誤差累積
  >   ```
  > - **GOP-QA 自動驗證**：每次 `base_mid.ts` 編碼後自動執行 `_verify_gop_closure()`
  >   - 通過：`✅ [GOP-QA] Scene N/N clean: X 個 I 幀，間隔嚴格 2.0s ±0.063s — GOP 牢籠完好`
  >   - 異常：`⚠️ [GOP-QA]` WARNING（記錄但不中斷產線）

  > **Layer 3 — 雙重保險（v15.6）**
  > - 以 re-probe 的 `base_mid.ts` 實際幀數（÷24）作為 `loop_list.txt` 的 `duration`，與物理 .ts 內容達幀級吻合

  **Stage 2.5（Acrossfade Audio Premix）：**
  - `acrossfade=d=5` 將所有音軌融合成超越 3600s 的 `audio_premix.wav`（PCM WAV 中繼，無損）
  - 最終 AAC 輸出強制 `-ar 48000`，消除 44100↔48000Hz 浮點換算漂移

  **Stage 2（物理矩陣拼接）：**
  - `-f concat -c:v copy`，零重編碼物理拼接
  - **自然 EOF 策略**：不強制 `-t 3600`，讓所有 unit.ts 播至自然 EOF，徹底消除最後一幀凍結延長

- **Constraint:**
  - `multi_scene_processor.py` 為 CEO 鎖定檔案，禁止未授權修改（見 Protocol LOCK）
  - `-tune film`（非 stillimage）：保留水波/動態細節
  - 正向濾鏡順序：`setpts → fps=24 → fade → norm`，此順序為鐵律，不可逆轉
  - 反向濾鏡順序：`reverse → setpts → fps=24 → norm`，`reverse` 必須最先，此順序為鐵律
  - `get_video_duration()` 必須使用 `frames / source_fps`，嚴禁硬編碼除以 24.0
  - Clip Cycling 已內建：`len(clips) < needed` 時自動循環複用（不 Fatal）
  - 音畫同步：最終 MP4 時長誤差 < 5s（自然 EOF 模式下約 59~60.3 分鐘，CEO 接受範圍）
- **DoD:**
  - 產出 `R&S_Echoes_{ch}_1HrMix_[TS].mp4`
  - 所有場景的 GOP-QA 日誌均顯示「GOP 牢籠完好」
  - 無靜止空洞（由雙重保險保證）；振盪場景無閃切（由 Ping-Pong 保證）
- **Handoff:** 交 `CW`（Protocol Meta），並觸發 `st.rerun()` 更新 Final Exports 面板

---

### [Protocol LOCK: CEO Protected Core Engine]（核心引擎 CEO 授權保護）

- **Trigger:** 任何人嘗試修改 `scripts/gear1_prod/multi_scene_processor.py`
- **Actor:** 任何工程師 / AI Agent
- **Action:**
  1. **立即停止**，不得進行任何修改
  2. 向 CEO 提出書面修改申請，說明：
     - 修改原因（Bug / 新功能 / 效能優化）
     - 預計修改的具體位置（函數名稱 + 行號）
     - 對產線的潛在影響評估
     - 預計的測試方案
  3. 取得 CEO 書面授權後，先備份至 `spec/backups/v[version]_pre_[YYYYMMDD]/`
  4. 修改後必須執行 GOP-QA 驗證測試：
     ```powershell
     python scripts/gear1_prod/multi_scene_processor.py --sandbox --channel lofi --target-duration 120 --scene-dwell-time 60
     ```
  5. 日誌必須出現 `✅ [GOP-QA] ... GOP 牢籠完好` 才算驗收通過
- **Constraint:**
  - 以下參數為 CEO 鎖定核心，**永遠不得移除或修改**：
    - `setpts=PTS-STARTPTS,fps=24`（正向濾鏡順序鎖定）
    - `reverse,setpts=PTS-STARTPTS,fps=24`（反向濾鏡順序鎖定，v15.7）
    - `-flags +cgop`（封閉 GOP）
    - `-g 48 -keyint_min 48`（嚴格 IDR）
    - `-sc_threshold 0`（關閉動態 I 幀）
    - `-video_track_timescale 24000`（統一時間基底）
    - `get_video_duration()` 的 `frames / source_fps` 計算邏輯
    - 雙重保險 re-probe `base_mid.ts` 邏輯
    - `get_loop_strategy()` 前綴讀取與 Ping-Pong 分支邏輯（v15.7）
  - Cursor Rule 已配置：`.cursor/rules/protect-multi-scene-processor.mdc`，開啟檔案時自動提醒
- **DoD:** 修改取得 CEO 授權，修改後通過 GOP-QA 驗證
- **Handoff:** 修改完成後更新 spec/ 歷史歸檔並通知 CEO

---

### [Protocol Meta: Tri-Engine CheatSheet Generation]（三引擎商業文案生成）

- **Trigger:**
  - Tab4 Step 1 完成（`run_phase4_sequence()`）後自動執行
  - 或 Tab4 Final Exports 面板偵測到缺失文件後觸發補生成
- **Actor:** `CW`（Metadata Copywriter）
- **Action:**
  1. `music_metadata_engine.py --channel {ch} --provider minimax`
     → 生成 `Tracklist_{ch}_[TS].txt` + `DistroKid_CheatSheet_{ch}_[TS].txt` + `metadata_distrokid_{ch}.json`
     - **v15.7：** `track_count = max(5, min(vault_count, 20))`，嚴禁傳入超過 20 首給 LLM（防 token 截斷）
  2. `backend.generate_youtube_cheatsheet(channel)`
     → 讀取 metadata JSON + Tracklist → 生成 `YouTube_CheatSheet_{ch}_[TS].txt`
  3. **Tracklist 時間戳補償：** `_generate_tracklist()` 每首扣除 `CROSSFADE_SEC=12`，防累積漂移
- **Constraint:**
  - 預設引擎：MiniMax M2.7（`--provider minimax`，`max_tokens=4096`）；超時可降級至 Zhipu（Protocol ZR）
  - 輸出必須落在 `assets/final_exports/{channel}/`；文件命名含時間戳防覆蓋
  - **v15.7 JSON 三重清洗：** LLM 回傳先剝除 Markdown 包裝 → 定位首個 `{` → 自動補全未閉合括號；3 次重試後仍失敗則 `sys.exit(1)`
- **DoD:** `final_exports/{channel}/` 包含五件全：WAV 母帶 + Tracklist + DistroKid CheatSheet + YouTube CheatSheet + metadata JSON
- **Handoff:** 交 `PM`（Protocol D）進入發行交接

---

### [Protocol D: Final Exports & Release]（成品發行與金庫代謝）

- **Trigger:** Protocol Meta 完成，或 CEO 於 Tab4 Final Exports 面板手動觸發補生成 / 發行
- **Actor:** `PM`（Label Manager）
- **Action:**
  1. **Final Exports 面板動態偵測（Tab4）：**
     `backend.get_final_exports(channel)` 掃描輸出目錄，回傳 `{wav, mp4, tracklist, yt_cheatsheet, dk_cheatsheet}`
     - 缺失 ≥ 2 份 → 顯示「一鍵補全」按鈕（`regenerate_all_missing_docs()`）
     - 各項缺失 → 顯示單項補生成按鈕
  2. **CEO 審核發行：** 透過 Streamlit Tab4 查閱最終成品清單，確認無誤後手動複製 CheatSheet 至 DistroKid / YouTube
  3. **金庫代謝：** Tab6 執行金庫重置（雙重確認防呆）；冷金庫超過 100 首時 FIFO 清理
- **Constraint:**
  - 嚴禁系統未經授權自動刪除資產；所有破壞性操作必須透過 UI 防呆驗證
  - `derivation_count + 1` 延遲扣款：僅在成片確認後執行
  - 發行交接文件（CheatSheet）由 CEO 手動操作，規避 Cloudflare 防護
- **DoD:** 成品五件齊全（WAV + MP4 + Tracklist + YT CheatSheet + DK CheatSheet）；金庫完成新陳代謝
- **Handoff:** 產線淨空，回歸待機。Telegram Bot 發送完工通知（若已啟動）

---

### [Protocol T: Telegram Remote Command]（CEO 遠端指揮中樞）

- **Trigger:** CEO 在 Telegram 傳送指令，或 Bot 偵測到金庫水位警報
- **Actor:** `PM` via `telegram_manager_bot.py`
- **Action:**
  - `/status` → 查詢金庫戰情報表（**按頻道分欄**：🎵 Lofi / 🌟 Light Music，各頻道顯示活水 / 歸檔 / Gen0~Gen3+ 分層百分比）
  - `/build` → 遠端啟動產線（SFX 選擇 → asyncio.Lock() 互鎖 → 背景執行）
  - `/vault_cleanup` → 冷庫容量檢查（≥ 90% 推送清理確認按鈕）
  - `/start` → 歡迎訊息
- **Constraint:**
  - `TELEGRAM_ALLOWED_USER_ID` 白名單：只允許授權 CEO 操作
  - Webhook 模式需填 `NGROK_AUTHTOKEN`（免費帳戶），Polling 模式無此要求
  - 訊息格式使用 **HTML parse mode**（避免 MarkdownV2 特殊字元跳脫錯誤）
  - `asyncio.Lock()` 防止重複觸發產線
- **DoD:** 指令被授權執行，回報結果訊息發送至 CEO
- **Handoff:** 背景任務執行中時持續可接收指令（非阻塞）

**啟動方式：**
```bash
python scripts/start_telegram_bot.py --polling   # 開發機
python scripts/start_telegram_bot.py --ngrok     # 本地 Webhook 測試（需 NGROK_AUTHTOKEN）
python scripts/start_telegram_bot.py --webhook   # 生產（Mac mini，需 TELEGRAM_WEBHOOK_URL）
```

---

## 例外處理協議（Exception & Fallback Protocols）

---

### [Protocol B: Beat Drop & Ban Track]（基因級下架）

- **Trigger:** CEO 審聽時發現異常壞軌或污染曲目
- **Actor:** `PM`
- **Action:** 透過 Tab6 執行下架指令，標記 `status='purged'`，執行物理刪除
- **Constraint:** 必須連同所有「衍生變體」一併物理拔除；嚴禁遺漏污染基因
- **DoD:** 壞軌及衍生基因從本地磁碟與 `rs_music_vault.db` 徹底抹除
- **Handoff:** 清除完成，產線恢復健康狀態

---

### [Protocol R: API Failsafe & UI Anti-Freeze]（API 斷崖保護與防阻塞）

- **Trigger:** LLM API 逾時 / 失敗；或 UI 發生轉圈卡死
- **Actor:** `PM`
- **Action:**
  1. **Tri-Engine 降級鏈：** MiniMax 超時（180s）→ 自動降級至 Zhipu GLM-4（Protocol ZR）
  2. **子程序防護：** 核心異常強制 `sys.exit(1)` + 寫入 log；嚴禁空 catch 假成功
  3. **UI 釋放：** 耗時任務改以 `threading.Thread(daemon=True)` + `PYTHONUNBUFFERED=1` 背景執行
  4. **殭屍行程清理：** `atexit` 回呼 `_cleanup_procs()` 優雅終止孤兒程序
- **Constraint:** 寧可安全停機，絕不使用舊資料偽造成功；異常必須回報至 log 或 UI 警告欄
- **DoD:** 產線安全停機並輸出診斷資訊，或成功轉入非阻塞背景模式
- **Handoff:** 列印異常報告，等待 CEO 介入或自動降級重試

---

### [Protocol ZR: LLM Fallback Chain]（三引擎降級鏈）

- **Trigger:** MiniMax（NVIDIA NIM）API 回傳錯誤 / 超時（180s）
- **Actor:** `CW` / `llm_client.py`
- **Action:**
  - MiniMax 失敗 → 自動切換至 Zhipu GLM-4（`provider="zhipu"`）
  - Zhipu 失敗 → 可選切換至 Gemini 2.5 Flash（視覺/多模態任務）
  - 全部失敗 → `sys.exit(1)` + 記錄完整錯誤至 log
- **Constraint:**
  - 降級切換必須記錄 log（`[LLM_FALLBACK] Provider switched: minimax → zhipu`）
  - 嚴禁靜默降級假裝成功；降級後回傳的 JSON 結構必須與原始要求相符
- **DoD:** 成功由備援引擎取得有效 JSON 輸出，或安全失敗並記錄
- **Handoff:** 繼續原 Protocol（Meta / A），以降級引擎的結果推進

---

### [Protocol DB: SQLite Thread Safety]（資料庫執行緒安全規範）

- **Trigger:** 任何模組需要存取 `rs_music_vault.db` 或 `veo_visual_vault.db`
- **Actor:** 所有與 DB 互動的模組（`AD`, `VD`, `PM`, Telegram Bot）
- **Action:**
  - 使用 `vault.conn` property（`threading.local()`，每條執行緒獨立連線）
  - 寫入完成後呼叫 `vault.conn.commit()`
  - 不得呼叫 `vault._get_connection()`（已廢除）
  - 不得手動 `conn.close()`（由 threading.local 生命週期管理）
- **Constraint:**
  - `_get_connection()` 在 `vault_database.py` 已不存在；任何呼叫此方法的代碼視為 Critical Bug
  - 跨執行緒共享同一 `sqlite3.connect()` 物件會觸發 `ProgrammingError`，必須用 `threading.local()` 隔離
- **DoD:** 無 `sqlite3.ProgrammingError`；所有執行緒可獨立安全讀寫 DB
- **Handoff:** DB 操作完成，結果回傳給呼叫方

---

### [Protocol VF: Video Freeze Diagnosis]（影片凍結根因排查）

- **Trigger:** 成品 MP4 出現週期性靜止畫面或視覺閃爍（每 N 秒凍結 / 閃一下）
- **Actor:** `QA`
- **Action（v15.7 四層根因診斷）：**

  | 症狀 | 根因 | 對應修復 |
  |------|------|---------|
  | 每 N 秒凍結 M 秒（M ≈ N × (30-24)/24）| `get_video_duration()` 硬除 24，30fps 素材時長誤算 | 確認代碼使用 `frames / source_fps`（Layer 1）|
  | 每 8s 邊界輕微卡頓 | B 幀跨 concat 邊界，解碼器補幀 | 確認 `-flags +cgop -keyint_min 48`（Layer 2）|
  | loop_list duration 與 .ts 不吻合 | fps 轉換捨入誤差 | 確認雙重保險 re-probe 邏輯（Layer 3）|
  | fade 在錯誤時間觸發 | setpts 在 fade 之後執行 | 確認濾鏡順序：`setpts → fps=24 → fade`（Layer 2）|
  | 10hr+ 影片音畫漂移 | 音訊取樣率 44100↔48000 換算誤差 | 確認 Stage 2 AAC 輸出有 `-ar 48000` |
  | 振盪場景（海浪/雲朵）8s 交接閃一下 | 正向接正向，結尾靜態幀突然重置 | 確認 `ping_` 前綴已設定，Ping-Pong 策略啟用（Layer 0）|
  | Ping-Pong 效果異常（反向播不順）| `reverse` 濾鏡在 `setpts` 之後 | 確認反向濾鏡順序：`reverse → setpts → fps=24`（Layer 0）|

  **GOP-QA 快速診斷指令（僅限手動排查，正式產線已自動執行）：**
  ```powershell
  ffprobe -v error -select_streams v:0 -show_entries "frame=pict_type,pts_time" -of csv unit_0.ts | Select-String ",I,"
  # 正常：每 2.000s 出現一個 I 幀（0.000, 2.000, 4.000...）
  # 異常：間隔不規則 → 確認 -g 48 -keyint_min 48 -sc_threshold 0
  ```
- **Constraint:** `multi_scene_processor.py` 為 CEO 鎖定檔案；排查後若需修改，必須走 Protocol LOCK
- **DoD:** 找出凍結根因，確認四層防禦參數均已正確設置
- **Handoff:** 問題確認後，走 Protocol LOCK 申請授權修改（若需要）

---

### [Protocol VS: Vault Shortage Recovery]（庫存短缺恢復 v15.7）

- **Trigger:** Phase 4 被跳過（`庫存為 0`），或 `lofi_assembler.py` 拋出 `VaultShortageException`
- **Actor:** `AD`
- **RCA（v15.7）：** `VaultShortageException` 在 v15.7 之前只在 Gen2 不足時填補，New(dc=0) 配額不足時會直接拋出異常，即使 Gen1 有大量可用曲目
- **Action（v15.7 修復後的遞補邏輯）：**
  1. 先從 Gen1 補足 New 配額缺口（Step 4a）
  2. 再從 New/Gen1 補足 Gen2 缺口（Step 4b）
  3. `total_selected >= 1` 即繼續，`_build_playlist()` 以重複播放填滿目標時長
  4. 只有 `total_selected == 0` 才拋出異常（真正庫存為空）
- **Constraint:** 不可修改 `lofi_assembler.py` 的 50/25/25 目標配額定義；僅動態遞補，不強制改配額
- **DoD:** Phase 4 成功完成，輸出 `R&S_Echoes_{ch}_1HrMix_[TS].wav`
- **Handoff:** WAV 母帶產出，進入 Phase 5（Protocol Q）

---

## 交付物驗收標準（Delivery Acceptance Criteria）

每次成功執行產線後，`assets/final_exports/{channel}/` 必須包含以下五件，方視為驗收通過：

| 檔案 | 內容 | 生成 Protocol |
|------|------|-------------|
| `R&S_Echoes_{ch}_1HrMix_[TS].mp4` | 1 小時廣播級無縫音畫同步影片（零靜止空洞 + 振盪場景零閃切）| Protocol Q v15.7 |
| `R&S_Echoes_{ch}_1HrMix_[TS].wav` | 1 小時無縫混音母帶 | Protocol Q（lofi_assembler）|
| `Tracklist_{ch}_[TS].txt` | 曲目清單（含 LUFS / BPM / 時間戳補償）| Protocol Meta |
| `YouTube_CheatSheet_{ch}_[TS].txt` | YouTube 標題 / 說明 / 標籤 | Protocol Meta |
| `DistroKid_CheatSheet_{ch}_[TS].txt` | DistroKid 版稅分拆文件 | Protocol Meta |

輔助文件（不計入驗收但為必要中繼站）：
- `metadata_distrokid_{ch}.json`：LLM 原始結構化輸出
- `assets/.logs/[任務名稱]_[TS].log`：後台即時日誌

**GOP-QA 品質閘門（v15.5 新增，自動執行）：**
- 每個場景的 `base_mid.ts` 必須出現：`✅ [GOP-QA] Scene N/N clean — GOP 牢籠完好`
- 若出現 `⚠️ [GOP-QA]` WARNING，產線繼續但需 CEO 事後確認

**Ping-Pong 品質閘門（v15.7 新增）：**
- `ping_` 前綴素材必須出現：`🔄 [v15.7] Ping-Pong 策略啟動：{filename}`
- `ford_` 前綴素材必須出現：`▶️  [v15.7] Forward 策略：{filename}`
- 反向編碼失敗降級必須出現：`⚠️ [v15.7] 反向片段編碼失敗，降級為 Forward 策略`（非必要出現，視素材而定）

---

## 版本歸檔

| 版本 | 路徑 | 說明 |
|------|------|------|
| v15.3 | `spec/content_assembly_workflow.v15.3.md` | 雙 LLM（GLM-4 + Gemini），無 TTAPI 備援，無 Webhook Bot |
| v15.4 | `spec/content_assembly_workflow.v15.4.md` | 三引擎 LLM、TTAPI 自動供彈、Webhook Bot、頻道分欄 /status |
| v15.6 | `spec/content_assembly_workflow.v15.6.md` | 廣播級無縫（三層防禦）、源幀率修正、雙重保險、GOP-QA、CEO 鎖定 |
| **v15.7（現役）** | `.openclaw/workflows/content_assembly_workflow.md` | Ping-Pong 智能迴圈、LLM JSON 修復、lofi 遞補邏輯、視覺 DB 路徑遷移、Protocol VN 新增 |
