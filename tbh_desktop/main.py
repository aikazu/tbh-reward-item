"""TBH desktop app entry point."""
from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from tbh_desktop import config_io
from tbh_desktop.paths import CONFIG_PATH
from tbh_desktop.ui.main_window import MainWindow
from tbh_desktop.ui.theme import apply_theme


def main() -> int:
    # Auto-generate config.json from config.default.json on first run.
    config_io.ensure_config(CONFIG_PATH)

    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    window.show()

    # --- Graceful shutdown wiring -------------------------------------------
    # aboutToQuit fires on app.quit() (triggered by SIGINT handler below) and
    # on normal window close. Force-stop proxy + scraper so nothing leaks.
    app.aboutToQuit.connect(window._cleanup)

    # SIGINT (Ctrl+C in the terminal) → graceful quit, not hard kill.
    # Qt's C++ event loop blocks Python signal handlers from running while
    # idle, so a 250ms timer wakes the interpreter periodically to let the
    # handler fire.
    def _on_sigint(_signum: int, _frame: object) -> None:
        app.quit()

    signal.signal(signal.SIGINT, _on_sigint)
    _wakeup_timer = QTimer()
    _wakeup_timer.timeout.connect(lambda: None)
    _wakeup_timer.start(250)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
