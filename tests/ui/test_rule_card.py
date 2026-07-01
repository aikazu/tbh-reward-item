"""Tests for RuleCard: pool_id + reward_kind (Normal/Boss/Act), chip row, signals.

Jul 2026 — tbh.city migration: cards now carry ``reward_kind`` + ``pool_id``
instead of v1's ``item_id`` + ``stage_type``. The pick signals collapsed
from three (pick_box_id / pick_box_loot / pick_gear) to two (pick_pool_id /
pick_replacement); the buttons live only in the DETAIL panel.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.rule_card import RuleCard


def _capture(card: RuleCard) -> dict[str, list]:
    captured: dict[str, list] = {
        "pick_pool_id": [],
        "pick_replacement": [],
        "remove": [],
        "edited": [],
    }
    card.pick_pool_id.connect(lambda: captured["pick_pool_id"].append(True))
    card.pick_replacement.connect(lambda: captured["pick_replacement"].append(True))
    card.remove.connect(lambda: captured["remove"].append(True))
    card.edited.connect(lambda: captured["edited"].append(True))
    return captured


def test_rule_card_renders_from_dict(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True,
        "name": "Test rule",
        "reward_kind": "normal",
        "pool_id": 9100111,
        "replacement_reward_item_ids": [529191, 419191],
    })
    assert card.name() == "Test rule"
    assert card.pool_id() == 9100111
    assert card.reward_kind() == "normal"
    assert card.replacement_ids() == [529191, 419191]


def test_rule_card_renders_boss_kind(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "Boss", "reward_kind": "boss",
        "pool_id": 9200111, "replacement_reward_item_ids": [],
    })
    assert card.reward_kind() == "boss"
    assert card.pool_id() == 9200111


def test_rule_card_renders_act_kind(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "Act 1 boss", "reward_kind": "act",
        "pool_id": 9301011, "replacement_reward_item_ids": [],
    })
    assert card.reward_kind() == "act"


def test_rule_card_pick_signals_still_emitted(qapp: QApplication) -> None:
    """Pick buttons live in the DETAIL panel, not the rule card (no UI
    duplication). The RuleCard still exposes the pick_* signals so
    MainWindow can trigger them programmatically when the user clicks
    the DETAIL-panel buttons."""
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "reward_kind": "normal",
        "pool_id": 9100111, "replacement_reward_item_ids": [],
    })
    captured = _capture(card)
    card.pick_pool_id.emit()
    card.pick_replacement.emit()
    assert captured["pick_pool_id"] == [True]
    assert captured["pick_replacement"] == [True]


def test_rule_card_add_chip_appends(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "reward_kind": "normal",
        "pool_id": 9100111, "replacement_reward_item_ids": [10],
    })
    card.add_ids([20, 30])
    assert card.replacement_ids() == [10, 20, 30]


def test_rule_card_add_chip_dedupes(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "reward_kind": "normal",
        "pool_id": 9100111, "replacement_reward_item_ids": [10, 20],
    })
    card.add_ids([20, 30, 10])
    assert card.replacement_ids() == [10, 20, 30]


def test_rule_card_remove_chip(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "reward_kind": "normal",
        "pool_id": 9100111, "replacement_reward_item_ids": [10, 20, 30],
    })
    card.remove_id(20)
    assert card.replacement_ids() == [10, 30]


def test_rule_card_set_active_toggles_border(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "reward_kind": "normal",
        "pool_id": 9100111, "replacement_reward_item_ids": [],
    })
    card.set_active(True)
    assert card.is_active() is True
    card.set_active(False)
    assert card.is_active() is False


def test_rule_card_remove_emits_signal(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "reward_kind": "normal",
        "pool_id": 9100111, "replacement_reward_item_ids": [],
    })
    captured = _capture(card)
    card.btn_remove.click()
    assert captured["remove"] == [True]


def test_rule_card_locked_disables_remove(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "reward_kind": "normal",
        "pool_id": 9100111, "replacement_reward_item_ids": [],
    }, locked=True)
    assert card.btn_remove.isEnabled() is False


def test_rule_card_chip_click_removes_id(qapp: QApplication) -> None:
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QMouseEvent
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "reward_kind": "normal",
        "pool_id": 9100111, "replacement_reward_item_ids": [10, 20, 30],
    })
    captured = _capture(card)
    chip = card._chips[1]
    event = QMouseEvent(QEvent.Type.MouseButtonPress, QPoint(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    chip.mousePressEvent(event)
    assert card.replacement_ids() == [10, 30]
    assert captured["edited"] == [True]


def test_rule_card_has_section_heading(qapp: QApplication) -> None:
    card = RuleCard()
    assert card.findChild(type(card.section_heading)) is not None
    assert card.section_heading.objectName() == "section_heading"


def test_rule_card_pool_id_display_is_mono(qapp: QApplication) -> None:
    card = RuleCard()
    family_str = " ".join(card.pool_id_display.font().families()).lower()
    assert "mono" in family_str or "jetbrains" in family_str


def test_rule_card_chips_have_rarity_border(qapp: QApplication) -> None:
    from tbh_desktop.ui.theme import RARITY
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "reward_kind": "normal",
        "pool_id": 9100111, "replacement_reward_item_ids": [10],
    })
    chip = card._chips[0]
    assert chip.rarity_color() == RARITY["COMMON"]
    from PySide6.QtWidgets import QFrame
    from tbh_desktop.ui.item_card import ItemCard
    assert ItemCard.paintEvent is not QFrame.paintEvent


def test_rule_card_unknown_id_shows_fallback_label(qapp: QApplication) -> None:
    from tbh_desktop.ui.rule_card import resolve_item_label
    label, rarity = resolve_item_label(999_999_999)
    assert "999999999" in label
    assert rarity in {"COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "MYTHIC"}


def test_rule_card_known_id_resolves_name(qapp: QApplication, tmp_path, monkeypatch) -> None:
    import json
    drops = tmp_path / "drops_index.json"
    drops.write_text(json.dumps([
        {"id": 605041, "name": "Gold Amulet", "rarity": "LEGENDARY"}
    ]))
    monkeypatch.setattr("tbh_desktop.ui.rule_card._DROPS_INDEX_PATH", drops)
    from tbh_desktop.ui.rule_card import resolve_item_label
    label, rarity = resolve_item_label(605041)
    assert "Gold" in label
    assert rarity == "LEGENDARY"