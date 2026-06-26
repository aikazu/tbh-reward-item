"""Async image cache for picker dialogs.

Loads icon images from URLs in a background thread (QThread) so the UI
stays responsive. Emits ``icon_ready(item_id, QIcon)`` when each image
finishes downloading.

Threading model:
- One QThread per ImageCache (set up on first request).
- Requests are queued; thread fetches them serially with requests.get()
  and decodes via QImage.
- Each request is identified by the caller's item_id so the picker can
  match the loaded icon back to the right list item.

Limitations:
- Cached in-memory only (QImage). Closing the dialog drops the cache.
- No dedup across multiple pickers — each dialog has its own cache.
- Failed downloads are silently dropped (no icon set). Network failures
  don't crash the picker.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

import requests
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap

log = logging.getLogger(__name__)


class _FetchTask:
    """A single URL → item_id download request."""
    __slots__ = ("url", "item_id")

    def __init__(self, url: str, item_id: int) -> None:
        self.url = url
        self.item_id = item_id


class ImageCache(QObject):
    """Background-thread image fetcher. Singleton-per-dialog.

    Usage::

        cache = ImageCache(self)        # parent = dialog for cleanup
        cache.icon_ready.connect(my_slot)
        cache.request("https://...", item_id=42)
    """

    icon_ready = Signal(int, QIcon)  # item_id, decoded icon

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: list[_FetchTask] = []
        self._seen_urls: set[str] = set()  # dedup within this cache
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: _FetcherThread | None = None

    def request(self, url: str, item_id: int) -> None:
        """Queue a fetch. If *url* was already requested in this cache, no-op
        (the first request will deliver its icon via icon_ready).
        """
        if not url:
            return
        with self._lock:
            if url in self._seen_urls:
                return
            self._seen_urls.add(url)
            self._queue.append(_FetchTask(url, item_id))
            self._ensure_thread()
            self._wake.set()

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = _FetcherThread(self._queue, self._lock, self._wake, self.icon_ready)
        self._thread.start()


class _FetcherThread(threading.Thread):
    """Drains the cache's request queue in a background thread."""

    def __init__(
        self,
        queue: list[_FetchTask],
        lock: threading.Lock,
        wake: threading.Event,
        signal: Any,  # SignalInstance at runtime; Any avoids pyright stub mismatch
    ) -> None:
        super().__init__(daemon=True, name="tbh-image-cache")
        self._queue = queue
        self._lock = lock
        self._wake = wake
        self._signal = signal

    def run(self) -> None:
        while True:
            task = self._next_task()
            if task is None:
                # No work; block until request() wakes us, or exit if shutting down.
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            try:
                self._fetch_one(task)
            except Exception as exc:
                log.debug("image fetch failed for %s: %s", task.url, exc)

    def _next_task(self) -> _FetchTask | None:
        with self._lock:
            if self._queue:
                return self._queue.pop(0)
        return None

    def _fetch_one(self, task: _FetchTask) -> None:
        resp = requests.get(task.url, timeout=10)
        resp.raise_for_status()
        img = QImage()
        if not img.loadFromData(resp.content):
            return
        # Scale to a sensible icon size — list widget will use iconSize().
        pixmap = QPixmap.fromImage(img.scaled(
            64, 64, Qt_KeepAspectRatio, Qt_SmoothTransformation,
        ))
        # Emit icon_ready on the GUI thread; Signal connections default to
        # Qt.AutoConnection which queues cross-thread to the receiver's thread.
        self._signal.emit(task.item_id, QIcon(pixmap))


# Qt enum aliases (deliberately module-level so the constant resolves at
# import time without importing the full Qt namespace into hot paths).
from PySide6.QtCore import Qt  # noqa: E402

Qt_KeepAspectRatio = Qt.AspectRatioMode.KeepAspectRatio
Qt_SmoothTransformation = Qt.TransformationMode.SmoothTransformation
