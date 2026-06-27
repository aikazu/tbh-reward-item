"""Tests for ItemCard: rarity border, selection state, compact mode."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.item_card import ItemCard
from tbh_desktop.ui.theme import RARITY


def test_item_card_renders_name_and_rarity(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 42, "name": "Long Sword", "rarity": "RARE"})
    assert card.name() == "Long Sword"
    assert card.rarity() == "RARE"


def test_item_card_default_unselected(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 1, "name": "x", "rarity": "COMMON"})
    assert card.is_selected() is False


def test_item_card_set_selected_toggles_flag(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 1, "name": "x", "rarity": "RARE"})
    card.set_selected(True)
    assert card.is_selected() is True
    card.set_selected(False)
    assert card.is_selected() is False


def test_item_card_compact_uses_chip_size(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 1, "name": "x", "rarity": "COMMON"})
    card.set_compact(True)
    assert card.sizeHint().height() <= 56
    card.set_compact(False)
    assert card.sizeHint().height() >= 96


def test_item_card_unknown_rarity_falls_back_to_common(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 1, "name": "x", "rarity": "NOT_A_TIER"})
    assert card.rarity() == "COMMON"
    # Border color must still resolve to a real RARITY value.
    assert card.rarity_color() == RARITY["COMMON"]
