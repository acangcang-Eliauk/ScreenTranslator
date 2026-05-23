@echo off
chcp 65001 >nul
title 屏幕翻译工具 ScreenTranslator

REM 检查管理员权限，如果没有则自动提权
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 正在请求管理员权限...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ========================================
echo   屏幕翻译工具 ScreenTranslator
echo ========================================
echo.
echo   F9 = 截图并翻译
echo   F8 = 显示/隐藏翻译悬浮窗
echo   F7 = 取消正在进行的翻译
echo   Ctrl+F8 = 打开设置面板
echo.
echo   已以管理员身份运行
echo   如需退出，右键点击系统托盘图标选择"退出"
echo ========================================
echo.

"C:\Users\Admin\AppData\Local\Python\bin\python.exe" "%~dp0main.py"

pause
