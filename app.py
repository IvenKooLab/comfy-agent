#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ComfyAgent 桌面壳（产品级入口）：
- WebView2 原生窗口（无边框浏览器感，有系统标题栏/图标）
- 服务在进程内后台线程运行，窗口关闭最小化到托盘
- 托盘菜单：打开 / 退出
- 日志写入 data/app.log
"""
import os
import sys
import threading

# 日志重定向（--noconsole 时没有 stdout）
BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "data", "app.log")


class _Logger:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, s):
        if s.strip():
            from datetime import datetime
            self.f.write(f"[{datetime.now():%H:%M:%S}] {s}\n")

    def flush(self):
        self.f.flush()


sys.stdout = _Logger(LOG_PATH)
sys.stderr = sys.stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as backend  # noqa: E402
import webview            # noqa: E402
import pystray            # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

PORT = int(backend.DEFAULT_SETTINGS["port"])
URL = f"http://127.0.0.1:{PORT}"
_icon = None
_window = None
_app_closing = threading.Event()


def _tray_icon():
    """程序托盘图标：渐变底 + C（与 exe 图标同款意象）。"""
    img = Image.new("RGB", (64, 64), (139, 92, 246))
    d = ImageDraw.Draw(img)
    for y in range(64):
        t = y / 63
        r = int(139 + (34 - 139) * t)
        g = int(92 + (211 - 92) * t)
        b = int(246 + (238 - 246) * t)
        d.line([(0, y), (64, y)], fill=(r, g, b))
    d.ellipse([14, 12, 50, 52], outline=(255, 255, 255), width=4)
    d.line([(30, 22), (44, 32), (30, 42)], fill=(255, 255, 255), width=4, joint="curve")
    return img


def _show_window():
    global _window
    try:
        if _window is not None:
            _window.show()
            return
    except Exception:
        pass
    _window = webview.create_window(
        "ComfyAgent · AI 创作台", URL,
        width=1500, height=940, min_size=(1180, 720),
        background_color="#08090d",
    )


def _on_window_closed():
    # 关窗 = 最小化到托盘（产品行为），除非正在退出
    if _app_closing.is_set():
        threading.Thread(target=_tray_stop_safe, daemon=True).start()


def _tray_stop_safe():
    try:
        if _icon:
            _icon.stop()
    except Exception:
        pass


def _quit(_=None, __=None):
    _app_closing.set()
    _tray_stop_safe()
    os._exit(0)


def _tray_run():
    global _icon
    _icon = pystray.Icon(
        "ComfyAgent", _tray_icon(), "ComfyAgent · AI 创作台",
        menu=pystray.Menu(
            pystray.MenuItem("打开创作台", lambda *_: _show_window(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda *_: _quit()),
        ),
    )
    _icon.run()


def main():
    try:
        httpd = backend.create_server()
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    except OSError:
        # 端口已占用 = 已有实例在跑，直接开窗口连它（单实例产品行为）
        print("* server already running, attaching window")
    threading.Thread(target=_tray_run, daemon=True).start()
    _show_window()
    _window.events.closed += _on_window_closed
    webview.start()


if __name__ == "__main__":
    main()
