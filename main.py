"""
ScreenTranslator - 屏幕翻译工具
F9: 截图并翻译 | F8: 显示/隐藏翻译悬浮窗
"""
import base64
import ctypes
import io
import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime

import mss
import requests
from PIL import Image

# ============================================================
# 配置 — 持久化存储
# ============================================================
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULTS = {
    "api_key": "",
    "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "model": "qwen3-vl-plus",
    "system_prompt": (
        "你是一个专业的多语言翻译助手。请仔细查看这张截图中的所有文字内容。"
        "你的任务是将图中的所有文字翻译成中文。\n\n"
        "翻译要求：\n"
        "1. 只返回翻译后的纯文本，不要添加任何解释、说明或前缀（如\"翻译结果：\"）\n"
        "2. 保持原文的大致格式和排版逻辑（段落、换行等）\n"
        "3. 如果图中有多个不同位置的文本段落，请在每个段落翻译前单独一行输出\"[方位描述]：\"，"
        "方位描述指该文字在图像中的位置（如\"[左上角]：\"、\"[中间]：\"、\"[右下角]：\"、\"[顶部标题]：\"等），"
        "然后紧接着输出该段落的翻译内容\n"
        "4. 对于表格或列表，保持其行列结构\n"
        "5. 如果遇到无法识别或无法翻译的文字，保留原文并标注\"[未识别]\"\n"
        "6. 对于专业术语和专有名词，优先使用通用的中文翻译，并在可能的情况下保留英文原名在括号内"
    ),
    "hotkey_capture": "F9",
    "hotkey_toggle": "F8",
    "overlay_alpha": 0.88,
    "overlay_width": 520,
    "overlay_height": 450,
    "jpeg_quality": 85,
    "request_timeout": 60,
    "max_retries": 2,
    "cooldown_sec": 0.6,
    "temperature": 0.1,
    "max_tokens": 4096,
}

CONFIG: dict = {}


def load_config():
    """从 config.json 加载，缺失的键用 DEFAULTS 补全"""
    cfg = dict(DEFAULTS)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update(saved)
    except Exception as e:
        print(f"[Config] 加载配置失败: {e}")
    return cfg


def save_config(cfg: dict):
    """仅保存与 DEFAULTS 不同的键（用户修改过的）"""
    try:
        # 只持久化用户可见的四个字段
        keys_to_save = ["api_key", "api_url", "model", "system_prompt"]
        to_save = {k: cfg[k] for k in keys_to_save if k in cfg}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Config] 保存配置失败: {e}")


# 应用启动时加载
CONFIG = load_config()

# ============================================================
# 翻译服务
# ============================================================
class TranslationService:
    """调用 Qwen3-VL-Plus API 进行图像翻译"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {CONFIG['api_key']}",
            "Content-Type": "application/json",
        })

    def translate(self, image_b64: str) -> str | None:
        """发送图片到API并返回翻译文本"""
        payload = {
            "model": CONFIG["model"],
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                    {"type": "text", "text": CONFIG["system_prompt"]},
                ],
            }],
            "temperature": CONFIG["temperature"],
            "max_tokens": CONFIG["max_tokens"],
        }

        last_error = None
        for attempt in range(CONFIG["max_retries"] + 1):
            try:
                resp = self.session.post(
                    CONFIG["api_url"],
                    json=payload,
                    timeout=CONFIG["request_timeout"],
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return content.strip() if isinstance(content, str) else str(content)
                elif resp.status_code == 401:
                    return f"[错误] API Key 无效，请检查配置。\n{resp.text[:300]}"
                elif resp.status_code == 429:
                    if attempt < CONFIG["max_retries"]:
                        time.sleep(2 ** (attempt + 1))
                        continue
                    return "[错误] 请求过于频繁，请稍后再试。"
                elif resp.status_code >= 500:
                    if attempt < CONFIG["max_retries"]:
                        time.sleep(2 ** (attempt + 1))
                        continue
                    return f"[错误] 服务器错误 ({resp.status_code})，请稍后再试。"
                else:
                    return f"[错误] API 返回错误 ({resp.status_code}):\n{resp.text[:300]}"
            except requests.ConnectionError:
                last_error = "无法连接到 API 服务器，请检查网络。"
                if attempt < CONFIG["max_retries"]:
                    time.sleep(2 ** (attempt + 1))
                    continue
            except requests.Timeout:
                last_error = "API 请求超时，请检查网络或稍后再试。"
                if attempt < CONFIG["max_retries"]:
                    time.sleep(2 ** (attempt + 1))
                    continue
            except Exception as e:
                last_error = f"未知错误: {str(e)}"
                if attempt < CONFIG["max_retries"]:
                    time.sleep(2 ** (attempt + 1))
                    continue
        return f"[错误] {last_error}"

# ============================================================
# 截图服务
# ============================================================
class ScreenCapture:
    """全屏截图并编码为 Base64"""

    @staticmethod
    def capture() -> str | None:
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # 0 = 所有显示器的虚拟桌面
                img = sct.grab(monitor)
                pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=CONFIG["jpeg_quality"])
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as e:
            print(f"[ScreenCapture] 截图失败: {e}")
            return None

# ============================================================
# 右上角 Toast 通知
# ============================================================
class ToastNotification:
    """右上角短暂文字提示，自动消失"""

    TOASTS: list["ToastNotification"] = []  # 当前活跃的 toast，用于错开位置

    def __init__(self, message: str, duration_ms: int = 2000, color: str = "#4CAF50"):
        self.root = tk.Toplevel()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg="#1E1E1E")

        # 计算位置（右上角，错开已有的 toast）
        sw = self.root.winfo_screenwidth()
        base_y = 60
        offset = len(ToastNotification.TOASTS) * 52
        x = sw - 320
        y = base_y + offset

        self.root.geometry(f"300x40+{x}+{y}")

        # 内部容器
        inner = tk.Frame(self.root, bg="#2D2D30", padx=0, pady=0)
        inner.pack(fill=tk.BOTH, expand=True)

        # 左侧色条
        bar = tk.Frame(inner, bg=color, width=4)
        bar.pack(side=tk.LEFT, fill=tk.Y)

        # 文字
        lbl = tk.Label(
            inner, text=f"  {message}", fg="#E8E8E8", bg="#2D2D30",
            font=("Microsoft YaHei UI", 10), anchor=tk.W,
        )
        lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        # Win32 置顶
        try:
            force_window_topmost(self.root)
        except Exception:
            pass

        ToastNotification.TOASTS.append(self)

        # 自动消失
        self.root.after(duration_ms, self.dismiss)

    def dismiss(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        if self in ToastNotification.TOASTS:
            ToastNotification.TOASTS.remove(self)
        self._reposition_others()

    @classmethod
    def _reposition_others(cls):
        for i, toast in enumerate(cls.TOASTS):
            try:
                sw = toast.root.winfo_screenwidth()
                base_y = 60
                y = base_y + i * 52
                x = sw - 320
                toast.root.geometry(f"+{x}+{y}")
            except Exception:
                pass

# ============================================================
# Win32 窗口工具
# ============================================================
# 常量
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_ASYNCWINDOWPOS = 0x4000
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080


def _get_hwnd(tk_widget) -> int:
    """获取 tkinter 控件对应的原生 Win32 窗口句柄"""
    frame = tk_widget.winfo_id()
    # tkinter 的 winfo_id() 返回的是客户区句柄，需要获取顶层窗口句柄
    hwnd = ctypes.windll.user32.GetAncestor(frame, 2)  # 2 = GA_ROOT
    return hwnd


def force_window_topmost(tk_widget):
    """使用 Win32 API 强制窗口置顶（对全屏游戏有效）"""
    hwnd = _get_hwnd(tk_widget)

    # 1) 设置扩展样式：TOPMOST + TOOLWINDOW（不在任务栏显示多余图标）
    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ex_style |= WS_EX_TOPMOST
    ex_style |= WS_EX_TOOLWINDOW
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

    # 2) SetWindowPos 强力置顶（不移动/不改变大小/不抢焦点）
    ctypes.windll.user32.SetWindowPos(
        hwnd, HWND_TOPMOST,
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_ASYNCWINDOWPOS,
    )


def restore_window_normal(tk_widget):
    """取消置顶状态"""
    hwnd = _get_hwnd(tk_widget)
    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ex_style &= ~WS_EX_TOPMOST
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
    ctypes.windll.user32.SetWindowPos(
        hwnd, HWND_NOTOPMOST,
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS,
    )


# ============================================================
# 管理员检测
# ============================================================
def is_running_as_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

# ============================================================
# Win32 键盘轮询热键（GetAsyncKeyState — 全屏游戏可用）
# ============================================================
VK_F7 = 0x76
VK_F8 = 0x77
VK_F9 = 0x78
VK_CONTROL = 0x11
VK_Q = 0x51
VK_E = 0x45
KEY_DOWN = 0x8000
THREAD_PRIORITY_HIGHEST = 2


class PollingHotkeyManager:
    """独立线程轮询 GetAsyncKeyState，不受 tkinter 主循环影响"""

    def __init__(self, tk_root: tk.Tk):
        self._root = tk_root
        self._bindings: list[tuple[int, int, callable, str]] = []
        self._prev_state: dict[str, bool] = {}
        self._debounce: dict[str, float] = {}
        self._running = False
        self._thread: threading.Thread | None = None

    def register(self, vk_code: int, modifier_vk: int, callback, name: str):
        """注册一个组合键：modifier_vk=0 表示无需修饰键"""
        self._bindings.append((vk_code, modifier_vk, callback, name))

    def start(self, interval_ms: int = 50):
        """启动独立轮询线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, args=(interval_ms / 1000.0,), daemon=True)
        self._thread.start()

    def stop(self):
        """停止轮询线程"""
        self._running = False

    def _poll_loop(self, interval_sec: float):
        """在独立线程中循环轮询，不受主线程阻塞影响"""
        # 提升线程优先级，确保游戏运行时仍能按时调度
        try:
            ctypes.windll.kernel32.SetThreadPriority(
                ctypes.windll.kernel32.GetCurrentThread(), THREAD_PRIORITY_HIGHEST,
            )
        except Exception:
            pass

        while self._running:
            try:
                for vk, mod_vk, callback, name in self._bindings:
                    key_down = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & KEY_DOWN)
                    if mod_vk != 0:
                        mod_ok = bool(ctypes.windll.user32.GetAsyncKeyState(mod_vk) & KEY_DOWN)
                    else:
                        # 纯按键：确保 Ctrl 未按下，防止 Ctrl+F8 误触发 F8
                        mod_ok = not bool(ctypes.windll.user32.GetAsyncKeyState(VK_CONTROL) & KEY_DOWN)

                    triggered = key_down and mod_ok
                    prev = self._prev_state.get(name, False)

                    if triggered and not prev:
                        now = time.time()
                        last = self._debounce.get(name, 0)
                        if now - last >= 0.35:
                            self._debounce[name] = now
                            cb = callback  # 捕获引用
                            self._root.after(0, cb)

                    self._prev_state[name] = triggered
            except Exception:
                pass

            time.sleep(interval_sec)


# ============================================================
# 悬浮窗
# ============================================================
class OverlayWindow:
    """半透明悬浮翻译窗口 — 使用 Win32 API 强力置顶"""

    def __init__(self):
        self.root = tk.Toplevel()
        self.root.withdraw()
        self._topmost_timer_id: str | None = None
        self._flashing = False

        # 基本窗口属性
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", CONFIG["overlay_alpha"])
        self.root.configure(bg="#2D2D30")

        # 默认位置（屏幕右上角）
        sw = self.root.winfo_screenwidth()
        x = sw - CONFIG["overlay_width"] - 40
        y = 60
        self.root.geometry(
            f"{CONFIG['overlay_width']}x{CONFIG['overlay_height']}+{x}+{y}"
        )

        # 窗口创建后立即应用 Win32 样式
        self.root.after(100, lambda: self._apply_win32_style())

        self._build_ui()
        self._bind_events()

    def _apply_win32_style(self):
        """应用 Win32 扩展样式（窗口创建后调用）"""
        try:
            force_window_topmost(self.root)
        except Exception:
            pass

    def _build_ui(self):
        # 标题栏
        self.title_bar = tk.Frame(self.root, bg="#1E1E1E", height=32, cursor="fleur")
        self.title_bar.pack(fill=tk.X, side=tk.TOP)
        self.title_bar.pack_propagate(False)

        close_btn = tk.Label(
            self.title_bar, text="✕", fg="#CCCCCC", bg="#1E1E1E",
            font=("Microsoft YaHei UI", 11), cursor="hand2", padx=10,
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self.hide())

        title_lbl = tk.Label(
            self.title_bar, text="  屏幕翻译 · Screen Translator",
            fg="#AAAAAA", bg="#1E1E1E", font=("Microsoft YaHei UI", 9),
        )
        title_lbl.pack(side=tk.LEFT)

        # 文本区域
        text_frame = tk.Frame(self.root, bg="#2D2D30")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        self.text_widget = tk.Text(
            text_frame,
            bg="#2D2D30",
            fg="#E8E8E8",
            insertbackground="#FFFFFF",
            selectbackground="#007ACC",
            selectforeground="#FFFFFF",
            font=("Microsoft YaHei UI", 11),
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            padx=14,
            pady=14,
            spacing2=4,
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True)

        # 初始欢迎文本
        self.text_widget.insert(
            "1.0",
            "欢迎使用屏幕翻译工具\n\n"
            "按 F9 截图并翻译当前屏幕内容\n"
            "按 F8 显示或隐藏此翻译窗口\n"
            "按 Ctrl+F8 显示或隐藏设置窗口\n"
            "按 Q / E 上下滚动翻译文本\n\n"
            "翻译结果将显示在这里...",
        )

        # 状态栏
        self.status_bar = tk.Frame(self.root, bg="#252526", height=24)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_bar.pack_propagate(False)

        self.status_label = tk.Label(
            self.status_bar, text="就绪", fg="#888888", bg="#252526",
            font=("Microsoft YaHei UI", 8), anchor=tk.W,
        )
        self.status_label.pack(fill=tk.X, padx=10)

        # 底部调整大小手柄
        self.resize_handle = tk.Frame(self.root, bg="#1E1E1E", height=4, cursor="size_ns")
        self.resize_handle.pack(fill=tk.X, side=tk.BOTTOM)

    def _bind_events(self):
        self.title_bar.bind("<Button-1>", self._drag_start)
        self.title_bar.bind("<B1-Motion>", self._drag_move)
        self._drag_data = {"x": 0, "y": 0}

        self.text_widget.bind("<MouseWheel>", self._on_mousewheel)
        self.root.bind("<Escape>", lambda e: self.hide())

        self.resize_handle.bind("<Button-1>", self._resize_start)
        self.resize_handle.bind("<B1-Motion>", self._resize_move)
        self._resize_data = {"y": 0, "h": 0}

        self.root.bind("<FocusIn>", lambda e: self.root.attributes("-alpha", 0.96))
        self.root.bind("<FocusOut>", lambda e: self.root.attributes("-alpha", CONFIG["overlay_alpha"]))

    def _drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _drag_move(self, event):
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    def _resize_start(self, event):
        self._resize_data["y"] = event.y_root
        self._resize_data["h"] = self.root.winfo_height()

    def _resize_move(self, event):
        dy = event.y_root - self._resize_data["y"]
        new_h = max(200, self._resize_data["h"] + dy)
        self.root.geometry(f"{CONFIG['overlay_width']}x{new_h}")

    def _on_mousewheel(self, event):
        self.text_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ---------- 置顶定时器 ----------

    def _start_topmost_timer(self):
        """每 400ms 重新断言置顶，对抗全屏游戏的持续渲染"""
        if self._topmost_timer_id is not None:
            return
        def _tick():
            if self.root.state() == "normal":
                try:
                    force_window_topmost(self.root)
                except Exception:
                    pass
                self._topmost_timer_id = self.root.after(400, _tick)
            else:
                self._topmost_timer_id = None
        self._topmost_timer_id = self.root.after(400, _tick)

    def _stop_topmost_timer(self):
        if self._topmost_timer_id is not None:
            self.root.after_cancel(self._topmost_timer_id)
            self._topmost_timer_id = None

    # ---------- 公开接口 ----------

    def show(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
        self.root.after(50, lambda: force_window_topmost(self.root))
        self.root.after(200, lambda: force_window_topmost(self.root))
        self.root.lift()
        # 启动定时置顶
        self._start_topmost_timer()

    def hide(self):
        self._stop_topmost_timer()
        restore_window_normal(self.root)
        self.root.withdraw()

    def toggle(self):
        if self.root.state() == "normal":
            self.hide()
        else:
            self.show()

    def set_text(self, text: str):
        self.root.after(0, self._update_text, text)

    def _update_text(self, text: str):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert("1.0", text)
        self.text_widget.config(state=tk.NORMAL)
        self.status_label.config(
            text=f"翻译完成 · {datetime.now().strftime('%H:%M:%S')}"
        )

# ============================================================
# 系统托盘
# ============================================================
def create_tray_icon(on_exit, on_show):
    """创建系统托盘图标"""
    try:
        import pystray

        # 生成简单图标 (16x16 蓝色方形)
        icon_img = Image.new("RGB", (32, 32), "#0078D4")
        # 画一个简单的 "T" 字
        from PIL import ImageDraw
        draw = ImageDraw.Draw(icon_img)
        draw.text((8, 6), "T", fill="#FFFFFF")

        menu = pystray.Menu(
            pystray.MenuItem("显示/隐藏翻译窗口", lambda: on_show()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda: on_exit()),
        )

        tray = pystray.Icon(
            "ScreenTranslator",
            icon_img,
            "屏幕翻译工具",
            menu,
        )
        return tray
    except ImportError:
        return None

# ============================================================
# 设置窗口
# ============================================================
class SettingsWindow:
    """Ctrl+F8 打开的设置面板 — 与翻译悬浮窗一致风格"""

    def __init__(self, on_save_callback):
        self.on_save = on_save_callback
        self.root = tk.Toplevel()
        self.root.withdraw()

        # ---- 与 OverlayWindow 一致的无边框半透明风格 ----
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg="#2D2D30")

        # 居中
        w, h = 520, 520
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # Win32 强力置顶
        self.root.after(100, lambda: force_window_topmost(self.root))

        self._build_ui()
        self._load_values()
        self.root.bind("<Escape>", lambda e: self.hide())

    def _build_ui(self):
        # ---- 可拖拽标题栏（与 OverlayWindow 一致） ----
        title_bar = tk.Frame(self.root, bg="#1E1E1E", height=32, cursor="fleur")
        title_bar.pack(fill=tk.X, side=tk.TOP)
        title_bar.pack_propagate(False)

        close_btn = tk.Label(
            title_bar, text="✕", fg="#CCCCCC", bg="#1E1E1E",
            font=("Microsoft YaHei UI", 11), cursor="hand2", padx=10,
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self.hide())

        tk.Label(
            title_bar, text="  设置 · Settings",
            fg="#AAAAAA", bg="#1E1E1E", font=("Microsoft YaHei UI", 9),
        ).pack(side=tk.LEFT)

        # 拖拽事件
        title_bar.bind("<Button-1>", self._drag_start)
        title_bar.bind("<B1-Motion>", self._drag_move)
        self._drag_data = {"x": 0, "y": 0}

        # ---- 内容区 ----
        content = tk.Frame(self.root, bg="#2D2D30", padx=16, pady=6)
        content.pack(fill=tk.BOTH, expand=True)

        fields = [
            ("API Key", "api_key"),
            ("模型名称", "model"),
            ("API 地址", "api_url"),
        ]
        self._entries: dict[str, tk.Widget] = {}

        for label, key in fields:
            tk.Label(content, text=label, fg="#AAAAAA", bg="#2D2D30",
                     font=("Microsoft YaHei UI", 10), anchor=tk.W,
            ).pack(fill=tk.X, pady=(10, 2))

            entry = tk.Entry(
                content, bg="#3E3E42", fg="#E8E8E8",
                insertbackground="#FFFFFF",
                font=("Consolas", 10),
                relief=tk.FLAT,
                highlightthickness=1,
                highlightbackground="#555555",
                highlightcolor="#007ACC",
            )
            if key == "api_key":
                entry.config(show="*")
            entry.pack(fill=tk.X, ipady=4)
            self._entries[key] = entry

        # ---- 系统提示词 ----
        tk.Label(content, text="系统提示词", fg="#AAAAAA", bg="#2D2D30",
                 font=("Microsoft YaHei UI", 10), anchor=tk.W,
        ).pack(fill=tk.X, pady=(12, 2))

        prompt_frame = tk.Frame(content, bg="#3E3E42",
                                highlightthickness=1, highlightbackground="#555555")
        prompt_frame.pack(fill=tk.BOTH, expand=True)

        prompt_text = tk.Text(
            prompt_frame, bg="#2D2D30", fg="#E8E8E8",
            insertbackground="#FFFFFF",
            font=("Microsoft YaHei UI", 9),
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            height=5,
            padx=8,
            pady=6,
        )
        prompt_text.pack(fill=tk.BOTH, expand=True)
        self._entries["system_prompt"] = prompt_text

        # ---- 按钮区 ----
        btn_frame = tk.Frame(self.root, bg="#252526", padx=16, pady=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        restore_btn = tk.Label(
            btn_frame, text="  恢复默认  ", fg="#CCCCCC", bg="#3E3E42",
            font=("Microsoft YaHei UI", 10), cursor="hand2",
            padx=14, pady=5,
        )
        restore_btn.pack(side=tk.LEFT)
        restore_btn.bind("<Button-1>", lambda e: self._restore_defaults())
        restore_btn.bind("<Enter>", lambda e: restore_btn.config(bg="#555555"))
        restore_btn.bind("<Leave>", lambda e: restore_btn.config(bg="#3E3E42"))

        save_btn = tk.Label(
            btn_frame, text="  保存  ", fg="#FFFFFF", bg="#0078D4",
            font=("Microsoft YaHei UI", 10, "bold"), cursor="hand2",
            padx=22, pady=5,
        )
        save_btn.pack(side=tk.RIGHT)
        save_btn.bind("<Button-1>", lambda e: self._save())
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg="#1E8AE8"))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg="#0078D4"))

    def _drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _drag_move(self, event):
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    def _load_values(self):
        for key, widget in self._entries.items():
            val = CONFIG.get(key, "")
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
                widget.insert("1.0", val)
                widget.edit_modified(False)
            else:
                widget.delete(0, tk.END)
                widget.insert(0, str(val))

    def _collect_values(self) -> dict:
        result = {}
        for key, widget in self._entries.items():
            if isinstance(widget, tk.Text):
                result[key] = widget.get("1.0", "end-1c")
            else:
                result[key] = widget.get()
        return result

    def _restore_defaults(self):
        for key, widget in self._entries.items():
            val = DEFAULTS.get(key, "")
            if isinstance(widget, tk.Text):
                widget.delete("1.0", tk.END)
                widget.insert("1.0", val)
            else:
                widget.delete(0, tk.END)
                widget.insert(0, str(val))

    def _save(self):
        new_vals = self._collect_values()
        CONFIG.update(new_vals)
        save_config(CONFIG)
        self.on_save()
        self.hide()
        ToastNotification("设置已保存", 2000, "#4CAF50")

    def show(self):
        self._load_values()
        self.root.deiconify()
        self.root.after(50, lambda: force_window_topmost(self.root))
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        self.root.withdraw()

    def toggle(self):
        if self.root.state() == "normal":
            self.hide()
        else:
            self.show()


# ============================================================
# 应用主控
# ============================================================
class App:
    def __init__(self):
        self.translated_text = ""
        self.is_translating = False
        self._lock = threading.Lock()
        self._last_f9_time = 0.0
        self._cancel_event = threading.Event()

        # 初始化 tkinter root（隐藏）
        self.tk_root = tk.Tk()
        self.tk_root.withdraw()
        self.tk_root.title("ScreenTranslator")

        # 轮询式热键管理器（GetAsyncKeyState，全屏游戏可用）
        self._hotkeys = PollingHotkeyManager(self.tk_root)

        # 服务
        self.translation_service = TranslationService()
        self.overlay = OverlayWindow()
        self.settings = SettingsWindow(on_save_callback=self._on_settings_saved)

        # 系统托盘
        self.tray = create_tray_icon(
            on_exit=self.shutdown,
            on_show=self.toggle_overlay,
        )

    def _register_hotkeys(self):
        """PollingHotkeyManager 版热键注册"""
        self._hotkeys.register(VK_F9, 0, self.on_capture, "F9")
        self._hotkeys.register(VK_F8, 0, self.on_toggle, "F8")
        self._hotkeys.register(VK_F7, 0, self.on_cancel, "F7")
        self._hotkeys.register(VK_F8, VK_CONTROL, self.on_settings, "Ctrl+F8")
        self._hotkeys.register(VK_Q, 0, self.on_scroll_up, "Q")
        self._hotkeys.register(VK_E, 0, self.on_scroll_down, "E")

        print("[ScreenTranslator] 启动完成")
        print(f"  F9 = 截图翻译 | F8 = 显示/隐藏翻译窗口 | F7 = 取消翻译 | Ctrl+F8 = 设置 | Q/E = 滚动")
        print(f"  模型: {CONFIG['model']}")

        if is_running_as_admin():
            self.tk_root.after(800, lambda: ToastNotification(
                "就绪 · F9 截图 F8 查看 F7 取消 Ctrl+F8 设置", 2000, "#4CAF50"
            ))
        else:
            self.tk_root.after(800, lambda: ToastNotification(
                "未以管理员运行！游戏内可能无效", 4000, "#FF9800"
            ))

    def on_capture(self):
        """F9 回调：截图并翻译"""
        now = time.time()
        if now - self._last_f9_time < CONFIG["cooldown_sec"]:
            return
        self._last_f9_time = now

        if self.is_translating:
            self._show_toast("翻译进行中，请稍候...", 1500, "#FF9800")
            return

        # 重置取消标志
        self._cancel_event.clear()

        # 立即反馈：F9 已被检测到
        self._show_toast("截图中...", 1000, "#2196F3")

        # 在后台线程执行翻译
        threading.Thread(target=self._do_translate, daemon=True).start()

    def on_cancel(self):
        """F7 回调：取消当前翻译"""
        if not self.is_translating:
            self._show_toast("没有正在进行的翻译", 1500, "#888888")
            return
        self._cancel_event.set()
        self._show_toast("正在取消翻译...", 1500, "#FF9800")

    def _show_toast(self, message: str, duration_ms: int = 2000, color: str = "#4CAF50"):
        """主线程安全地弹出 toast 通知"""
        self.tk_root.after(0, lambda: ToastNotification(message, duration_ms, color))

    def _do_translate(self):
        with self._lock:
            self.is_translating = True

        try:
            # 1) 截图
            img_b64 = ScreenCapture.capture()
            if self._cancel_event.is_set():
                self._show_toast("翻译已取消", 2000, "#888888")
                return
            if img_b64 is None:
                self._show_toast("截图失败", 2500, "#F44336")
                self.overlay.set_text("[错误] 截图失败，请重试。")
                return

            self._show_toast("截图成功 · 翻译中...", 1500, "#4CAF50")

            # 2) 调用 API
            result = self.translation_service.translate(img_b64)

            # 3) 检查是否在 API 调用期间被取消
            if self._cancel_event.is_set():
                self._show_toast("翻译已取消", 2000, "#888888")
                return

            if result:
                self.translated_text = result
                self.overlay.set_text(result)
                self._show_toast("翻译完毕 · 按 F8 查看", 2500, "#4CAF50")
            elif result is not None and result.startswith("[错误]"):
                self._show_toast("翻译失败", 3000, "#F44336")
                self.overlay.set_text(result)
            else:
                self._show_toast("API 返回空结果", 3000, "#FF9800")
                self.overlay.set_text("[错误] API 返回空结果")
        except Exception as e:
            if self._cancel_event.is_set():
                self._show_toast("翻译已取消", 2000, "#888888")
            else:
                self._show_toast(f"异常: {str(e)[:30]}", 3000, "#F44336")
                self.overlay.set_text(f"[错误] {str(e)}")
        finally:
            with self._lock:
                self.is_translating = False
            self._cancel_event.clear()

    def on_scroll_up(self):
        """Q 键：翻译文本上滑"""
        if self.overlay.root.state() != "normal":
            return
        self.tk_root.after(0, lambda: self.overlay.text_widget.yview_scroll(-3, "units"))

    def on_scroll_down(self):
        """E 键：翻译文本下滑"""
        if self.overlay.root.state() != "normal":
            return
        self.tk_root.after(0, lambda: self.overlay.text_widget.yview_scroll(3, "units"))

    def on_toggle(self):
        """F8 回调：切换悬浮窗显示"""
        self.tk_root.after(0, self.overlay.toggle)

    def on_settings(self):
        """Ctrl+F8 回调：打开/关闭设置窗口"""
        self.tk_root.after(0, self.settings.toggle)

    def _on_settings_saved(self):
        """设置保存后更新 TranslationService（API Key 等可能已变）"""
        self.translation_service.session.headers.update({
            "Authorization": f"Bearer {CONFIG['api_key']}",
        })

    def toggle_overlay(self):
        self.tk_root.after(0, self.overlay.toggle)

    def _notify(self, title: str, message: str):
        """在悬浮窗状态栏显示消息"""
        self.tk_root.after(0, lambda: self.overlay.status_label.config(
            text=f"{title} · {datetime.now().strftime('%H:%M:%S')}"
        ))

    def shutdown(self):
        """清理并退出"""
        print("[ScreenTranslator] 正在退出...")
        self._hotkeys.stop()
        if self.tray:
            self.tray.stop()
        self.tk_root.destroy()
        os._exit(0)

    def run(self):
        """启动主循环"""
        self._register_hotkeys()
        self._hotkeys.start()
        if self.tray:
            threading.Thread(target=self.tray.run, daemon=True).start()
        self.tk_root.mainloop()

# ============================================================
# 入口
# ============================================================
def main():
    # 隐藏控制台 (仅打包后生效)
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0
        )
    except Exception:
        pass

    app = App()
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()

if __name__ == "__main__":
    main()
