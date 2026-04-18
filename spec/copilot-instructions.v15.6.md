# GitHub Copilot Custom Instructions: R&S Echoes AI Factory
# v15.6 — 廣播級無縫矩陣引擎 · 源幀率修正 · 雙重保險 · CEO 鎖定
# 最後更新: 2026-04-15
#   v15.5: Closed GOP · setpts 濾鏡優先順序 · 嚴格 IDR · GOP-QA · -ar 48000
#   v15.6: get_video_duration 源幀率修正（根治 30fps 2 秒凍結）· 雙重保險 · CEO 鎖定
# 歸檔舊版: spec/copilot-instructions.v15.4.md
# ========================================================
#
# 你是一位頂級的結對編程專家 (Pair Programmer)。你必須嚴格遵守以下由 CTO 定義的
# v15.6「廣播級無縫矩陣 · CEO 鎖定核心引擎」產線鐵律。
# 你的任務是協助開發者實踐這些規則，絕不可給出違背此文件或舊版架構的建議。
# 參考文件: 架構說明書_v15.6.md、.clinerules、.openclaw/project.yml

---

## 1. BOOTSTRAP & SYSTEM INTEGRITY（啟動與系統防禦）

1. **Workspace Lock:** Strictly operate within `WORKSPACE_ROOT`. Use `pathlib.Path` for all paths. FORBIDDEN to suggest hardcoded drive letters (`F:/`, `/Volumes/`). Always resolve root via `env_manager.EnvConfig`.

2. **Channel-Aware Routing（頻道動態路由）:** NEVER suggest global `OUTPUT_DIR` variables or hardcoded channel paths. All outputs MUST be routed through `config.workspace_root / "assets" / ... / channel`.

3. **ZERO SILENT FAILURES:** 嚴禁空 `try-except` 或 `pass` 隱藏錯誤。核心流程（FFmpeg、API、DB）失敗時必須寫入 log（含 stderr）並呼叫 `sys.exit(1)`。

4. **Absolute Banned Scripts（黑名單）:** 絕對禁止 import 或呼叫 `rs_manager.py` 與 `video_processor.py`。這兩個腳本已永久封存：
   - 所有 UI 互動 → `app.py` + `backend.py`（Streamlit）
   - 所有影片處理 → `multi_scene_processor.py`（CEO 鎖定，見 Section 8）

---

## 2. PIPELINE DISCIPLINE v15.6（產線核心鐵律）

1. **Encode-Once-Repeat（模組化極速渲染）:** 處理視覺循環延長時，**嚴禁 `-stream_loop -1` 重新編碼，嚴禁 `xfade`**。必須建議「預烤三版本（in/mid/out）」`fade` 濾鏡 + `concat demuxer` 文字清單無損複製。

2. **Zero-Recode Concat（Stage 2 物理拼接）:** Stage 2 音畫縫合必須強制 **`-c:v copy`**。禁止任何影片濾鏡 (`-vf`) 導致重新編碼，維持極速渲染速度。

3. **Acrossfade Audio Premix（Stage 2.5 預混音）:** 禁止在 Stage 2 用 concat 處理碎 `.wav`。必須建議 `acrossfade=d=5` 預先縫合成單一 `audio_premix.wav`（長度須超過 3600s）。

4. **Natural EOF Strategy（自然 EOF）:** 廢除 `-shortest`。**同時廢除 `-t 3600`**。Stage 2 讓所有 unit.ts 播至自然 EOF，消除最後一幀強制凍結延長的問題。最終成品時長允許 59~60.3 分鐘的自然誤差。

5. **Broadcast-Grade Video Compression（v15.6 鎖定）:** Stage 1 鑄造素材必須包含完整防禦陣列（見 Section 7）。嚴禁固定位元率 `-b:v`，嚴禁省略任何 Closed GOP 參數。

6. **Delayed Commit（延遲扣款）:** 絕對禁止在選取素材階段執行 DB 扣款。必須在成片確認寫入後才執行 `UPDATE derivation_count + 1`。

---

## 3. TRI-ENGINE LLM ARCHITECTURE（三引擎 LLM）

> v15.4 廢除舊版「Gemini Supremacy」。三引擎統一透過 `scripts/common/llm_client.py` 路由。

1. **預設引擎 — MiniMax M2.7:**
   - `provider="minimax"` → `minimaxai/minimax-m2.7` via NVIDIA NIM
   - `OpenAI(base_url=config.nvidia_base_url, api_key=config.nvidia_api_key, timeout=180.0)`
   - 適用：metadata、DistroKid CheatSheet、複雜推理
   - **嚴禁直接呼叫 `openai.OpenAI()` 沒有設定 `base_url`**（會走向 OpenAI 正式端點而非 NVIDIA NIM）

2. **批量引擎 — Zhipu GLM-4:**
   - `provider="zhipu"` → `glm-4` via ZhipuAI SDK
   - 適用：`generate_ceo_prompts.py` 批量供彈（> 5 組時優先推薦）

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

3. **跨執行緒警告:** 若看到 `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`，原因是共享連線物件。修正方式：改用 `vault.conn`。

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

## 7. BROADCAST-GRADE FFMPEG DISCIPLINE v15.6（廣播級 FFmpeg 鐵律）

> ⚠️ 以下所有參數由 CEO 鎖定於 `multi_scene_processor.py`。Copilot 不得建議移除或變更任何一項。

### Stage 1 編碼防禦陣列（完整，不可拆分）

```python
# ✅ v15.6 鎖定版 — 完整防禦陣列
common_enc = [
    "-map_metadata", "-1", "-an",
    "-c:v", "libx264", "-preset", "medium", "-tune", "film", "-crf", "28",
    "-pix_fmt", "yuv420p",
    "-g", "48", "-keyint_min", "48",       # 嚴格 IDR：最大=最小=48 幀
    "-sc_threshold", "0",                  # 關閉動態 I 幀偵測
    "-flags", "+cgop",                     # 強制封閉 GOP
    "-video_track_timescale", "24000",     # 統一時間基底
]

# ❌ 禁止（v15.4 舊版）
common_enc = ["-tune", "stillimage", "-g", "48"]  # 缺少 Closed GOP 防禦
```

### 濾鏡鏈順序（鐵律，絕對不可逆轉）

```python
# ✅ 正確：先建立絕對 0-based 時間軸，fade 才能幀級精準落點
vf_pre = "setpts=PTS-STARTPTS,fps=24"
passes = [
    (base_in,  f"{vf_pre},fade=t=in:st=0:d={fade_dur},{norm}",               "fade-in"),
    (base_mid, f"setpts=PTS-STARTPTS,fps=24,{norm}",                          "clean"),
    (base_out, f"{vf_pre},fade=t=out:st={fade_out_st}:d={fade_dur},{norm}",  "fade-out"),
]

# ❌ 禁止：fade 在 setpts 之前 → fade 在「髒時間軸」上錯位觸發
vf_wrong = f"fade=t=out:st=6.0,setpts=PTS-STARTPTS,fps=24"
```

### get_video_duration()（v15.6 — 源幀率修正，絕對禁止逆轉）

```python
# ✅ 正確：動態讀取源幀率，frames / source_fps
cmd = [
    "ffprobe", "-v", "error", "-select_streams", "v:0",
    "-count_packets", "-show_entries", "stream=nb_read_packets,r_frame_rate",
    "-of", "csv=p=0", str(video_path)
]
# 解析：fps_str="30/1", frames_str="240"
# duration = 240 / 30.0 = 8.0s  ← 正確

# ❌ 禁止：硬除 24.0（30fps 素材 240 幀 → 誤算 10.0s → concat 末幀凍結 2 秒）
duration = frames / 24.0
```

### 雙重保險 loop_list（v15.6 — re-probe base_mid.ts）

```python
# ✅ 正確：re-probe 已編碼的 base_mid.ts，切斷對上游估算的依賴
ts_probe = subprocess.run([
    "ffprobe", "-v", "error", "-select_streams", "v:0",
    "-count_packets", "-show_entries", "stream=nb_read_packets",
    "-of", "csv=p=0", str(base_mid)
], capture_output=True, text=True, timeout=10)
real_ts_dur = int(ts_probe.stdout.strip()) / 24.0  # 幀級精準

# ❌ 禁止：直接用上游 base_dur 估算值填入 loop_list（可能含 fps 轉換捨入誤差）
f.write(f"duration {base_dur}\n")
```

### GOP-QA 自動驗證（v15.5 — 每次 base_mid.ts 後必須呼叫）

```python
# ✅ 必須在 base_mid.ts 編碼後呼叫
self._verify_gop_closure(base_mid, expected_interval=2.0, label=f"Scene {idx+1}/{N} clean")
# 通過 → "✅ [GOP-QA] ... GOP 牢籠完好"
# 失敗 → "⚠️ [GOP-QA]" WARNING（記錄，不中斷產線）
```

### 音訊取樣率鎖定（v15.5 — 防長片音畫漂移）

```python
# ✅ Stage 2 最終 AAC 輸出必須加 -ar 48000
["-c:a", "aac", "-b:a", "320k", "-ar", "48000"]

# ❌ 省略 -ar → 44100↔48000Hz 換算浮點誤差，10hr+ 影片音畫漂移
```

---

## 8. CEO-LOCKED CORE ENGINE（核心引擎 CEO 授權保護）

> **`scripts/gear1_prod/multi_scene_processor.py` 為 CEO 鎖定檔案（v15.6 起生效）。**

**Copilot 規則：**
- 當用戶要求修改 `multi_scene_processor.py` 時，**必須先提示需要 CEO 授權**
- 不得主動建議刪除或修改 Section 7 中任何鎖定參數
- 不得建議將 `-tune film` 改回 `-tune stillimage`
- 不得建議移除 `-flags +cgop`、`-sc_threshold 0`、`-keyint_min 48` 中的任何一項
- 不得建議將 `get_video_duration()` 改回硬除 `24.0` 的舊版邏輯
- 不得建議省略雙重保險的 re-probe 步驟
- 不得建議省略 `_verify_gop_closure()` 的呼叫

**若用戶確認已獲 CEO 授權，修改後必須提醒執行 GOP-QA 沙盒驗證：**
```powershell
python scripts/gear1_prod/multi_scene_processor.py --sandbox --channel lofi --target-duration 120 --scene-dwell-time 60
# 日誌必須出現：✅ [GOP-QA] ... GOP 牢籠完好
```

---

## 9. VAULT DERIVATION DEFAULTS（金庫衍生次數規範）

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

## 10. TELEGRAM BOT RULES（Webhook Bot 規範）

1. **訊息格式 — 強制 HTML:** 建議 Telegram 訊息時，**必須使用 `parse_mode="HTML"`，嚴禁 `MarkdownV2`**。
   ```python
   # ✅ 正確
   await update.message.reply_text(text, parse_mode="HTML")
   ```

2. **/status 頻道分欄:** `/status` 查詢必須用 `GROUP BY channel` SQL，分別顯示 Lofi / Light Music 各自庫存。

3. **ngrok authtoken 必填:** 建議使用 `--ngrok` 模式時，必須提醒先設定 `.env` 的 `NGROK_AUTHTOKEN`：
   ```python
   from pyngrok import conf as ngrok_conf
   ngrok_conf.get_default().auth_token = os.environ.get("NGROK_AUTHTOKEN", "")
   ```

4. **asyncio.Lock() 互鎖:** 產線觸發類指令（`/build`）必須使用 `asyncio.Lock()` 防止重複觸發。

5. **安全白名單:** 所有指令必須驗證 `update.effective_user.id == int(config.telegram_allowed_user_id)`。

---

## 11. NO RPA POLICY（廢除幽靈上傳）

You are FORBIDDEN from writing Playwright, Selenium, or `requests` scripts to automate uploads to DistroKid or YouTube. All publishing is 100% manual via CheatSheet copy-paste by the CEO. Do not suggest automation for these platforms.

---

## 12. DYNAMIC SUB-AGENT HANDOFF（子代理交接規範）

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

## 13. LANGUAGE & COMMUNICATION DIRECTIVE

1. **Internal Reasoning & Execution:** Use English for thinking, tool calls, code generation, and terminal commands.
2. **User Communication:** Use Traditional Chinese（繁體中文）for ALL chat responses, explanations, and progress reports to the CEO.

---

## 14. CONSTITUTION IMMUTABILITY（最高修憲權鎖定）

You MUST NEVER generate code or commands that attempt to automatically modify:
`.github/copilot-instructions.md`, `.clinerules`, `project.yml`, `架構說明書_*.md`, or any workflow `.md` files.  
These are strictly human-managed core configuration files. Updates require explicit CEO/CTO instruction.

---

## 15. ZERO-WASTE WORKSPACE DISCIPLINE（零廢棄紀律）

- **NO Micro-Reports:** FORBIDDEN from generating `.md` reports to document execution steps (e.g., do NOT create `CTO_Patch_Report.md`). Results → terminal/chat only.
- **No Test File Residue:** Temporary scripts (`_test_*.py`, `_audit_*.py`) MUST be deleted immediately after use.
- **No Debugging Artifacts:** Goal: pristine workspace. Violations trigger `workspace_sweeper.py`.

---

## QUICK REFERENCE CARD v15.6（違禁對照速查）

```
❌ 舊版寫法 / 禁止                              ✅ v15.6 正確寫法
──────────────────────────────────────────────────────────────────────────
import google.generativeai 直接使用              llm_client.generate_structured_json(provider="minimax")
vault._get_connection()                         vault.conn（threading.local property）
conn.close()                                    不呼叫 close（由生命週期管理）
parse_mode="MarkdownV2"                         parse_mode="HTML"
subprocess env 未設 PYTHONUNBUFFERED            env={**os.environ, "PYTHONUNBUFFERED": "1"}
max_derivation_limit 預設 3（音頻）             max_derivation_limit 預設 5（音頻）
ngrok.connect() 未設 authtoken                  ngrok_conf.get_default().auth_token = token
Stage 2 加 -vf 濾鏡                            Stage 2 強制 -c:v copy
使用 -shortest                                  自然 EOF（不加 -t 限制）
使用 -t 3600 截斷                               自然 EOF 策略（Stage 2 無 -t）
stream_loop -1 或 xfade                        Encode-Once-Repeat + concat -c:v copy
capture_output=True                            Popen + PYTHONUNBUFFERED=1
選曲時扣款 derivation_count                    成片確認後才 UPDATE derivation_count + 1
Telegram /status 合併顯示                       GROUP BY channel 分欄顯示
-tune stillimage                               -tune film（保留動態細節）
Stage 1 缺少 -flags +cgop                      完整 Closed GOP 防禦陣列（九參數）
Stage 1 缺少 -sc_threshold 0                   同上
Stage 1 缺少 -keyint_min 48                    同上
Stage 1 缺少 -video_track_timescale 24000      同上
get_video_duration 硬除 24.0                    動態讀取 r_frame_rate，frames/source_fps
fade 濾鏡放在 setpts 之前                       setpts=PTS-STARTPTS,fps=24 → fade → norm
loop_list duration 用上游估算值                  re-probe base_mid.ts 實際幀數÷24（雙重保險）
省略 _verify_gop_closure() 呼叫                每次 base_mid.ts 後必須呼叫 GOP-QA
Stage 2 AAC 不設 -ar                           強制 -ar 48000（防長片音畫漂移）
未授權修改 multi_scene_processor.py            先取得 CEO 書面授權 + 通過 GOP-QA 沙盒驗證
```
