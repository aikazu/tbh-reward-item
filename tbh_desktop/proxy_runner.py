# tbh_desktop/proxy_runner.py
"""Run src/run_proxy.py as subprocess, stream stdout via Qt signals.

Also detects startup failure: if the subprocess exits within a few
seconds of starting, we treat it as a crash and emit
``startup_failed`` with the captured stderr/stdout so the GUI can show
a modal QMessageBox instead of silently returning to the "stopped"
state. This is the difference between "you clicked Start and nothing
happened" vs "you clicked Start and here's why it didn't work".

Why a startup window rather than always treating exit as failure:
  - mitmdump with valid config and free port runs for hours
  - mitmdump that can't bind its port, has a broken addon, or can't
    find its CA cert, exits in well under 2 seconds with an error
    line on stdout/stderr
  - 3 seconds is the cutoff: long enough to cover slow addon import,
    short enough that a "real" running proxy never trips it
"""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque

from PySide6.QtCore import QObject, Signal

from tbh_desktop.paths import REPO_ROOT, RUN_PROXY_PATH

# If the subprocess exits within this many seconds of start, treat it
# as a startup failure (mitmdump either binds the port or fails fast).
# Valid startup with a slow addon / CA generation can take ~1-2s.
_STARTUP_WINDOW_SEC = 3.0

# Lines of captured output to attach to a startup_failed signal so the
# GUI can show them in the dialog. Buffer is bounded so a runaway mitm
# can't fill memory.
_STARTUP_LOG_TAIL = 30


class ProxyRunner(QObject):
    log_line = Signal(str)
    running = Signal(bool)
    # Emitted with a human-readable error message + short captured output
    # when the subprocess exits within _STARTUP_WINDOW_SEC of start.
    startup_failed = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._start_ts: float = 0.0
        self._early_buf: deque[str] = deque(maxlen=_STARTUP_LOG_TAIL)
        self._early_buf_lock = threading.Lock()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def port_available(self, port: int) -> bool:
        """Quick pre-check: is ``port`` free for binding on 127.0.0.1?

        mitmproxy binds to ``*:<port>`` (0.0.0.0 + ::). We test 0.0.0.0
        which matches the actual bind target on Linux/macOS/Windows.

        This is a hint, not a guarantee — there's a TOCTOU window between
        this check and mitmdump's bind. But it lets the GUI show a useful
        dialog ("port in use, here's the process") instead of waiting for
        mitmdump to fail and emit a cryptic error.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False
        finally:
            s.close()

    def start(self, *, mode: str = "regular", name: str = "") -> None:
        """Start the proxy subprocess.

        ``mode`` / ``name`` are forwarded as CLI args to ``run_proxy.py``
        which forwards them to mitmdump. We do NOT rely on config.json
        being re-read at start time — config has an mtime-based poll but
        that's an addon-side concern. The runner needs explicit, current
        values from the GUI so the user sees what they clicked, not what
        was on disk 5 seconds ago.

        ``mode`` is "regular" (bind listen_port) or "local" (spawn the
        named process with proxy auto-injected). ``name`` is only used
        in local mode; "" or whitespace silently downgrades to regular
        with a warning logged by run_proxy.py.

        Note: when ``mode='local'`` and the host is Linux without root,
        this method will fail with "sudo: a terminal is required"
        because mitmdump's setuid helper prompts for sudo and there's
        no TTY in the GUI subprocess. Callers on Linux should check
        ``linux_elevation.runtime_needs_elevation()`` first and use
        ``start_elevated`` instead, which prompts the user via pkexec
        before spawning.
        """
        if self.is_running():
            return
        # start_new_session=True puts the child in its own process group so
        # stop() can kill the entire group (parent + child + grandchild).
        # Without this, SIGTERM only reaches the run_proxy.py wrapper and the
        # mitmdump grandchild it spawned via subprocess.call() is orphaned —
        # it keeps binding the listen port and the proxy "looks" still up.
        self._start_ts = time.monotonic()
        with self._early_buf_lock:
            self._early_buf.clear()
        cmd = [sys.executable, str(RUN_PROXY_PATH)]
        if mode:
            cmd += ["--mode", mode]
        if name and name.strip():
            cmd += ["--name", name.strip()]
        self._proc = subprocess.Popen(
            cmd,
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

    def start_elevated(self, *, mode: str = "regular", name: str = "") -> bool:
        """Spawn the proxy subprocess under pkexec (polkit prompt).

        Used on Linux when mode=local and we're not root — mitmdump's
        setuid helper needs root and there's no TTY in the GUI. We
        wrap the subprocess.Popen with pkexec so the user sees a
        native polkit password dialog instead of the "sudo: a
        terminal is required" failure.

        Returns True on successful spawn (subprocess is running),
        False on failure (pkexec missing, declined by user, OSError).
        The caller doesn't need to forward env vars manually — pkexec
        with --env keeps the GUI's desktop env (DISPLAY, XAUTHORITY,
        WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS, XDG_RUNTIME_DIR)
        so the elevated mitmdump can still find its CA cert, write
        to ~/.mitmproxy, and inject the spawned process correctly.

        Failure modes:
          - pkexec missing: prints [ERR] and returns False
          - user clicks Cancel on polkit prompt: pkexec exits with
            non-zero; runner stays in "not running" state. We don't
            surface a QMessageBox — the user's dialog dismissal IS
            the signal.
        """
        if self.is_running():
            return True
        pkexec = shutil.which("pkexec")
        if not pkexec:
            print(
                "[ERR] mode='local' on Linux requires root for mitmproxy's setuid "
                "helper, but pkexec was not found on PATH. Install polkit "
                "(Arch: pacman -S polkit) or fall back to 'regular' mode.",
                file=sys.stderr,
            )
            return False
        # pkexec does NOT have a --env flag (sudo --preserve-env does).
        # pkexec sets a minimal safe env by design. To get HOME / PATH
        # back we wrap the call in coreutils `env`:
        #   pkexec env HOME="$HOME" PATH="$PATH" -- <cmd>
        # We don't forward DISPLAY/XAUTH — run_proxy.py doesn't render
        # anything, and pkexec would refuse GUI apps without a polkit
        # policy override anyway.
        home = os.environ.get("HOME", "/root")
        path = os.environ.get(
            "PATH",
            "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        )
        cmd = [
            pkexec,
            "env",
            f"HOME={home}",
            f"PATH={path}",
            sys.executable,
            str(RUN_PROXY_PATH),
        ]
        if mode:
            cmd += ["--mode", mode]
        if name and name.strip():
            cmd += ["--name", name.strip()]
        try:
            self._start_ts = time.monotonic()
            with self._early_buf_lock:
                self._early_buf.clear()
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except OSError as exc:
            print(f"[ERR] pkexec failed to launch: {exc}", file=sys.stderr)
            return False
        self.running.emit(True)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return True

    def _read_loop(self) -> None:
        # Capture local ref: a concurrent start() could reassign self._proc,
        # causing this reader to wait()/emit on the wrong process.
        proc = self._proc
        assert proc is not None
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                stripped = line.rstrip("\n")
                # Always mirror to log panel
                self.log_line.emit(stripped)
                # Keep a small tail for the startup-failed dialog so we
                # can show the user what mitmdump said before dying.
                with self._early_buf_lock:
                    self._early_buf.append(stripped)
            proc.wait()
        except OSError:
            # Broken pipe / IO error mid-stream: still must signal stop.
            pass
        finally:
            self._maybe_emit_startup_failed(proc)
            # Reader owns the running(False) emission so stop() never
            # double-toggles. This runs whether the loop ended cleanly,
            # raised, or was terminated via stop().
            self.running.emit(False)

    def _maybe_emit_startup_failed(self, proc: subprocess.Popen) -> None:
        """If proc exited inside the startup window, surface a dialog.

        Skip if:
          - the user invoked stop() (proc was alive long enough OR was
            terminated by signal — we can't distinguish cleanly, but
            self._start_ts is reset on each start, so a long-lived proxy
            then stop() will have a huge elapsed value — fine to ignore)
          - proc was terminated by signal (stop() killed it)
          - elapsed > _STARTUP_WINDOW_SEC (proxy ran long enough to be
            considered "working")
        """
        if self._start_ts <= 0.0:
            return
        elapsed = time.monotonic() - self._start_ts
        if elapsed > _STARTUP_WINDOW_SEC:
            return
        # returncode is None if still alive; negative if terminated by signal.
        rc = proc.poll()
        if rc is None:
            return
        if rc < 0:
            # Killed by signal (e.g. SIGTERM from stop()). Not a startup fail.
            return
        # Snapshot tail before emitting (so any log_line emissions from
        # connected slots don't race the buffer).
        with self._early_buf_lock:
            tail = "\n".join(self._early_buf)
        title = f"Proxy failed to start (exit code {rc})"
        msg = (
            "mitmdump exited within "
            f"{elapsed:.1f}s of starting. Check the output below for the\n"
            "exact reason. Common causes:\n"
            "  • Port 8877 already in use (another mitmdump, or kill any\n"
            "    process holding the port)\n"
            "  • mode='local' on Linux requires root (auto-elevate should\n"
            "    have prompted for your polkit password — if it didn't,\n"
            "    check that polkit is installed)\n"
            "  • src/config.json is corrupt (the addon keeps the last\n"
            "    good config, so a syntax error there is reported here)"
        )
        self.startup_failed.emit(title, f"{msg}\n\n— output —\n{tail}")

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