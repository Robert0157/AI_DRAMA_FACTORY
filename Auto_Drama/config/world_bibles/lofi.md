# Story Bible — R&S Echoes Lo-Fi · World: **Surreal & Modern（超現實現代）**

> Status: CEO-approved draft (2026-09-09). Runtime config: `config/worlds.yaml` → `worlds.lofi`.
> Format: vertical 9:16, 175s/episode YouTube Shorts. Publish Wed+Sat 19:30. LUFS -14. Default speech zh + zh/en subs; scifi/space west episodes may be `language=en`.

## 1. 世界立場（Core Stance）
讓觀眾在深夜走進「比表面更不真實的城市」：超現實、夜間氛圍、時尚現代、科幻、太空星際皆可；求真與真假翻轉是核心樂趣。可留 30% 開放/帶刺結局。

## 2. 最小敘事結構（單話閉合）
`日常異象 → 追查 → 反轉（真假顛倒） → 回味`
範例（東方）：整條街的人其實是同一人的夢；末班地鐵只有主角能看見終點站。
範例（西方）：太空站維修員發現自己維修的是自己的記憶。

## 3. 節奏與台詞
- 快轉折、利落台詞；允許科幻/網路語彙但核心仍是「人的故事」。
- 語音：預設中文；`language=en`＋west/scifi/space 話數用英文語音。
- 雙字幕：繁中＋英文（直式安全區）。

## 4. 角色原型（Regional Visual Packs → 3–4 套直式 Seedance 參考圖）
東方池（archetype_keys: night_cab_driver, oracle_of_neon_city, memory_repairer, midnight_messenger）：
1. 夜班計程車司機：舊夾克、城市青年、車內霓虹反光。
2. 霓虹城占卜師：未來東方服飾、全息羅盤、冷光。
3. 記憶修復師：實驗室白袍＋東方刺繡混搭、資料流眼鏡。
4. 午夜使者：黑傘、夜雨、面具半掩。

西方池（archetype_keys: space_station_tech, android_night_clerk, fashion_visionary, stellar_wanderer）：
1. 太空站技師：太空服內搭、失重工具帶、地球窗外。
2. 仿生人夜班店員：24h 便利／唱片行、發光關節接縫。
3. 時尚設計師：都會工作室、布料投影、前衛剪裁。
4. 星際流浪者：舊化斗篷＋星圖、銀河背景。
> 同世界東西方各用對應子包；東方＝未來東方雨夜城，西方＝太空/都會，視覺不互穿幫。

## 5. 美術 DNA（由既有視覺資產庫實地分析重構 2026-09-09）
分析來源：X `video_clips/lofi/`（直式 1080×1920，23–48s fwd 動態）。實測視覺母題＝**時尚編輯 × 超現實象徵 × 冷調高對比**：

**核心場景母題**
- **時尚 runway / model 編輯照**：極簡灰 studio runway、全幅單人女模走秀（中性神情、oversize/雕塑感服裝、`fwd_fashion_runway_shot`、`fwd_model_*` 系列）——本世界最強記憶點。
- **重複品牌人物**：Sophia／Emily／Emma／Amy／Mia 等固定化名女模（`fwd_Sophia_*` 敞篷車/白梯/大衣、`fwd_Emily_walking_on_gallery`…）＝可發展為「世界主角原型」真人基模。
- **超現實象徵物**：煙霧/撕裂質感服裝＋金屬圓環（`Woman_with_smoky_dress`）、金面具三面/手持金眼面具（`Three_faces_with_golden_masks`、`Woman_holding_golden_eye_mask`）、發光球體神器、浮空船（`Mystical_oracle`、`Steampunk_airship`）、斷裂地球儀/馬群凍結/人形消散荒野。
- **科技×日常**：星雲窗外銀河列車＋霓虹青描邊咖啡杯（`fwd_cosmos_train` 的日常×宇宙反差）、蒸氣龐克咖啡機、冰雪暴走女子、深夜長廊。
- **移動美學**：全部 fwd（前進/走入畫面）動態；train/車/飛行/雪暴等強方向性運動。

**光影/色調語彙（送 Seedance 直式 prompt 用）**
- 深藍灰/板岩/黑為主底＋局部霓虹青、金屬銀、金面具色、煙霧質感；高對比、輪廓光、editorial 打光（非自然光）。
- 東方子設定＝未來東方雨夜城霓虹／玻璃倒影；西方子設定＝太空站銀河／都會玻璃帷幕／蒸汽龐克機械。人物＝時裝輪廓單一主體置中。
- **直式 9:16**：主體全幅置中，鏡頭採「向前推進(fwd)」語法；上方留字幕安全區。

**對新系統的用法**：既有 loop 庫＝本世界「mood 板＋環境背景素材池＋fwd 運鏡範本」；新劇集 Seedance 場景與角色造型應重現上述冷調時尚×超現實語彙，保持頻道宇宙跨集一致。

## 6. 配樂 DNA
沿用 lofi/urban 基因（chill beats 基底），可加 synthwave／太空氛圍／時尚電音；器樂無詞（禁人聲）。
CEO 手動 SUNO 主路徑：每話依 emotion_arc 產 music_plan + SUNO 提示稿 → inbox `epXX_segNN.mp3` → amix。

## 7. 紅線表
純無厘頭／說教／受版權保護之現代 IP 角色（影視、動畫、明星形象一律禁）／時事政治／宗教儀式寫實細節。西方僅公有領域或自創改編。

## 8. Metadata 風格
標題＝帶鉤子（《雨夜的記憶店》《他載到一位不該存在的乘客》）；描述＝EN 主＋中文＋夜聽/科幻 CTA；tags 含 R&S Echoes / cyberpunk / scifi / night 系。
