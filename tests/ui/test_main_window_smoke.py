"""Smoke test: launch MainWindow in offscreen mode, verify the four zones exist."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
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


def test_main_window_has_four_zones(_qapp: QApplication, workdir) -> None:
    win = MainWindow()
    assert win.findChild(type(win.editor.rule_list())) is not None
    assert win.findChild(type(win.left_rail)) is not None
    assert win.findChild(type(win.item_browser)) is not None
    assert win.findChild(type(win.log_dock.widget())) is not None
    win.close()


def test_main_window_screenshot(qapp: QApplication, workdir, _tmp_path: Path) -> None:
    win = MainWindow()
    win.resize(1400, 800)
    win.show()
    qapp.processEvents()
    out = Path("tests/ui/_artifacts")
    out.mkdir(parents=True, exist_ok=True)
    pix = win.grab()
    pix.save(str(out / "main_window.png"))
    assert (out / "main_window.png").exists()
    assert (out / "main_window.png").stat().st_size > 0
    win.close()


def test_main_window_toolbar_has_three_zones(_qapp: QApplication, workdir) -> None:
    """Arsenal directive: toolbar groups buttons into primary (Start/Stop),
    secondary (Scrape/Check/Save/Reset), and ghost (Copy Steam) zones,
    each declared via toolbar_zone property so QSS styles them differently."""
    win = MainWindow()
    assert win.btn_start.property("toolbar_zone") == "primary"
    assert win.btn_stop.property("toolbar_zone") == "primary"
    assert win.btn_refresh_gear.property("toolbar_zone") == "secondary"
    assert win.btn_check_data.property("toolbar_zone") == "secondary"
    assert win.btn_save.property("toolbar_zone") == "secondary"
    assert win.btn_reset.property("toolbar_zone") == "secondary"
    assert win.btn_copy_steam.property("toolbar_zone") == "ghost"
    win.close()


def test_main_window_toolbar_port_field_is_mono(_qapp: QApplication, workdir) -> None:
    win = MainWindow()
    families = " ".join(win.port_edit.font().families()).lower()
    assert "mono" in families or "jetbrains" in families
    win.close()


def test_main_window_status_dot_object_name(_qapp: QApplication, workdir) -> None:
    """Status dot must declare objectName='status_dot_pulse' so the QSS
    pulsing animation can target it (and so left_rail.status_dot can also
    use it)."""
    win = MainWindow()
    assert win.status_dot.objectName() == "status_dot_pulse"
    win.close()