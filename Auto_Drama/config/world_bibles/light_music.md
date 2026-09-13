# Story Bible — R&S Echoes Light Music · World: **Nature & Healing（自然療癒）**

> Status: CEO-approved draft (2026-09-09). Runtime config: `config/worlds.yaml` → `worlds.light_music`.
> Format: vertical 9:16, 175s/episode YouTube Shorts. Publish Wed+Sat 14:00. LUFS -14. Default speech zh + zh/en subs.

## 1. 世界立場（Core Stance）
每一話的任務是讓觀眾「被自然與善意接住，重獲平靜」。衝突永遠小、可被理解、以溫柔化解。
可涵蓋自然／田園／山海／家庭／溫馨／療癒系誌怪／人間煙火。

## 2. 最小敘事結構（單話閉合）
`相遇 → 誤解或小困境 → 自然/善意解開 → 餘韻`
範例（東方）：狐仙其實是來幫老農看診；寺裡老鐘自己響是提醒旅人避雨。
範例（西方）：森林守護者每晚替迷路孩子點燈（北歐民間母題改編）。

## 3. 節奏與台詞
- 慢節奏；台詞少而清（每話對白量低，Seedance 對嘴更穩）。
- 語音：預設中文；經 `language=en` 標記之西方童話話數可英文語音。
- 雙字幕：繁中＋英文（直式安全區內）。

## 4. 角色原型（Regional Visual Packs → 3–4 套直式 Seedance 參考圖）
東方池（archetype_keys: mountain_guide_monk, herb_sprite_maiden, shepherd_child, nature_young_girl）：
1. 山寺引路僧：灰白僧袍、溫和眉目、提昏黃燈籠。
2. 草木精靈少女：素衣、髮間有綠芽/花、光點隨行。
3. 可愛牧童（小孩）：短褐、竹笠、腰間掛葉笛，牽著小牛或坐在溪石上吹笛，圓潤天真。
4. 自然系年輕女孩：棉麻衣裙、赤足提花籃（採花/採茶/抱小動物），明亮溫暖。

西方池（archetype_keys: village_child_friend, flower_fairy, lake_spirit, gentle_goddess）：
1. 鄉村小孩與動物：圍裙裙裝、雀斑、常伴小鹿/羊。
2. 花仙子/小精靈：通透花瓣翅、花冠、螢光花粉光點、小巧玲瓏（可男孩/女孩/中性）。
3. 湖畔精靈：薄紗水色長裙、湖畔霧光。
4. 溫柔女神（美麗女神形象）：月桂/花環長髮、垂落絲綢裙、聖潔柔光、自然神性。
> 同世界內東西方故事各用對應子包，視覺一致但不互穿幫。

## 5. 美術 DNA（由既有視覺資產庫實地分析重構 2026-09-09）
分析來源：F `assets/video_clips/vault/light_music/`（橫式 1920×1080 loop，舊）＋X `video_clips/light_music/`（直式 1080×1920 / 720×1280 loop）＋`AI_characters/image/` 氛圍圖庫。實測視覺母題：

**招牌核心場景（反覆出現＝頻道記憶點）**
- **海岸暮光 × 木造度假別墅/懸崖小屋**：層層木平台、陽台欄杆、暖燈串/燈籠、無邊際泳池、棕櫚、岩石海灣、躺在躺椅上放鬆的人（X `Twilight_coastal_1520`、F `ping_twilight_coastal_smooth`、`AI_characters` cliff-villa 系列）。
- **暮色或晨曦的自然光譜**：天空由藍→橙/蜜桃的暮光（twilight）與晨光（morning）；或月夜金雲滿月（`Nature03` 金色月夜海）。
- **水的一切**：海洋波浪、湖面漣漪、落葉飄浮、溪流/瀑布、燭光/風鈴映水（`lake_ripples`、`ocean*`、`waterflow*`、`Zen_atmosphere`）。
- **內在溫暖空間**：茶室、書房、小木屋、玻璃花房、火爐/壁火、燭光晚餐（`tearoom`、`Studyroom`、`Seamless_fire`、`Garden010` 湖畔燭光晚餐）。
- **物件靜物**：咖啡蒸氣（`water_coffee` 霧谷陽台咖啡杯）、杯盤、花園花卉、葡萄/樹葉搖曳。
- **東方山林寂靜**：石徑涼亭＋霧嵐秋山＋流水（`fwd_Seasons_transforming`）——東方子設定專屬。

**光影/色調語彙（送 Seedance 直式 prompt 用）**
- 暖橙/蜜桃/蜜糖的暮色或柔和晨藍；燭火與暖燈串＝局部暖光點；水面反射/光斑；低飽和、低對比、霧感柔和（East：水墨暈染、寺院屋簷、山嵐；West：鄉間小鎮、森林、湖畔石屋、北歐霧林）。
- 運鏡＝緩慢無縫 loop 或極緩前推/平移（fwd 向），少手持晃動；30fps 或 24fps 皆宜，保持「靜止中只有微動」的呼吸感。
- **直式 9:16 構圖**：主體/水平線置中偏上；上方留字幕安全區；下方可保留水面/桌面細節。

**對新系統的用法**：既有 loop 庫＝本世界的「環境 mood 板＋環境背景素材池」（純音樂 loop Shorts 可直用）；新劇集的 Seedance 場景構圖應重現上述光影語彙，讓「頻道宇宙」跨劇集/跨短影一致。

## 6. 配樂 DNA
沿用 `.openclaw/music_genes_light_music.md`（New Age/Celtic/piano/zen）；可加溫馨弦樂與家庭向主題；器樂無詞（禁人聲）。
CEO 手動 SUNO 主路徑：每話依 emotion_arc 產 music_plan + SUNO 提示稿 → inbox `epXX_segNN.mp3` → amix。

## 7. 紅線表（寫入 Stage1 限制）
血腥恐怖結局／時事政治／宗教儀式寫實細節／受版權保護之現代 IP 角色／說教。西方僅公有領域或自創改編（避版權風控）。

## 8. Metadata 風格
標題＝一句意象（《山寺鐘聲》《湖心燈火》）；描述＝EN 主＋中文＋頻道品牌與播放節奏 CTA；tags 含 R&S Echoes / nature / relax 系。
