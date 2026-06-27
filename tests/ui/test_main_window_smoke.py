"""Smoke test: launch MainWindow in offscreen mode, verify the four zones exist."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

# Force offscreen so we never open a real window during CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tbh_desktop.ui.main_window import MainWindow


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch) -> None:
    # Point CONFIG_PATH at a tmp config so the real file isn't clobbered.
    cfg = tmp_path / "config.json"
    cfg.write_text('{"listen_port": 8877, "specific_queue_rules": [], "range_replacement": {}}')
    monkeypatch.setattr("tbh_desktop.ui.main_window.CONFIG_PATH", cfg)
    monkeypatch.setattr("tbh_desktop.paths.CONFIG_PATH", cfg)


def test_main_window_has_four_zones(qapp: QApplication, workdir) -> None:
    win = MainWindow()
    assert win.findChild(type(win.editor.rule_list())) is not None
    assert win.findChild(type(win.left_rail)) is not None
    assert win.findChild(type(win.item_browser)) is not None
    assert win.findChild(type(win.log_dock.widget())) is not None
    win.close()