$ErrorActionPreference = "Stop"

# 切换到项目目录，避免从其他位置启动时找不到模板和城市数据。
$projectRoot = $PSScriptRoot
if (-not $projectRoot) {
    $projectRoot = (Get-Location).Path
}
Set-Location $projectRoot

$env:WEATHER_HOST = "0.0.0.0"
$env:WEATHER_PORT = "5000"

Write-Host ""
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host "  ATMOS Weather Station - LAN Share Mode" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor DarkGray
Write-Host "Keep this window open while the site is running." -ForegroundColor Yellow
Write-Host "Allow Python on private networks if Windows Firewall asks." -ForegroundColor Yellow
Write-Host ""
Write-Host "Starting website..." -ForegroundColor Cyan
Write-Host ""

python app.py
