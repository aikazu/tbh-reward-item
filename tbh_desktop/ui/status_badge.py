"""Status badge widget — colored dot + label as a single pill.

Replaces the previous bare floating status dot in the toolbar. A dot
without a label is ambiguous (red could mean running / stopped / error
/ connecting / on-fire) and the user has to hover for the tooltip to
find out. A labeled badge is unambiguous at a glance.

Usage::

    badge = StatusBadge(text_off="STOPPED", text_on="RUNNING")
    badge.set_state(running=True)  # changes pill color + text

The widget is a horizontal pill containing:
  - a small dot label (QChar bullet, color via theme)
  - the state label (uppercase, letter-spaced, fixed-width font)

State is exposed as a dynamic Qt property so QSS can target each state
via ``[state='running']`` / ``[state='stopped']`` selectors if a
future theme wants to override the inline colors.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from tbh_desktop.ui.theme import MOCHA


class StatusBadge(QFrame):
    """Pill-shaped dot + label status indicator."""

    def __init__(
        self,
        text_off: str = "STOPPED",
        text_on: str = "RUNNING",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("status_badge")
        self._text_off = text_off
        self._text_on = text_on
        self._running: bool = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 12, 4)
        layout.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setObjectName("status_badge_dot")
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._dot)

        self._label = QLabel(text_off)
        self._label.setObjectName("status_badge_label")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self.set_state(False)

    def set_state(self, running: bool) -> None:
        """Update the badge to reflect a new running/stopped state."""
        if running == self._running:
            return
        self._running = running
        if running:
            bg, fg, dot_color = MOCHA["green"], MOCHA["crust"], MOCHA["green"]
        else:
            bg, fg, dot_color = MOCHA["surface1"], MOCHA["subtext"], MOCHA["red"]
        self.setStyleSheet(
            f"#status_badge {{"
            f"  background-color: {bg};"
            f"  border: none;"
            f"  border-radius: 11px;"
            f"}}"
            f"#status_badge QLabel#status_badge_dot {{"
            f"  color: {dot_color};"
            f"  font-size: 12px;"
            f"  background: transparent;"
            f"}}"
            f"#status_badge QLabel#status_badge_label {{"
            f"  color: {fg};"
            f"  font-size: 11px;"
            f"  font-weight: 700;"
            f"  letter-spacing: 1px;"
            f"  background: transparent;"
            f"}}"
        )
        self._label.setText(self._text_on if running else self._text_off)
        self.setToolTip("Proxy running" if running else "Proxy stopped")
        # Drive a dynamic property so QSS can target each state too.
        self.setProperty("state", "running" if running else "stopped")
        # Re-polish so Qt picks up the new dynamic property value.
        self.style().unpolish(self)
        self.style().polish(self)

    def is_running(self) -> bool:
        return self._running
