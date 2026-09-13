# Auto_Drama — 書本章節 → 自動短劇產線（指揮官層）

> 目標：人類只指定一本書的章節（例如《閱微草堂筆記》某卷），系統自動完成
> 階段一（劇本擴寫＋分鏡）→ 階段二（角色/場景影像）→ 階段三（配音對嘴）
> → 階段四（剪輯＋情緒配樂＋字幕），輸出可上 YouTube 的長/短影音。

## 設計原則

1. **零侵入原始系統**：本資料夾完全獨立。`F:\AI_DRAMA_FACTORY\LocalMiniDrama-main`
   與 `scripts/` 等原有內容**完全不修改**。
2. **原地引用 LocalMiniDrama**：透過其 REST API（`http://127.0.0.1:5679/api/v1`）
   以 HTTP 驅動，永不直接改動其原始碼/資料夾。
3. **Episodic Routing**：所有輸出動態路由至 `output/episodes/{series}/{episode_id}`，
   禁止全域寫死的輸出路徑。
4. **ZERO SILENT FAILURES**：核心流程失敗一律記錄並 `sys.exit(1)`，禁止空 `except`。
5. **雙模式**：`mock` 模式（無網路、無 API Key，純流程驗證）與 `live` 模式（真實產線）。

## 快速開始

```bash
# Mock 端到端 demo（不需任何 API Key / 網路）
python run.py book --source sample_inputs/yuewei_sample.txt --mock

# Live 逐鏡驅動 LocalMiniDrama（Seedance 2.5 + @圖片N 綁定 + preflight）
# 前置：LMD 後端已啟動（node backend-node/src/server.js，API :5679）
python run.py lmd-episode --episode-id 1 --drama-id 1 \
    --bindings bindings_ep01.json --episode-title "山寺狐影" --force

# 查看 CLI 說明
python run.py --help
```

### `lmd-episode`（Live 全自動鏈）

Auto_Drama 以 REST 驅動 LocalMiniDrama 後端，為指定劇集逐鏡產出 Seedance 2.5 影片：

1. 依 `--bindings`（`{storyboard_number: [char_id,...]}`）把角色綁定到各分鏡
   （未提供時以角色名/別名自動掃描）。
2. 呼叫 `GET /videos/episode/:id/preflight-reference-assets` 整集檢查
   （缺角色資產即中止，對應 CEO 硬閘門）。
3. 逐鏡取得 `GET /storyboards/:id/omni-reference-plan`（權威 `@圖片N` 槽位與 URL）。
4. 缺提示詞時呼叫 `POST /storyboards/:id/universal-segment-prompt` 以 LLM 產出
   含 `@圖片N` 的全能片段文本。
5. `POST /videos`（`storyboard_id` + `reference_image_urls` + `@圖片N` prompt），
   輪詢至 completed，下載改名 `epXX_scNN_shMMM.mp4` 至 `output/episodes/{series}/.../shots/`。
6. （預設）`concat demuxer -c:v copy` 無損拼接單片 + `shots_manifest.json`。

常用旗標：`--limit N`（沙盒只跑前 N 鏡）、`--force`（重新生成）、`--no-concat`、
`--no-generate-universal`、`--model`（預設 `dreamina-seedance-2-5-260628`）。

## 目錄結構

```
Auto_Drama/
├── run.py                  # CLI 入口
├── config/
│   ├── settings.yaml       # 中央設定（LMD 位址、輸出路由、階段開關）
│   └── emotion_map.yaml    # 情緒 → Suno 配樂提示詞映射（古風志怪）
├── auto_drama/
│   ├── config.py           # 讀取設定（env 覆寫）
│   ├── paths.py            # 路徑解析（pathlib，禁硬編碼磁碟機）
│   ├── logging_util.py     # 統一 logger（console + 檔案）
│   ├── state.py            # 產線狀態機（SQLite, threading.local 保護）
│   ├── schemas.py          # 資料模型（dataclass）
│   ├── json_clean.py       # LLM JSON 三重清洗
│   ├── emotion_arc.py      # 情緒弧線聚合 + Suno prompt 映射
│   ├── lmd_client.py       # LocalMiniDrama REST client（真實端點）
│   ├── suno_client.py      # Suno 官方 / Docker 雙後端 client
│   ├── llm_client.py       # DeepSeek-R1 直連 client（古文擴寫）
│   ├── ffmpeg.py           # concat / amix / 字幕 / acrossfade 助手
│   ├── stages.py           # 四大階段 Runner（provider 注入）
│   ├── orchestrator.py     # 產線狀態機主流程
│   ├── mock_provider.py    # Mock provider（demo 用）
│   ├── cli.py              # argparse CLI
│   └── telegram_ctl.py     # Telegram 遠端控制（HITL）
├── tests/
├── sample_inputs/
└── output/                 # 產物（執行時自動建立）
```

## 環境變數（live 模式需要，禁止寫入 yaml）

| 變數 | 用途 |
|------|------|
| `LMD_BASE_URL` | LocalMiniDrama 後端位址（預設 `http://127.0.0.1:5679`） |
| `DEEPSEEK_API_KEY` | 劇本擴寫/分鏡 LLM |
| `SUNO_API_KEY` | Suno 官方 API（`SUNO_BACKEND=official` 時） |
| `SUNO_BACKEND` | `official` 或 `docker`（`http://localhost:3000`） |
| `AUTO_DRAMA_OUTPUT_ROOT` | 輸出根目錄覆寫 |
