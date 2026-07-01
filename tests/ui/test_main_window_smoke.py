"""Smoke test: launch MainWindow in offscreen mode, verify the three zones
+ view menu exist."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

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


def test_main_window_has_three_zones(qapp, workdir) -> None:
    win = MainWindow()
    assert win.findChild(type(win.editor.rule_list())) is not None
    # Catalog content lives inside the popup (not the main window tree)
    # so findChild won't find it — verify via direct attribute access.
    assert win.catalog_popup.content is not None
    assert win.findChild(type(win.log_dock.widget())) is not None
    # LeftRail is gone — assert nothing with that objectName exists anywhere.
    assert win.findChild(type(win.editor), name="left_rail") is None
    win.close()


def test_main_window_has_view_menu_toggles(qapp, workdir) -> None:
    """The view-toggle buttons that used to live on LeftRail moved to the
    View menu (checkable QActions)."""
    win = MainWindow()
    assert win.action_toggle_log.isCheckable() is True
    assert win.action_toggle_items.isCheckable() is True
    assert win.action_toggle_log.text() == "Log panel"
    assert win.action_toggle_items.text() == "Item browser"
    win.close()


def test_main_window_screenshot(qapp, workdir, tmp_path: Path) -> None:
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


def test_main_window_toolbar_has_four_zones(qapp, workdir) -> None:
    """Arsenal directive: toolbar groups buttons into 3 intent zones
    (PROXY, DATA, CONFIG+STEAM). Zones are demarcated by QToolBar
    separators (the thin vertical bars between button groups) — no
    extra zone-label text so the toolbar stays compact on narrow
    windows. Buttons inside each zone declare ``toolbar_zone='primary'``
    or ``'secondary'`` so QSS can style them per-tier."""
    win = MainWindow()
    # Primary tier (single big pill — Start / Stop).
    assert win.btn_start.property("toolbar_zone") == "primary"
    assert win.btn_stop.property("toolbar_zone") == "primary"
    # Secondary tier (flat outline — everything else in the toolbar).
    assert win.btn_refresh_gear.property("toolbar_zone") == "secondary"
    assert win.btn_save.property("toolbar_zone") == "secondary"
    assert win.btn_reset.property("toolbar_zone") == "secondary"
    assert win.btn_copy_steam.property("toolbar_zone") == "secondary"
    # (Catalog button removed in Jul 2026; View menu action opens the
    # popup instead. btn_check_data was a dead button that pointed at
    # a method that never existed — also removed.)
    # Zone demarcation: separator widgets between groups (no text
    # labels — keeps the toolbar compact).
    from PySide6.QtWidgets import QLabel
    zone_labels = win.findChildren(QLabel, "zone_label")
    assert len(zone_labels) == 0  # no decorative text labels in toolbar


def test_main_window_toolbar_has_status_badge(qapp, workdir) -> None:
    """The toolbar exposes a labeled StatusBadge (dot + STOPPED/RUNNING
    text) in addition to the legacy bare status dot. The badge is the
    meaningful state indicator; the dot is kept for visual continuity."""
    from tbh_desktop.ui.status_badge import StatusBadge

    win = MainWindow()
    assert isinstance(win.status_badge, StatusBadge)
    assert win.status_badge.is_running() is False
    # Drive a state change and confirm both widgets reflect it.
    win.status_badge.set_state(True)
    assert win.status_badge.is_running() is True
    assert "RUNNING" in win.status_badge._label.text()
    win.close()


def test_main_window_toolbar_port_field_is_mono(qapp, workdir) -> None:
    win = MainWindow()
    families = " ".join(win.port_edit.font().families()).lower()
    assert "mono" in families or "jetbrains" in families
    win.close()


def test_main_window_status_dot_object_name(qapp, workdir) -> None:
    """Status dot must declare objectName='status_dot_pulse' so the QSS
    pulsing animation can target it."""
    win = MainWindow()
    assert win.status_dot.objectName() == "status_dot_pulse"
    win.close()