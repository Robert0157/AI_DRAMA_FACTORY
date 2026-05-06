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

function Read-DotEnvValue {
    param(
        [string]$DotEnvPath,
        [string]$Key
    )
    if (-not (Test-Path -LiteralPath $DotEnvPath)) { return $null }
    foreach ($line in Get-Content -LiteralPath $DotEnvPath) {
        $t = $line.Trim()
        if ($t -eq "" -or $t.StartsWith("#")) { continue }
        if ($t -notmatch "^(?:export\s+)?$([Regex]::Escape($Key))\s*=\s*(.+)$") { continue }
        $val = $Matches[1].Trim()
        if ($val.Length -ge 2 -and $val[0] -eq $val[-1] -and ($val[0] -eq "'" -or $val[0] -eq '"')) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        return $val
    }
    return $null
}

$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$StreamingRoot = if ($env:STREAMING_ROOT) { $env:STREAMING_ROOT } elseif ($env:STEAM_ROOT) { $env:STEAM_ROOT } else { Join-Path $RepoRoot "Streaming" }
$DotEnvFile = Join-Path $RepoRoot ".env"

$EnvFile = Join-Path $StreamingRoot "secrets\rtmp.env"
$Playlist = Join-Path $StreamingRoot "config\concat_playlist.txt"
$ConfigDir = Join-Path $StreamingRoot "config"
$LogDir = Join-Path $StreamingRoot "logs"
$targetFps = 30
$keyintSec = 2
$keyintFrames = $targetFps * $keyintSec

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
    $rtmpUrl = Read-DotEnvValue -DotEnvPath $DotEnvFile -Key "YOUTUBE_RTMP_URL"
    if ([string]::IsNullOrWhiteSpace($rtmpUrl)) {
        $ytKey = Read-DotEnvValue -DotEnvPath $DotEnvFile -Key "YOUTUBE_KEY"
        if (-not [string]::IsNullOrWhiteSpace($ytKey)) {
            $rtmpUrl = "rtmp://a.rtmp.youtube.com/live2/$ytKey"
        }
    }
}
if ([string]::IsNullOrWhiteSpace($rtmpUrl)) {
    Write-Host "缺少 RTMP 位址：請設定 `$env:YOUTUBE_RTMP_URL`、Streaming/secrets/rtmp.env，或 repo .env 內 YOUTUBE_RTMP_URL / YOUTUBE_KEY" -ForegroundColor Red
    exit 1
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "Streaming 根目錄：$StreamingRoot" -ForegroundColor Cyan
Write-Host "Playlist：$Playlist" -ForegroundColor Cyan
if ($Once) {
    Write-Host "模式：單次執行（-Once）" -ForegroundColor DarkYellow
} else {
    Write-Host "按 Ctrl+C 結束；ffmpeg 退出後將依退避策略自動重試…" -ForegroundColor DarkYellow
}

$backoff = 5
$maxBackoff = 300

Push-Location $ConfigDir
try {
    do {
        $ts = Get-Date -Format "yyyyMMdd_HHmmss"
        $log = Join-Path $LogDir "ffmpeg_$ts.log"
        "—— 開始 ffmpeg @ $ts ——" | Out-File -FilePath $log -Encoding utf8
        Write-Host "—— 開始 ffmpeg @ $ts ——" -ForegroundColor Green

        $ffmpegArgs = @(
            "-hide_banner", "-loglevel", "info", "-nostdin",
            "-re", "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-stream_loop", "-1",
            "-i", "concat_playlist.txt",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p", "-r", "$targetFps",
            "-g", "$keyintFrames", "-keyint_min", "$keyintFrames", "-sc_threshold", "0",
            "-b:v", "2500k", "-maxrate", "3000k", "-bufsize", "6000k",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
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
        Write-Host "ℹ️  $backoff 秒後重試…" -ForegroundColor DarkYellow
        Start-Sleep -Seconds $backoff
        if ($code -eq 0) {
            $backoff = 5
        } elseif ($backoff -lt $maxBackoff) {
            $backoff = [Math]::Min($maxBackoff, $backoff * 2)
        }
    } while ($true)
} finally {
    Pop-Location
}
