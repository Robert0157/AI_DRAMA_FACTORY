# Auto_Drama — Mac mini M4 生產部署檢查清單
> 適用對象：把 Windows 開發好的 `LocalMiniDrama-main` + `Auto_Drama` 部署到
> Mac mini M4 外接 SSD（`/Volumes/AI_Workspace/AI_DRAMA_FACTORY`）。
> 原始 Windows 工作區保持不動（本清單只做「新增/複製」，不做刪改）。

## Phase 0 — 前置檢查（Mac 上執行一次）
- [ ] 開啟「遠端登入 SSH」：系統設定 → 一般 → 共享 → 遠端登入 → 開啟
- [ ] 確認外接 Thunderbolt SSD 已掛載：`ls /Volumes/AI_Workspace/` 看得到
- [ ] 安裝 Homebrew：`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
- [ ] 安裝 Node.js ≥ 18：`brew install node`；驗證 `node -v`
- [ ] 安裝 Python ≥ 3.11：`brew install python@3.12`；驗證 `python3 -V`
- [ ] 安裝 ffmpeg：`brew install ffmpeg`
- [ ] （可選）安裝 Docker Desktop — Suno docker 備援後端 `services/suno-api/` 用
- [ ] 確認 Mac 上已有原始工作區副本，或準備建立：
      `mkdir -p /Volumes/AI_Workspace/AI_DRAMA_FACTORY`

## Phase 1 — Windows → Mac 同步（在 Windows 執行）
- [ ] `cd F:\AI_DRAMA_FACTORY\Auto_Drama\deploy`
- [ ] 編輯 `sync_to_mac.ps1` 填好 `MacUser` / `MacHost`
- [ ] 執行 `powershell -ExecutionPolicy Bypass -File .\sync_to_mac.ps1`
- [ ] 驗證 Mac 端檔案：`ls /Volumes/AI_Workspace/AI_DRAMA_FACTORY/Auto_Drama`

## Phase 2 — Mac 端安裝 LocalMiniDrama 後端
- [ ] `cd /Volumes/AI_Workspace/AI_DRAMA_FACTORY/LocalMiniDrama-main/backend-node`
- [ ] `npm install`
- [ ] 檢查設定檔存在：`cat configs/config.yaml`（無則從 `config.example.yaml` 複製）
- [ ] （建議）把 `storage.local_path` 指向 SSD 資產目錄：
      `configs/config.yaml` → `storage.local_path: /Volumes/AI_Workspace/AI_DRAMA_FACTORY/assets/episodes`
- [ ] 首次啟動前遷移：`npm run migrate`
- [ ] 啟動：`npm start` → 驗證 `curl http://127.0.0.1:5679/health` 回 `{"status":"ok"}`

## Phase 3 — Mac 端安裝 Auto_Drama
- [ ] `cd /Volumes/AI_Workspace/AI_DRAMA_FACTORY/Auto_Drama`
- [ ] `python3 -m venv venv && source venv/bin/activate`
- [ ] `pip install -r requirements.txt`
- [ ] 建立環境檔：`cp deploy/env/auto_drama.env.example deploy/env/auto_drama.env`
      填入真實金鑰（**不要**把金鑰寫進 git）
- [ ] Mock 驗證：`python run.py book --source sample_inputs/yuewei_sample.txt --mock`
- [ ] Live 驗證：`set -a; source deploy/env/auto_drama.env; set +a; python run.py book --source sample_inputs/yuewei_sample.txt --live --stage1-only`

## Phase 4 — 常駐化（launchd，開機自啟）
- [ ] `cd /Volumes/AI_Workspace/AI_DRAMA_FACTORY/Auto_Drama/deploy/launchd`
- [ ] 依 `install_launchd.sh` 說明編輯 plist 內的絕對路徑/使用者名稱
- [ ] `./install_launchd.sh`
- [ ] 驗證：`launchctl list | grep auto-drama`
- [ ] 重開機後確認兩支 daemon 自動起來（LMD :5679 + Telegram bot）

## Phase 5 — 環境切換與收尾
- [ ] 在 Mac 端 `env.md`（若有）切到 `TARGET_ENV=MAC_M4` 區塊
- [ ] Telegram `/status` 測通
- [ ] 確認 Windows 端原始工作區仍可獨立運作（未受影響）

## 重要提醒
1. **SQLite 不得放 SMB 網路磁碟**：Mac 端請一律用本機 `/Volumes/...` 路徑執行，
   Windows 端 `X:\`（若有 SMB 掛載）僅供「看檔案」。
2. **金鑰管理**：`deploy/env/auto_drama.env` 加入 `.gitignore`，禁止入 git。
3. **不要同步**：`venv/`、`node_modules/`、`output/`、`logs/`、`data/`（Mac 各自重建）。
