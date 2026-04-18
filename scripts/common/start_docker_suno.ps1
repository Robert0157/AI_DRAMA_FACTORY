# ============================================================
# start_docker_suno.ps1
# Agent 自動啟動腳本：無需人工介入，全自動喚起 Docker Desktop
# 並以 detached 模式啟動 suno-api 服務。
# 呼叫方式：powershell -ExecutionPolicy Bypass -File scripts\common\start_docker_suno.ps1
# ============================================================

$DOCKER_DESKTOP = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$COMPOSE_DIR    = "f:\AI_DRAMA_FACTORY\suno-api"
$MAX_WAIT_SEC   = 120   # Docker Daemon 最長等待秒數
$SVC_PORT       = 3000  # suno-api 服務埠口

# ── 1. 確保 Docker Daemon 正在執行 ──────────────────────────
function Wait-DockerReady {
    Write-Host "[DOCKER] 檢查 Docker Daemon 狀態..."
    $elapsed = 0
    while ($elapsed -lt $MAX_WAIT_SEC) {
        $result = docker info 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[DOCKER] Daemon 就緒。"
            return $true
        }
        if ($elapsed -eq 0) {
            Write-Host "[DOCKER] Daemon 未啟動，正在喚醒 Docker Desktop..."
            Start-Process -FilePath $DOCKER_DESKTOP -WindowStyle Hidden
        }
        Start-Sleep -Seconds 5
        $elapsed += 5
        Write-Host "[DOCKER] 等待中... ($elapsed / $MAX_WAIT_SEC 秒)"
    }
    Write-Host "[ERROR] Docker Daemon 在 $MAX_WAIT_SEC 秒內未就緒，中止。"
    exit 1
}

# ── 2. 確認 suno-api container 是否已在運行 ────────────────
function Get-SunoContainerState {
    $running = docker ps --format "{{.Names}}" 2>&1 | Select-String "suno-api"
    return ($null -ne $running -and $running -ne "")
}

# ── 3. 等待 HTTP port 3000 就緒 ────────────────────────────
function Wait-PortReady {
    param([int]$TimeoutSec = 60)
    Write-Host "[SUNO] 等待 localhost:$SVC_PORT 就緒..."
    $elapsed = 0
    while ($elapsed -lt $TimeoutSec) {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:$SVC_PORT" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
            Write-Host "[SUNO] 服務就緒！HTTP $($resp.StatusCode)"
            return $true
        } catch {
            Start-Sleep -Seconds 3
            $elapsed += 3
        }
    }
    Write-Host "[WARN] Port $SVC_PORT 在 $TimeoutSec 秒內未回應，請手動確認容器日誌。"
    return $false
}

# ── 主流程 ─────────────────────────────────────────────────
Wait-DockerReady

if (Get-SunoContainerState) {
    Write-Host "[SUNO] suno-api container 已在執行中，跳過啟動。"
} else {
    Write-Host "[SUNO] 啟動 suno-api container（detached 模式）..."
    Push-Location $COMPOSE_DIR
    docker compose up --build -d
    $exitCode = $LASTEXITCODE
    Pop-Location

    if ($exitCode -ne 0) {
        Write-Host "[ERROR] docker compose up 失敗（exit=$exitCode），中止。"
        exit 1
    }
    Write-Host "[SUNO] Container 已啟動。"
}

Wait-PortReady -TimeoutSec 90
Write-Host "[OK] suno-api 就緒：http://localhost:$SVC_PORT"
exit 0
