**[CTO 架構修正與衝刺計畫重構報告]**

### 🎟️ Ticket 1: 「故事脊椎 (Story Backbone)」的逆向提煉
**目標**：在挖礦階段就將影片的情緒起伏提煉出來，存入基因庫，作為未來引導音樂生成的骨幹。
* **歸屬部門**：⚙️ 齒輪二 (研發部)
* **修改檔案**：`batch_style_analyzer_sqlite.py` (核心挖礦引擎)
* **工程實作細項**：
  * 在 `analyze_with_glm4v_multimodal` 函數的 Prompt 中，強制 `GLM-4V-Plus` 在看那張「十二宮格縮圖大圖」時，多解析出一個欄位：`"story_backbone"`。
  * 要求模型輸出一段 50 字的情緒起伏圖（例如：`"前段壓抑沉悶 -> 中段機械式重複 -> 結尾詭異釋懷"`）。
  * 將這個 `"story_backbone"` 寫入資料庫 `audio_genes` 的 JSON 結構中。未來齒輪一的 `chinese_api_audio_engine.py` 只要無腦讀取這個欄位去生成音樂即可。

### 🎟️ Ticket 2: 角色一致性的「圖生片 (Image-to-Video)」錨點機制
**目標**：解決影片主角長相變來變去的問題，用極低成本鎖定角色特徵。
* **歸屬部門**：🏭 齒輪一 (生產部)
* **修改檔案 A**：新增 `image_anchor_generator.py` (Local Skill)
  * **工程實作細項**：在產線進入 `Protocol V` 之前，撰寫一支極輕量的腳本。呼叫通義萬相或 GLM-4V 生圖 API，傳入藍圖中的視覺基因，生成 1 張主角的「基準設計圖 (Anchor Image)」，存入 `/Volumes/AI_Workspace/AI_DRAMA_FACTORY/assets/image_anchors/`。
* **修改檔案 B**：`project.yml`
  * **工程實作細項**：在 `VD` (視覺導演) 的 `AGENT_CORE_RESPONSIBILITIES` 中強制規定：呼叫即夢 API 時，**必須讀取 `image_anchors` 裡的基準圖，並強制使用即夢的「圖生片 (Image-to-Video)」端點**，確保 6 個分鏡的主角長相完全鎖死。

### 🎟️ Ticket 3: Python `librosa` 音樂踩點動態剪輯 (Beat-Sync)
**目標**：打破目前死板的平鋪直敘，讓影片的「切換點」完美砸在音樂的「重拍」上，創造大師級的蒙太奇呼吸感。
* **歸屬部門**：🏭 齒輪一 (生產部)
* **修改檔案**：`auto_editor.py` (M4 硬體加速剪輯台)
* **工程實作細項**：
  * 引入 `import librosa`。
  * 新增函數 `detect_beat_timestamps(audio_file)`，利用 `librosa.onset.onset_detect` 抓出整首音樂的高能量重拍時間點陣列。
  * 改寫 FFmpeg `concat` 的邏輯。不要只是無腦把短片接起來，而是利用 Python 計算，讓每一段 `.mp4` 的 `inpoint` 和 `outpoint` 精準對齊 librosa 算出來的重拍秒數。

### 🎟️ Ticket 4: 環境音 (Foley) 陣列的逆向拆解
**目標**：在研發階段就建檔「這套美學該配什麼環境音」，讓純音樂影片充滿電影級沉浸感。
* **歸屬部門**：⚙️ 齒輪二 (研發部)
* **修改檔案**：`batch_style_analyzer_sqlite.py` (核心挖礦引擎)
* **工程實作細項**：
  * 修改 `GLM-4V-Plus` 的 Prompt。要求模型在分析影片與音樂時，從我們預設的實體白噪音庫（如：`keyboard.wav`, `clock_tick.wav`, `rain.wav`, `paper_flip.wav`）中，挑選出最符合該影片氛圍的 2~3 個音效。
  * 將這些音效名稱存入資料庫 `audio_genes` 的 `"foley_array"` 欄位中。
  * （*備註：未來齒輪一的 `auto_editor.py` 只要讀取這個陣列，用 FFmpeg `amix` 濾鏡無腦疊加上去，就能不花任何 API Token 創造出極致的立體空間感。*）

---
