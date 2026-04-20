# 第一輪 + 第二輪本機驗證（Windows PowerShell 5.1+）
# 前提：已安裝 ffmpeg、Python；Streaming/config/live_manifest.json 與 Streaming/queue/*.mp4 已就緒。
#
# 用法（在 repo 根目錄）：
#   .\scripts\streaming_steam\validate_local_round12.ps1
#   $env:STREAMING_ROOT = "D:\path\Streaming"; .\scripts\streaming_steam\validate_local_round12.ps1
#   （相容舊名：$env:STEAM_ROOT）

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$StreamingRoot = if ($env:STREAMING_ROOT) { $env:STREAMING_ROOT } elseif ($env:STEAM_ROOT) { $env:STEAM_ROOT } else { Join-Path $RepoRoot "Streaming" }

Write-Host "== Round 1: build concat_playlist.txt ==" -ForegroundColor Cyan
$manifest = Join-Path $StreamingRoot "config\live_manifest.json"
if (-not (Test-Path $manifest)) {
    Write-Host "缺少 $manifest — 請先建立 manifest" -ForegroundColor Red
    exit 1
}
$py = Join-Path $RepoRoot "scripts\streaming_steam\emit_concat_from_manifest.py"
$text = & python $py --streaming-root $StreamingRoot --manifest $manifest 2>&1
if ($LASTEXITCODE -ne 0) { throw "emit_concat_from_manifest.py failed: $text" }
$out = Join-Path $StreamingRoot "config\concat_playlist.txt"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($out, ($text -split "`n" | ForEach-Object { $_.TrimEnd("`r") }), $utf8NoBom)
Get-Content $out
Write-Host "OK: $out" -ForegroundColor Green

Write-Host "`n== Round 2: ffmpeg concat + copy -> null (15s) ==" -ForegroundColor Cyan
Push-Location (Join-Path $StreamingRoot "config")
try {
    & ffmpeg -hide_banner -loglevel warning -t 15 -re -f concat -safe 0 -stream_loop -1 `
        -i "concat_playlist.txt" -c copy -f null -
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg exit $LASTEXITCODE" }
} finally {
    Pop-Location
}
Write-Host "OK: Round 2 finished (exit 0)." -ForegroundColor Green
Write-Host "接縫處若出現 DTS 警告，可再以真實 1hr 母帶複測。" -ForegroundColor DarkYellow
