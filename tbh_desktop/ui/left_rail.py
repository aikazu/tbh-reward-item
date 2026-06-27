"""60 px vertical icon rail on the left edge of the main window."""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.theme import status_dot_style


class Action(str, Enum):
    START = "start"
    STOP = "stop"
    SAVE = "save"
    RESET = "reset"
    SCRAPE = "scrape"
    CHECK_DATA = "check_data"
    COPY_STEAM = "copy_steam"
    TOGGLE_LOG = "toggle_log"
    TOGGLE_ITEMS = "toggle_items"


_ICON_LABELS: list[tuple[Action, str, str]] = [
    (Action.START,       "btn_start",  "Start proxy (Ctrl+S to save first)"),
    (Action.STOP,        "btn_stop",   "Stop proxy"),
    (Action.SAVE,        "btn_save",   "Save config"),
    (Action.RESET,       "btn_reset",  "Reset config to default"),
    (Action.SCRAPE,      "btn_scrape", "Scrape gear + drops index"),
    (Action.CHECK_DATA,  "btn_check",  "Show cache status"),
    (Action.COPY_STEAM,  "btn_steam",  "Copy Steam launch option"),
    (Action.TOGGLE_LOG,  "btn_log",    "Show/hide log dock"),
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

        self.btn_start = self._mk_button(Action.START)
        self.btn_stop = self._mk_button(Action.STOP)
        self.btn_save = self._mk_button(Action.SAVE)
        self.btn_reset = self._mk_button(Action.RESET)
        self.btn_scrape = self._mk_button(Action.SCRAPE)
        self.btn_check = self._mk_button(Action.CHECK_DATA)
        self.btn_steam = self._mk_button(Action.COPY_STEAM)
        self.btn_log = self._mk_button(Action.TOGGLE_LOG)
        self.btn_items = self._mk_button(Action.TOGGLE_ITEMS)

        # First group: proxy control
        outer.addWidget(self.btn_start)
        outer.addWidget(self.btn_stop)
        outer.addItem(QSpacerItem(0, 12))
        # Middle group: config / data
        outer.addWidget(self.btn_save)
        outer.addWidget(self.btn_reset)
        outer.addWidget(self.btn_scrape)
        outer.addWidget(self.btn_check)
        outer.addWidget(self.btn_steam)
        outer.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        # Bottom group: view toggles
        outer.addWidget(self.btn_log)
        outer.addWidget(self.btn_items)

        # Status + port
        bottom = QVBoxLayout()
        bottom.setSpacing(4)
        self.status_dot = QLabel("●")
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_dot.setStyleSheet(status_dot_style(False))
        self.status_dot.setToolTip("Proxy status: stopped")
        bottom.addWidget(self.status_dot)

        self.port_edit = QLineEdit()
        self.port_edit.setFixedWidth(44)
        self.port_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.port_edit.setPlaceholderText("pt")
        self.port_edit.setToolTip("Proxy listen port (requires restart after change)")
        bottom.addWidget(self.port_edit)
        outer.addLayout(bottom)

        # Initial state: proxy not running.
        self.set_proxy_running(False)
        self.set_scraping(False)

    # ---- public API --------------------------------------------------
    def set_proxy_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.status_dot.setStyleSheet(status_dot_style(running))
        self.status_dot.setToolTip(
            "Proxy status: running" if running else "Proxy status: stopped"
        )

    def set_scraping(self, scraping: bool) -> None:
        self.btn_scrape.setEnabled(not scraping)
        if scraping:
            self.btn_scrape.setText("…")
        else:
            self.btn_scrape.setText("↻")

    def port_text(self) -> str:
        return self.port_edit.text().strip()

    def set_port_text(self, text: str) -> None:
        self.port_edit.setText(text)

    # ---- internals ---------------------------------------------------
    def _mk_button(self, action: Action) -> QPushButton:
        entry = next(e for e in _ICON_LABELS if e[0] == action)
        _, obj_name, tooltip = entry
        b = QPushButton(self._label_for(action))
        b.setObjectName(obj_name)
        b.setToolTip(tooltip)
        b.setFixedSize(44, 44)
        b.clicked.connect(lambda: self.action.emit(action))
        return b

    @staticmethod
    def _label_for(action: Action) -> str:
        return {
            Action.START:       "▶",
            Action.STOP:        "■",
            Action.SAVE:        "💾",
            Action.RESET:       "⟲",
            Action.SCRAPE:      "↻",
            Action.CHECK_DATA:  "ℹ",
            Action.COPY_STEAM:  "📋",
            Action.TOGGLE_LOG:  "≡",
            Action.TOGGLE_ITEMS: "▦",
        }[action]