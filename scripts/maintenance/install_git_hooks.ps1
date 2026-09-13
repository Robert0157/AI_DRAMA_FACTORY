# Install versioned git hooks into .git/hooks (pre-push = dual-line QA gate).
# Usage: powershell -File scripts/maintenance/install_git_hooks.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # repo root
$source = Join-Path $root "scripts\maintenance\hooks\pre-push"
$targetDir = Join-Path $root ".git\hooks"
$target = Join-Path $targetDir "pre-push"

if (-not (Test-Path $source)) { throw "hook source missing: $source" }
if (-not (Test-Path $targetDir)) { throw ".git/hooks not found (not a git repo?): $targetDir" }

Copy-Item $source $target -Force
# Normalize to LF so sh can execute it on Windows.
$content = [System.IO.File]::ReadAllText($target) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText($target, $content, (New-Object System.Text.UTF8Encoding($false)))

Write-Output "installed: $target"
Write-Output "verify:    git push (hook runs verify_dual_line_release.py and blocks on failure)"
