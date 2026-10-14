"""桌面切换面板 —— 程序入口。

用法：
    pythonw main.py       # 正常启动（无控制台窗口）
    python  main.py       # 调试启动（保留控制台输出）

功能一览：
    · 悬浮面板点数字直达任意桌面（无切换动画）
    · 右键数字：移动当前窗口 / 重命名桌面 / 删除桌面
    · 全局热键 Alt+1..9 切换，Ctrl+Alt+1..9 搬运当前窗口，Alt+` 返回上一桌面
    · 托盘菜单：主题、不透明度、紧凑模式、开机自启
"""

from __future__ import annotations

import ctypes
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QWidget,
)

import config
from hotkeys import HotkeyManager
from panel import Panel
from vda import VirtualDesktop, VirtualDesktopError, foreground_window

APP_TITLE = "桌面切换面板"
MUTEX_NAME = r"Local\DesktopSwitcherPanel_SingleInstance"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "DesktopSwitcherPanel"

_mutex_handle = None  # 保持引用，防止互斥体被回收


# ---------------------------------------------------------------- 单实例

def acquire_single_instance() -> bool:
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not _mutex_handle:
        return True
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


# ---------------------------------------------------------------- 开机自启

def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(exe_dir, "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    script = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"))
    return f'"{exe}" "{script}"'


def is_autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- 托盘图标

def make_icon(number: int) -> QIcon:
    px = QPixmap(64, 64)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0A84FF"))
    p.drawRoundedRect(3, 3, 58, 58, 15, 15)
    p.setPen(QColor("#FFFFFF"))
    font = QFont()
    font.setPixelSize(38 if number < 10 else 28)
    font.setBold(True)
    p.setFont(font)
    p.drawText(px.rect(), Qt.AlignCenter, str(number))
    p.end()
    return QIcon(px)


# ---------------------------------------------------------------- 主程序

class App:
    def __init__(self) -> None:
        self.cfg = config.load()

        try:
            self.vd = VirtualDesktop()
        except VirtualDesktopError as exc:
            QMessageBox.critical(None, APP_TITLE, str(exc))
            sys.exit(1)

        self.panel = Panel(self.vd, self.cfg)

        # 隐藏宿主窗口：只为给 RegisterHotKey 提供一个接收 WM_HOTKEY 的句柄
        self._host = QWidget()
        self._host.setWindowFlags(Qt.Tool)
        self._host.resize(1, 1)
        self._host.hide()
        self.hotkeys = HotkeyManager(int(self._host.winId()))

        self.tray = QSystemTrayIcon(make_icon(self.vd.current + 1))
        self.tray.setToolTip(APP_TITLE)

        self._wire()
        self._build_tray_menu()
        self.tray.show()
        self.panel.show()
        self.apply_hotkeys(self.cfg.get("hotkeys", True), report=False)
        self._refresh_tray_icon(self.vd.current)

    # ---------- 信号连接 ----------

    def _wire(self) -> None:
        self.hotkeys.switch.connect(self.panel.goto)
        self.hotkeys.move_window.connect(self._move_foreground)
        self.hotkeys.goto_prev.connect(lambda: self.vd.go_relative(-1))
        self.panel.desktop_changed.connect(self._refresh_tray_icon)
        self.panel.settings_requested.connect(self._popup_menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _move_foreground(self, index: int) -> None:
        hwnd = foreground_window()
        if hwnd:
            self.vd.move_window(hwnd, index)

    def _refresh_tray_icon(self, index: int) -> None:
        self.tray.setIcon(make_icon(index + 1))
        self.tray.setToolTip(f"{APP_TITLE} · 桌面 {index + 1}")

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.panel.setVisible(not self.panel.isVisible())

    # ---------- 托盘菜单 ----------

    def _build_tray_menu(self) -> None:
        menu = QMenu()

        self.act_toggle = QAction("显示 / 隐藏面板", menu)
        self.act_toggle.triggered.connect(lambda: self.panel.setVisible(not self.panel.isVisible()))
        menu.addAction(self.act_toggle)

        self.act_compact = QAction("紧凑模式（悬停展开）", menu, checkable=True)
        self.act_compact.setChecked(bool(self.cfg.get("compact")))
        self.act_compact.toggled.connect(self.panel.set_compact)
        menu.addAction(self.act_compact)

        menu.addAction("面板归位", self.panel.reset_position)

        # 主题
        theme_menu = menu.addMenu("主题")
        group = QActionGroup(theme_menu)
        for label, key in (("深色", "dark"), ("浅色", "light")):
            act = QAction(label, theme_menu, checkable=True)
            act.setChecked(self.cfg.get("theme") == key)
            act.triggered.connect(lambda _=False, k=key: self._set_theme(k))
            group.addAction(act)
            theme_menu.addAction(act)

        # 不透明度
        opacity_menu = menu.addMenu("不透明度")
        for pct in (100, 92, 80, 65, 50):
            act = QAction(f"{pct}%", opacity_menu, checkable=True)
            act.setChecked(abs(float(self.cfg.get("opacity", 0.92)) * 100 - pct) < 1)
            act.triggered.connect(lambda _=False, p=pct: self._set_opacity(p / 100))
            opacity_menu.addAction(act)

        self.act_animate = QAction("使用系统切换动画", menu, checkable=True)
        self.act_animate.setChecked(bool(self.cfg.get("animate")))
        self.act_animate.toggled.connect(lambda v: self.cfg.update({"animate": v}) or config.save(self.cfg))
        menu.addAction(self.act_animate)

        menu.addSeparator()

        self.act_hotkeys = QAction("启用全局热键", menu, checkable=True)
        self.act_hotkeys.setChecked(bool(self.cfg.get("hotkeys")))
        self.act_hotkeys.toggled.connect(self.apply_hotkeys)
        menu.addAction(self.act_hotkeys)

        self.act_autostart = QAction("开机自动启动", menu, checkable=True)
        self.act_autostart.setChecked(is_autostart_enabled())
        self.act_autostart.toggled.connect(self._toggle_autostart)
        menu.addAction(self.act_autostart)

        menu.addSeparator()
        menu.addAction("快捷键说明…", self._show_help)
        menu.addAction("退出", self.quit)

        self._menu = menu
        self.tray.setContextMenu(menu)

    def _popup_menu(self, global_pos) -> None:
        self._menu.popup(global_pos)

    # ---------- 设置项 ----------

    def _set_theme(self, key: str) -> None:
        self.panel._apply_theme(key)
        config.save(self.cfg)

    def _set_opacity(self, value: float) -> None:
        self.panel.set_opacity(value)
        config.save(self.cfg)

    def _toggle_autostart(self, enabled: bool) -> None:
        if set_autostart(enabled):
            self.cfg["autostart"] = enabled
            config.save(self.cfg)
        else:
            self.act_autostart.setChecked(is_autostart_enabled())

    def apply_hotkeys(self, enabled: bool, report: bool = True) -> None:
        self.cfg["hotkeys"] = bool(enabled)
        if enabled:
            failed = self.hotkeys.register_all()
            if failed and report:
                QMessageBox.information(
                    self.panel,
                    APP_TITLE,
                    "以下热键已被其它程序占用，未能注册：\n\n"
                    + "、".join(failed)
                    + "\n\n面板点击不受影响，可继续使用。",
                )
        else:
            self.hotkeys.unregister_all()
        config.save(self.cfg)

    def _show_help(self) -> None:
        QMessageBox.information(
            self.panel,
            APP_TITLE,
            "面板操作\n"
            f"　左键数字：切到该桌面\n"
            "　右键数字：移动当前窗口 / 重命名 / 删除桌面\n"
            "　左键 + 拖动：移动面板位置（松手后自动记住）\n"
            "　面板 ＋：新建虚拟桌面\n\n"
            "全局热键\n"
            "　Alt + 1..9　　　 切到第 N 个桌面\n"
            "　Ctrl + Alt + 1..9　把当前窗口移到第 N 个桌面\n"
            "　Alt + `　　　　　 返回上一个桌面\n\n"
            "配置与面板位置保存在：\n"
            f"　{config.CONFIG_FILE}",
        )

    def quit(self) -> None:
        try:
            self.panel.cfg["pos"] = [self.panel.x(), self.panel.y()]
            config.save(self.panel.cfg)
        except Exception:
            pass
        self.hotkeys.unregister_all()
        self.tray.hide()
        QApplication.quit()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setQuitOnLastWindowClosed(False)  # 面板隐藏时程序继续在托盘运行

    if not acquire_single_instance():
        QMessageBox.information(None, APP_TITLE, "程序已经在运行了（见系统托盘）。")
        return 0

    instance = App()
    app.aboutToQuit.connect(instance.hotkeys.unregister_all)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
