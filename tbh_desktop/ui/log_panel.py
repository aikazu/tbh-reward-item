# tbh_desktop/ui/log_panel.py
"""Read-only log viewer with FIFO cap and empty-state placeholder.

Renders an italic muted "No log entries yet" hint when the panel is
empty (first launch / no activity yet) so it doesn't look like a
broken blank rectangle. The hint is implemented as a child ``QLabel``
that's toggled on/off; the ``empty`` dynamic property on the QPlainTextEdit
drives the matching QSS state (see ``theme.log_panel_style``).

Also exposes ``summary()`` for use in the bottom-bar collapsed view
so the user can still see the latest line without expanding the dock.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QContextMenuEvent, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.theme import MOCHA, empty_state_style, log_panel_style


_EMPTY_HINT = "No log entries yet — start the proxy to see traffic."


class LogPanel(QWidget):
    """Log viewer: empty-state hint + monospace FIFO log.

    Wraps a ``QPlainTextEdit`` (the actual viewer) + a centered
    ``QLabel`` (the empty-state hint) inside a vertical layout. Toggling
    visibility between them is automatic based on whether any lines have
    been appended.
    """

    MAX_LINES = 10_000

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Empty-state hint label — visible only when no log lines exist.
        self._empty_label = QLabel(_EMPTY_HINT)
        self._empty_label.setObjectName("empty_state")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(empty_state_style())
        self._empty_label.setProperty("role", "empty_hint")
        self._layout.addWidget(self._empty_label)

        # The actual log viewer.
        self._viewer = QPlainTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Built-in FIFO cap — oldest blocks dropped automatically.
        self._viewer.setMaximumBlockCount(self.MAX_LINES)
        # Use a monospace font for log readability. FiraCode Nerd Font is
        # the user's preferred terminal font; fall back through the same
        # chain as the rest of the app.
        mono = QFont("FiraCode Nerd Font Mono", 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setFamily("FiraCode Nerd Font Mono")
        self._viewer.setFont(mono)
        self._viewer.setStyleSheet(log_panel_style())
        # Ensure the viewer itself never grabs focus — read-only context.
        self._viewer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._viewer.setProperty("role", "viewer")
        self._layout.addWidget(self._viewer)

        self._update_empty_state()

    # ---- public API --------------------------------------------------
    def append_log(self, line: str) -> None:
        self._viewer.appendPlainText(line)
        self._viewer.ensureCursorVisible()
        self._update_empty_state()

    def clear_log(self) -> None:
        self._viewer.clear()
        self._update_empty_state()

    def last_line(self) -> str | None:
        text = self._viewer.toPlainText().rstrip()
        if not text:
            return None
        return text.splitlines()[-1]

    def line_count(self) -> int:
        """Number of non-empty lines in the viewer."""
        text = self._viewer.toPlainText().rstrip()
        if not text:
            return 0
        return len(text.splitlines())

    # ---- context menu (right-click on the viewer) -------------------
    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self._viewer.createStandardContextMenu()
        menu.addSeparator()

        clear_action = QAction("Clear", self)
        clear_action.triggered.connect(self.clear_log)
        menu.addAction(clear_action)

        save_action = QAction("Save to file...", self)
        save_action.triggered.connect(self._save_to_file)
        menu.addAction(save_action)

        menu.exec(event.globalPos())

    # ---- internals ---------------------------------------------------
    def _update_empty_state(self) -> None:
        empty = self.line_count() == 0
        self._empty_label.setVisible(empty)
        self._viewer.setVisible(not empty)
        # Drive the empty='true' QSS state on the viewer too, so any
        # future styles that key on it (we don't use it now but the
        # theme has it for safety) stay in sync.
        self._viewer.setProperty("empty", empty)
        # Re-polish so Qt picks up the new dynamic property value.
        self._viewer.style().unpolish(self._viewer)
        self._viewer.style().polish(self._viewer)

    def _save_to_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save log",
            "tbh.log",
            "Log files (*.log);;Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._viewer.toPlainText())
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not write to {path}:\n{exc}")
