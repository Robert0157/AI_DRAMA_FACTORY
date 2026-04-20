# 將 Windows 本機 Streaming/queue_staging 增量同步到 Mac（rsync over SSH）
# 前提：Mac 已掛載外接碟；Windows 已安裝 Git for Windows（內含 rsync）；已設定 SSH 公鑰免密（BatchMode）。
#
# 用法（在 repo 根或任意目錄）：
#   .\scripts\streaming_steam\sync_queue_staging_to_mac.ps1
#   .\scripts\streaming_steam\sync_queue_staging_to_mac.ps1 -MacHost "robert@192.168.1.111" -DryRun
#
# 工作排程器請見：scripts/streaming_steam/WINDOWS_TASK_SCHEDULER_queue_staging.md

param(
    [string]$MacHost = "robert@192.168.1.111",
    [string]$RemoteStaging = "/Volumes/AI_Workspace/AI_Drama_Factory/Streaming/queue_staging",
    [string]$LocalStaging = "",
    [string]$RsyncExe = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Convert-WindowsPathToCygpath {
    param([Parameter(Mandatory = $true)][string]$WinPath)
    $full = (Resolve-Path -LiteralPath $WinPath).Path
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "無法轉換為 rsync 用路徑：$WinPath"
    }
    $drive = $Matches[1].ToLowerInvariant()
    $rest = $Matches[2].Replace("\", "/")
    return "/cygdrive/$drive/$rest"
}

$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $LocalStaging) {
    $LocalStaging = Join-Path $RepoRoot "Streaming\queue_staging"
}
if (-not (Test-Path -LiteralPath $LocalStaging)) {
    New-Item -ItemType Directory -Force -Path $LocalStaging | Out-Null
}

if (-not $RsyncExe) {
    $candidates = @(
        "C:\Program Files\Git\usr\bin\rsync.exe",
        "${env:ProgramFiles(x86)}\Git\usr\bin\rsync.exe",
        "C:\Program Files\Git\mingw64\bin\rsync.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) {
            $RsyncExe = $c
            break
        }
    }
}
if (-not $RsyncExe -or -not (Test-Path -LiteralPath $RsyncExe)) {
    throw "找不到 rsync.exe。請安裝 Git for Windows，或指定 -RsyncExe 完整路徑。"
}

$localCyg = (Convert-WindowsPathToCygpath -WinPath $LocalStaging).TrimEnd("/") + "/"
$remoteDest = "${MacHost}:$RemoteStaging/"

# SSH：免互動；首次主機可自動寫入 known_hosts（若你希望更嚴格可改為 yes）
$sshOpts = "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30"

$rsyncArgs = @(
    "-avz",
    "--partial",
    "--timeout=300",
    "--human-readable",
    "-e", $sshOpts
)
if ($DryRun) {
    $rsyncArgs += "-n"
}

# 來源尾端 / = 只同步目錄內容，避免多包一層 queue_staging
$rsyncArgs += $localCyg
$rsyncArgs += $remoteDest

Write-Host "== sync_queue_staging_to_mac ==" -ForegroundColor Cyan
Write-Host "  rsync: $RsyncExe"
Write-Host "  from:  $localCyg"
Write-Host "  to:    $remoteDest"
if ($DryRun) {
    Write-Host "  mode:  DRY RUN (-n)" -ForegroundColor Yellow
}

& $RsyncExe @rsyncArgs
if ($LASTEXITCODE -ne 0) {
    throw "rsync 結束碼 $LASTEXITCODE"
}
Write-Host "OK: sync finished." -ForegroundColor Green
