# Workflow: R&S Echoes AI Factory Assembly Line (v15.3 幻影輪播矩陣 統一極速版)
**Target:** R&S Echoes 多頻道影音全自動封裝產線
**Infrastructure:** 支援 Windows (Dev/Test) 與 Mac mini (OpenClaw Production)

## 1. Workflow Objective & Core Discipline
本工作流定義了 V15.3「雙棲企劃」與「幻影輪播矩陣」的標準作業程序。專注於消除 OOM 崩潰、以 75 倍速極速算圖、確保 1 小時音畫絕對同步、以及視覺金庫的非重複性金字塔抽樣。

* **Strict Discipline 1 (Unified Genesis Synergy):** 廢除 GLM-4。所有企劃必須聯動影像與音訊，由 `gemini-2.5-flash` 統一接管。輸出的 JSON 必須包含視覺場景標籤，用於金庫防重複檢索。
* **Strict Discipline 2 (Physical Path Neutrality):** 所有 Agent 處理路徑時，必須呼叫 `EnvConfig` 獲取根目錄，絕對禁止硬編碼盤符（如 F: 或 /Volumes/）。
* **Strict Discipline 3 (Modular Rendering & Pre-baked Fade):** 廢除舊版交疊與 xfade。Stage 1 必須實施「Encode-Once-Repeat」與「預烤三版本 (in/mid/out)」，以實現極速 10 分鐘長鏡頭並自帶呼吸燈轉場 (Dip to Black)。
* **Strict Discipline 4 (Audio Premix Supremacy):** 廢除單曲無限重複與 audio concat demuxer。Stage 2.5 必須實施「預混音 (Acrossfade Premix)」，確保音訊無斷層且 FFmpeg 時間軸絕對正確。Stage 2 必須使用 `-c:v copy` 物理拼接。
* **Strict Discipline 5 (Streamlit UI Singularity):** 全產線操作（包含單一母帶回收、供彈、發行企劃、金庫代謝）必須統歸至 Streamlit Web UI。`rs_manager.py` 已被永久封存。

---

## ⚙️ 齒輪二：R&D 逆向研發線 (Dormant / Manual Trigger Only)
> **戰略定位**：本模組為 R&S Echoes 的「基因圖書館」。平時處於冷鎖定狀態以節省 API 成本，僅在 CEO 籌備新頻道或需要新曲風基因時，由手動指令喚醒。

### [Protocol RE: Multimodal Style Mining] (基因提煉與逆向工程)
* **Trigger:** CEO 透過中控台下達手動啟動指令。
* **Actor:** `$$RE` (Reverse Engineer).
* **Action:** 生成相關關鍵字，抓取目標風格影像並提煉 `audio_genes` 與 `video_genes`。
* **Constraint:** 執行期間必須嚴格監控計費帳目。任務完成後必須強制寫入 `style_vault.db`。
* **DoD:** 獲得至少 20 組高品質的新曲風基因。
* **Handoff:** 基因入庫後，發送報告給 CEO，系統立即轉入休眠回歸主線。

---

## ⚙️ 齒輪一：日常生產線 (Daily Manufacturing Pipeline)
## 2. The Assembly Line Protocols (產線標準作業流程)

### [Protocol A: Genesis & Drag-and-Drop Ingestion] (雙棲企劃與拖曳入庫)
* **Trigger:** CEO 透過 Streamlit UI 點擊「一鍵供彈」，並將滿意的音檔拖曳至上傳區。
* **Actor:** `$$CW` (Copywriter) & `$$PM` (Project Manager).
* **Action:** 1. **背景供彈**: `app.py` 透過背景執行緒呼叫 Gemini 2.5 Flash 生成雙棲企劃，不卡死 UI。
    2. **CEO 拖曳入庫**: 透過 Streamlit 上傳的檔案，由後端自動分類至對應頻道的 `ceo_approved_beats/{channel}/`。
* **Constraint:** 嚴格執行頻道隔離，上傳之素材絕對不可跨頻道混淆。
* **DoD:** 產線盤點完成，明確鎖定待處理之音頻清單。
* **Handoff:** 將素材與執行權交接給 `AD` 進入母帶處理 (Protocol M)。

### [Protocol M: Strict Auto-Mastering Engine] (嚴格母帶處理)
* **Trigger:** Protocol A 確認靶場內有新素材。
* **Actor:** `$$AD` (Audio & Mastering Engineer).
* **Action:** 執行 `audio_mastering_engine.py`。使用 FFmpeg `-af loudnorm` 進行精準響度標準化，轉換為 44.1kHz / 16-bit 無損 WAV。
* **Constraint:** 動態 LUFS 輸出：Lofi 為 `-16.0 LUFS`，Light Music 為 `-18.0 LUFS`。成品存入隔離的 `vault_ready_for_mix/{channel}/`。
* **DoD:** 產出符合頻道發行標準之單曲，並完成資料庫入庫登記。
* **Handoff:** 將狀態標記為 Mastered，交接給 `VD` 與 `QA` 準備進入大矩陣縫合 (Protocol Q)。

### [Protocol V: Visual Pyramid Vault] (金字塔視覺金庫調度)
* **Trigger:** CEO 於 UI 啟動 1 小時幻影輪播矩陣。
* **Actor:** `$$VD` (Vision Director).
* **Action:** `visual_vault_db.py` 實施「金字塔抽樣 (Pyramid Sampling)」，選出 6 支 8 秒短片。
* **Constraint:** 1. 嚴格遵守 50% (全新) / 25% (二手) / 25% (三手) 抽樣比例。
    2. 防重疊機制：連續場景的 `scene_tags` 絕對不可有交集。
    3. 延遲扣款：僅在成片成功產出後，才對中選的素材執行 `derivation_count + 1`。
* **DoD:** 鎖定 6 支不重複的高質感短片清單。
* **Handoff:** 將抽樣完成的素材路徑清單交接給 `QA` (Protocol Q)。

### [Protocol Q: Phantom Matrix & Encode-Once-Repeat] (幻影矩陣與模組化極速拼接)
* **Trigger:** UI 下達幻影輪播啟動 (接收 Protocol V 素材清單 或 單素材覆寫模式)。
* **Actor:** `$$QA` (Phantom Rotation Expert).
* **Action:** 執行 `multi_scene_processor.py` (V15.3)。
    1. **Stage 1 (預烤三版本)**: 將 6 支短片各自鑄造為 in/mid/out 三段，並使用 concat copy 瞬間拉長為 6 個 10 分鐘帶有呼吸轉場的實體影片。
    2. **Stage 2.5 (預混音防斷層)**: 使用 `acrossfade` 將所有音樂融合成一根超越 3600 秒的 `audio_premix.wav`。
    3. **Stage 2 (終極陣列拼接)**: 使用 `-f concat -c:v copy` 將 6 個長鏡頭與預混音瞬間物理縫合。
* **Constraint:** 絕對棄用 `-shortest` 旗標以防時間戳漂移，強制以 `-t target_duration` 鎖死精確時長 (3600s)。影像壓縮強制為 `-preset medium -tune stillimage -fps 24 -crf 28`。
* **DoD:** 在 10 分鐘內產出畫質完美且精確達 1 小時的 `R&S_Echoes_{channel}_1HrMix_*.mp4`。
* **Handoff:** 交接給 `CW` 進行商業企劃文案生成 (Protocol Meta)。

### [Protocol Meta: Unified CheatSheet Engine] (一站式商業文案合體)
* **Trigger:** 1 小時 MP4 與全軌 WAV 生成完畢。
* **Actor:** `$$CW` (Metadata Copywriter) & `$$PM`.
* **Action:** 呼叫 Gemini 2.5 Flash API (Structured Outputs) 生成 JSON，合併專屬 Tracklist，產出最終版發行企劃書。
* **Constraint:** 輸出的 `YouTube_CheatSheet_*.txt` 必須位於頻道的專屬子目錄內。
* **DoD:** 成功產出文案風格符合該頻道且可直接發布的 YouTube/DistroKid 企劃書。
* **Handoff:** 將 `next_agent` 設為 `PM` 進入發行交接與代謝流程 (Protocol D & L)。

### [Protocol D & L: Streamlit Hub & Vault Metabolism] (單一樞紐與金庫代謝)
* **Trigger:** 產線完工，或 CEO 手動觸發審計 / 水位達 90%。
* **Actor:** `$$PM` (Label Manager).
* **Action:** 1. **UI 審計**: CEO 透過 Streamlit 的 Tab 面板查閱雙金庫報表、進行安全發行。
    2. **雙重防護清空**: CEO 透過 UI 下方的「紅色警告區」執行雙重打勾驗證，安全地將舊素材封存或刪除。
    3. **定期代謝**: 嚴控冷金庫 100 首容量上限，執行 FIFO 清理。
* **Constraint:** 嚴禁系統未經授權自動刪除資產，所有破壞性操作必須透過 UI 防呆驗證。
* **DoD:** 成品交由 CEO 發行完畢，金庫完成新陳代謝，冗餘資產消滅。
* **Handoff:** 產線淨空，回歸待機狀態，等待下一輪任務。

---

## 3. Exception & Fallback Protocol (防護與例外處理)

### [Protocol B: Beat Drop & Ban Track] (基因級下架)
* **Trigger:** CEO 審聽時發現異常壞軌。
* **Actor:** `$$PM`.
* **Action:** 透過中控台執行下架指令，將該曲目標記為 `purged`，並執行物理刪除。
* **Constraint:** 必須連同該曲目的「所有衍生變體」一併物理拔除，嚴禁遺漏。
* **DoD:** 壞軌及其污染基因被徹底從本地磁碟與資料庫中抹除。
* **Handoff:** 清除完成，產線恢復健康狀態。

### [Protocol R: UI Blocking & API Failsafe] (防阻塞與斷崖保護)
* **Trigger:** Gemini API 回傳逾時、失敗，或 UI 發生轉圈卡死。
* **Actor:** `$$PM`.
* **Action:** 1. **API 防護**: 強制呼叫 `sys.exit(1)` 並發送錯誤日誌，拒絕繼續執行。
    2. **UI 釋放**: 啟動 Python Background Threading (`daemon=True`) 處理耗時任務。
* **Constraint:** 寧可失敗報警，也絕對嚴禁使用假資料或舊資料偽造成功 Prompt 以欺騙系統。
* **DoD:** 產線安全停機，或 UI 成功轉入背景非阻塞模式。
* **Handoff:** 將異常報告列印於終端機，等待 CEO 介入修復。
