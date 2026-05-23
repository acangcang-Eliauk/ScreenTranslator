# ScreenTranslator - 屏幕翻译工具

Windows 10 屏幕截图翻译工具，基于 Qwen3-VL-Plus 视觉大模型。

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

## 安装与运行

```bash
pip install -r requirements.txt
python main.py
```

或双击 `run.bat`（自动请求管理员权限，游戏全屏下必需）。

## 设置

`Ctrl+F8` 打开设置面板，可配置：
- **API Key** — Qwen API 密钥
- **模型名称** — 默认为 `qwen3-vl-plus`
- **API 地址** — DashScope API 端点
- **系统提示词** — 指导模型输出格式的提示词

修改后点击"保存"，立即生效，无需重启。配置持久化至 `config.json`。

## 依赖

- Python 3.10+
- `mss` — 高速屏幕截图
- `Pillow` — 图像处理
- `requests` — HTTP 请求
- `pystray` — 系统托盘图标（可选）

## 设计文档

详细设计报告见 [design_report.md](design_report.md)
