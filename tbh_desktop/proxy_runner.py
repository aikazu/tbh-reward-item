# tbh_desktop/proxy_runner.py
"""Run src/run_proxy.py as subprocess, stream stdout via Qt signals."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, Signal

from tbh_desktop.paths import REPO_ROOT, RUN_PROXY_PATH


class ProxyRunner(QObject):
    log_line = Signal(str)
    running = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.is_running():
            return
        # start_new_session=True puts the child in its own process group so
        # stop() can kill the entire group (parent + child + grandchild).
        # Without this, SIGTERM only reaches the run_proxy.py wrapper and the
        # mitmdump grandchild it spawned via subprocess.call() is orphaned —
        # it keeps binding the listen port and the proxy "looks" still up.
        self._proc = subprocess.Popen(
            [sys.executable, str(RUN_PROXY_PATH)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self.running.emit(True)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        # Capture local ref: a concurrent start() could reassign self._proc,
        # causing this reader to wait()/emit on the wrong process.
        proc = self._proc
        assert proc is not None
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                self.log_line.emit(line.rstrip("\n"))
            proc.wait()
        except OSError:
            # Broken pipe / IO error mid-stream: still must signal stop.
            pass
        finally:
            # Reader owns the running(False) emission so stop() never
            # double-toggles. This runs whether the loop ended cleanly,
            # raised, or was terminated via stop().
            self.running.emit(False)

    def stop(self) -> None:
        if not self.is_running() or self._proc is None:
            return
        # Kill the entire process group (run_proxy.py + its mitmdump child)
        # instead of just the parent. terminate()/kill() only signal the
        # wrapper, leaving mitmdump orphaned on the listen port.
        proc = self._proc
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            # Already gone — nothing to do.
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
                return
            except subprocess.TimeoutExpired:
                # Polite timeout — escalate to SIGKILL on the whole group.
                os.killpg(pgid, signal.SIGKILL)
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Last resort: nothing more we can do from Python; log it.
                    pass
        except ProcessLookupError:
            # Group already gone (e.g. mitmdump exited on its own and took the
            # wrapper with it). Treat as a clean stop.
            return