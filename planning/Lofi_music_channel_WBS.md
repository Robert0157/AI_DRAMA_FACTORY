這是一份為 **R\&S Echoes** 量身打造的三階層工作分解結構（WBS）。

整個計劃將時程錨定在硬體的到位節點：以 **4月18日 Mac mini M4 抵達** 為分水嶺，前期專注於架構設計與 AI 管線開發，後期則集中於伺服器部署與直播測試。

## ---

**🌲 R\&S Echoes：AI 自動化產製與 24/7 直播系統 WBS**

### **第一階段：基礎架構與環境整備 (Phase 1: Architecture & Prep)**

*核心目標：完成商業授權、品牌視覺，並在現有設備上完成核心腳本的開發測試。*

* **1.1 品牌與授權資產建立**  
  * **1.1.1 帳號與 API 權限開通**  
    * **What:** 註冊並開通 Suno Pro/Premier 商業授權帳號、DistroKid 音樂發行帳號，取得必要之 API Key。  
    * **When:** 4月1日 \- 4月2日  
    * **Who:** 人類---> Suno API key, DistroKid musician pro帳號設定都已經完成
  * **1.1.2 視覺資產生成**  
    * **What:** 產出 R\&S Echoes 頻道 Logo、YouTube 橫幅（Banner）、以及符合「自然風」與「均方根值」概念的標準化封面底圖。  
    * **When:** 4月1日 \- 4月2日  
    * **Who:** AI (圖像生成模型如 Midjourney) 負責生成，人類負責最終審定。  ---> image:RS_lofi_gril.png video:RS_lofi_gril_01.mp4
* **1.2 自動化管線 (Pipeline) 邏輯開發**  
  * **1.2.1 AI Agent 角色定義與框架搭建**  
    * **What:** 在 Openclaw 框架下規劃專屬的 AI Agent 角色（例如定義一個專職的「Prompt Engineer Agent」），賦予其生成音樂提示詞的 System Prompt 與參數限制。  
    * **When:** 4月1日 \- 4月2日  
    * **Who:** 人類 和 AI (架構師)  --> modify project.yml, workflow, 架構說明書
  * **1.2.2 核心處理腳本撰寫**  
    * **What:** 使用 Cursor AI 等輔助開發工具，撰寫 Python 腳本原型。功能包含：呼叫 API、抓取音檔、使用 FFmpeg 疊加自然音軌（鳥鳴/水聲），以及執行 \-14 LUFS 響度正規化。  
    * **When:** 4月1日 \- 4月3日  
    * **Who:** 人類 與 AI (Cursor AI 協同開發)

### ---

**第二階段：AI 自動化音樂生成迴圈 (Phase 2: AI Generation Loop)**

*核心目標：讓系統能根據設定，自動且持續地產出符合 R\&S Echoes 標準的高品質音軌。*

* **2.1 參數生成與指令下達**  
  * **2.1.1 動態 Prompt 組合**  
    * **What:** 根據預設的情境標籤庫（如 Genre, Reverb, Pacing），隨機組合出符合 Instrumental 與 Ambient 條件的 Suno 生成指令。  
    * **When:** 系統運行時（動態觸發）  
    * **Who:** AI (Openclaw Agent / LLM)  
  * **2.1.2 任務排隊與 API 呼叫**  
    * **What:** 將生成的 Prompt 送入 Suno，建立任務佇列，並監控生成狀態直到音軌完成。  
    * **When:** 系統運行時（動態觸發）  
    * **Who:** AI (管線控制腳本)  
* **2.2 音訊後製與母帶處理 (Auto-Mastering)**  
  * **2.2.1 檔案抓取與環境音疊加**  
    * **What:** 下載生成的 WAV 檔，系統自動隨機選取並疊加一段本地儲存的「高品質自然環境音軌」。  
    * **When:** 音軌下載完成後立即執行  
    * **Who:** AI (FFmpeg 自動化處理)  
  * **2.2.2 響度校正與 Metadata 寫入**  
    * **What:** 將合成後的音檔調整至 \-14 LUFS（針對 YouTube）與 \-2.0 dBTP 峰值限制，並自動寫入藝術家名稱、曲風等 Metadata，存入 /Master\_Pool/ 資料夾。  
    * **When:** 音檔合成後立即執行  
    * **Who:** AI (SoX 或 FFmpeg 音訊濾鏡)

### ---

**第三階段：本地端渲染與 24/7 直播部署 (Phase 3: Deployment & Streaming)**

*核心目標：將開發好的系統移植至專屬伺服器，啟動無人值守的 24 小時直播。*

* **3.1 伺服器硬體與推流環境建置**  
  * **3.1.1 硬體初始化與網路配置**  
    * **What:** Mac mini M4 拆箱與系統初始化，設定固定 IP 或穩定的網路連線，建立標準化的目錄結構（如生成區、暫存區、推流區）。  
    * **When:** 4月18日 \- 4月19日  
    * **Who:** 人類  
  * **3.1.2 推流引擎安裝與配置**  
    * **What:** 在 Mac mini M4 上安裝 Liquidsoap、FFmpeg 等核心推流套件，並配置 YouTube 的 RTMP 金鑰與推流環境變數。  
    * **When:** 4月19日 \- 4月21日  
    * **Who:** 人類  
* **3.2 直播控制與分發運營**  
  * **3.2.1 檔案監控與播放清單熱更新 (Hot Reload)**  
    * **What:** 執行 Watchdog 腳本監控 /Master\_Pool/ 資料夾。一旦有新生成的成品進入，立即將其路徑動態寫入 Liquidsoap 的循環清單中，設定 10 秒 Cross-fade 無縫換歌。  
    * **When:** 4月22日開始運行測試  
    * **Who:** AI (Watchdog 監控腳本與 Liquidsoap)  
  * **3.2.2 視覺渲染與 RTMP 推流**  
    * **What:** 將動態播放清單的音訊，結合預設的 4K 靜態微動態背景圖（Cinemagraph），進行低功耗即時編碼，並持續推送到 YouTube 伺服器。  
    * **When:** 4月25日（預定上線日）起 24/7 持續執行  
    * **Who:** AI (FFmpeg 即時編碼器)  
  * **3.2.3 多平台資產分發 (Spotify/Apple Music)**  
    * **What:** 從 /Master\_Pool/ 挑選表現良好的音軌，批次上傳至 DistroKid，執行瀑布式發行策略。  
    * **When:** 每週排程執行  
    * **Who:** 人類 (初期確認品質) \-\> AI (後期若有 API 對接可轉自動化)