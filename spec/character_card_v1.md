# `character_card.v1` — B 線角色「文字錨」規格書

> v1.0 ｜ 2026-09-12 ｜ 依據：架構說明書 §5.5「角色一致性雙錨定制」（v16.2.7）
> 配套：影像錨＝P2 定裝四視圖（`@圖片N`）；本卡為文字錨，兩者同時產出、同時送 CP-D 審核。

## 1. 目的與時機

- 解決病灶：「角色每一鏡長相／氣質不一致」。
- 產生時機：**P2 定裝階段**（鑄造閘門 `lock_ready` 通過後），與四視圖定裝照同步產出。
- 來源依據：forge 角色聖經（`bible.protagonists／antagonists／canon.characters`）＋劇本節錄中已鎖定的外貌／服裝描述。

## 2. 存放與相容性

- 主檔：`character_vault.db`（每角色一列；`card_json` 欄——欄位擴充於 P2 前完成）。
- Sidecar：`assets/episodes/<series>/casting/<char_id>.card.json`（人工審閱、工具互通）。
- 相容：欄位為 **SillyTavern Character Card V2 之子集** ＋ 產線擴充槽 `x_pipeline`；可選 PNG 內嵌（tEXt `chara`，base64）供互通。
- 邊界：**僅借格式，不作產線依賴**——第三方程式不進產線（架構說明書 §5.4 裁定維持）。

## 3. 欄位定義

| 欄位 | 必填 | 說明 |
|---|---|---|
| `name` | ✓ | 角色正式名（如 林宇翔） |
| `aliases` | | 語言／場合變體（Leo、翔哥） |
| `role` | ✓ | 定位（主角／反派／支援） |
| `appearance` | ✓ | 固定外貌特徵：臉型、髮型髮色、瞳色、體態、年齡感、標誌特徵 |
| `costume` | ✓ | 服裝（依分弧註記：Arc1…Arc4） |
| `fixed_keywords` | ✓ | 每鏡 prompt 必附固定關鍵字塊（≤20 詞；英文）；含負面防漂移詞 |
| `voice_fingerprint` | ✓ | 語言指紋（語域／口頭禪／句法；對白一致性） |
| `personality` | | 性格摘要（編劇參考） |
| `ref_images` | ✓ | 影像錨：`character_vault.db` 四視圖 ID 清單（前／側／背／特寫） |
| `x_pipeline` | | 產線擴充：首出場集、`@圖片N` 槽位、VEO 備援提示詞引用 |

## 4. 產線使用規則

1. **分鏡 prompt 組裝**：`分鏡描述 + fixed_keywords + @圖片N 綁定`（文字錨＋影像錨同鏡生效）。
2. **LocalMiniDrama**：`omniReferencePlan`（權威計畫）維持槽位順序；參考圖解析失敗 loud-fail（已實作）。
3. **Seedance 量產**：角色首次出場前須有 ≥1 張基準圖，否則 `CharacterReferenceMissingException` 中斷（既有硬閘門）。
4. **審核**：卡片與定裝照同捆進 CP-D 審核包（供 CEO 閱讀為文字＋圖；機器 JSON 不上桌）。

## 5. 紅線

- **禁第三方 IP**：不得使用社群既有角色卡內容（動漫／遊戲角色）；角色一律原創或公版神話原型改寫。
- **風格鎖定**：好萊塢實拍（photo-real）；禁二次元／插畫風關鍵字。
- **單一來源**：卡內容必須可由劇本聖經＋定裝照追溯，不得外部未審內容直入。
- **不依賴**：任何第三方角色卡格式僅供互通；產線運作不得依賴外部程式或服務。

## 6. 範例（節錄）

```json
{
  "name": "林宇翔",
  "aliases": ["Leo"],
  "role": "主角／直播主",
  "appearance": "25 歲東亞男性，短黑髮微亂，濃眉，清瘦，笑時左側酒窩",
  "costume": {"Arc1": "連帽外套＋耳麥", "Arc3": "磨損皮夾克＋充電腰包"},
  "fixed_keywords": "photo-real, 25yo East Asian male, short messy black hair, slim build, hoodie, lav mic, cinematic lighting; --no beard, glasses, anime",
  "voice_fingerprint": "直播腔＋自嘲短句；焦慮時語速加快成連珠炮",
  "personality": "從蹭流量到守護故事；口硬心軟",
  "ref_images": ["cv_lin_front", "cv_lin_side", "cv_lin_back", "cv_lin_closeup"],
  "x_pipeline": {"first_ep": 1, "image_slots": ["@圖片1"], "veo_backup_ref": "veo/lin_backup.txt"}
}
```

（其餘常設角色：蘇晴、夸父、雅典娜、虛無、洛基、黑粉團首領——P2 定裝時逐位產出）

## 7. 與顧問建議之對照（2026-09-12 複評結論）

| 顧問步驟 | 裁定 | 落地方式 |
|---|---|---|
| SillyTavern 建卡定義外貌／服裝／固定關鍵字 | ✓ 借概念與格式 | 本規格 `character_card.v1`（自建、可互通） |
| 用 SillyTavern 產出對話與鏡頭描寫 | ✗ 不採用 | 維持 `script_forge` 多代理評審＋ CP-D 閘門（繞過即違反治理） |
| 角色 PNG／JSON 直餵 LocalMiniDrama 當 Anchor | ✗ 修正 | 文字卡僅進 prompt 關鍵字層；**影像錨必須自產四視圖**（版權＋多視角＋實拍風格） |
