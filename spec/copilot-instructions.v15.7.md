# GitHub Copilot Custom Instructions: R&S Echoes AI Factory
# v15.7 — 智能 Ping-Pong 迴圈引擎 · LLM JSON 修復 · 選曲遞補 · 視覺 DB 遷移
# 最後更新: 2026-04-17
#   v15.5: Closed GOP · setpts 濾鏡優先順序 · 嚴格 IDR · GOP-QA · -ar 48000
#   v15.6: get_video_duration 源幀率修正（根治 30fps 2 秒凍結）· 雙重保險 · CEO 鎖定
#   v15.7: ping_/ford_ 前綴 Ping-Pong 迴圈 · LLM max_tokens=4096 + JSON 三重清洗 · lofi 選曲遞補 · 視覺 DB 路徑遷移
# 歸檔舊版: spec/copilot-instructions.v15.6.md
# ========================================================
#
# 你是一位頂級的結對編程專家 (Pair Programmer)。你必須嚴格遵守以下由 CTO 定義的
# v15.7「智能 Ping-Pong 迴圈引擎 · CEO 鎖定核心引擎」產線鐵律。
# 你的任務是協助開發者實踐這些規則，絕不可給出違背此文件或舊版架構的建議。
# 參考文件: 架構說明書_v15.7.md、.clinerules、.openclaw/project.yml

---

## 1. BOOTSTRAP & SYSTEM INTEGRITY（啟動與系統防禦）

1. **Workspace Lock:** Strictly operate within `WORKSPACE_ROOT`. Use `pathlib.Path` for all paths. FORBIDDEN to suggest hardcoded drive letters (`F:/`, `/Volumes/`). Always resolve root via `env_manager.EnvConfig`.

2. **Channel-Aware Routing（頻道動態路由）:** NEVER suggest global `OUTPUT_DIR` variables or hardcoded channel paths. All outputs MUST be routed through `config.workspace_root / "assets" / ... / channel`.

3. **ZERO SILENT FAILURES:** 嚴禁空 `try-except` 或 `pass` 隱藏錯誤。核心流程（FFmpeg、API、DB）失敗時必須寫入 log（含 stderr）並呼叫 `sys.exit(1)`。

4. **Absolute Banned Scripts（黑名單）:** 絕對禁止 import 或呼叫 `rs_manager.py` 與 `video_processor.py`。這兩個腳本已永久封存：
   - 所有 UI 互動 → `app.py` + `backend.py`（Streamlit）
   - 所有影片處理 → `multi_scene_processor.py`（CEO 鎖定，見 Section 8）

---

## 2. PIPELINE DISCIPLINE v15.7（產線核心鐵律）

1. **Encode-Once-Repeat（模組化極速渲染）:** 處理視覺循環延長時，**嚴禁 `-stream_loop -1` 重新編碼，嚴禁 `xfade`**。必須建議「預烤三版本（in/mid/out）」`fade` 濾鏡 + `concat demuxer` 文字清單無損複製。

2. **Zero-Recode Concat（Stage 2 物理拼接）:** Stage 2 音畫縫合必須強制 **`-c:v copy`**。禁止任何影片濾鏡 (`-vf`) 導致重新編碼，維持極速渲染速度。

3. **Acrossfade Audio Premix（Stage 2.5 預混音）:** 禁止在 Stage 2 用 concat 處理碎 `.wav`。必須建議 `acrossfade=d=5` 預先縫合成單一 `audio_premix.wav`（長度須超過 3600s）。

4. **Natural EOF Strategy（自然 EOF）:** 廢除 `-shortest`。**同時廢除 `-t 3600`**。Stage 2 讓所有 unit.ts 播至自然 EOF，消除最後一幀強制凍結延長的問題。最終成品時長允許 59~60.3 分鐘的自然誤差。

5. **Broadcast-Grade Video Compression（v15.7 鎖定）:** Stage 1 鑄造素材必須包含完整防禦陣列（見 Section 7）。嚴禁固定位元率 `-b:v`，嚴禁省略任何 Closed GOP 參數。

6. **Delayed Commit（延遲扣款）:** 絕對禁止在選取素材階段執行 DB 扣款。必須在成片確認寫入後才執行 `UPDATE derivation_count + 1`。

7. **Ping-Pong Loop Strategy（v15.7）:** 讀取 `ping_`/`ford_` 前綴決定迴圈策略。**嚴禁** 忽略前綴或對所有素材使用相同策略。詳見 Section 6。

---

## 3. TRI-ENGINE LLM ARCHITECTURE（三引擎 LLM）

> v15.4 廢除舊版「Gemini Supremacy」。三引擎統一透過 `scripts/common/llm_client.py` 路由。

1. **預設引擎 — MiniMax M2.7:**
   - `provider="minimax"` → `minimaxai/minimax-m2.7` via NVIDIA NIM
   - `OpenAI(base_url=config.nvidia_base_url, api_key=config.nvidia_api_key, timeout=180.0)`
   - **`max_tokens=4096`**（v15.7：從 2048 提升，防止雙語曲名 JSON 截斷）
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

6. **LLM JSON 三重清洗（v15.7，`llm_client._clean_json_response()`）:**
   ```python
   # ✅ 正確：三重清洗後才 json.loads()
   def _clean_json_response(response_text: str) -> str:
       import re as _re
       text = response_text.strip()
       # Step 1: 剝除 ```json ... ``` Markdown 包裝
       text = _re.sub(r'```(?:json)?\s*\n?', '', text, flags=_re.IGNORECASE)
       text = _re.sub(r'\n?```', '', text).strip()
       # Step 2: 定位首個 '{'，截取後段（應對 LLM 前置說明文字）
       brace_start = text.find('{')
       if brace_start > 0:
           text = text[brace_start:]
       # Step 3: 自動補全未閉合括號（應對 max_tokens 截斷）
       text += '}' * (text.count('{') - text.count('}'))
       text += ']' * (text.count('[') - text.count(']'))
       return text.strip()
   
   # ❌ 禁止：直接 json.loads(response_text)（會在 LLM 截斷時拋 JSONDecodeError）
   ```

7. **track_count 上限（v15.7，`music_metadata_engine.py`）:**
   ```python
   # ✅ 正確：限制傳入 LLM 的曲數
   track_count = len(list(vault_dir.glob("*.wav"))) if vault_dir.exists() else 15
   track_count = max(5, min(track_count, 20))   # 至少 5 首，最多 20 首
   
   # ❌ 禁止：直接傳入實際曲數（190 首 → token 溢位 → JSON 截斷）
   track_count = len(list(vault_dir.glob("*.wav")))
   ```

---

## 4. SQLITE THREAD SAFETY（資料庫執行緒安全規範）

> v15.4 廢除 `_get_connection()`，統一改用 `.conn` property（threading.local）。

1. **唯一合法入口:** 所有 `VaultDatabase` / `VisualVaultDB` 存取只能使用 `vault.conn`（`@property`，`threading.local()` 保護）。
   ```python
   # ✅ 正確
   cursor = vault.conn.cursor()
   
   # ❌ 禁止 — _get_connection() 已廢除
   conn = vault._get_connection()
   ```

2. **禁止手動 close:** 不得呼叫 `conn.close()`，由 `threading.local` 生命週期管理。

3. **跨執行緒警告:** 若看到 `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`，原因是共享連線物件。修正方式：改用 `vault.conn`。

4. **影片改名後必須同步 DB（v15.7）:**
   ```python
   # ✅ 正確：改名後立即更新 veo_visual_vault.db
   cursor = vault.conn.cursor()
   cursor.execute(
       "UPDATE video_assets SET video_id = ?, file_path = ? WHERE video_id = ?",
       (new_video_id, new_file_path, old_video_id)
   )
   vault.conn.commit()
   
   # ❌ 禁止：只改磁碟檔名不更新 DB（multi_scene_processor.py 會 FileNotFoundError）
   os.rename(old_path, new_path)  # 不配對 DB UPDATE → Critical Bug
   ```

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

## 6. PING-PONG LOOP STRATEGY（v15.7 智能迴圈策略）

> **核心新功能。`video_loop_classifier.py` + `multi_scene_processor.py` 協同實現。**

### 前綴命名規則

| 前綴 | 策略 | 適用場景 | loop_list 結構 |
|------|------|---------|--------------|
| `ping_` | Ping-Pong（正反交替）| 海浪、雲朵、煙霧等振盪型 | `in → mid → rev → mid → rev → ... → out` |
| `ford_` | Forward（正向重複）| 瀑布、城市、靜態場景 | `in → mid → mid → mid → ... → out` |

### `get_loop_strategy()` 實作規範

```python
# ✅ 正確：video_loop_classifier.py
def get_loop_strategy(vid_path: Path) -> str:
    name = vid_path.name.lower()
    if name.startswith("ping_"):
        return "pingpong"
    elif name.startswith("ford_"):
        return "forward"
    else:
        log.warning(f"⚠️ 影片無前綴，預設 forward 策略: {vid_path.name}")
        return "forward"

# ❌ 禁止：以 CV 分析或硬編碼清單決定策略（已廢除，改由 CEO 命名決定）
```

### Ping-Pong Stage 1 反向編碼

```python
# ✅ 正確：v15.7 反向片段鑄造
if loop_strategy == "pingpong":
    base_mid_rev = temp_dir / f"base_{idx}_mid_rev.ts"
    vf_rev = f"reverse,{common_vf_base}"   # reverse 必須在 setpts 之前！
    cmd_rev = ["ffmpeg", ..., "-vf", vf_rev, *common_enc, str(base_mid_rev)]
    ok_rev = self._run_ffmpeg_with_progress(cmd_rev, ...)
    if not ok_rev:
        log.warning("⚠️ [v15.7] 反向片段編碼失敗，降級為 Forward 策略")
        loop_strategy = "forward"   # 自動降級，產線不中斷

# ❌ 禁止：vf_rev = f"{common_vf_base},reverse"（setpts 在 reverse 之前 → 時間軸錯亂）
```

### Ping-Pong loop_list.txt 生成

```python
# ✅ 正確：Ping-Pong 正反交替
with open(loop_list, "w") as f:
    f.write(f"file '{base_in.resolve().as_posix()}'\nduration {real_ts_dur}\n")
    if loop_strategy == "pingpong" and base_mid_rev is not None:
        for i in range(mid_count):
            seg = base_mid if i % 2 == 0 else base_mid_rev
            f.write(f"file '{seg.resolve().as_posix()}'\nduration {real_ts_dur}\n")
    else:
        for _ in range(mid_count):
            f.write(f"file '{base_mid.resolve().as_posix()}'\nduration {real_ts_dur}\n")
    f.write(f"file '{base_out.resolve().as_posix()}'\nduration {real_ts_dur}\n")

# ❌ 禁止：對 pingpong 策略也只寫 base_mid（未利用 base_mid_rev → 無 Ping-Pong 效果）
```

---

## 7. BROADCAST-GRADE FFMPEG DISCIPLINE v15.7（廣播級 FFmpeg 鐵律）

> ⚠️ 以下所有參數由 CEO 鎖定於 `multi_scene_processor.py`。Copilot 不得建議移除或變更任何一項。

### Stage 1 編碼防禦陣列（完整，不可拆分）

```python
# ✅ v15.7 鎖定版 — 完整防禦陣列（同 v15.6，v15.7 新增 Ping-Pong 分支但不改此陣列）
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

### 正向濾鏡鏈順序（鐵律，絕對不可逆轉）

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

### 反向濾鏡鏈順序（v15.7 鎖定，Ping-Pong 專用，絕對不可逆轉）

```python
# ✅ 正確：reverse 必須最先 → 再 setpts 歸零 → 再 fps=24 標準化
vf_rev = f"reverse,setpts=PTS-STARTPTS,fps=24,{norm}"
# 邏輯：先物理倒轉幀序列，再重置 PTS 為 0-based，確保倒轉後時間軸乾淨

# ❌ 禁止：setpts 在 reverse 之前 → reverse 後 PTS 仍為雜亂值 → 時間軸錯亂
vf_wrong_rev = f"setpts=PTS-STARTPTS,fps=24,reverse,{norm}"
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

> **`scripts/gear1_prod/multi_scene_processor.py` 為 CEO 鎖定檔案（v15.6 起生效，v15.7 持續）。**

**Copilot 規則：**
- 當用戶要求修改 `multi_scene_processor.py` 時，**必須先提示需要 CEO 授權**
- 不得主動建議刪除或修改 Section 7 中任何鎖定參數
- 不得建議將 `-tune film` 改回 `-tune stillimage`
- 不得建議移除 `-flags +cgop`、`-sc_threshold 0`、`-keyint_min 48` 中的任何一項
- 不得建議將 `get_video_duration()` 改回硬除 `24.0` 的舊版邏輯
- 不得建議省略雙重保險的 re-probe 步驟
- 不得建議省略 `_verify_gop_closure()` 的呼叫
- **v15.7 新增：** 不得建議將 `reverse` 濾鏡移到 `setpts` 之後
- **v15.7 新增：** 不得建議移除 `get_loop_strategy()` 前綴分支邏輯
- **v15.7 新增：** 不得建議對 `pingpong` 策略省略 `base_mid_rev.ts` 的鑄造

**若用戶確認已獲 CEO 授權，修改後必須提醒：**
1. 先備份至 `spec/backups/v15.7_pre_[YYYYMMDD]/`
2. 執行 GOP-QA 沙盒驗證：
```powershell
python scripts/gear1_prod/multi_scene_processor.py --sandbox --channel lofi --target-duration 120 --scene-dwell-time 60
# 日誌必須出現：✅ [GOP-QA] ... GOP 牢籠完好
```

---

## 9. VIDEO NAMING & DB SYNC（影片前綴命名與 DB 同步 v15.7）

> **所有 vault 影片命名規範。Copilot 在建議任何影片入庫或改名操作時必須遵守。**

### 命名規則

```
ping_[原始名稱].mp4  →  Ping-Pong 策略（振盪場景：海浪、雲朵、煙霧）
ford_[原始名稱].mp4  →  Forward 策略（單向場景：瀑布、城市、靜態）
```

### 建議的改名 + DB 同步模板

```python
# ✅ 正確：改名與 DB 更新必須配對執行
import os
from pathlib import Path

old_path = Path("assets/video_clips/vault/lofi/ping_caffee01.mp4")
new_path = old_path.parent / "ford_coffee01.mp4"

# Step 1: 磁碟改名
old_path.rename(new_path)

# Step 2: 立即更新 DB
new_video_id = new_path.stem                          # "ford_coffee01"
new_file_path = str(new_path.relative_to(workspace)) # "assets/video_clips/vault/lofi/ford_coffee01.mp4"
old_video_id  = old_path.stem                         # "ping_caffee01"

cursor = vault.conn.cursor()
cursor.execute(
    "UPDATE video_assets SET video_id = ?, file_path = ? WHERE video_id = ?",
    (new_video_id, new_file_path, old_video_id)
)
vault.conn.commit()

# ❌ 禁止：只做其中一步
os.rename(old_path, new_path)  # 沒有 DB UPDATE → FileNotFoundError
```

### 禁止事項

- **嚴禁** 建議無前綴的 vault 影片（`get_loop_strategy()` 無法正確分類）
- **嚴禁** 建議只改磁碟不更新 `veo_visual_vault.db`
- **嚴禁** 建議用 CV/ML 分析取代前綴命名（已廢棄，CEO 人工審閱命名為最終標準）

---

## 10. AUDIO VAULT SELECTION（lofi_assembler 選曲遞補規範 v15.7）

> `lofi_assembler.py` `VaultSelection.select()` v15.7 修復邏輯。

```python
# ✅ 正確：v15.7 遞補邏輯（Step 4a / 4b）
# Step 4a：New(dc=0) 不足 → 從 Gen1 補足
new_deficit = quota_new - len(selected_new)
if new_deficit > 0:
    additional_from_gen1 = self._select_from_pool(pool_gen1, new_deficit)
    selected_gen1.extend(additional_from_gen1)

# Step 4b：Gen2 不足 → 先從 New 補，再從 Gen1 補
gen2_deficit = quota_gen2 - len(selected_gen2)
if gen2_deficit > 0:
    additional_from_new = self._select_from_pool(pool_new, gen2_deficit)
    selected_new.extend(additional_from_new)
    gen2_deficit -= len(additional_from_new)
    if gen2_deficit > 0:
        additional_from_gen1 = self._select_from_pool(pool_gen1, gen2_deficit)
        selected_gen1.extend(additional_from_gen1)

# Step 5：total >= 1 繼續，_build_playlist 重複播放填滿目標時長
total_selected = len(selected_new) + len(selected_gen1) + len(selected_gen2)
if total_selected < 1:
    raise VaultShortageException("庫存完全為空")  # 只有真的空庫才拋出

# ❌ 禁止（v15.6 Bug）：因配額未達到就拋出異常（190 首可用卻報庫存為 0）
if total_selected < self.target_tracks:
    raise VaultShortageException(...)  # 錯誤！應繼續而非拋出
```

---

## 11. UI SINGULARITY & THREAD SAFETY（Streamlit 樞紐與非阻塞規範）

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

## 12. VAULT DERIVATION DEFAULTS（金庫衍生次數規範）

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

## 13. TELEGRAM BOT RULES（Webhook Bot 規範）

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

## 14. NO RPA POLICY（廢除幽靈上傳）

You are FORBIDDEN from writing Playwright, Selenium, or `requests` scripts to automate uploads to DistroKid or YouTube. All publishing is 100% manual via CheatSheet copy-paste by the CEO. Do not suggest automation for these platforms.

---

## 15. DYNAMIC SUB-AGENT HANDOFF（子代理交接規範）

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

## 16. LANGUAGE & COMMUNICATION DIRECTIVE

1. **Internal Reasoning & Execution:** Use English for thinking, tool calls, code generation, and terminal commands.
2. **User Communication:** Use Traditional Chinese（繁體中文）for ALL chat responses, explanations, and progress reports to the CEO.

---

## 17. CONSTITUTION IMMUTABILITY（最高修憲權鎖定）

You MUST NEVER generate code or commands that attempt to automatically modify:
`.github/copilot-instructions.md`, `.clinerules`, `project.yml`, `架構說明書_*.md`, or any workflow `.md` files.  
These are strictly human-managed core configuration files. Updates require explicit CEO/CTO instruction.

---

## 18. ZERO-WASTE WORKSPACE DISCIPLINE（零廢棄紀律）

- **NO Micro-Reports:** FORBIDDEN from generating `.md` reports to document execution steps (e.g., do NOT create `CTO_Patch_Report.md`). Results → terminal/chat only.
- **No Test File Residue:** Temporary scripts (`_test_*.py`, `_audit_*.py`) MUST be deleted immediately after use.
- **No Debugging Artifacts:** Goal: pristine workspace. Violations trigger `workspace_sweeper.py`.

---

## QUICK REFERENCE CARD v15.7（違禁對照速查）

```
❌ 舊版寫法 / 禁止                              ✅ v15.7 正確寫法
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
正向 fade 濾鏡放在 setpts 之前                  setpts=PTS-STARTPTS,fps=24 → fade → norm
反向 setpts 放在 reverse 之前（v15.7）          reverse → setpts=PTS-STARTPTS,fps=24 → norm
loop_list duration 用上游估算值                  re-probe base_mid.ts 實際幀數÷24（雙重保險）
省略 _verify_gop_closure() 呼叫                每次 base_mid.ts 後必須呼叫 GOP-QA
Stage 2 AAC 不設 -ar                           強制 -ar 48000（防長片音畫漂移）
未授權修改 multi_scene_processor.py            先取得 CEO 書面授權 + 備份 + GOP-QA 沙盒驗證
MiniMax max_tokens=2048（v15.7）              max_tokens=4096
傳超過 20 首 track_count 給 LLM（v15.7）      max(5, min(vault_count, 20))
LLM 回傳 JSON 直接 json.loads()（v15.7）      先執行 _clean_json_response() 三重清洗
vault 影片無 ping_/ford_ 前綴（v15.7）         CEO 審閱後命名前綴，再入庫
影片改名後不更新 veo_visual_vault.db（v15.7）  UPDATE video_assets SET video_id=?, file_path=?
lofi 配額未達 50/25/25 就拋出異常（v15.7）     total>=1 繼續；僅 total==0 才拋出 VaultShortageException
Ping-Pong vf_rev 中 setpts 在 reverse 之前    reverse 必須最先：reverse,setpts,fps=24,{norm}
pingpong 策略省略 base_mid_rev.ts（v15.7）     base_mid_rev.ts 必須鑄造；loop_list 正反交替
```
