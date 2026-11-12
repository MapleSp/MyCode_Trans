$ErrorActionPreference = "Stop"

# 如果网站没有运行，就先在后台启动本地服务。
$projectRoot = $PSScriptRoot
if (-not $projectRoot) {
    $projectRoot = (Get-Location).Path
}
Set-Location $projectRoot

$serverProcess = $null
$serverReady = $false

try {
    $health = Invoke-RestMethod `
        -Uri "http://127.0.0.1:5000/api/health" `
        -TimeoutSec 3
    $serverReady = $health.status -eq "ok"
} catch {
    $serverReady = $false
}

if (-not $serverReady) {
    $env:WEATHER_HOST = "0.0.0.0"
    $env:WEATHER_PORT = "5000"
    Write-Host "Starting the local weather website..." -ForegroundColor Cyan
    $serverProcess = Start-Process `
        -FilePath "python" `
        -ArgumentList "app.py" `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru

    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod `
                -Uri "http://127.0.0.1:5000/api/health" `
                -TimeoutSec 2
            if ($health.status -eq "ok") {
                $serverReady = $true
                break
            }
        } catch {
            # 服务尚未初始化完成，继续等待。
        }
    }
}

if (-not $serverReady) {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
    throw "The local website failed to start on port 5000."
}

Write-Host ""
Write-Host "The public tunnel is starting..." -ForegroundColor Cyan
Write-Host "Share the HTTPS address printed below with your friends." -ForegroundColor Green
Write-Host "Keep this window open. Press Ctrl+C to stop sharing." -ForegroundColor Yellow
Write-Host ""

try {
    # 明确转发到 IPv4，避免 localhost 被解析为 IPv6 后出现 502。
    ssh `
        -o StrictHostKeyChecking=accept-new `
        -o ServerAliveInterval=30 `
        -o ExitOnForwardFailure=yes `
        -R 80:127.0.0.1:5000 `
        nokey@localhost.run
} finally {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
}
