# tbh_desktop/proxy_runner.py
"""Run src/run_proxy.py as subprocess, stream stdout via Qt signals."""
from __future__ import annotations

import subprocess
import sys
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from tbh_desktop.paths import REPO_ROOT, RUN_PROXY_PATH


class ProxyRunner(QObject):
    log_line = Signal(str)
    running = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.is_running():
            return
        self._proc = subprocess.Popen(
            [sys.executable, str(RUN_PROXY_PATH)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.running.emit(True)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self.log_line.emit(line.rstrip("\n"))
        self._proc.wait()
        self.running.emit(False)

    def stop(self) -> None:
        if not self.is_running() or self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self.running.emit(False)