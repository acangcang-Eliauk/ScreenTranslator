# ScreenTrans 安装脚本
# 以管理员身份运行此脚本
param([switch]$Silent)

$ErrorActionPreference = "Stop"
$AppName = "ScreenTrans"
$AppDir = "$env:LOCALAPPDATA\Programs\$AppName"
$ExeName = "ScreenTrans.exe"
$IconName = "icon.ico"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---- 1. 复制文件 ----
Write-Host "=== 安装 ScreenTrans ===" -ForegroundColor Cyan
Write-Host "  目标: $AppDir"
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
Copy-Item "$ScriptDir\$ExeName" "$AppDir\$ExeName" -Force
Copy-Item "$ScriptDir\$IconName" "$AppDir\$IconName" -Force -ErrorAction SilentlyContinue

# ---- 2. 开始菜单快捷方式 ----
$StartMenu = [Environment]::GetFolderPath("Programs")
$ShortcutPath = "$StartMenu\$AppName.lnk"
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$AppDir\$ExeName"
$Shortcut.WorkingDirectory = $AppDir
$Shortcut.Description = "屏幕翻译工具 - 基于 Qwen3-VL-Plus"
if (Test-Path "$AppDir\$IconName") {
    $Shortcut.IconLocation = "$AppDir\$IconName,0"
}
$Shortcut.Save()
Write-Host "  [OK] 开始菜单快捷方式" -ForegroundColor Green

# ---- 3. 桌面快捷方式 ----
$Desktop = [Environment]::GetFolderPath("Desktop")
$DesktopShortcut = "$Desktop\$AppName.lnk"
$DShortcut = $WScriptShell.CreateShortcut($DesktopShortcut)
$DShortcut.TargetPath = "$AppDir\$ExeName"
$DShortcut.WorkingDirectory = $AppDir
$DShortcut.Description = "屏幕翻译工具 - 基于 Qwen3-VL-Plus"
if (Test-Path "$AppDir\$IconName") {
    $DShortcut.IconLocation = "$AppDir\$IconName,0"
}
$DShortcut.Save()
Write-Host "  [OK] 桌面快捷方式" -ForegroundColor Green

# ---- 4. 注册表卸载信息 ----
$UninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
New-Item -Path $UninstallKey -Force | Out-Null
Set-ItemProperty -Path $UninstallKey -Name "DisplayName" -Value "ScreenTrans 屏幕翻译工具"
Set-ItemProperty -Path $UninstallKey -Name "UninstallString" -Value "powershell -Command `"Remove-Item -Recurse -Force '$AppDir'; Remove-Item -Force '$ShortcutPath','$DesktopShortcut'; Remove-Item -Recurse -Force 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName'; Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name '$AppName' -ErrorAction SilentlyContinue`""
Set-ItemProperty -Path $UninstallKey -Name "DisplayIcon" -Value "$AppDir\$ExeName,0"
Set-ItemProperty -Path $UninstallKey -Name "Publisher" -Value "ScreenTranslator"
Set-ItemProperty -Path $UninstallKey -Name "NoModify" -Value 1 -Type DWord
Set-ItemProperty -Path $UninstallKey -Name "NoRepair" -Value 1 -Type DWord
Write-Host "  [OK] 注册表卸载信息" -ForegroundColor Green

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Cyan
Write-Host "  开始菜单和桌面已创建快捷方式"
Write-Host "  可通过 '设置 > 应用' 卸载"

if (-not $Silent) {
    Write-Host "`n按任意键退出..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
