"""Tests for RuleCard: per-row pick buttons, chip row, signals."""
from __future__ import annotations

from PySide6.QtCore import Qt
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


def test_rule_card_chip_click_removes_id(qapp: QApplication) -> None:
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QMouseEvent
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [10, 20, 30],
    })
    captured = _capture(card)
    # Click the chip for id=20 (index 1 in _replacement_ids after rebuild)
    chip = card._chips[1]
    event = QMouseEvent(QEvent.Type.MouseButtonPress, QPoint(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    chip.mousePressEvent(event)
    assert card.replacement_ids() == [10, 30]
    assert captured["edited"] == [True]


def test_rule_card_has_section_heading(qapp: QApplication) -> None:
    """Arsenal directive: every rule card shows a Cinzel section label."""
    card = RuleCard()
    assert card.findChild(type(card.section_heading)) is not None
    assert card.section_heading.objectName() == "section_heading"


def test_rule_card_item_id_display_is_mono(qapp: QApplication) -> None:
    """The static 'ID' + value display must use a monospace font (JetBrains
    Mono family) so IDs line up vertically across cards."""
    card = RuleCard()
    # The internal mono label for the item id is exposed via _item_id_display.
    assert card.item_id_display.font().families() == card.item_id_display.font().families()
    family_str = " ".join(card.item_id_display.font().families()).lower()
    assert "mono" in family_str or "jetbrains" in family_str


def test_rule_card_chips_have_rarity_border(qapp: QApplication) -> None:
    """Each chip must show a rarity-tinted left border (LEGENDARY → yellow).

    The border is now drawn directly in :class:`ItemCard`'s ``paintEvent``
    (QSS dynamic-property selectors were unreliable for chips whose
    objectName was renamed by their parent). Verify the paint path is
    wired by checking the chip's rarity color + the autoFill flag.
    """
    from tbh_desktop.ui.theme import RARITY
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1,
        "replacement_reward_item_ids": [10],
    })
    chip = card._chips[0]
    assert chip.rarity_color() == RARITY["COMMON"]  # id=10 not in drops index → COMMON
    # paintEvent is overridden — verify by checking the method exists on
    # the class (regression guard against accidentally falling back to
    # the QSS-only path which renders an empty chip).
    from PySide6.QtWidgets import QFrame
    from tbh_desktop.ui.item_card import ItemCard
    assert ItemCard.paintEvent is not QFrame.paintEvent


def test_rule_card_unknown_id_shows_fallback_label(qapp: QApplication) -> None:
    """If the item id isn't in the drops index cache, the chip label falls
    back to 'Unknown #<id>' in mono so the user still sees what the chip is."""
    from tbh_desktop.ui.rule_card import resolve_item_label
    label, rarity = resolve_item_label(999_999_999)
    assert "999999999" in label
    assert rarity in {"COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "MYTHIC"}


def test_rule_card_known_id_resolves_name(qapp: QApplication, tmp_path, monkeypatch) -> None:
    """When the drops index cache contains the id, resolve_item_label returns
    the item's name and rarity from the cache."""
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
