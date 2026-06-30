"""TBH desktop app entry point."""
from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from tbh_desktop import __app_name__, __version__, config_io
from tbh_desktop.paths import APP_ICON, CONFIG_PATH
from tbh_desktop.ui.main_window import MainWindow
from tbh_desktop.ui.support_dialog import SupportDialog
from tbh_desktop.ui.theme import apply_theme, register_fonts


def main() -> int:
    # Auto-generate config.json from config.default.json on first run.
    config_io.ensure_config(CONFIG_PATH)

    # NOTE on root: the GUI itself does NOT need root. Only mitmdump's
    # local-redirector setuid helper does, and only when mode='local'.
    # The elevation happens at Start-button time via ProxyRunner.
    # start_elevated(), which wraps just run_proxy.py (not the GUI) in
    # pkexec. Running the launcher under sudo would actually break
    # things: the elevated root process can't attach to the user's
    # X11/Wayland session, so the window never appears. Always launch
    # as the regular desktop user.

    app = QApplication(sys.argv)
    register_fonts()
    apply_theme(app)

    # App identity — taskbar / titlebar icon + desktop metadata.
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_name__)
    app.setApplicationVersion(__version__)
    if APP_ICON.exists():
        app.setWindowIcon(QIcon(str(APP_ICON)))

    window = MainWindow()
    window.show()

    # QRIS support popup — once per launch. Wrapped so a popup failure
    # (missing image, theme glitch) never blocks the app from running.
    try:
        SupportDialog(parent=window).exec()
    except Exception as exc:  # noqa: BLE001
        print(f"[TBH] support popup skipped: {exc}", flush=True)

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
