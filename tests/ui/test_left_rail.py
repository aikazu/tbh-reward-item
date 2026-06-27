"""Tests for LeftRail: action enum + disabled state mirroring proxy state."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.left_rail import Action, LeftRail


def test_left_rail_emits_action_on_click(qapp: QApplication) -> None:
    rail = LeftRail()
    captured: list[Action] = []
    rail.action.connect(captured.append)
    rail.btn_start.click()
    rail.set_proxy_running(True)  # enable btn_stop for the next click
    rail.btn_stop.click()
    rail.btn_save.click()
    assert Action.START in captured
    assert Action.STOP in captured
    assert Action.SAVE in captured


def test_left_rail_running_disables_start(qapp: QApplication) -> None:
    rail = LeftRail()
    rail.set_proxy_running(True)
    assert rail.btn_start.isEnabled() is False
    assert rail.btn_stop.isEnabled() is True
    rail.set_proxy_running(False)
    assert rail.btn_start.isEnabled() is True
    assert rail.btn_stop.isEnabled() is False


def test_left_rail_scraping_disables_scrape(qapp: QApplication) -> None:
    rail = LeftRail()
    rail.set_scraping(True)
    assert rail.btn_scrape.isEnabled() is False
    rail.set_scraping(False)
    assert rail.btn_scrape.isEnabled() is True