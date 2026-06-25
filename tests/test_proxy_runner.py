# tests/test_proxy_runner.py
"""Tests for proxy_runner."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tbh_desktop import proxy_runner


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
    qtbot.waitUntil(lambda: "[TBH] hello" in lines, timeout=2000)
    assert "[TBH] hello" in lines


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
    assert True in states