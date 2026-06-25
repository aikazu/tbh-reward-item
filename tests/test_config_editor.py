"""Tests for ConfigEditor."""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from tbh_desktop.ui.config_editor import ConfigEditor

SAMPLE = {
    "specific_queue_rules": [
        {
            "enabled": True,
            "name": "White box",
            "item_id": 910801,
            "replacement_reward_item_ids": [406171],
        },
        {
            "enabled": False,
            "name": "Blue box",
            "item_id": 920801,
            "replacement_reward_item_ids": [406171],
        },
    ],
    "range_replacement": {
        "enabled": False,
        "match_min_item_id": 0,
        "match_max_item_id": 0,
        "replacement_reward_item_ids": [],
    },
}


@pytest.fixture
def editor(qtbot):
    e = ConfigEditor()
    qtbot.addWidget(e)
    e.load(SAMPLE)
    return e


def test_remove_button_disabled_initially(editor):
    """After load, no row selected -> btn_remove and btn_pick_box disabled."""
    assert editor.rules_table.currentRow() < 0
    assert not editor.btn_remove.isEnabled()
    assert not editor.btn_pick_box.isEnabled()


def test_default_rule_cannot_be_removed(editor, monkeypatch):
    """Locked (default) rule: _remove_rule is a no-op and shows a warning."""
    monkeypatch.setattr(
        "tbh_desktop.ui.config_editor.QMessageBox.warning", lambda *a, **k: 0
    )
    editor.rules_table.selectRow(0)
    editor._remove_rule()
    assert editor.rules_table.rowCount() == 2


def test_default_rule_remove_shows_warning(editor, monkeypatch):
    """Removing a locked row triggers QMessageBox.warning."""
    calls: list[tuple] = []

    def _fake_warning(*args, **kwargs):
        calls.append((args, kwargs))
        return 0

    monkeypatch.setattr(
        "tbh_desktop.ui.config_editor.QMessageBox.warning", _fake_warning
    )
    editor.rules_table.selectRow(0)
    editor._remove_rule()
    assert len(calls) == 1


def test_added_rule_is_removable(editor, monkeypatch):
    """A rule added via 'Add rule' is unlocked and removable."""
    editor._add_rule()
    assert editor.rules_table.rowCount() == 3
    # New row is at index 2; select it.
    editor.rules_table.selectRow(2)
    assert editor.btn_remove.isEnabled()
    editor._remove_rule()
    assert editor.rules_table.rowCount() == 2


def test_pick_box_button_enabled_only_with_valid_item_id(editor):
    """btn_pick_box enabled only when the selected row has a valid int item_id."""
    editor.rules_table.selectRow(0)
    assert editor.selected_rule_item_id() == 910801
    assert editor.btn_pick_box.isEnabled()

    # Edit item_id to invalid text "abc"; re-run the state handler manually
    # (selection-change is what drives the handler; text edit alone does not).
    editor.rules_table.item(0, 2).setText("abc")
    editor._update_action_button_states()
    assert not editor.btn_pick_box.isEnabled()

    # Empty string also invalid.
    editor.rules_table.item(0, 2).setText("")
    editor._update_action_button_states()
    assert not editor.btn_pick_box.isEnabled()


def test_pick_box_tooltip_when_disabled(editor):
    """No selection -> btn_pick_box tooltip carries the Indonesian hint; cleared
    once a valid row is selected."""
    assert editor.rules_table.currentRow() < 0
    assert "Pilih rule" in editor.btn_pick_box.toolTip()

    editor.rules_table.selectRow(0)
    assert editor.btn_pick_box.toolTip() == ""
