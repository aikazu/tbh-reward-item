# tbh_desktop/ui/log_panel.py
"""Read-only log viewer with FIFO cap."""
from __future__ import annotations

from PySide6.QtGui import QAction, QContextMenuEvent
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPlainTextEdit


class LogPanel(QPlainTextEdit):
    MAX_LINES = 10_000

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Built-in FIFO cap — oldest blocks dropped automatically. No manual trim.
        self.setMaximumBlockCount(self.MAX_LINES)
        from tbh_desktop.ui.theme import log_panel_style
        self.setStyleSheet(log_panel_style())

    def append_log(self, line: str) -> None:
        # ensureCursorVisible guarantees auto-scroll even on overflow trim.
        self.appendPlainText(line)
        self.ensureCursorVisible()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.createStandardContextMenu()
        menu.addSeparator()

        clear_action = QAction("Clear", self)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)

        save_action = QAction("Save to file...", self)
        save_action.triggered.connect(self._save_to_file)
        menu.addAction(save_action)

        menu.exec(event.globalPos())

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
                f.write(self.toPlainText())
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not write to {path}:\n{exc}")
