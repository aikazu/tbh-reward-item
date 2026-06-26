# tbh_desktop/gear_scraper_runner.py
"""Run scraper.refresh_gear_full in a background thread, stream progress via Qt signals.

Prevents the UI from freezing during the long-running scrape (CloakBrowser
binary download + 28 category×grade combos with LOAD MORE clicks).
"""
from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from tbh_desktop import scraper


class GearScraperRunner(QObject):
    """Background gear scraper. Emits progress/log/finished/error signals."""

    log_line = Signal(str)
    finished = Signal(int, int)     # total_items, num_files
    error = Signal(str)
    scraping = Signal(bool)         # True when started, False when done

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        """Signal the scrape to stop. The thread's own try/finally handles
        browser.close() — calling it from here would race the scrape thread's
        in-progress close() and corrupt the Playwright state machine.
        """
        self._cancel.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)

    def start(self) -> None:
        if self.is_running():
            return
        self._cancel.clear()
        self.scraping.emit(True)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        # Capture original log methods BEFORE patching. Wrap the entire
        # capture-patch-call-restore sequence in try/finally so that any
        # failure between capture and try open can't leak the patched
        # logger.
        orig_info = scraper.log.info
        orig_warning = scraper.log.warning

        def _info_interceptor(fmt: str, *args: Any) -> None:
            orig_info(fmt, *args)
            # scraper logs: "gear %s/%s scraped %d items"
            try:
                msg = fmt % args if args else fmt
                self.log_line.emit(msg)
            except Exception:
                self.log_line.emit(fmt)

        def _warn_interceptor(fmt: str, *args: Any) -> None:
            orig_warning(fmt, *args)
            try:
                msg = fmt % args if args else fmt
                self.log_line.emit(f"[warn] {msg}")
            except Exception:
                self.log_line.emit(f"[warn] {fmt}")

        scraper.log.info = _info_interceptor       # type: ignore[method-assign]
        scraper.log.warning = _warn_interceptor     # type: ignore[method-assign]
        try:
            from tbh_desktop.paths import GEAR_CACHE_DIR
            results = scraper.refresh_gear_full(GEAR_CACHE_DIR, cancel_event=self._cancel)
            total = sum(len(v) for v in results.values())
            self.finished.emit(total, len(results))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            scraper.log.info = orig_info             # type: ignore[method-assign]
            scraper.log.warning = orig_warning       # type: ignore[method-assign]
            self.scraping.emit(False)
