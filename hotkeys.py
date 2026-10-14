"""全局热键支持：Win32 RegisterHotKey + Qt 原生事件过滤器。

Qt 本身没有全局热键 API，这里直接用 ctypes 调 user32，不引入第三方库。

实现说明：
    不能让 QObject 与 QAbstractNativeEventFilter 多重继承——
    PyQt5 在这种情况下的 nativeEventFilter 回调不会被触发。
    因此这里拆成两层：_Filter 只负责收消息，HotkeyManager 负责注册和发信号。

默认绑定：
    Alt + 1..9        切到第 N 个桌面
    Ctrl + Alt + 1..9 把当前窗口移到第 N 个桌面（人留在原地）
    Alt + `           返回上一个桌面
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PyQt5.QtCore import QAbstractNativeEventFilter, QObject, pyqtSignal

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_DIGIT = {n: 0x30 + n for n in range(1, 10)}  # '1'..'9'
VK_OEM_3 = 0xC0  # 反引号 `


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hWnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class _Filter(QAbstractNativeEventFilter):
    """只做一件事：把 WM_HOTKEY 转交给回调。"""

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt 命名)
        if message is None:
            return False, 0
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
        except (ValueError, OSError):
            return False, 0
        if msg.message == WM_HOTKEY:
            return self._callback(int(msg.wParam))
        return False, 0


class HotkeyManager(QObject):
    """注册/注销全局热键，并把按键翻译成 Qt 信号。"""

    switch = pyqtSignal(int)       # 桌面序号（0 基）
    move_window = pyqtSignal(int)  # 把当前窗口移到该桌面
    goto_prev = pyqtSignal()

    _ID_SWITCH = 100
    _ID_MOVE = 200
    _ID_PREV = 300

    def __init__(self, host_hwnd: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._hwnd = wintypes.HWND(int(host_hwnd))
        self._user32 = ctypes.windll.user32
        self._registered: list[int] = []
        self._filter = _Filter(self._on_hotkey)
        self._filter_installed = False

    # ---------------- 消息处理 ----------------

    def _on_hotkey(self, hid: int):
        # 注册时 id = 基准 + n（n 为 1..9 的自然数），桌面序号是 0 基，所以要减 1
        if self._ID_SWITCH < hid <= self._ID_SWITCH + 9:
            self.switch.emit(hid - self._ID_SWITCH - 1)
        elif self._ID_MOVE < hid <= self._ID_MOVE + 9:
            self.move_window.emit(hid - self._ID_MOVE - 1)
        elif hid == self._ID_PREV:
            self.goto_prev.emit()
        return True, 0  # 已处理，不再向下传递

    # ---------------- 注册 ----------------

    def register_all(self) -> list[str]:
        """注册全部热键，返回注册失败的条目描述（空列表代表全部成功）。"""
        self.unregister_all()
        failed: list[str] = []
        mods = MOD_ALT | MOD_NOREPEAT

        for n in range(1, 10):
            if not self._reg(self._ID_SWITCH + n, mods, VK_DIGIT[n]):
                failed.append(f"Alt+{n}")
        if not self._reg(self._ID_PREV, mods, VK_OEM_3):
            failed.append("Alt+`")
        move_mods = MOD_ALT | MOD_CONTROL | MOD_NOREPEAT
        for n in range(1, 10):
            if not self._reg(self._ID_MOVE + n, move_mods, VK_DIGIT[n]):
                failed.append(f"Ctrl+Alt+{n}")

        if self._registered and not self._filter_installed:
            app = self._app()
            if app is not None:
                app.installNativeEventFilter(self._filter)
                self._filter_installed = True
        return failed

    def _reg(self, hid: int, mods: int, vk: int) -> bool:
        if self._user32.RegisterHotKey(self._hwnd, hid, mods, vk):
            self._registered.append(hid)
            return True
        return False

    def unregister_all(self) -> None:
        for hid in self._registered:
            self._user32.UnregisterHotKey(self._hwnd, hid)
        self._registered.clear()
        if self._filter_installed:
            app = self._app()
            if app is not None:
                app.removeNativeEventFilter(self._filter)
            self._filter_installed = False

    @staticmethod
    def _app():
        from PyQt5.QtWidgets import QApplication

        return QApplication.instance()
