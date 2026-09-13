# ============================================================================
# Auto_Drama — Windows -> Mac mini 同步腳本 (PowerShell)
# 優先使用 rsync（若本機有）；否則退回 scp -r（無法排除資料夾，請見警告）。
#
# 用法:
#   powershell -ExecutionPolicy Bypass -File .\sync_to_mac.ps1 -MacUser alice -MacHost 192.168.1.50
#
# 參數（可省略，使用預設）:
#   -MacUser    Mac 使用者名稱
#   -MacHost    Mac IP / 主機名
#   -MacRoot    Mac 端工作區根目錄（預設 /Volumes/AI_Workspace/AI_DRAMA_FACTORY）
#   -LocalRoot  Windows 端工作區根目錄（預設 F:\AI_DRAMA_FACTORY）
# ============================================================================
param(
    [string]$MacUser = "YOUR_MAC_USER",
    [string]$MacHost = "YOUR_MAC_HOST_OR_IP",
    [string]$MacRoot  = "/Volumes/AI_Workspace/AI_DRAMA_FACTORY",
    [string]$LocalRoot = "F:\AI_DRAMA_FACTORY"
)

$ErrorActionPreference = "Stop"

# 要同步的子資料夾（LocalMiniDrama 引擎 + Auto_Drama 指揮官）。
$Items = @("LocalMiniDrama-main", "Auto_Drama")

# rsync 排除清單（大檔/執行期產物一律不上傳，Mac 端各自重建）。
$Excludes = @(
    "--exclude", "node_modules/",
    "--exclude", "venv/",
    "--exclude", ".venv/",
    "--exclude", "__pycache__/",
    "--exclude", ".git/",
    "--exclude", "output/",
    "--exclude", "logs/",
    "--exclude", "data/",
    "--exclude", "*.pyc",
    "--exclude", ".DS_Store"
)

if ($MacUser -eq "YOUR_MAC_USER" -or $MacHost -eq "YOUR_MAC_HOST_OR_IP") {
    Write-Host "[sync] 請先編輯本檔，填入 -MacUser 與 -MacHost" -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $LocalRoot)) {
    Write-Host "[sync] LocalRoot 不存在: $LocalRoot" -ForegroundColor Red
    exit 1
}

# --- 找 rsync（Git for Windows / MSYS2 通常提供）---
$rsync = Get-Command rsync -ErrorAction SilentlyContinue

if ($rsync) {
    Write-Host "[sync] 使用 rsync -> $($rsync.Source)"
    foreach ($item in $Items) {
        $src = Join-Path $LocalRoot $item
        if (-not (Test-Path $src)) {
            Write-Host "[sync] 略過(不存在): $src" -ForegroundColor Yellow
            continue
        }
        $dst = "$MacUser@$MacHost`:$MacRoot/$item/"
        Write-Host "[sync] $item -> $dst"
        & $rsync.Source -avz --delete $Excludes "$src/" $dst
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
else {
    # --- 退回 scp（無排除能力，會連 node_modules 一起傳；僅建議首次全量）---
    Write-Host "[sync] 未找到 rsync，改用 scp -r（警告：無法排除 node_modules/venv 等）" -ForegroundColor Yellow
    foreach ($item in $Items) {
        $src = Join-Path $LocalRoot $item
        if (-not (Test-Path $src)) {
            Write-Host "[sync] 略過(不存在): $src" -ForegroundColor Yellow
            continue
        }
        $dst = "$MacUser@$MacHost`:$MacRoot/"
        Write-Host "[sync] scp -r $item -> $dst"
        & scp -r "$src" $dst
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    Write-Host @"

[sync] 注意：scp 無法排除大目錄。建議在 Mac 端事後清理:
  rm -rf $MacRoot/Auto_Drama/venv $MacRoot/Auto_Drama/output $MacRoot/Auto_Drama/logs $MacRoot/Auto_Drama/data
  rm -rf $MacRoot/LocalMiniDrama-main/backend-node/node_modules $MacRoot/LocalMiniDrama-main/frontweb/node_modules
"@ -ForegroundColor Yellow
}

Write-Host "[sync] 完成。可在 Mac 端驗證: ls $MacRoot" -ForegroundColor Green
