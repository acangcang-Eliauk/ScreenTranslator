@echo off
title 安装 ScreenTrans
echo === 安装 ScreenTrans 屏幕翻译工具 ===
echo.
echo 需要管理员权限以创建快捷方式。
echo.

REM 请求管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

REM 运行安装脚本
powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
