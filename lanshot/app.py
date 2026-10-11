from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import queue
import subprocess
import threading
import tkinter as tk
import webbrowser
import winreg
from pathlib import Path
from tkinter import messagebox

import pystray
import qrcode
from PIL import Image, ImageDraw, ImageGrab, ImageTk

from .capture import copy_image_to_clipboard
from .config import APP_NAME, Settings, app_data_dir, startup_command
from .server import MobileServer
from .store import ScreenshotStore

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0xA771
ERROR_ALREADY_EXISTS = 183
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]


def create_icon(size: int = 256) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size * 0.08
    radius = int(size * 0.22)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill="#6574ff",
    )
    draw.rounded_rectangle(
        (size * 0.25, size * 0.31, size * 0.75, size * 0.69),
        radius=int(size * 0.06),
        outline="white",
        width=max(3, int(size * 0.055)),
    )
    draw.ellipse(
        (size * 0.43, size * 0.40, size * 0.57, size * 0.58),
        fill="white",
    )
    draw.rounded_rectangle(
        (size * 0.38, size * 0.245, size * 0.62, size * 0.36),
        radius=int(size * 0.035),
        fill="white",
    )
    return image


class HotkeyListener:
    def __init__(self, callback, on_error) -> None:
        self.callback = callback
        self.on_error = on_error
        self.thread: threading.Thread | None = None
        self.thread_id: int | None = None
        self.ready = threading.Event()
        self.registered = False

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="LanShotHotkey", daemon=True)
        self.thread.start()
        self.ready.wait(timeout=2)

    def _run(self) -> None:
        self.thread_id = kernel32.GetCurrentThreadId()
        self.registered = bool(
            user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("A"))
        )
        self.ready.set()
        if not self.registered:
            self.on_error()
            return
        message = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                self.callback()
        user32.UnregisterHotKey(None, HOTKEY_ID)

    def stop(self) -> None:
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)


class PairingWindow:
    def __init__(self, root: tk.Tk, url: str) -> None:
        self.root = root
        self.url = url
        self.window: tk.Toplevel | None = None
        self.qr_photo: ImageTk.PhotoImage | None = None

    def show(self) -> None:
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
            return
        window = tk.Toplevel(self.root)
        self.window = window
        window.title("LanShot 手机配对")
        window.resizable(False, False)
        window.configure(bg="#11141c")
        window.protocol("WM_DELETE_WINDOW", self.close)
        try:
            window.iconphoto(True, ImageTk.PhotoImage(create_icon(64)))
        except tk.TclError:
            pass

        frame = tk.Frame(window, bg="#11141c", padx=28, pady=24)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text="手机扫码接收截图",
            bg="#11141c",
            fg="#f5f7fb",
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack()
        tk.Label(
            frame,
            text="确保手机和电脑连接同一个 Wi-Fi",
            bg="#11141c",
            fg="#98a2b3",
            font=("Microsoft YaHei UI", 10),
        ).pack(pady=(5, 16))

        qr = qrcode.QRCode(version=None, box_size=7, border=3)
        qr.add_data(self.url)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="#11141c", back_color="white").convert("RGB")
        self.qr_photo = ImageTk.PhotoImage(qr_image)
        tk.Label(frame, image=self.qr_photo, bg="white", bd=0).pack()

        url_box = tk.Entry(
            frame,
            width=46,
            relief="flat",
            readonlybackground="#222735",
            fg="#d6d9e0",
            font=("Segoe UI", 9),
            justify="center",
        )
        url_box.insert(0, self.url)
        url_box.configure(state="readonly")
        url_box.pack(fill="x", pady=(16, 12), ipady=7)

        buttons = tk.Frame(frame, bg="#11141c")
        buttons.pack(fill="x")
        tk.Button(
            buttons,
            text="复制地址",
            command=self._copy,
            bg="#6574ff",
            fg="white",
            activebackground="#7683ff",
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=7,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))
        tk.Button(
            buttons,
            text="在电脑预览",
            command=lambda: webbrowser.open(self.url),
            bg="#292f3d",
            fg="white",
            activebackground="#353d4f",
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=7,
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left", expand=True, fill="x", padx=(5, 0))

        window.update_idletasks()
        x = max(0, (window.winfo_screenwidth() - window.winfo_width()) // 2)
        y = max(0, (window.winfo_screenheight() - window.winfo_height()) // 2)
        window.geometry(f"+{x}+{y}")
        window.lift()
        window.focus_force()

    def _copy(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.url)
        self.root.update()
        if self.window:
            self.window.title("已复制配对地址")
            self.root.after(1400, lambda: self.window and self.window.title("LanShot 手机配对"))

    def close(self) -> None:
        if self.window:
            self.window.destroy()
        self.window = None
        self.qr_photo = None


class LanShotApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.settings, self.config_path = Settings.load()
        self.data_dir = app_data_dir()
        self.store = ScreenshotStore(self.data_dir / "Screenshots", self.settings.keep_images)
        self.server = MobileServer(self.store, self.settings.token, self.settings.preferred_port)
        self.server.start()
        if self.server.port != self.settings.preferred_port:
            self.settings.preferred_port = self.server.port
            self.settings.save(self.config_path)
        self.ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self.root.after(50, self._drain_ui_queue)
        self.pairing = PairingWindow(root, self.server.url)
        self.exiting = False

        self.tray = pystray.Icon(APP_NAME, create_icon(64), "LanShot · Ctrl+Alt+A")
        self.tray.menu = pystray.Menu(
            pystray.MenuItem("截取整个桌面   Ctrl+Alt+A", self._tray_capture, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("手机配对（二维码）", self._tray_pair),
            pystray.MenuItem("复制配对地址", self._tray_copy_url),
            pystray.MenuItem("打开截图文件夹", self._tray_open_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("开机自动启动", self._tray_toggle_startup, checked=lambda _item: self.startup_enabled()),
            pystray.MenuItem("退出 LanShot", self._tray_exit),
        )
        self.tray.run_detached()

        self.hotkey = HotkeyListener(
            callback=lambda: self._on_ui(self.begin_capture),
            on_error=lambda: self._on_ui(self._hotkey_error),
        )
        self.hotkey.start()
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
        self.root.after(450, self._first_run)

    def _on_ui(self, callback) -> None:
        if not self.exiting:
            self.ui_queue.put(callback)

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                callback = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as exc:
                messagebox.showerror("LanShot", f"操作失败：\n{exc}")
        if not self.exiting:
            self.root.after(50, self._drain_ui_queue)

    def _first_run(self) -> None:
        if self.settings.first_run:
            self.settings.first_run = False
            self.settings.save(self.config_path)
            self.pairing.show()
            self.notify("已在右下角托盘运行", "手机扫码配对后，按 Ctrl+Alt+A 即可发送截图。")

    def begin_capture(self) -> None:
        if self.exiting:
            return
        try:
            image = ImageGrab.grab(all_screens=True)
            record = self.store.publish(image)
            clipboard_note = ""
            try:
                copy_image_to_clipboard(image)
                clipboard_note = "，并已复制到剪贴板"
            except OSError:
                pass
            self.notify("整个桌面已发送到手机", f"{record.width} × {record.height}{clipboard_note}")
        except Exception as exc:
            messagebox.showerror("LanShot", f"截取整个桌面失败：\n{exc}")

    def notify(self, title: str, message: str) -> None:
        try:
            self.tray.notify(message, title)
        except Exception:
            pass

    def _hotkey_error(self) -> None:
        self.notify("快捷键被占用", "Ctrl+Alt+A 已被其他软件占用，请用托盘菜单截图。")

    def _tray_capture(self, _icon=None, _item=None) -> None:
        self._on_ui(self.begin_capture)

    def _tray_pair(self, _icon=None, _item=None) -> None:
        self._on_ui(self.pairing.show)

    def _tray_copy_url(self, _icon=None, _item=None) -> None:
        def copy() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.server.url)
            self.root.update()
            self.notify("配对地址已复制", "请发送到手机浏览器打开。")
        self._on_ui(copy)

    def _tray_open_folder(self, _icon=None, _item=None) -> None:
        self.store.directory.mkdir(parents=True, exist_ok=True)
        os.startfile(self.store.directory)

    @staticmethod
    def startup_enabled() -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
        except OSError:
            return False

    def _tray_toggle_startup(self, _icon=None, _item=None) -> None:
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                if self.startup_enabled():
                    winreg.DeleteValue(key, APP_NAME)
                    state = "已关闭开机自动启动"
                else:
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
                    state = "已开启开机自动启动"
            self.notify("LanShot", state)
            self.tray.update_menu()
        except OSError as exc:
            self._on_ui(lambda: messagebox.showerror("LanShot", f"修改开机启动失败：\n{exc}"))

    def _tray_exit(self, _icon=None, _item=None) -> None:
        self._on_ui(self.shutdown)

    def shutdown(self) -> None:
        if self.exiting:
            return
        self.exiting = True
        self.hotkey.stop()
        self.server.stop()
        try:
            self.tray.stop()
        finally:
            self.root.quit()
            self.root.destroy()


def acquire_single_instance() -> int | None:
    handle = kernel32.CreateMutexW(None, False, "Local\\LanShot-{B76910DA-1377-4EBD-8848-54856D39AC0D}")
    if not handle or kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        if handle:
            kernel32.CloseHandle(handle)
        return None
    return int(handle)


def run() -> int:
    mutex = acquire_single_instance()
    if mutex is None:
        user32.MessageBoxW(None, "LanShot 已经在右下角托盘运行。", "LanShot", 0x40)
        return 0
    root = tk.Tk()
    try:
        LanShotApp(root)
        root.mainloop()
    except OSError as exc:
        messagebox.showerror("LanShot 启动失败", f"手机接收服务无法启动：\n{exc}")
        return 1
    finally:
        kernel32.CloseHandle(mutex)
    return 0



