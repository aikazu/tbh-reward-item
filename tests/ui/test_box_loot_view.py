"""Tests for the extracted BoxLootView (non-dialog, embeddable widget)."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.box_loot_picker import BoxLootView


SAMPLE_LOOT = [
    {"id": 1, "name": "Minor Ruby", "kind": "material", "rarity": "COMMON", "family": "gem"},
    {"id": 2, "name": "Soul Stone", "kind": "material", "rarity": "RARE",   "family": "stone"},
    {"id": 3, "name": "Gold Ingot", "kind": "material", "rarity": "EPIC",   "family": "metal"},
]


def test_box_loot_view_renders(qapp: QApplication) -> None:
    view = BoxLootView(items=SAMPLE_LOOT, scope_box_name="Test Box", mode="box_loot")
    assert view.size().isValid()


def test_box_loot_view_filter_by_family(qapp: QApplication) -> None:
    view = BoxLootView(items=SAMPLE_LOOT, mode="box_loot")
    view.set_family_filter("gem")
    assert all(i["family"] == "gem" for i in view.visible_items())


def test_box_loot_view_selected_ids(qapp: QApplication) -> None:
    view = BoxLootView(items=SAMPLE_LOOT, mode="box_loot")
    # Pretend the user clicked rows with ids 1 and 3.
    view.set_selected_ids_for_test([1, 3])
    assert view.selected_ids() == [1, 3]