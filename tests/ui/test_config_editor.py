"""Tests for ConfigEditor: keeps load/dump API, delegates to RuleListView."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.config_editor import ConfigEditor


SAMPLE = {
    "specific_queue_rules": [
        {"enabled": True, "name": "R1", "item_id": 100, "replacement_reward_item_ids": [1, 2]},
    ],
    "range_replacement": {
        "enabled": False, "name": "Range replacement",
        "match_min_item_id": 0, "match_max_item_id": 0,
        "replacement_reward_item_ids": [7],
    },
}


def test_config_editor_load_dump_round_trip(qapp: QApplication) -> None:
    editor = ConfigEditor()
    editor.load(SAMPLE)
    out = editor.dump()
    assert out["specific_queue_rules"] == SAMPLE["specific_queue_rules"]
    assert out["range_replacement"]["replacement_reward_item_ids"] == [7]


def test_config_editor_exposes_rule_list(qapp: QApplication) -> None:
    editor = ConfigEditor()
    editor.load(SAMPLE)
    assert editor.rule_list().row_count() == 1