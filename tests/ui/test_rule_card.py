"""Tests for RuleCard: per-row pick buttons, chip row, signals."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.rule_card import RuleCard


def _capture(card: RuleCard) -> dict[str, list]:
    """Wire all RuleCard signals to a dict for inspection."""
    captured: dict[str, list] = {
        "pick_box_id": [],
        "pick_box_loot": [],
        "pick_gear": [],
        "remove": [],
        "edited": [],
    }
    card.pick_box_id.connect(lambda: captured["pick_box_id"].append(True))
    card.pick_box_loot.connect(lambda: captured["pick_box_loot"].append(True))
    card.pick_gear.connect(lambda: captured["pick_gear"].append(True))
    card.remove.connect(lambda: captured["remove"].append(True))
    card.edited.connect(lambda: captured["edited"].append(True))
    return captured


def test_rule_card_renders_from_dict(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True,
        "name": "Test rule",
        "item_id": 12345,
        "replacement_reward_item_ids": [529191, 419191],
    })
    assert card.name() == "Test rule"
    assert card.item_id() == 12345
    assert card.replacement_ids() == [529191, 419191]


def test_rule_card_pick_buttons_emit_signals(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [],
    })
    captured = _capture(card)
    card.btn_pick_box_id.click()
    card.btn_pick_box_loot.click()
    card.btn_pick_gear.click()
    assert captured["pick_box_id"] == [True]
    assert captured["pick_box_loot"] == [True]
    assert captured["pick_gear"] == [True]


def test_rule_card_add_chip_appends(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [10],
    })
    card.add_ids([20, 30])
    assert card.replacement_ids() == [10, 20, 30]


def test_rule_card_add_chip_dedupes(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [10, 20],
    })
    card.add_ids([20, 30, 10])
    assert card.replacement_ids() == [10, 20, 30]


def test_rule_card_remove_chip(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [10, 20, 30],
    })
    card.remove_id(20)
    assert card.replacement_ids() == [10, 30]


def test_rule_card_set_active_toggles_border(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [],
    })
    card.set_active(True)
    assert card.is_active() is True
    card.set_active(False)
    assert card.is_active() is False


def test_rule_card_remove_emits_signal(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [],
    })
    captured = _capture(card)
    card.btn_remove.click()
    assert captured["remove"] == [True]


def test_rule_card_locked_disables_remove(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [],
    }, locked=True)
    assert card.btn_remove.isEnabled() is False
