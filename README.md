# ScreenTrans - 屏幕翻译工具

Windows 10 屏幕截图翻译工具，基于 Qwen3-VL-Plus 视觉大模型。

## 安装

1. 下载 `ScreenTrans.exe` 和 `install.ps1` 到同一目录
2. 双击 `install.bat`（自动请求管理员权限）
3. 安装完成后，开始菜单和桌面均有快捷方式

或从源码运行：

```bash
pip install -r requirements.txt
python main.py
```

## 快捷键

| 按键 | 功能 |
|------|------|
| `F9` | 截取全屏并翻译 |
| `F8` | 显示/隐藏半透明翻译悬浮窗 |
| `F7` | 取消正在进行的翻译 |
| `Ctrl+F8` | 打开设置面板 |
| `Q` | 悬浮窗中向上滚动 |
| `E` | 悬浮窗中向下滚动 |
| `Esc` | 关闭悬浮窗/设置面板 |

## 设置

`Ctrl+F8` 打开设置面板，可配置：
- **API Key** — Qwen API 密钥（默认空，需自行填入）
- **模型名称** — 默认为 `qwen3-vl-plus`
- **API 地址** — DashScope API 端点
- **系统提示词** — 指导模型输出格式的提示词
- **开机自启** — 勾选后随 Windows 自动启动

修改后点击"保存"，立即生效，无需重启。

## 打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name ScreenTrans --icon=icon.ico main.py
```

产出 `dist/ScreenTrans.exe`，配合 `install.ps1` 完成安装。

## 设计文档

详细设计报告见 [design_report.md](design_report.md)
