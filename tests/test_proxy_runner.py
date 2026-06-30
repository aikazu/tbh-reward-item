# tests/test_proxy_runner.py
"""Tests for proxy_runner.

Two layers:
  - Pure-helper tests for ``_taskkill_tree`` / ``_posix_kill_tree`` /
    ``_kill_process_tree`` — run by default, no Qt needed.
  - Runner integration tests (start/stop wiring, signal emission) —
    marked ``@pytest.mark.gui`` because they instantiate ``QObject``
    with Signal members, which requires a Qt-aware environment.

Skipped by default (the runner integration tests are gui-marked).
Run with ``pytest -m gui`` to exercise the runner tests too.
"""
from __future__ import annotations

import signal
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from tbh_desktop import proxy_runner


# ----------------------------------------------------------------- pure helpers
# These don't touch Qt at all — they only call subprocess.run / os.killpg.
# We still leave them in the same file for cohesion (they're testing the
# proxy_runner module's surface) but don't tag them gui so they run by default.


def test_taskkill_tree_invokes_taskkill_with_tree_and_force() -> None:
    """Windows path: must call taskkill with /T (tree) and /F (force)."""
    with patch.object(proxy_runner.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        proxy_runner._taskkill_tree(12345)
    args = mock_run.call_args.args[0]
    assert args == ["taskkill", "/T", "/F", "/PID", "12345"]
    # capture_output=True so no console window pops up; text=True for strings.
    assert mock_run.call_args.kwargs.get("capture_output") is True
    assert mock_run.call_args.kwargs.get("text") is True


def test_taskkill_tree_treats_not_found_as_success() -> None:
    """taskkill returns 128 ('process not found') when the PID is gone.
    That should NOT log a warning — the user's stop intent is already met
    and a noisy warning would suggest the Stop button is broken."""
    with patch.object(proxy_runner.subprocess, "run") as mock_run, \
         patch("builtins.print") as mock_print:
        mock_run.return_value = MagicMock(
            returncode=128, stdout="", stderr="ERROR: process not found"
        )
        proxy_runner._taskkill_tree(12345)
    mock_print.assert_not_called()


def test_taskkill_tree_logs_other_failures() -> None:
    """Anything other than 0 / 128 is a real failure that the user should
    see — log to stderr so the GUI can surface it."""
    with patch.object(proxy_runner.subprocess, "run") as mock_run, \
         patch("builtins.print") as mock_print:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Access is denied"
        )
        proxy_runner._taskkill_tree(12345)
    mock_print.assert_called_once()
    msg = mock_print.call_args.args[0]
    assert "taskkill" in msg
    assert "Access is denied" in msg


def test_posix_kill_tree_sends_sigterm_then_sigkill_on_timeout(monkeypatch) -> None:
    """POSIX path: SIGTERM first, wait, then SIGKILL on escalation.

    ``proc.wait()`` always times out → escalation must fire."""
    sigterm_calls: list[int] = []
    sigkill_calls: list[int] = []

    def fake_getpgid(pid: int) -> int:
        return pid + 1000

    def fake_killpg(pgid: int, sig: int) -> None:
        if sig == signal.SIGTERM:
            sigterm_calls.append(pgid)
        elif sig == signal.SIGKILL:
            sigkill_calls.append(pgid)

    proc = MagicMock()
    proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=1)

    # ``raising=False`` because ``os.getpgid``/``os.killpg``/``signal.SIGKILL``
    # don't exist on Windows — the attributes are created by monkeypatch just
    # for the duration of this test. SIGKILL = 9 is the POSIX canonical value.
    monkeypatch.setattr(proxy_runner.os, "getpgid", fake_getpgid, raising=False)
    monkeypatch.setattr(proxy_runner.os, "killpg", fake_killpg, raising=False)
    monkeypatch.setattr(proxy_runner.signal, "SIGKILL", 9, raising=False)
    proxy_runner._posix_kill_tree(12345, proc=proc)

    assert sigterm_calls == [13345]
    assert sigkill_calls == [13345]  # escalated
    assert proc.wait.call_count == 2  # one per phase


def test_posix_kill_tree_returns_when_proc_exits_during_grace(monkeypatch) -> None:
    """If mitmdump exits cleanly during the SIGTERM grace window, we must
    NOT escalate to SIGKILL — that would be wasteful and noisy in logs."""
    sigterm_calls: list[int] = []
    sigkill_calls: list[int] = []

    def fake_getpgid(pid: int) -> int:
        return pid + 1000

    def fake_killpg(pgid: int, sig: int) -> None:
        if sig == signal.SIGTERM:
            sigterm_calls.append(pgid)
        elif sig == signal.SIGKILL:
            sigkill_calls.append(pgid)

    proc = MagicMock()
    proc.wait.return_value = 0  # exited cleanly

    monkeypatch.setattr(proxy_runner.os, "getpgid", fake_getpgid, raising=False)
    monkeypatch.setattr(proxy_runner.os, "killpg", fake_killpg, raising=False)
    proxy_runner._posix_kill_tree(12345, proc=proc)

    assert sigterm_calls == [13345]
    assert sigkill_calls == []  # no escalation
    assert proc.wait.call_count == 1


def test_posix_kill_tree_handles_already_gone(monkeypatch) -> None:
    """If ``os.getpgid`` raises ``ProcessLookupError``, the process is
    already gone — return cleanly without calling ``os.killpg``."""
    def fake_getpgid(pid: int) -> int:
        raise ProcessLookupError
    monkeypatch.setattr(proxy_runner.os, "getpgid", fake_getpgid, raising=False)
    # Should not raise. ``killpg`` must NOT be called.
    with patch.object(proxy_runner.os, "killpg", create=True) as mock_killpg:
        proxy_runner._posix_kill_tree(12345, proc=None)
    mock_killpg.assert_not_called()


def test_kill_process_tree_dispatches_to_windows_helper(monkeypatch) -> None:
    """Platform dispatcher: ``sys.platform == 'win32'`` must route to
    ``_taskkill_tree``, never ``_posix_kill_tree``."""
    monkeypatch.setattr(proxy_runner.sys, "platform", "win32")
    with patch.object(proxy_runner, "_taskkill_tree") as mock_tk, \
         patch.object(proxy_runner, "_posix_kill_tree") as mock_pk:
        proxy_runner._kill_process_tree(777, proc=None)
    mock_tk.assert_called_once_with(777)
    mock_pk.assert_not_called()


def test_kill_process_tree_dispatches_to_posix_helper(monkeypatch) -> None:
    """Platform dispatcher: anything that isn't Windows routes to the
    POSIX helper (killpg with escalation)."""
    monkeypatch.setattr(proxy_runner.sys, "platform", "linux")
    with patch.object(proxy_runner, "_taskkill_tree") as mock_tk, \
         patch.object(proxy_runner, "_posix_kill_tree") as mock_pk:
        proxy_runner._kill_process_tree(777, proc=None)
    mock_pk.assert_called_once_with(777, proc=None)
    mock_tk.assert_not_called()


# --------------------------------------------------------------------- runner
# The runner integration tests below need QObject (Signal members) and
# therefore carry ``@pytest.mark.gui`` explicitly. Skipped by default.


@pytest.mark.gui
def test_runner_emits_log_lines(qtbot) -> None:
    runner = proxy_runner.ProxyRunner()
    lines: list[str] = []
    runner.log_line.connect(lines.append)
    with patch("tbh_desktop.proxy_runner.subprocess.Popen") as mock_popen:
        proc = MagicMock()
        proc.stdout = iter(["[TBH] hello\n", "[TBH] world\n"])
        proc.poll.return_value = 0
        mock_popen.return_value = proc
        runner.start()
    qtbot.waitUntil(lambda: "[TBH] world" in lines, timeout=2000)
    assert "[TBH] hello" in lines
    assert "[TBH] world" in lines


@pytest.mark.gui
def test_running_signal_toggles(qtbot) -> None:
    runner = proxy_runner.ProxyRunner()
    states: list[bool] = []
    runner.running.connect(states.append)
    with patch("tbh_desktop.proxy_runner.subprocess.Popen") as mock_popen:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.poll.return_value = 0
        mock_popen.return_value = proc
        runner.start()
    qtbot.waitUntil(lambda: True in states, timeout=2000)
    qtbot.waitUntil(lambda: False in states, timeout=2000)
    assert True in states
    assert False in states


@pytest.mark.gui
def test_stop_delegates_to_kill_process_tree(qtbot, monkeypatch) -> None:
    """``stop()`` must route to ``_kill_process_tree`` with the live PID
    and the live Popen object. This is the contract the desktop Stop
    button relies on — the actual platform kill logic is exercised by
    the helper tests above."""
    runner = proxy_runner.ProxyRunner()
    captured: dict = {}

    def fake_kill(pid, *, proc=None):
        captured["pid"] = pid
        captured["proc"] = proc

    monkeypatch.setattr(proxy_runner, "_kill_process_tree", fake_kill)

    with patch("tbh_desktop.proxy_runner.subprocess.Popen") as mock_popen:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.poll.return_value = None  # report "running" until stop()
        proc.pid = 99999
        mock_popen.return_value = proc
        runner.start()
        runner.stop()

    assert captured["pid"] == 99999
    assert captured["proc"] is proc


@pytest.mark.gui
def test_stop_swallows_not_implemented_error(qtbot, monkeypatch) -> None:
    """Defensive safety net: if a future refactor reintroduces a POSIX-only
    API on Windows (e.g. ``os.killpg``), ``stop()`` must log to stderr
    instead of crashing the GUI's Stop button click."""
    runner = proxy_runner.ProxyRunner()
    monkeypatch.setattr(
        proxy_runner,
        "_kill_process_tree",
        lambda *a, **kw: (_ for _ in ()).throw(NotImplementedError("os.killpg")),
    )
    with patch("tbh_desktop.proxy_runner.subprocess.Popen") as mock_popen, \
         patch("builtins.print") as mock_print:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.poll.return_value = None
        proc.pid = 4242
        mock_popen.return_value = proc
        runner.start()
        # Should not raise.
        runner.stop()
    # The defensive net should have printed a warning with the failing PID.
    assert any("4242" in str(call) for call in mock_print.call_args_list)


@pytest.mark.gui
def test_stop_short_circuits_when_not_running() -> None:
    """Calling stop() with no live subprocess must be a no-op — no
    helper invocation, no exception."""
    runner = proxy_runner.ProxyRunner()
    with patch.object(proxy_runner, "_kill_process_tree") as mock_kill:
        runner.stop()
    mock_kill.assert_not_called()