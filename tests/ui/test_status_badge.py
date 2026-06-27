"""Tests for the StatusBadge widget — dot + label pill."""
from __future__ import annotations

from tbh_desktop.ui.status_badge import StatusBadge


def test_badge_starts_in_stopped_state(qapp) -> None:
    badge = StatusBadge()
    assert badge.is_running() is False
    assert "STOPPED" in badge._label.text()


def test_badge_set_state_running_toggles_text_and_color(qapp) -> None:
    badge = StatusBadge()
    badge.set_state(True)
    assert badge.is_running() is True
    assert "RUNNING" in badge._label.text()
    # The dynamic QSS state property must flip too.
    assert badge.property("state") == "running"
    badge.set_state(False)
    assert badge.is_running() is False
    assert "STOPPED" in badge._label.text()
    assert badge.property("state") == "stopped"


def test_badge_set_state_is_idempotent(qapp) -> None:
    badge = StatusBadge()
    badge.set_state(True)
    text1 = badge._label.text()
    badge.set_state(True)
    text2 = badge._label.text()
    assert text1 == text2


def test_badge_object_names_match_theme_qss(qapp) -> None:
    """Theme QSS keys on these object names — they must stay stable."""
    badge = StatusBadge()
    assert badge.objectName() == "status_badge"
    assert badge._dot.objectName() == "status_badge_dot"
    assert badge._label.objectName() == "status_badge_label"


def test_badge_custom_text_overrides(qapp) -> None:
    badge = StatusBadge(text_off="IDLE", text_on="LIVE")
    assert "IDLE" in badge._label.text()
    badge.set_state(True)
    assert "LIVE" in badge._label.text()
