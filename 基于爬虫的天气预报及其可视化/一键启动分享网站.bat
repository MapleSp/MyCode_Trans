@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo 正在启动 ATMOS 智能气象台...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_share.ps1"

echo.
echo 网站已停止。按任意键关闭窗口。
pause >nul
