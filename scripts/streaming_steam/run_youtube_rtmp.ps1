# 第三輪：concat + copy 推 YouTube RTMP（建議先用測試金鑰）
# 前置：第一／二輪已通過；已產生 Streaming/config/concat_playlist.txt；ffmpeg 在 PATH。
#
# 用法（repo 根目錄）：
#   .\scripts\streaming_steam\run_youtube_rtmp.ps1
#   $env:STREAMING_ROOT = "D:\path\Streaming"; .\scripts\streaming_steam\run_youtube_rtmp.ps1
#   .\scripts\streaming_steam\run_youtube_rtmp.ps1 -Once   # 單次 ffmpeg、不迴圈重試
#
# RTMP 位址（擇一）：
#   ① 環境變數：$env:YOUTUBE_RTMP_URL = 'rtmp://a.rtmp.youtube.com/live2/xxxx'（優先於檔案）
#   ② 檔案：Streaming/secrets/rtmp.env（見 scripts/streaming_steam/rtmp.env.template）
#      export YOUTUBE_RTMP_URL='rtmp://a.rtmp.youtube.com/live2/xxxx'

param(
    [switch]$Once
)

$ErrorActionPreference = "Stop"

function Read-YouTubeRtmpUrl {
    param([string]$EnvFilePath)
    $url = $null
    foreach ($line in Get-Content -LiteralPath $EnvFilePath) {
        $t = $line.Trim()
        if ($t -eq "" -or $t.StartsWith("#")) { continue }
        if ($t -notmatch '^(?:export\s+)?YOUTUBE_RTMP_URL\s*=\s*(.+)$') { continue }
        $val = $Matches[1].Trim()
        if ($val.Length -ge 2 -and $val[0] -eq $val[-1] -and ($val[0] -eq "'" -or $val[0] -eq '"')) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        $url = $val
        break
    }
    if ([string]::IsNullOrWhiteSpace($url)) {
        throw "無法從 rtmp.env 解析 YOUTUBE_RTMP_URL（請確認含 export YOUTUBE_RTMP_URL='rtmp://...'）"
    }
    return $url
}

$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$StreamingRoot = if ($env:STREAMING_ROOT) { $env:STREAMING_ROOT } elseif ($env:STEAM_ROOT) { $env:STEAM_ROOT } else { Join-Path $RepoRoot "Streaming" }

$EnvFile = Join-Path $StreamingRoot "secrets\rtmp.env"
$Playlist = Join-Path $StreamingRoot "config\concat_playlist.txt"
$ConfigDir = Join-Path $StreamingRoot "config"
$LogDir = Join-Path $StreamingRoot "logs"

if (-not (Test-Path -LiteralPath $Playlist)) {
    Write-Host "找不到 $Playlist — 請先執行 validate_local_round12.ps1 或 build_concat_playlist.sh" -ForegroundColor Red
    exit 1
}

$rtmpUrl = $null
if (-not [string]::IsNullOrWhiteSpace($env:YOUTUBE_RTMP_URL)) {
    $rtmpUrl = $env:YOUTUBE_RTMP_URL.Trim()
    Write-Host "使用環境變數 YOUTUBE_RTMP_URL（略過 rtmp.env）" -ForegroundColor DarkYellow
} elseif (Test-Path -LiteralPath $EnvFile) {
    $rtmpUrl = Read-YouTubeRtmpUrl -EnvFilePath $EnvFile
} else {
    Write-Host "缺少 RTMP 位址：請設定 `$env:YOUTUBE_RTMP_URL`，或複製 rtmp.env.template 至`n  $EnvFile" -ForegroundColor Red
    Write-Host "（YouTube 後台 → 直播 → 串流失效備援 → 顯示金鑰；建議先用「測試直播」）" -ForegroundColor DarkYellow
    exit 1
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "Streaming 根目錄：$StreamingRoot" -ForegroundColor Cyan
Write-Host "Playlist：$Playlist" -ForegroundColor Cyan
if ($Once) {
    Write-Host "模式：單次執行（-Once）" -ForegroundColor DarkYellow
} else {
    Write-Host "按 Ctrl+C 結束；ffmpeg 退出後 5 秒自動重試…" -ForegroundColor DarkYellow
}

Push-Location $ConfigDir
try {
    do {
        $ts = Get-Date -Format "yyyyMMdd_HHmmss"
        $log = Join-Path $LogDir "ffmpeg_$ts.log"
        "—— 開始 ffmpeg @ $ts ——" | Out-File -FilePath $log -Encoding utf8
        Write-Host "—— 開始 ffmpeg @ $ts ——" -ForegroundColor Green

        $ffmpegArgs = @(
            "-hide_banner", "-loglevel", "info", "-nostdin",
            "-re", "-f", "concat", "-safe", "0", "-stream_loop", "-1",
            "-i", "concat_playlist.txt",
            "-c:v", "copy", "-c:a", "copy",
            "-f", "flv", $rtmpUrl
        )
        # ffmpeg 將日誌寫入 stderr，PowerShell 會包成 ErrorRecord；統一成字串再寫檔
        $prevEa = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        try {
            & ffmpeg @ffmpegArgs 2>&1 | ForEach-Object {
                $line = "$_"
                Add-Content -LiteralPath $log -Value $line -Encoding utf8
                Write-Host $line
            }
        } finally {
            $ErrorActionPreference = $prevEa
        }
        $code = $LASTEXITCODE
        $endLine = "—— ffmpeg 結束 exit=$code @ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ——"
        Add-Content -LiteralPath $log -Value $endLine
        Write-Host $endLine -ForegroundColor $(if ($code -eq 0) { "Green" } else { "Yellow" })

        if ($Once) { break }
        Start-Sleep -Seconds 5
    } while ($true)
} finally {
    Pop-Location
}
