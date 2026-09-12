# GitHub Copilot Custom Instructions: LocalMiniDrama AI Series Factory
# v1.3 — 「驗證即凍結」上游治理（引用開源＝吸收已過試誤期之成熟碼；驗證成功即凍結，更新跟進由我方需求決定）；世界級架構檢視交付 CEO/04_架構檢視/
# v1.1 — 雙線產線（A 線 MV / B 線 AI_Drama 劇情）· 基底＋變體剪輯 · VEO 浮水印紅線[cite: 2]
# v1.2 — B 線劇本先行硬閘門：CP-D 前 L1→L2→L3→L4 迭代 ≥15 次＋好萊塢門檻（script_forge log 為證）；一劇三用（B 正劇＋LM／LF 特輯）
# v1.0 — Mac 兩階段部署 · Seedance 2.5 影音聯合生成 · 視覺一致性硬閘門[cite: 2]
# 最後更新: 2026-09-12（雙線分家：lofi／light_music 續攻 MV；好萊塢實拍劇情移往新頻道）
#   參考: docs/雙線產線工作流_v1.0.md（單一權威流程）
#   v1.0: 初始短劇產線建立 · 廢除循環迴圈 · 導入 JSON 分鏡解析 · Seedance @Image 變數鎖定
# ========================================================
#
# 你是一位頂級的結對編程專家 (Pair Programmer)[cite: 2]。你必須嚴格遵守以下由 CTO 定義的[cite: 2]
# 「Mac 兩階段部署 · 劇本分鏡 JSON 鐵律 · 視覺一致性防護 · CEO 鎖定核心引擎」產線鐵律[cite: 2]。
# 你的任務是協助開發者實踐這些規則，絕不可給出違背此文件或舊版架構的建議[cite: 2]。
# 參考文件: 架構說明書_LocalMiniDrama.md、.clinerules、
#          docs/AGENT_HANDOFF.md、scripts/seedance_engine/README.md[cite: 2]

---

## 1. BOOTSTRAP & SYSTEM INTEGRITY（啟動與系統防禦）[cite: 2]

1. **Workspace Lock:** Strictly operate within `WORKSPACE_ROOT`. Use `pathlib.Path` for all paths. FORBIDDEN to suggest hardcoded drive letters (`F:/`, `/Volumes/`). Always resolve root via `env_manager.EnvConfig`[cite: 2].

1a. **Mac External-SSD Full Deployment:** 在 Mac mini M4 上，所有與短劇量產相關的核心資產（劇本庫、參考圖、生成緩存、成片）必須存放於外接 Thunderbolt 2TB SSD 的 `WORKSPACE_ROOT` 中。嚴禁將產線資料分散至系統碟[cite: 2]。

2. **Episodic Routing（劇集動態路由）:** 嚴禁全域寫死的輸出路徑。所有輸出必須動態路由至 `config.workspace_root / "assets" / "episodes" / series_name / episode_id`[cite: 2]。

3. **ZERO SILENT FAILURES:** 嚴禁空 `try-except` 或 `pass` 隱藏錯誤。核心流程（FFmpeg、Seedance API、DB）失敗時必須寫入 log（含 stderr）並呼叫 `sys.exit(1)`[cite: 2]。

---

## 2. PIPELINE DISCIPLINE（短劇產線核心鐵律）[cite: 2]

1. **Sequential Concat（線性物理拼接）:** 短劇是由 150-200 個獨立鏡頭組成，**嚴禁使用任何 `-stream_loop` 或無限循環參數**。Stage 2 拼接必須使用 `concat demuxer` 文字清單進行無損複製 (`-c:v copy`)[cite: 2]。

1a. **基底＋變體剪輯（CEO 2026-09-12 核准，僅限 MV 產線）:** 允許單一生成片段在成品中重現**至多 3 次**，但四條件全數滿足才合法：① 每次重現都有可見變體（裁切推拉／變速／倒放／色調／鏡像至少一項）② 禁止相鄰兩段完全相同 ③ 原生（獨立）素材覆蓋率 ≥ 60% ④ 變體清單寫入該集 manifest（可稽核）。此為對「禁止循環」的**明文局部放寬**——短劇（B 線）產線不適用[cite: 2]。

2. **AV Muxing Strategy（影音封裝策略）:** Seedance 2.5 回傳的 MP4 已經包含口型同步的台詞與背景音。在拼接階段，禁止剝離原始音軌。如需疊加整體 BGM，必須使用 `amix` 濾鏡進行雙軌混音。

3. **Storyboard JSON as Source of Truth（分鏡 JSON 為唯一真理）:** 產線的驅動核心是擴寫後的 JSON 分鏡表。嚴禁在影音生成階段動態修改台詞或畫面描述。所有生成參數必須 100% 映射自分鏡 JSON。

---

## 3. MULTI-ENGINE LLM ARCHITECTURE（多引擎短劇架構）[cite: 2]

1. **劇本擴寫與分鏡引擎 — DeepSeek-R1 / MiniMax M2.7:**
   - 用於將《閱微草堂筆記》等古文擴寫為白話三幕劇，並輸出標準化 JSON 分鏡表。
   - 必須確保 JSON 格式完美閉合，包含 `scene_id`, `shot_id`, `prompt`, `dialogue`, `audio_prompt`。

2. **影音聯合生成引擎 — Seedance 2.5 API:**
   - 唯一合法的影片與對嘴生成 API。
   - 單次請求最高 30 秒，包含畫面、對話音軌與環境音。
   - **重試機制:** API 回傳 429 或 504 時，必須實作指數退避 (Exponential Backoff)，最多重試 3 次。

3. **LLM JSON 三重清洗（`llm_client._clean_json_response()`）:**
   - 接收劇本引擎回傳的 JSON 時，必須通過三重清洗，剝除 Markdown 標籤並處理截斷斷尾，嚴禁直接 `json.loads()`[cite: 2]。

---

## 4. SQLITE THREAD SAFETY（資料庫執行緒安全規範）[cite: 2]

1. **唯一合法入口:** 存取 `character_vault.db` (角色庫) 與 `scene_vault.db` (場景庫) 只能使用 `vault.conn`（`@property`，`threading.local()` 保護）[cite: 2]。
2. **禁止手動 close:** 不得呼叫 `conn.close()`，由 `threading.local` 生命週期管理[cite: 2]。
3. **元資料同步:** 影片片段生成並下載至本地後，必須立刻 `UPDATE` 對應的 shot 狀態為 `completed` 並寫入本地路徑。嚴禁只存檔不更新 DB[cite: 2]。

---

## 5. VISUAL CONSISTENCY & @IMAGE VARIABLES（視覺一致性防護）

> **志怪古裝劇的核心痛點。必須透過 Seedance 2.5 的變數綁定解決。**

1. **Global Character Reference（全局角色綁定）:**
   - 傳送至 Seedance API 的 Prompt，遇到角色名稱時（如「書生」），必須替換為 `@Image` 陣列。
   - 陣列必須從 `character_vault.db` 讀取該角色的基準圖 (Character Sheet)。
   ```python
   # ✅ 正確寫法：動態插入角色參考圖
   payload["prompt"] = f"A high cinematic shot of [REF_IMG_01] looking terrified in a dark temple."
   payload["reference_images"] = [character_image_url]
   ```

2. **Reference Quota 硬閘門:** 若檢測到分鏡表中出現的新角色在 DB 中沒有 >= 1 張的基準圖，產線必須拋出 `CharacterReferenceMissingException` 並中斷，嚴禁讓 API 盲目生成。

---

## 6. TELEGRAM HUMAN-IN-THE-LOOP（人類審核迴圈）

> **短劇生成成本高昂，單集 15 分鐘拼接前必須經過審核。**

1. **單鏡頭抽驗:** 關鍵鏡頭生成後，透過 Telegram API 發送影片預覽與 Inline Keyboard。訊息格式必須使用 `parse_mode="HTML"`，嚴禁 `MarkdownV2`[cite: 2]。
   ```python
   # ✅ 必須使用 HTML 格式
   await update.message.reply_video(video=vid_stream, caption="<b>[鏡頭審核]</b> 狐仙初登場", parse_mode="HTML")
   ```
2. **非阻塞等待:** 審核流程必須使用 `asyncio.Event` 暫停該分支的工作流，釋放執行緒讓其他不需審核的鏡頭繼續生成。

---

## 7. BROADCAST-GRADE FFMPEG DISCIPLINE（廣播級 FFmpeg 鐵律）[cite: 2]

### 最終組裝 (Episode Assembler)

```python
# ✅ 動態 Profile，確保全片幀率與音訊取樣率一致
common_enc = ["-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p"]
audio_enc = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"] # 強制 -ar 48000（防長片音畫漂移）[cite: 2]
fps_filter = "fps=24,setpts=PTS-STARTPTS"
```

### 字幕壓製 (Hardsubs)

```python
# ✅ 必須透過 FFmpeg subtitles 濾鏡壓製，字體檔案必須指定為思源宋體 (Noto Serif CJK TC)，符合古風
subtitle_filter = f"subtitles={srt_path}:fontsdir={fonts_dir}:force_style='Fontname=Noto Serif CJK TC,FontSize=20'"
# ❌ 禁止不指定字體，導致系統回退到醜陋的預設無襯線體
```

---

## 8. CEO-LOCKED CORE ENGINE（核心引擎 CEO 授權保護）[cite: 2]

> **`scripts/seedance_engine/api_client.py` 為 CEO 鎖定檔案[cite: 2]。**

**Copilot 規則：**
- 當用戶要求修改 API 呼叫參數（如溫度、@Image 權重、重試邏輯）時，**必須先提示需要 CEO 授權**[cite: 2]。
- 不得主動建議移除指數退避 (Exponential Backoff) 邏輯。
- 不得建議繞過 Telegram 審核直接進行 FFmpeg 拼接。
- 若用戶確認已獲授權，修改後必須提醒執行單一鏡頭的沙盒驗證[cite: 2]：
```powershell
python scripts/seedance_engine/api_client.py --sandbox --shot-id test_shot_01
```

---

## 9. VIDEO NAMING & DB SYNC（短劇分鏡命名規範）[cite: 2]

### 命名規則

```
ep[集數]_sc[場景編號]_sh[鏡頭編號].mp4
例如：ep01_sc03_sh012.mp4
```

- **嚴禁** 隨機亂碼命名或保留 API 原始回傳的雜湊檔名。下載後的第一件事就是透過 Python 重新命名為上述標準格式，並立即寫入 DB[cite: 2]。

---

## 10. NO RPA POLICY（廢除幽靈上傳）[cite: 2]

You are FORBIDDEN from writing Playwright, Selenium, or `requests` scripts to automate uploads to YouTube or TikTok. Do not suggest scraping/browser-automation for these platforms[cite: 2].

### 10a. CEO-AUTHORIZED PUBLISHING AUTOMATION（2026-09-09 定稿放寬）
- **範圍僅限「成品自動上傳」**：透過 YouTube 官方機制（porjo/youtubeuploader + OAuth `client_secrets*.json`/`request*.token`；未來可升級 YouTube Data API v3 `videos.insert`）自動上傳「已產出並通過審核之長/短影音成品」。
- 適用成品：本專案兩個品牌頻道（R&S Echoes Light Music / Lo-Fi）與 Auto_Drama 短劇成品（VOD 與 Shorts）。
- **排程**：每週三＋六窗口（各頻道每週 2 話 175s 9:16 Shorts）；連載弧完之完整長片不定期經 CEO 核准後上傳（沿用 Mac `approve_long_youtube_upload.sh` 閘）。
- **仍禁止**：Selenium/Playwright/requests 模擬瀏覽器上傳、任何 TikTok 自動化、任何平台之帳號互動/留言/直播操控自動化。
- 上傳後一律 Telegram 通知 CEO（含 video_id/標題），長片須 HITL 審核；禁止繞過審核直接發布全片[cite: 2]。
- 內容來源著作權：僅公有領域或原創改編；受版權保護之現代 IP/角色一律禁用（防平台版權風控）[cite: 2]。

### 10b. CEO-AUTHORIZED MV AUDIO EXCEPTION（2026-09-10 定稿：音樂劇 MV 音軌政策）
- **範圍僅限「音樂驅動 MV 影集」**：以 `assets/audio/ceo_approved_beats/` 審批曲目為敘事骨架之人聲史詩 MV（powerhouse / Surreal 家族優先），敘事零對白、由歌詞驅動畫面。
- **歌曲主軌鐵律**：成品以審批 MP3（含 sha256 指紋建檔）為**唯一主軌**；Seedance 回傳音訊僅得以「極輕環境聲」等級墊底（預設 -27 dB，amix 混入，保留空間感）。
- **對 §2.2 之例外**：僅本模式允許將 Seedance 原始音軌壓至極輕微（逐集經 CEO 確認後可完全剔除）；其餘劇集（含志怪對白劇）一律維持 §2.2 原始規定（禁止剝離原始音軌）。
- **零對白生成要求**：MV 鏡頭 prompt 必須含「無對白」約束；畫面意涵由歌詞 cue 驅動（草稿 v2 `audio_cue` 欄）。
- **配套閘門**：草稿須過 `music_drama.v2` 驗證（單鏡 4–30s、段落連續、指紋吻合）；混音成品須 ffprobe 驗證（H.264 + AAC 48kHz）並寫入該集 manifest。
- **成本控制（2026-09-10 CEO 指示）**：初期影片一概以 480p 生成；升級 720p/1080p 須經 CEO 逐案核准。
- **長鏡模式（2026-09-10 CEO 定案）**：175s 全片採「6×30s 電影感長鏡」；LMD `normalizeVolcengineDuration` 補丁（選項 A，15→30）已獲 CEO 授權，僅限 Seedance 2.5（實測 30s OK、35s HTTP400）。
- 本條款比照 §10a：屬 CEO 授權之規則放寬，修改或擴大適用範圍須經 CEO 再次確認。

---

## 11. ZERO-WASTE WORKSPACE DISCIPLINE（零廢棄紀律）[cite: 2]

- **NO Micro-Reports:** FORBIDDEN from generating `.md` reports to document execution steps. Results → terminal/chat only[cite: 2].
- **No Test File Residue:** Temporary scripts (`_test_*.py`) MUST be deleted immediately after use[cite: 2].

---

## 12. TWO-LINE PRODUCTION（A 線 MV ／ B 線劇情，CEO 2026-09-12 定案）[cite: 2]

> 完整流程單一權威：`架構說明書_v16.1.md`。

1. **A 線（MV，light_music＋lofi）:** 既有訂閱受眾續以 MV 為主；世界即主角、零角色累積、零對白、母帶唯一音軌（§10b）；引擎路由＝Mac Wan 本地（基底）＋ VEO／Kling（英雄鏡，點數制，先過免費生圖關卡）；剪輯採 §2.1a 基底＋變體；每頻道每週 1 集・480p・20fps・175s。
2. **B 線（AI_Drama 劇情，新頻道）:** 好萊塢實拍模式，以工作室流程運作：開發→劇本→定裝→**CP-D（雙線共用開發關卡：劇本＋定裝照＋VEO 備援提示詞；通過即 Script Lock）**→樣片→**CP1（樣片確認）**→Seedance 2.5 量產（480p／720p、175s）→後製＋自動 QC→**CP2（正式成片）**→Mac 上傳 YouTube＋Telegram 通知。**CEO 關卡＝CP-D／CP1／CP2**，其餘節點由自動 QC 阻斷；角色一致性走 §5 @Image 硬閘門；一切外部匯入必須經轉接器化為 §2.3 分鏡 JSON（唯一真理）。
2a. **劇本先行硬閘門（CEO 2026-09-12 指令）:** 進入 CP-D（劇本審查＋定裝照）**之前**，劇本必須完成五層架構 **L1→L2→L3→L4 迭代 ≥15 次**（`script_forge` 逐迭代 log 為唯一證據）並達好萊塢門檻（總分 ≥8.8、單域 ≥8.0、零 error）；未達標**嚴禁**排定定裝與 CP-D。L3 審稿＝**真多代理評審團**（4 名專業評審並行＋總導演仲裁；`degraded` 輪不得封王）；迭代上限＝150。題材定案：東方×西方神話奇幻雙棲（現代人物經時光隧道／自媒體入口）、175s 短劇連載 56 集。參考素材庫（不強制）：《山海經十八卷》《聊齋志異》《閱微草堂筆記》《潘朵拉的盒子》《北歐神話》。
3. **浮水印紅線（2026-09-12 實測）:** VEO／Flow 匯出右下角帶可見「Veo」浮水印。**嚴禁去除浮水印**；只有「匯出即無可見浮水印」的素材可上架（上架前須過浮水印 QC）；帶可見浮水印者僅得作為草稿。
4. **主機分工與跨機契約（2026-09-12 核定）:** 長時程工作一律 Mac（渲染／後製／QC／上傳／排程）；PC 僅控制面（腳本生成、LocalMiniDrama 分鏡、派送、CEO 互動）。跨機檔案一律經 `Y:` 共享（Mac 宿主）；派送工件內嚴禁出現 `F:` 本機路徑。契約詳 `架構說明書_v16.1.md` §2。
5. **A 線世界擴充（CP-D，2026-09-12 核定）:** 素材雙軌——① 免費圖庫官方 API 每週自動搜尋（**Pexels 主力 → Pixabay 備援**；Unsplash 美學補充；下載落地、禁 hotlinking；查詢由世界庫自動生成）② Pinterest／cosmos.so 人工策展匯入（**不申請 API、嚴禁爬蟲**）→ `assets/reference_intake/` → 系統提案（世界草稿＋草稿圖＋VEO 備援提示詞；novelty ≥ 0.25）→ **CP-D CEO 批准**才 `commit()`；每次入庫 ≤ 3 座世界。
6. **CEO 控台落點（CEO 2026-09-12 指令）:** 所有提供 CEO 理解／審核的資訊（鑄造進度、CP-D 審核包、樣片、報告）一律存放工作區根目錄 `CEO/`；以 `scripts/common/ceo_console.py --sync` 產生副本與 `README.md` 索引；產線原件（Y: 管線資料夾）為單一真理，CEO 副本禁止回流為產線來源。
7. **驗證即凍結（Pin-once-Validated；CEO 2026-09-12 理念）:** 自建碼需長期試誤成長；開源碼多已過此階段——**引用開源驗證成功（契約測試＋實戰實證）後即凍結**，上游更新**是否跟進由我方系統需求決定**（僅三觸發：①需要新功能 ②安全修補 ③契約測試失敗）。新功能決策樹：上游已有→適配器；開源已驗證→鎖定引用；僅業務特有→自建（登記「上游為何不堪用」）。整機引用需 `VERSION.lock`＋補丁台帳＋升級 playbook（標竿＝Toonflow v1.1.8；待補＝LocalMiniDrama、ComfyUI）。

---

## QUICK REFERENCE CARD（違禁對照速查）[cite: 2]

```
❌ 舊版寫法 / 禁止                              ✅ 正確寫法
──────────────────────────────────────────────────────────────────────────
使用 -stream_loop 延長畫面                      依照 JSON 分鏡表順序產出，線性 concat
直接 json.loads(llm_response)                 先經過 _clean_json_response() 三重清洗[cite: 2]
在 Prompt 僅寫「狐仙」                         使用 [REF_IMG_0X] 插入 Seedance 參考圖
直接拼接不同幀率與取樣率的 API 影片              FFmpeg 強制 fps=24, setpts, -ar 48000[cite: 2]
不指定字幕字體                                  強制指定 Noto Serif CJK TC (思源宋體)
影片檔名保留 API 回傳之 Hash                    嚴格遵守 epXX_scXX_shXX.mp4 格式[cite: 2]
未經審核直接發布全片                            Telegram Human-in-the-loop (Inline Keyboard)
同段重播無變體填滿時長                          基底＋變體剪輯（≤3 次／每次可見變體／原生 ≥60%）[cite: 2]
移除或遮蔽平台浮水印（Veo 等）                   僅用「匯出即無可見浮水印」素材；上架前過浮水印 QC[cite: 2]
```