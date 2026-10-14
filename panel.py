"""悬浮面板：一排数字按钮，点哪个就跳到哪个桌面。

设计要点
- 无边框 + 置顶 + 不抢焦点（WindowDoesNotAcceptFocus）：
  点击面板不会把当前窗口切到后台，所以「把当前窗口移到别的桌面」才能拿到正确的窗口句柄。
- 定时轮询桌面数量与当前序号，用 Win+Ctrl+←/→ 切换时面板也能同步。
- 紧凑模式：平时只留一枚显示当前桌面的小药丸，鼠标移上去自动展开。
"""

from __future__ import annotations

from PyQt5.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QWidget,
)

from vda import VirtualDesktop, foreground_window

CHIP_W, CHIP_H = 30, 26
POLL_MS = 350

THEMES = {
    "dark": {
        "card_bg": "rgba(28, 28, 30, 0.90)",
        "card_border": "rgba(255, 255, 255, 0.16)",
        "text": "#F2F2F7",
        "text_dim": "#9A9AA0",
        "chip_bg": "rgba(255, 255, 255, 0.10)",
        "chip_hover": "rgba(255, 255, 255, 0.22)",
        "chip_press": "rgba(255, 255, 255, 0.32)",
        "active_bg": "#0A84FF",
        "active_text": "#FFFFFF",
        "handle": "rgba(255, 255, 255, 0.22)",
    },
    "light": {
        "card_bg": "rgba(250, 250, 252, 0.94)",
        "card_border": "rgba(0, 0, 0, 0.14)",
        "text": "#1C1C1E",
        "text_dim": "#6E6E73",
        "chip_bg": "rgba(0, 0, 0, 0.06)",
        "chip_hover": "rgba(0, 0, 0, 0.13)",
        "chip_press": "rgba(0, 0, 0, 0.20)",
        "active_bg": "#007AFF",
        "active_text": "#FFFFFF",
        "handle": "rgba(0, 0, 0, 0.20)",
    },
}


def _style(t: dict) -> str:
    return f"""
    QFrame#card {{
        background: {t['card_bg']};
        border: 1px solid {t['card_border']};
        border-radius: 10px;
    }}
    QLabel#num, QPushButton#num {{
        color: {t['text']};
    }}
    QLabel#num {{
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton {{
        background: {t['chip_bg']};
        color: {t['text']};
        border: none;
        border-radius: 6px;
        font-size: 13px;
    }}
    QPushButton:hover {{ background: {t['chip_hover']}; }}
    QPushButton:pressed {{ background: {t['chip_press']}; }}
    QPushButton[active="true"] {{
        background: {t['active_bg']};
        color: {t['active_text']};
        font-weight: 500;
    }}
    QPushButton[active="true"]:hover {{ background: {t['active_bg']}; }}
    """


class Panel(QWidget):
    desktop_changed = pyqtSignal(int)
    settings_requested = pyqtSignal(QPoint)

    def __init__(self, vd: VirtualDesktop, cfg: dict) -> None:
        super().__init__()
        self.vd = vd
        self.cfg = cfg
        self._chips: list[QPushButton] = []
        self._press_gp: QPoint | None = None
        self._dragging = False
        self._collapsed = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("桌面切换面板")

        self._card = QFrame(self)
        self._card.setObjectName("card")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)

        row = QHBoxLayout(self._card)
        row.setContentsMargins(7, 6, 9, 6)
        row.setSpacing(5)

        # 左侧细条，纯视觉拖拽提示（整块面板其实都能拖）
        self._handle = QFrame()
        self._handle.setFixedSize(3, 16)
        self._handle.setCursor(Qt.SizeAllCursor)
        self._handle.setToolTip("按住拖动可移动面板")
        row.addWidget(self._handle)

        self._chips_box = QWidget()
        self._chips_row = QHBoxLayout(self._chips_box)
        self._chips_row.setContentsMargins(0, 0, 0, 0)
        self._chips_row.setSpacing(4)
        row.addWidget(self._chips_box)

        self._pill = QLabel()
        self._pill.setObjectName("num")
        self._pill.setAlignment(Qt.AlignCenter)
        self._pill.setFixedSize(CHIP_W, CHIP_H)
        self._pill.setToolTip("鼠标移上来展开全部桌面")
        self._pill.hide()
        row.addWidget(self._pill)

        self._plus = QPushButton("+")
        self._plus.setFixedSize(CHIP_W - 4, CHIP_H)
        self._plus.setCursor(Qt.PointingHandCursor)
        self._plus.setToolTip("新建一个虚拟桌面")
        self._plus.clicked.connect(self._create_desktop)
        row.addWidget(self._plus)

        self._apply_theme(cfg.get("theme", "dark"))
        self.setWindowOpacity(float(cfg.get("opacity", 0.92)))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._sync)
        self._timer.start(POLL_MS)

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._collapse)

        self._rebuild()
        self._restore_position()
        self._last_current = self.vd.current
        self._apply_compact(bool(cfg.get("compact", False)), init=True)

    # ---------------- 界面同步 ----------------

    def _rebuild(self) -> None:
        while self._chips_row.count():
            item = self._chips_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._chips.clear()

        for i in range(self.vd.count):
            chip = QPushButton(str(i + 1))
            chip.setFixedSize(CHIP_W, CHIP_H)
            chip.setCursor(Qt.PointingHandCursor)
            title = self.vd.name(i)
            chip.setToolTip(f"桌面 {i + 1}" + (f" · {title}" if title else "")
                            + "\n左键切换 · 右键更多操作")
            chip.setContextMenuPolicy(Qt.CustomContextMenu)
            chip.customContextMenuRequested.connect(
                lambda _pos, idx=i, w=chip: self._chip_menu(idx, w)
            )
            chip.clicked.connect(lambda _=False, idx=i: self.goto(idx))
            chip.installEventFilter(self)
            self._chips_row.addWidget(chip)
            self._chips.append(chip)

        self._refresh_highlight()
        self._pill.setText(str(self.vd.current + 1))
        self.adjustSize()

    def _refresh_highlight(self) -> None:
        cur = self.vd.current
        for i, chip in enumerate(self._chips):
            active = i == cur
            if chip.property("active") != active:
                chip.setProperty("active", active)
                chip.style().unpolish(chip)
                chip.style().polish(chip)

    def _sync(self) -> None:
        if self.vd.count != len(self._chips):
            self._rebuild()
        self._refresh_highlight()

        cur = self.vd.current
        if cur != getattr(self, "_last_current", -1):
            self._last_current = cur
            self._pill.setText(str(cur + 1))
            self.desktop_changed.emit(cur)

    def goto(self, index: int) -> None:
        """切换到指定桌面，并立即刷新选中态（不等轮询）。"""
        self.vd.go(index, animate=bool(self.cfg.get("animate", False)))
        self._last_current = self.vd.current
        self._refresh_highlight()
        for i, chip in enumerate(self._chips):
            chip.setProperty("active", i == self._last_current)
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        self._pill.setText(str(self._last_current + 1))
        self.desktop_changed.emit(self._last_current)

    def _create_desktop(self) -> None:
        self.vd.create()
        QTimer.singleShot(120, self._rebuild)

    # ---------------- 右键菜单 ----------------

    def _chip_menu(self, index: int, anchor: QWidget) -> None:
        menu = QMenu(self)
        menu.addAction(f"切换到桌面 {index + 1}", lambda: self.goto(index))
        menu.addSeparator()
        menu.addAction("把当前窗口移过来", lambda: self._move_window(index, follow=False))
        menu.addAction("移过来并跟过去", lambda: self._move_window(index, follow=True))
        menu.addSeparator()
        menu.addAction("重命名此桌面…", lambda: self._rename(index))
        act_del = menu.addAction("删除此桌面…", lambda: self._remove(index))
        act_del.setEnabled(self.vd.count > 1)
        menu.exec_(anchor.mapToGlobal(QPoint(0, anchor.height() + 2)))

    def _move_window(self, index: int, follow: bool) -> None:
        hwnd = foreground_window()
        if not hwnd or hwnd == int(self.winId()):
            return
        if self.vd.move_window(hwnd, index) and follow:
            self.goto(index)

    def _rename(self, index: int) -> None:
        current = self.vd.name(index)
        title, ok = QInputDialog.getText(self, "重命名桌面", f"桌面 {index + 1} 的名称：", text=current)
        if ok:
            self.vd.rename(index, title)
            self._rebuild()

    def _remove(self, index: int) -> None:
        if self.vd.count <= 1:
            return
        fallback = 0 if index != 0 else 1
        ans = QMessageBox.question(
            self,
            "删除虚拟桌面",
            f"确定删除桌面 {index + 1} 吗？\n该桌面上的窗口会被移到桌面 {fallback + 1}。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes and self.vd.remove(index, fallback):
            QTimer.singleShot(150, self._rebuild)

    # ---------------- 外观 ----------------

    def _apply_theme(self, name: str) -> None:
        t = THEMES.get(name, THEMES["dark"])
        self.cfg["theme"] = name if name in THEMES else "dark"
        self.setStyleSheet(_style(t))
        self._handle.setStyleSheet(f"background: {t['handle']}; border-radius: 1px;")
        self.update()

    def set_opacity(self, value: float) -> None:
        value = max(0.25, min(1.0, float(value)))
        self.cfg["opacity"] = value
        self.setWindowOpacity(value)

    def set_compact(self, on: bool) -> None:
        self.cfg["compact"] = bool(on)
        if on:
            self._collapse()
        else:
            self._expand()

    def _apply_compact(self, on: bool, init: bool = False) -> None:
        if on:
            self._collapse()
        else:
            self._expand()

    def _collapse(self) -> None:
        if not self.cfg.get("compact"):
            return
        self._collapsed = True
        self._chips_box.hide()
        self._plus.hide()
        self._pill.show()
        self.adjustSize()

    def _expand(self) -> None:
        self._collapsed = False
        self._chips_box.show()
        self._plus.show()
        self._pill.hide()
        self.adjustSize()

    def enterEvent(self, event):  # noqa: N802
        self._collapse_timer.stop()
        if self.cfg.get("compact"):
            self._expand()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        if self.cfg.get("compact"):
            self._collapse_timer.start(320)
        super().leaveEvent(event)

    # ---------------- 拖动 ----------------

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_gp = event.globalPos()
        elif event.button() == Qt.RightButton:
            self.settings_requested.emit(event.globalPos())

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._track_drag(event.globalPos()):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._end_drag()

    def eventFilter(self, obj, event):  # noqa: N802
        """让鼠标落在按钮上时也能拖动面板：超过阈值即拖拽，并吞掉随后的点击。"""
        if isinstance(obj, QPushButton):
            etype = event.type()
            if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._press_gp = event.globalPos()
            elif etype == QEvent.MouseMove:
                if self._press_gp and self._track_drag(event.globalPos()):
                    obj.setDown(False)
                    obj.update()
                    return True
            elif etype == QEvent.MouseButtonRelease:
                if self._end_drag():
                    return True
        return super().eventFilter(obj, event)

    def _track_drag(self, gp: QPoint) -> bool:
        if self._press_gp is None:
            return False
        if not self._dragging and (gp - self._press_gp).manhattanLength() < 5:
            return False
        self._dragging = True
        self.move(self.pos() + gp - self._press_gp)
        self._press_gp = gp
        return True

    def _end_drag(self) -> bool:
        was = self._dragging
        self._press_gp = None
        self._dragging = False
        if was:
            self._store_position()
            self.cfg["pos"] = [self.x(), self.y()]
            from config import save

            save(self.cfg)
        return was

    # ---------------- 位置 ----------------

    def _restore_position(self) -> None:
        pos = self.cfg.get("pos")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            self.move(int(pos[0]), int(pos[1]))
            if self._on_screen():
                return
        self._place_default()

    def _on_screen(self) -> bool:
        for screen in QApplication.screens():
            if screen.availableGeometry().intersects(self.frameGeometry()):
                return True
        return False

    def _place_default(self) -> None:
        geo = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(geo.right() - self.width() - 24, geo.bottom() - self.height() - 24)

    def _store_position(self) -> None:
        self.cfg["pos"] = [self.x(), self.y()]

    def reset_position(self) -> None:
        self._place_default()
        self._store_position()
        from config import save

        save(self.cfg)
