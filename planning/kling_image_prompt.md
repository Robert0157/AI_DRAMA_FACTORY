這是一套為 AI 影音自動化生成工作流量身打造的 Prompt 拆解方案。將這支結合傳統非洲節奏與現代電子元素的影片，逆向工程還原為 Suno (音樂生成) 與 Kling (影像生成) 能直接消化的指令。

### 1. Suno 音樂生成 Prompt 分析與設定

影片的音樂核心在於「傳統非洲打擊樂」與「現代 Cinematic Afro-house」的融合。節奏極具爆發力與催眠感，為舞者的極速腳步提供了完美的驅動引擎。

* **音樂風格 (Genre/Style)：** Cinematic Afro-house, Tribal Electronic, Zaouli dance rhythm.
* **音樂基因 (Vibe/Mood)：** Hypnotic, energetic, ancient meets modern, spiritual, driving, pulsating.
* **核心樂器 (Instruments)：** Djembe (金貝鼓), Talking drum (說話鼓), Ankle bells (腳踝鈴鐺), Deep synth bass (深沉電子貝斯), Rhythmic handclaps (節奏拍手).
* **節奏 (Rhythm)：** Fast-paced polyrhythm (快速複合節奏), heavy downbeat (重拍), 120-130 BPM 但帶有極密集的 16/32 分音符打擊樂點綴。

**👉 Suno Style Prompt (音樂風格標籤)：**
請將以下標籤貼入 Suno 的 `Style of Music` 欄位（Suno 對英文標籤辨識度最佳）：
> Cinematic Afro-house, high-energy tribal percussion, fast djembe, talking drum, silver ankle bells, deep pulsating electronic bass, rhythmic clapping, hypnotic polyrhythm, epic build-up, 125 BPM

**👉 Suno Lyrics Structure (歌詞結構建議)：**
若要重現影片中那種低沉、如咒語般的 spoken word (唸唱)，可以在 Suno 的歌詞欄位加入類似以下的結構（利用中括號 `[]` 來引導 AI 結構）：
```text
[Spoken Word Intro]
This is not just music.
This is memory in motion.
When the dune rolls beneath the floor,
My feet remember what they knew before.

[Intense Tribal Beat Build-up]
Heel to toe, toe to heel.
The rhythm is real.
Talking drum, don't whisper small.

[Heavy Bass Drop / Chorus]
Ta doom! Ta doom!
Feel that pulse in the room!
The drum moves my feet! (x3)
Still strong, still sweet!

[Percussion Solo - Djembe & Ankle Bells]
(Instrumental fast footwork rhythm)
```

---

### 2. 可靈 (Kling) 影片生成 Prompt 拆解 (按鏡頭邏輯)

為了在 Kling 中重現這種「超現實非洲舞蹈」的視覺張力，Prompt 必須極度強調**服裝細節、物理動態（尤其是腳部與沙塵的互動）以及攝影機運動**。Kling 對於英文的空間與動態描述理解較為精準。

以下模擬影片中幾個關鍵的視覺節奏點，轉換為 Kling 適用的 Prompt：

**鏡頭 A：開場建立鏡頭 (Setting the Scene - 對應音樂前奏)**
* **影片風格/內容：** 超現實非洲沙漠，黃金時刻的光線。舞者穿著華麗複雜的幾何圖騰服飾與 Zaouli 面具，靜止站立，營造神秘感。
* **運鏡/音樂結合：** 緩慢推軌 (Dolly in)，配合音樂的低頻鋪陳。
* **Kling Prompt：**
> A cinematic wide shot of a vast surreal African desert dune at golden hour. A single majestic Zaouli dancer stands completely still, wearing a vibrant, intricately patterned traditional mask and colorful fringe garments. Dramatic volumetric lighting, photorealistic, 8k resolution, hyper-detailed. Slow dolly in camera movement.

**鏡頭 B：細節特寫與節奏啟動 (The Beat Kicks In - 對應密集鼓點)**
* **影片風格/內容：** 極高頻率的腳步特寫。腳踝上的銀鈴鐺閃爍，快速踩踏揚起地面的沙塵。
* **運鏡/音樂結合：** 極端特寫 (Extreme Close-up)，高速快門凝結沙塵，鏡頭微震動以匹配 "Ta doom" 的重拍。
* **Kling Prompt：**
> Extreme close-up shot on a dancer's feet adorned with intricate silver ankle bells. The feet are rapidly and fiercely stomping on fine desert sand, kicking up dynamic clouds of dust. High shutter speed, hyper-detailed textures, cinematic lighting. Slight camera shake, fast and energetic dynamic motion.

**鏡頭 C：超現實物理動態 (The Core Dance - 對應副歌高潮)**
* **影片風格/內容：** 展示 Zaouli 舞的核心特徵——上半身如雕像般靜止，下半身的流蘇與雙腿以不可思議的速度瘋狂舞動。
* **運鏡/音樂結合：** 低角度仰角 (Low angle)，環繞跟拍，展現舞者的氣勢與服裝動態。
* **Kling Prompt：**
> A low angle medium shot tracking a surreal African dancer. The dancer's upper body and mask are completely stoic and motionless, while their lower body and legs move at an incredibly fast, blurring speed in a traditional Zaouli dance. Vividly colored costume fringes sway rapidly. Realistic physics, high contrast, surrealistic mood, 4K, dynamic sweeping camera.

**鏡頭 D：重拍定格與魔法元素 (The Climax / Visual Accent - 對應音樂停頓或重擊)**
* **影片風格/內容：** 每次腳跟重落地時，地面產生微光的魔法波紋，增強超現實感。
* **運鏡/音樂結合：** 快速 Zoom-in，適合後期搭配音樂波形做 Speed Ramping (變速剪輯)。
* **Kling Prompt：**
> Dynamic fast zoom-in shot of a tribal dancer stomping hard on the ground. Glowing magical dust and subtle light ripples emit from the ground where the foot impacts. Hyper-realistic, dramatic shadows, neon accents on traditional tribal patterns, cinematic action composition.

**💡 實戰小建議：**
在 AI 影音工作流中，Kling 生成的素材通常是恆定速率的。要達到您原影片中那種「動作和音樂節拍吻合一致」的境界，**最關鍵的最後一步**是將 Kling 生成的這些鏡頭 (特別是鏡頭 B 與 D)，放入剪輯軟體中，對準 Suno 生成的音軌波形圖的波峰（重拍），進行**時間重映射 (Speed Ramping)**——在鼓點打下前一幀加速畫面，打下瞬間放慢或定格畫面。順帶一提，如果要取得所有應用程式的完整功能，請開啟 Gemini 系列應用程式活動記錄。

中文提示 (英文提示在下方)：

圖像 A (有電腦的書房與男人)：
一幅美麗的豪華現代山景書房照片。整個場景由巨大的全景落地窗佔導，窗外是雲霧繚繞、森林茂密的深峽谷和遠方的高山。一個簡約木製控制台辦公桌從牆壁延伸出來。桌子上放著一台現代一體機電腦（例如 iMac）和幾本書。一個金屬框辦公椅放在桌子旁。一位大約 38 歲的男人，身穿商務休閒服（例如西裝外套和襯衫），坐在辦公椅上。他的身體和椅子輕微轉向，現在面向窗戶和遠方的景觀，背對或側對電腦。他的右手輕放在大腿上。他的頭抬起，目光看向遠方的山峰，表現出深思。窗戶射入的自然光是柔和的日光，形成柔和的陰影。室內有柔和的環境燈光。高度細節，構圖完美，超高清，4k。

圖像 B (無電腦的書房與女學生)：
一幅寬敞、華麗的實木地板豪華書房照片。全景落地窗佔導了整個場景，窗外是壮麗的、森林茂密的峽谷和雲霧繚繞的高山。一個華麗的實木辦公桌放在地板上。桌上沒有電腦，但有書籍、樂譜和卡帶。一個皮革辦公椅（或調整為更適合女生的椅子）放在桌子旁。一個長髮女學生，身穿寬鬆的 Lofi 街頭服飾（例如超大連帽衫），戴著耳機（例如 vintage 風格）。她靠在辦公桌上。她的右手托著頭，頭靠在手上，身體靠在桌子上。她面向窗戶，看向遠方，表現出發呆、迷失在思考中。溫暖柔軟的日光從窗戶射入，懷舊和治愈的氛圍。極致細節，超級採樣放大，超高清，4k。

English Prompts:

Image A (Study with Computer and Man):
A beautiful photograph of a luxurious, modern mountain-view study. The entire scene is dominated by massive floor-to-ceiling windows, looking out over a spectacular, forest-covered deep canyon and distant high mountains shrouded in cloud and mist. A minimalist wooden console desk is built into the wall. On the desk sits a modern all-in-one computer (like an iMac) and a few books. A metal-framed office chair is positioned by the desk. A man, approximately 38 years old, dressed in a business-casual outfit (like a blazer and collared shirt), is seated in the chair. His body and the chair are slightly turned, now facing the window and the distant landscape, with his back or side to the computer. His right hand rests lightly on his lap. His head is up, and his eyes are looking far into the distance over the mountain peaks, expressing deep contemplation. The natural light from the window is soft and diffuse, casting gentle shadows. The room has soft ambient lighting. Highly detailed, perfect composition, 4k.

Image B (Study without Computer and Female Student):
A beautiful photograph of a spacious, ornate wooden floor luxurious study. Massive floor-to-ceiling windows dominate the scene, looking out over a spectacular, forest-covered canyon and distant high mountains shrouded in cloud and mist. A rich solid wood desk sits on the floor. On the desk, there is no computer, but instead books, musical scores, and cassettes. A leather office chair is positioned by the desk. A long-haired female student, dressed in oversized comfortable Lofi streetwear (like an oversized hoodie), is wearing headphones (like a vintage style). She is leaning on the desk. Her right hand is propping up her head, resting on her hand and leaning against the desk. She is facing the window, looking out into the distance, with a blank stare, lost in thought. Warm and soft natural daylight is filtering in from the window, nostalgic and healing atmosphere. Extreme detail, super-resolution upscale, 4k.

中文提示：
一幅美麗的豪華現代海景書房照片，暮色降臨的傍晚時分。場景由巨大的落地窗主導，窗外是壯麗的深藍色海洋和海岸線，遠處山坡上的城市燈火剛亮起，天空呈現日落後的晚霞餘暉。室內有一個設計獨特的多層木製辦公桌，結合了背後的樹木盆景和架子。桌上放著一台現代化的一體機電腦（類似 iMac）、鍵盤、書籍和裝飾品。書桌旁有一張舒適的灰色旋轉辦公椅。前景有一個低矮的沙發床和木製茶几，上面放著茶具。房間內有溫暖的環境照明，如桌燈和地燈。一位大約 38 歲的男人，身穿商務休閒服，坐在辦公椅上。他的身體微微轉向窗戶，背對電腦。他靠在桌面上，右手托著頭，目光望向窗外的暮色海景和城市燈火，表現出發呆、深思或疲憊的狀態。極致細節，電影級光影，超高清，4k，寫實風格。

English Prompt:
A beautiful photograph of a luxurious, modern ocean-view study during twilight. The scene is dominated by massive floor-to-ceiling windows, looking out over a spectacular deep blue ocean and coastline, with city lights beginning to glow on the distant hillside and the afterglow of a sunset in the sky. Inside, there is a uniquely designed multi-tiered wooden desk integrated with a bonsai tree and shelving behind it. On the desk sits a modern all-in-one computer (like an iMac), a keyboard, books, and decorative items. A comfortable grey swivel office chair is positioned by the desk. In the foreground, there is a low daybed sofa and a wooden coffee table with a tea set. The room is warmly lit with ambient lighting from desk lamps and a floor lamp. A man, approximately 38 years old, dressed in business-casual attire, is seated in the office chair. His body is slightly turned towards the window, with his back to the computer. He is leaning on the desk, his right hand propping up his head, staring blankly out at the twilight ocean and city lights, expressing a state of being lost in thought, contemplation, or exhaustion. Extreme detail, cinematic lighting, super-resolution upscale, 4k, realistic style.

圖一 (book4.jpg)：冬日木屋的沉浸式遊戲房
這張圖充滿了強烈的溫暖包覆感，木質調與冷色調的窗外形成強烈對比，非常適合帶有強烈重低音或節拍較重的 Lo-Fi 曲風。

中文提示詞：
一幅溫馨的鄉村現代風遊戲房與書房照片。牆壁採用深色木鑲板，內建層架並配有溫暖的隱藏式 LED 燈條。牆上掛著一個巨大的螢幕，顯示著史詩般的奇幻火焰風景。寬敞的木桌上放著一台筆記型電腦、發光的機械鍵盤和滑鼠，下方懸掛著耳機。桌旁有一張黑色人體工學辦公椅。右側有一個巨大的、看起來極其舒適的焦糖色（橘棕色）懶骨頭沙發，上面放著灰色抱枕。左側的窗戶可以看到外面被雪覆蓋的樹木，營造出冬日小木屋的氛圍。木地板上鋪著一塊灰色的毛絨地毯。極致細節，溫暖舒適的燈光，4k，超高清。

English Prompt:
A cozy, rustic-modern gaming room and study. The walls are covered in dark wood paneling with built-in shelves illuminated by warm LED strip lights. A massive monitor is mounted on the wall, displaying an epic fantasy fire landscape. On the spacious wooden desk sits a laptop, a glowing mechanical keyboard, and a mouse, with headphones hanging underneath. A black ergonomic office chair is positioned by the desk. To the right, there is a large, incredibly comfortable-looking burnt-orange beanbag sofa with grey throw pillows. The window on the left reveals a snowy outdoor scene with bare winter trees, creating a winter cabin vibe. A plush grey rug lies on the wooden floor. Extreme detail, warm and cozy lighting, 4k, super-resolution.

🌿 圖二 (book5.jpg)：峽谷湖畔的晨光工作室
這張圖明亮、通透且充滿生機，自然光影的表現非常完美，適合節奏輕快、帶有吉他或清晨鳥鳴的晨間 Chillhop。

中文提示詞：
一幅明亮、豪華的現代書房照片，擁有令人驚嘆的湖光山色。巨大的落地玻璃窗提供了無遮擋的視野，外面是平靜的深藍色湖泊和從水面拔地而起的陡峭、鬱鬱蔥蔥的懸崖與群山。一張設計時尚、邊緣圓潤的現代木桌靠窗擺放。桌上有一台一體機電腦、鍵盤、室內盆栽和精緻的玻璃球裝飾。搭配一張造型獨特的雕塑感木製椅子。窗邊左側可以看到一棵有著秋天紅色樹葉的樹。強烈而清晰的自然陽光灑入室內，在桌子和木地板上投下鮮明的陰影。充滿靈感、寧靜且親近自然，電影級攝影，4k。

English Prompt:
A photograph of a bright, luxurious modern study with a breathtaking lake and mountain view. Massive floor-to-ceiling glass windows provide an unobstructed view of a calm deep blue lake and steep, lush cliffs and mountains rising directly from the water. A sleek, modern wooden desk with rounded edges is positioned by the window. On the desk is an all-in-one computer, keyboard, indoor plants, and an elegant glass globe decor. It is paired with a uniquely shaped, sculptural wooden chair. A tree with striking red autumn leaves is visible near the window on the left. Strong, clear natural sunlight streams into the room, casting distinct shadows on the desk and wooden floor. Inspiring, serene, and nature-connected, cinematic photography, 4k.

🌅 圖三 (book6.jpg)：黃昏雪山的極簡閱讀室
這張圖帶有極強的禪意與專注力，莫蘭迪色調與乾淨的幾何線條，完美契合用來讀書、做報告的「Ambient Study Beats」（氛圍學習音樂）。

中文提示詞：
一幅極簡主義的現代書房照片，擁有全景的高山湖泊視野。一個巨大的矩形景觀窗完美地框住了外面的風景：平靜的湖面、對岸的點點房屋以及遠處連綿的阿爾卑斯雪山。室內設計非常簡潔，兩側有內建的灰色櫥櫃和頂部帶有溫暖照明的書架。一張長條形的極簡書桌橫跨窗戶前方，桌上放著一本打開的書、平板電腦、簡單的文具和一盞小檯燈。搭配一張現代的灰色布面辦公椅。木地板上鋪著一塊編織地毯，角落和地上隨意疊放著幾摞書。溫暖的黃昏夕陽從右側照射進來，在牆壁和桌面上拉出長長的金色陰影。禪意、專注、寧靜，建築攝影風格，4k。

English Prompt:
A photograph of a minimalist, contemporary study with a panoramic view of an alpine lake. A massive rectangular picture window perfectly frames the landscape outside: a calm lake, a distant shore with houses, and a range of snow-capped mountains in the background. The interior design is very clean, featuring built-in grey cabinetry and bookshelves with warm under-cabinet lighting on the sides. A long, minimalist desk spans the width of the window. On the desk rests an open book, a tablet, simple stationery, and a small lamp. A modern grey fabric office chair is pulled up to the desk. A woven area rug lies on the wooden floor, with stacks of books casually placed on the floor and in corners. Warm, golden-hour sunset light streams in from the right, casting long golden shadows across the wall and desk. Zen, focused, serene, architectural photography style, 4k.


