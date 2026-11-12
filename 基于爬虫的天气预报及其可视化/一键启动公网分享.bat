@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo 正在启动跨网络分享，请等待 HTTPS 地址出现...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_public_share.ps1"

echo.
echo 公网分享已停止。按任意键关闭窗口。
pause >nul
