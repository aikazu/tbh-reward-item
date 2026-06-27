"""Tests for LeftRail: view-toggle enum + status mirroring."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.left_rail import Action, LeftRail


def test_left_rail_emits_toggle_log(qapp: QApplication) -> None:
    rail = LeftRail()
    captured: list[Action] = []
    rail.action.connect(captured.append)
    rail.btn_log.click()
    assert captured == [Action.TOGGLE_LOG]


def test_left_rail_emits_toggle_items(qapp: QApplication) -> None:
    rail = LeftRail()
    captured: list[Action] = []
    rail.action.connect(captured.append)
    rail.btn_items.click()
    assert captured == [Action.TOGGLE_ITEMS]


def test_left_rail_status_dot_toggles_on_running(qapp: QApplication) -> None:
    rail = LeftRail()
    rail.set_proxy_running(True)
    assert "running" in rail.status_dot.toolTip().lower()
    rail.set_proxy_running(False)
    assert "stopped" in rail.status_dot.toolTip().lower()


def test_left_rail_port_round_trip(qapp: QApplication) -> None:
    rail = LeftRail()
    rail.set_port_text("9000")
    assert rail.port_text() == "9000"


def test_left_rail_has_no_action_buttons(qapp: QApplication) -> None:
    """Arsenal directive: the rail is status + port + view toggles ONLY.
    Action buttons (start/stop/save/etc) live in the top toolbar — keeping
    them on the rail too was a UX mistake we explicitly removed."""
    rail = LeftRail()
    forbidden = {
        "btn_start", "btn_stop", "btn_save", "btn_reset",
        "btn_scrape", "btn_check", "btn_steam",
    }
    present = {child.objectName() for child in rail.findChildren(type(rail.btn_log))}
    assert present.isdisjoint(forbidden), (
        f"LeftRail still has redundant action buttons: {present & forbidden}"
    )