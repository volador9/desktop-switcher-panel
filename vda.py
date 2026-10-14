"""VirtualDesktopAccessor.dll 的 ctypes 封装。

只依赖标准库。DLL 通过 Windows 未公开的 COM 接口实现，
因此可以「一键直达」任意桌面、跨桌面搬运窗口，且不带切换动画
（系统原生的 Win+Ctrl+→ 只能逐个切、并且有动画延迟）。

DLL 由 Lej77 fork 维护（MIT），要求 Windows 11 24H2 26100.2605 及以上。
所有导出函数出错时返回 -1。
"""

from __future__ import annotations

import ctypes
import os
import sys

DLL_NAME = "VirtualDesktopAccessor.dll"


def dll_path() -> str:
    """定位 DLL：兼容源码运行与 PyInstaller 打包后运行。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, DLL_NAME)


class VirtualDesktopError(RuntimeError):
    pass


class VirtualDesktop:
    """虚拟桌面的读写门面。"""

    def __init__(self, path: str | None = None) -> None:
        target = path or dll_path()
        if not os.path.exists(target):
            raise VirtualDesktopError(f"找不到 {DLL_NAME}：{target}")
        try:
            self._dll = ctypes.CDLL(target)
        except OSError as exc:  # 极少数情况下被杀软拦截
            raise VirtualDesktopError(f"加载 {DLL_NAME} 失败：{exc}") from exc
        self._declare()

    def _declare(self) -> None:
        d = self._dll
        i32, hwnd = ctypes.c_int, ctypes.c_void_p

        d.GetDesktopCount.restype = i32
        d.GetCurrentDesktopNumber.restype = i32

        d.GoToDesktopNumber.argtypes = [i32]
        d.GoToDesktopNumber.restype = i32
        d.GoToDesktopNumberWithAnimation.argtypes = [i32]
        d.GoToDesktopNumberWithAnimation.restype = i32

        d.GetWindowDesktopNumber.argtypes = [hwnd]
        d.GetWindowDesktopNumber.restype = i32
        d.MoveWindowToDesktopNumber.argtypes = [hwnd, i32]
        d.MoveWindowToDesktopNumber.restype = i32
        d.IsWindowOnCurrentVirtualDesktop.argtypes = [hwnd]
        d.IsWindowOnCurrentVirtualDesktop.restype = i32

        d.CreateDesktop.restype = i32
        d.RemoveDesktop.argtypes = [i32, i32]
        d.RemoveDesktop.restype = i32
        d.MoveDesktop.argtypes = [i32, i32]
        d.MoveDesktop.restype = i32

        d.GetDesktopName.argtypes = [i32, ctypes.c_char_p, ctypes.c_size_t]
        d.GetDesktopName.restype = i32
        d.SetDesktopName.argtypes = [i32, ctypes.c_char_p]
        d.SetDesktopName.restype = i32

    # ---------- 读 ----------

    @property
    def count(self) -> int:
        n = self._dll.GetDesktopCount()
        return n if n > 0 else 1

    @property
    def current(self) -> int:
        """当前桌面序号（0 基）。读不到时回退为 0。"""
        n = self._dll.GetCurrentDesktopNumber()
        return n if n >= 0 else 0

    def name(self, index: int) -> str:
        """桌面名称，Windows 11 未命名的桌面返回空串。"""
        buf = ctypes.create_string_buffer(256)
        if self._dll.GetDesktopName(index, buf, ctypes.sizeof(buf)) < 0:
            return ""
        return buf.value.decode("utf-8", "replace")

    # ---------- 写 ----------

    def go(self, index: int, animate: bool = False) -> bool:
        """跳到指定桌面。animate=True 时使用系统切换动画。"""
        fn = self._dll.GoToDesktopNumberWithAnimation if animate else self._dll.GoToDesktopNumber
        return fn(index) != -1

    def go_relative(self, delta: int) -> bool:
        """按偏移量前后切换，自动在首尾之间环绕。"""
        total = self.count
        if total < 2:
            return False
        return self.go((self.current + delta) % total)

    def move_window(self, hwnd: int, index: int) -> bool:
        if not hwnd:
            return False
        return self._dll.MoveWindowToDesktopNumber(hwnd, index) != -1

    def window_desktop(self, hwnd: int) -> int:
        if not hwnd:
            return -1
        return self._dll.GetWindowDesktopNumber(hwnd)

    def create(self) -> bool:
        return self._dll.CreateDesktop() != -1

    def remove(self, index: int, fallback: int | None = None) -> bool:
        """删除桌面，其上的窗口会被移到 fallback（默认相邻桌面）。"""
        if self.count <= 1:
            return False
        if fallback is None:
            fallback = index - 1 if index > 0 else 1
        return self._dll.RemoveDesktop(index, fallback) != -1

    def rename(self, index: int, title: str) -> bool:
        return self._dll.SetDesktopName(index, title.encode("utf-8")) != -1


def foreground_window() -> int:
    """取当前前台窗口句柄（用于「把当前窗口移到别的桌面」）。"""
    return int(ctypes.windll.user32.GetForegroundWindow())
