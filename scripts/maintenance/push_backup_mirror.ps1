#Requires -Version 5.1
<#
.SYNOPSIS
  呼叫 push_backup_mirror.py，將本 repo mirror 推送到 BACKUP_MIRROR_URL。
  請在專案根 .env 設定 BACKUP_MIRROR_URL，或先設定環境變數。
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root
python scripts/maintenance/push_backup_mirror.py @args
exit $LASTEXITCODE
