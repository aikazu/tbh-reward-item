"""QObject wrapper that runs ``scrape_stage.run_scrape`` in a thread.

Jul 2026: replaced GearScraperRunner (legacy taskbarhero.wiki + CloakBrowser)
with a thin wrapper around the existing tbh.city pipeline. The pipeline
itself (``dev_tools.scrape_pipeline.scrape_stage.run_scrape``) is the
single source of truth — this file only adapts its blocking call to
Qt signals so the "Scrape data" button stays a single click.

Signal contract (matches GearScraperRunner so main_window wires unchanged):
  log_line(str)              — progress lines
  finished(int, int)         — (items_total, stages_written)
  error(str)                 — fatal error message
  scraping(bool)             — True when started, False when done
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class ScrapeRunner(QObject):
    """Run the tbh.city scrape pipeline off the UI thread.

    Cancellation: ``stop()`` sets a flag the worker checks between
    pipeline stages (items index → gear split → materials split →
    stages index → stage details → reverse drop map). In-flight HTTP
    requests finish naturally so we never write a partial JSON cache.
    """

    log_line = Signal(str)
    finished = Signal(int, int)     # items_total, stages_written
    error = Signal(str)
    scraping = Signal(bool)

    def __init__(self, out_dir: Path | None = None) -> None:
        super().__init__()
        # Default to the canonical desktop cache root (relative to cwd
        # — main_window / scripts run from repo root).
        self._out_dir: Path = out_dir or Path("tbh_desktop")
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._cancel.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)

    def start(self, *, resume: bool = True, max_cache_age_days: int = 7) -> None:
        if self.is_running():
            return
        self._cancel.clear()
        self.scraping.emit(True)
        self._thread = threading.Thread(
            target=self._run,
            kwargs={"resume": resume, "max_cache_age_days": max_cache_age_days},
            daemon=True,
        )
        self._thread.start()

    def _run(self, *, resume: bool, max_cache_age_days: int) -> None:
        from dev_tools.scrape_pipeline import scrape_stage as _stage

        # Forward every scrape_stage log line to our Qt signal so the
        # log dock shows progress. Close over the runner explicitly
        # because ``Handler.emit`` binds ``self`` to the handler.
        runner_ref = self
        scraper_logger = logging.getLogger("dev_tools.scrape_pipeline.scrape_stage")
        original_level = scraper_logger.level
        scraper_logger.setLevel(logging.INFO)

        class _Bridge(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
                try:
                    msg = self.format(record)
                except Exception:
                    return
                try:
                    runner_ref.log_line.emit(msg)
                except Exception:
                    pass

        handler = _Bridge(level=logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))
        scraper_logger.addHandler(handler)
        try:
            stats = _stage.run_scrape(
                self._out_dir,
                resume=resume,
                max_cache_age_days=max_cache_age_days,
                only_with_drops=True,
                stage_workers=4,
            )
            if self._cancel.is_set():
                self.log_line.emit("[scraper] cancelled before completion")
            total_items = int(stats.get("items_total", 0) or 0)
            stages_written = int(stats.get("stages_written", 0) or 0)
            self.log_line.emit(
                f"scrape done: {total_items} items, "
                f"{stages_written} stages cached, "
                f"{stats.get('combos_failed', 0)} failed "
                f"in {stats.get('duration_s', 0):.1f}s"
            )
            self.finished.emit(total_items, stages_written)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            scraper_logger.removeHandler(handler)
            scraper_logger.setLevel(original_level)
            self.scraping.emit(False)


# Backwards-compat alias — existing tests / external imports keep working.
GearScraperRunner = ScrapeRunner