# 備份儲存庫（GitHub Mirror）設定說明

本目錄透過 [`.github/workflows/backup-mirror.yml`](workflows/backup-mirror.yml) 將**目前這個 repo** 以 `git push --mirror` 同步到另一個 GitHub 儲存庫，作為離線災備或第二份完整複本（含分支、標籤；與一般 `git clone` 再 `push` 的用途不同，請先閱讀下方注意事項）。

## 1. 在 GitHub 建立「備份用」空儲存庫

1. 登入 GitHub → **New repository**。
2. 建議命名例如：`AI_DRAMA_FACTORY_BACKUP`（勿與主 repo 同名同帳號下搞混即可）。
3. **不要**初始化 README / .gitignore / license（保持空 repo，避免第一次 push 衝突）。
4. 建議設為 **Private**。

## 2. 建立 Personal Access Token（PAT）

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens**。
2. 建立 **Fine-grained** 或 **Classic** token，至少需具備：
   - 對**備份儲存庫**的 **Contents: Read and write**（或 classic 的 `repo` 範圍僅限該 repo）。
3. 複製 token（只顯示一次，請自行安全保管）。

## 3. 設定 Repository Secret（主專案這邊）

在**主 repo**（本專案）→ **Settings** → **Secrets and variables** → **Actions** → **New repository secret**：

| Name | 值 |
|------|-----|
| `BACKUP_MIRROR_URL` | 見下一節格式 |

### `BACKUP_MIRROR_URL` 格式

將 `OWNER`、`REPO_BACKUP`、`YOUR_TOKEN_HERE` 換成你的帳號／備份 repo 名稱／PAT：

```text
https://x-access-token:YOUR_TOKEN_HERE@github.com/OWNER/REPO_BACKUP.git
```

範例：

```text
https://x-access-token:ghp_xxxxxxxx@github.com/MyOrg/AI_DRAMA_FACTORY_BACKUP.git
```

## 4. 手動執行與排程

- **手動**：主 repo → **Actions** → **Backup mirror (secondary repo)** → **Run workflow**。
- **排程**：workflow 內建每週日 UTC 05:00 執行一次（可在 YAML 內改 `cron`）。

若未設定 `BACKUP_MIRROR_URL`，workflow 會成功結束並顯示 **warning**，不會失敗洗版。

## 5. 注意事項（必讀）

- **`git push --mirror` 會覆寫備份端與來源不一致的 refs**；備份 repo 應專用、不要當一般開發分支用。
- **`.env`、金鑰**若曾 commit 進主 repo，mirror 也會進備份；請依賴 `.gitignore` 與**勿提交密鑰**的習慣。
- PAT 外洩等同帳號風險；若疑慮外洩，立刻在 GitHub **撤銷 token** 並換新 Secret。

## 6. 還原方式（簡述）

在乾淨目錄：

```bash
git clone --mirror https://github.com/OWNER/REPO_BACKUP.git
cd REPO_BACKUP.git
git push --mirror https://github.com/OWNER/MAIN_REPO.git
```

實際還原前請先確認備份 repo 內容與權限，必要時先另目錄試推。

## 7. 本機實作（與 Actions 相同行為）

專案已內建腳本，使用**與 Secret 相同名稱**的環境變數 `BACKUP_MIRROR_URL`：

1. 在專案根目錄 `.env` 加入一行（值請自行替換，**勿 commit**）：

   ```env
   BACKUP_MIRROR_URL=https://x-access-token:YOUR_PAT@github.com/OWNER/REPO_BACKUP.git
   ```

2. 在**已初始化 git 的專案根**執行：

   ```bash
   python scripts/maintenance/push_backup_mirror.py
   ```

   - 先檢查而不推送：

     ```bash
     python scripts/maintenance/push_backup_mirror.py --dry-run
     ```

3. Windows 可改用：

   ```powershell
   .\scripts\maintenance\push_backup_mirror.ps1
   ```

腳本會暫時新增遠端名稱 `rs-backup-mirror`，推送完成後移除，避免留在本機 `git remote -v`。
