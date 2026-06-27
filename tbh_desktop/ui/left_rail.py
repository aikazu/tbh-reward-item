"""60 px vertical rail on the left edge of the main window.

Contains only: status indicator + port field + view toggles.
Action buttons (START/STOP/SAVE/RESET/SCRAPE/CHECK/COPY) live in the
top toolbar — duplicating them here was the source of the original UI
mistake.
"""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.theme import status_dot_style


class Action(str, Enum):
    TOGGLE_LOG = "toggle_log"
    TOGGLE_ITEMS = "toggle_items"


_ICON_LABELS: list[tuple[Action, str, str]] = [
    (Action.TOGGLE_LOG,   "btn_log",   "Show/hide log dock"),
    (Action.TOGGLE_ITEMS, "btn_items", "Show/hide item browser"),
]


class LeftRail(QWidget):
    action = Signal(object)  # emits Action

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("left_rail")
        self.setFixedWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # View toggles — top of rail
        self.btn_log = self._mk_button(Action.TOGGLE_LOG)
        self.btn_items = self._mk_button(Action.TOGGLE_ITEMS)
        outer.addWidget(self.btn_log)
        outer.addWidget(self.btn_items)

        # Push status + port to the bottom
        outer.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Status indicator (proxy running/stopped)
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("status_dot_pulse")
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_dot.setStyleSheet(status_dot_style(False))
        self.status_dot.setToolTip("Proxy status: stopped")
        outer.addWidget(self.status_dot)

        # Port field
        self.port_edit = QLineEdit()
        self.port_edit.setObjectName("port_edit")
        self.port_edit.setFixedWidth(44)
        self.port_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.port_edit.setPlaceholderText("port")
        self.port_edit.setToolTip("Proxy listen port (requires restart after change)")
        outer.addWidget(self.port_edit)

        # Initial state.
        self.set_proxy_running(False)

    # ---- public API --------------------------------------------------
    def set_proxy_running(self, running: bool) -> None:
        self.status_dot.setStyleSheet(status_dot_style(running))
        self.status_dot.setToolTip(
            "Proxy status: running" if running else "Proxy status: stopped"
        )

    def port_text(self) -> str:
        return self.port_edit.text().strip()

    def set_port_text(self, text: str) -> None:
        self.port_edit.setText(text)

    # ---- internals ---------------------------------------------------
    def _mk_button(self, action: Action) -> QPushButton:
        entry = next(e for e in _ICON_LABELS if e[0] == action)
        _, obj_name, tooltip = entry
        b = QPushButton()
        b.setObjectName(obj_name)
        b.setToolTip(tooltip)
        b.setFixedSize(44, 44)
        b.setIconSize(QSize(20, 20))
        icon = self._icon_for(action)
        if icon is not None:
            b.setIcon(icon)
        b.clicked.connect(lambda: self.action.emit(action))
        return b

    def _icon_for(self, action: Action) -> QIcon | None:
        """Return a QStyle standard icon for ``action``."""
        style = QApplication.style()
        if style is None:
            return None
        return {
            Action.TOGGLE_LOG:   style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            Action.TOGGLE_ITEMS: style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
        }[action]