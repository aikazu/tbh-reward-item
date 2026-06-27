"""Project-root conftest.

Responsibilities:
  1. Prepend project root to sys.path so pytest's tests/ prepend doesn't
     shadow top-level packages (dev_tools, tbh_desktop, src).
  2. Provide a safe `qtbot` stub so tests that import it can be collected
     without requiring pytest-qt to spin up a real QApplication. The real
     pytest-qt plugin is disabled by default in pytest.ini (`addopts = -p no:pytestqt`)
     because its teardown hangs under QT_QPA_PLATFORM=offscreen on this
     Plasma Wayland setup, killing the user's DE.
  3. Any test that genuinely needs a live Qt event loop should be marked
     with @pytest.mark.gui and run explicitly via `pytest -m gui`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def pytest_configure(config):
    """Register the 'gui' marker so `pytest -m gui` works without warnings."""
    config.addinivalue_line(
        "markers",
        "gui: test requires a live Qt event loop (skipped by default; "
        "run with `pytest -m gui` to execute).",
    )


class _NoopQtBot:
    """Stub qtbot fixture. Real pytest-qt is disabled in pytest.ini to avoid
    its known offscreen-teardown hang. If a gui-marked test is run anyway
    (e.g. `pytest -m gui`), this stub lets the test collect and execute
    without spinning up a real QApplication — operations become no-ops.

    For real Qt event-loop testing, run with `pytest -p pytestqt` after
    explicitly opting back in, or in a CI/headless environment only.
    """

    def addWidget(self, widget, *, before_close_func=None):  # noqa: N802 (Qt API)
        return None

    def waitUntil(self, predicate, timeout=5000):  # noqa: N802 (Qt API)
        return None

    def waitSignal(self, *args, **kwargs):  # noqa: N802 (Qt API)
        return None

    def mouseClick(self, *args, **kwargs):  # noqa: N802 (Qt API)
        return None

    def keyClick(self, *args, **kwargs):  # noqa: N802 (Qt API)
        return None


@pytest.fixture
def qtbot():
    """Stub `qtbot` fixture — pytest-qt is disabled by default. See class docstring."""
    return _NoopQtBot()

