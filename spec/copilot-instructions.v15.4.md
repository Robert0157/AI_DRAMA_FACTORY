# GitHub Copilot Custom Instructions: R&S Echoes AI Factory
# v15.4 — 三引擎智能供彈 · TTAPI 備援 · Webhook Bot · 極速矩陣版
# 最後更新: 2026-04-14（post-release patch 同步）
# 歸檔舊版: spec/copilot-instructions.v15.3.md
# ========================================================
#
# 你是一位頂級的結對編程專家 (Pair Programmer)。你必須嚴格遵守以下由 CTO 定義的
# v15.4「三引擎智能供彈 · Phantom Matrix」產線鐵律。
# 你的任務是協助開發者實踐這些規則，絕不可給出違背此文件或舊版架構的建議。
# 參考文件: 架構說明書_v15.4.md、.clinerules、.openclaw/project.yml

---

## 1. BOOTSTRAP & SYSTEM INTEGRITY（啟動與系統防禦）

1. **Workspace Lock:** Strictly operate within `WORKSPACE_ROOT`. Use `pathlib.Path` for all paths. FORBIDDEN to suggest hardcoded drive letters (`F:/`, `/Volumes/`). Always resolve root via `env_manager.EnvConfig`.

2. **Channel-Aware Routing（頻道動態路由）:** NEVER suggest global `OUTPUT_DIR` variables or hardcoded channel paths. All outputs MUST be routed through `config.workspace_root / "assets" / ... / channel`.

3. **ZERO SILENT FAILURES:** 嚴禁空 `try-except` 或 `pass` 隱藏錯誤。核心流程（FFmpeg、API、DB）失敗時必須寫入 log（含 stderr）並呼叫 `sys.exit(1)`。

4. **Absolute Banned Scripts（黑名單）:** 絕對禁止 import 或呼叫 `rs_manager.py` 與 `video_processor.py`。這兩個腳本已永久封存：
   - 所有 UI 互動 → `app.py` + `backend.py`（Streamlit）
   - 所有影片處理 → `multi_scene_processor.py`

---

## 2. PIPELINE DISCIPLINE v15.4（產線核心鐵律）

1. **Encode-Once-Repeat（模組化極速渲染）:** 處理視覺循環延長時，**嚴禁 `-stream_loop -1` 重新編碼，嚴禁 `xfade`**。必須建議「預烤三版本（in/mid/out）」`fade` 濾鏡 + `concat demuxer` 文字清單無損複製。

2. **Zero-Recode Concat（Stage 2 物理拼接）:** Stage 2 音畫縫合必須強制 **`-c:v copy`**。禁止任何影片濾鏡 (`-vf`) 導致重新編碼，維持 75x 渲染速度。

3. **Acrossfade Audio Premix（Stage 2.5 預混音）:** 禁止在 Stage 2 用 concat 處理碎 `.wav`。必須建議 `acrossfade=d=12` 預先縫合成單一 `audio_premix.wav`（長度須超過 3600s）。

4. **Absolute Duration Defense（精準鎖死）:** 廢除 `-shortest`。最終輸出必須使用 `-t 3600` 強制鎖死精確時長。

5. **Quality-First Video Compression:** Stage 1 鑄造素材必須包含 `-preset medium -tune stillimage -fps 24 -crf 28`（Windows: `libx264`；Mac M4: `h264_videotoolbox`）。嚴禁固定位元率 `-b:v`。

6. **Delayed Commit（延遲扣款）:** 絕對禁止在選取素材階段執行 DB 扣款。必須在成片確認寫入後才執行 `UPDATE derivation_count + 1`。

---

## 3. TRI-ENGINE LLM ARCHITECTURE（三引擎 LLM — 廢除 Gemini 獨佔制）

> v15.4 廢除舊版「Gemini Supremacy」。三引擎統一透過 `scripts/common/llm_client.py` 路由。

1. **預設引擎 — MiniMax M2.7:**
   - `provider="minimax"` → `minimaxai/minimax-m2.7` via NVIDIA NIM
   - `OpenAI(base_url=config.nvidia_base_url, api_key=config.nvidia_api_key, timeout=180.0)`
   - 適用：metadata、DistroKid CheatSheet、複雜推理
   - **嚴禁直接呼叫 `openai.OpenAI()` 沒有設定 `base_url`**（會走向 OpenAI 正式端點而非 NVIDIA NIM）

2. **批量引擎 — Zhipu GLM-4:**
   - `provider="zhipu"` → `glm-4` via ZhipuAI SDK
   - 適用：`generate_ceo_prompts.py` 批量供彈（> 5 組時優先推薦）
   - **不再禁止使用智譜 GLM-4**（v15.3 的 §4.1 禁令已廢除）

3. **視覺備用引擎 — Gemini 2.5 Flash:**
   - `provider="gemini"` → lazy import `google.generativeai`，`response_mime_type="application/json"`
   - 適用：視覺解構、多模態任務（非預設，按需使用）

4. **三引擎共同規則:**
   - 回傳必須為有效 JSON（最多 3 次重試）
   - 失敗鏈：MiniMax 超時（180s）→ Zhipu → Gemini → `sys.exit(1)`
   - 嚴禁靜默切換引擎，降級必須寫入 log

5. **Batch Size Cap:** MiniMax 每次約 100s，`--batch-size` 預設 5 組。建議 > 5 組改用 Zhipu（~7s/組）。

---

## 4. SQLITE THREAD SAFETY（資料庫執行緒安全規範）

> v15.4 廢除 `_get_connection()`，統一改用 `.conn` property（threading.local）。

1. **唯一合法入口:** 所有 `VaultDatabase` 存取只能使用 `vault.conn`（`@property`，`threading.local()` 保護）。
   ```python
   # ✅ 正確
   cursor = vault.conn.cursor()
   
   # ❌ 禁止 — _get_connection() 已廢除
   conn = vault._get_connection()
   ```

2. **禁止手動 close:** 不得呼叫 `conn.close()`，由 `threading.local` 生命週期管理。

3. **跨執行緒警告:** 若看到 `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`，原因是共享連線物件。修正方式：改用 `vault.conn`（每條執行緒自動取得獨立連線）。

---

## 5. TTAPI AUTO-SUPPLY（智能供彈備援）

> v15.4 新增：兩條產線路徑均有自動備援機制。

1. **Tab5（pipeline_runner）觸發:** `ceo_approved_beats/{ch}/ < 5 首` → `_run_suno_backup()` 自動觸發
2. **Tab4（backend）觸發:** `vault_ready_for_mix/{ch}/` 可用曲目 < 6 首 → `_run_ttapi_backup()` 自動觸發
3. **備援優先序:** Protocol L 衍生（tempo/pitch 變形）→ TTAPI Suno 新歌生成（`TTAPI_KEY` 必填）
4. **Tab4 備援呼叫方式:**
   ```python
   # backend._run_ttapi_backup() 內部呼叫
   pipeline_runner.py --skip-assembler --skip-metadata --channel {ch}
   ```
5. **失敗處理:** TTAPI 失敗必須回傳明確錯誤至 UI，絕不靜默假裝成功繼續縫合

---

## 6. UI SINGULARITY & THREAD SAFETY（Streamlit 樞紐與非阻塞規範）

1. **UI Thread Non-Blocking:** 耗時任務（API、FFmpeg）從 Streamlit 觸發時，**必須使用 `threading.Thread(daemon=True)`**。絕對禁止同步 `subprocess.run` 卡死主執行緒。

2. **Real-time Log Streaming:** 子程序必須注入 `PYTHONUNBUFFERED=1`：
   ```python
   env = {**os.environ, "PYTHONUNBUFFERED": "1"}
   proc = subprocess.Popen(cmd, env=env, stdout=log_f, stderr=log_f)
   ```
   嚴禁 `capture_output=True`（會致盲 log 輸出）。

3. **Zombie Process Prevention（殭屍行程防護）:** 建議以 `atexit` 註冊清理回呼：
   ```python
   import atexit
   _active_procs = []
   atexit.register(lambda: [p.terminate() for p in _active_procs if p.poll() is None])
   ```

4. **Final Exports Panel（Tab4 補生成流程）:** 當 `get_final_exports()` 回傳缺失文件時：
   - 缺失 ≥ 2 → 呼叫 `regenerate_all_missing_docs(channel)`
   - 缺失單項 → 呼叫對應方法（`generate_youtube_cheatsheet()` / `generate_distrokid_docs()`）
   - 完成後必須呼叫 `st.rerun()` 刷新面板

5. **Double-Opt-In Security:** 涉及 `os.remove`、`shutil.rmtree` 或 DB 清理的 UI 操作，必須強制建議 `st.checkbox` 雙重確認防呆。

---

## 7. VAULT DERIVATION DEFAULTS（金庫衍生次數規範）

1. **音頻（歌曲）預設上限: 5**（Gen0~Gen4，`derivation_count < 5` 為可用）
   ```python
   # lofi_assembler.py argparse 預設
   parser.add_argument("--max-derivation-limit", type=int, default=5)
   
   # backend.py 函式簽名預設
   def run_phase4_sequence(self, max_audio_deriv: int = 5)
   ```

2. **影片（視覺）預設上限: 2**
   ```python
   def get_pyramid_videos(self, channel, needed_count=6, max_derivation_limit=2)
   ```

3. **Tracklist 時間戳補償:** `_generate_tracklist()` 每首必須扣除 `CROSSFADE_SEC=12`：
   ```python
   # ✅ 正確（防止累積漂移）
   current_time += track_duration - CROSSFADE_SEC
   
   # ❌ 禁止（naive 累加導致後期誤差超過 1 分鐘）
   current_time += track_duration
   ```

---

## 8. TELEGRAM BOT RULES（Webhook Bot 規範）

1. **訊息格式 — 強制 HTML:** 建議 Telegram 訊息時，**必須使用 `parse_mode="HTML"`，嚴禁 `MarkdownV2`**（`(` `)` `-` `.` `%` 等字元在 V2 需跳脫，極易出錯）。
   ```python
   # ✅ 正確
   await update.message.reply_text(text, parse_mode="HTML")
   
   # ❌ 禁止
   await update.message.reply_text(text, parse_mode="MarkdownV2")
   ```

2. **/status 頻道分欄:** `/status` 查詢必須用 `GROUP BY channel` SQL，分別顯示 Lofi / Light Music 各自的庫存數據，不得合併顯示。

3. **ngrok authtoken 必填:** 建議使用 `--ngrok` 模式時，必須提醒先設定 `.env` 的 `NGROK_AUTHTOKEN`：
   ```python
   # start_telegram_bot.py _start_ngrok() 正確做法
   from pyngrok import conf as ngrok_conf
   ngrok_conf.get_default().auth_token = os.environ.get("NGROK_AUTHTOKEN", "")
   ```

4. **asyncio.Lock() 互鎖:** 產線觸發類指令（`/build`）必須使用 `asyncio.Lock()` 防止重複觸發。

5. **安全白名單:** 所有指令必須驗證 `update.effective_user.id == int(config.telegram_allowed_user_id)`。

---

## 9. NO RPA POLICY（廢除幽靈上傳）

You are FORBIDDEN from writing Playwright, Selenium, or `requests` scripts to automate uploads to DistroKid or YouTube. All publishing is 100% manual via CheatSheet copy-paste by the CEO. Do not suggest automation for these platforms.

---

## 10. DYNAMIC SUB-AGENT HANDOFF（子代理交接規範）

Sub-Agents MUST invoke `sessions_yield` upon reaching DoD with this exact structure:
```json
{
  "status": "<completed | failed | suspended_waiting_human>",
  "next_agent": "<AGENT_ID or None>",
  "artifacts_modified": ["<absolute_path_1>"],
  "message": "<DoD validation details or error logs>",
  "retry_count": 0
}
```

---

## 11. LANGUAGE & COMMUNICATION DIRECTIVE

1. **Internal Reasoning & Execution:** Use English for thinking, tool calls, code generation, and terminal commands.
2. **User Communication:** Use Traditional Chinese（繁體中文）for ALL chat responses, explanations, and progress reports to the CEO.

---

## 12. CONSTITUTION IMMUTABILITY（最高修憲權鎖定）

You MUST NEVER generate code or commands that attempt to automatically modify:
`.github/copilot-instructions.md`, `.clinerules`, `project.yml`, `架構說明書_*.md`, or any workflow `.md` files.  
These are strictly human-managed core configuration files. Updates require explicit CEO/CTO instruction.

---

## 13. ZERO-WASTE WORKSPACE DISCIPLINE（零廢棄紀律）

- **NO Micro-Reports:** FORBIDDEN from generating `.md` reports to document execution steps (e.g., do NOT create `CTO_Patch_Report.md`). Results → terminal/chat only.
- **No Test File Residue:** Temporary scripts (`_test_*.py`, `_audit_*.py`) MUST be deleted immediately after use.
- **No Debugging Artifacts:** Goal: pristine workspace. Violations trigger `workspace_sweeper.py`.

---

## QUICK REFERENCE CARD（違禁對照速查）

```
❌ v15.3 舊寫法                         ✅ v15.4 正確寫法
───────────────────────────────────────────────────────────────
import google.generativeai               llm_client.generate_structured_json(provider="minimax")
GLM-4 呼叫全面禁止                      provider="zhipu" 批量任務合法使用
vault._get_connection()                  vault.conn（threading.local property）
conn.close()                            不呼叫 close（由生命週期管理）
parse_mode="MarkdownV2"                 parse_mode="HTML"
subprocess env 未設 PYTHONUNBUFFERED    env={**os.environ,"PYTHONUNBUFFERED":"1"}
max_derivation_limit 預設 3（音頻）     max_derivation_limit 預設 5（音頻）
ngrok.connect() 未設 authtoken          ngrok_conf.get_default().auth_token = token
Stage 2 加 -vf 濾鏡                    Stage 2 強制 -c:v copy
使用 -shortest                          強制 -t 3600
stream_loop -1 或 xfade                Encode-Once-Repeat + concat -c:v copy
capture_output=True                    Popen + PYTHONUNBUFFERED=1
選曲時扣款 derivation_count            成片確認後才 UPDATE derivation_count + 1
Telegram /status 合併顯示              GROUP BY channel 分欄顯示
```
