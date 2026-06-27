"""Tests for BoxLootView: set_items swaps data without rebuilding the widget."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.box_loot_picker import BoxLootView


@pytest.fixture
def box_loot_cache(tmp_path: Path) -> Path:
    cache = tmp_path / "box_loot_cache"
    cache.mkdir()
    (cache / "910751.json").write_text(
        '[{"id": 500014, "name": "Fighter Helmet", "kind": "gear"},'
        ' {"id": 605041, "name": "Gold Amulet", "kind": "material", "family": "DECORATION"}]'
    )
    return cache


def test_set_items_swaps_data(qapp: QApplication, box_loot_cache: Path) -> None:
    """Arsenal directive: BoxLootView must expose set_items() so the
    ItemBrowser can swap in a specific box's loot list when the user
    selects a rule — no widget rebuild, no dialog round-trip."""
    view = BoxLootView(items=[], mode="box_loot")
    assert len(view._all_items) == 0

    from tbh_desktop.scraper import read_box_cache
    items = read_box_cache(box_loot_cache, 910751)
    view.set_items(items)

    # Both items loaded (mode="box_loot" keeps materials, drops gear).
    assert len(view._all_items) == 1
    assert view._all_items[0]["id"] == 605041


def test_set_items_preserves_filters(qapp: QApplication) -> None:
    """After set_items, the rarity + family + search filters must still
    apply — they're UI state that should not be wiped by data swap."""
    view = BoxLootView(
        items=[
            {"id": 1, "name": "Common Stone", "kind": "material", "rarity": "COMMON", "family": "CRAFTING"},
            {"id": 2, "name": "Rare Stone", "kind": "material", "rarity": "RARE", "family": "CRAFTING"},
        ],
        mode="materials",
    )
    # Set rarity filter to RARE before swap.
    rare_idx = view.rarity_filter.findData("RARE")
    view.rarity_filter.setCurrentIndex(rare_idx)

    # Swap in two new items (still has RARE).
    view.set_items([
        {"id": 3, "name": "Epic Stone", "kind": "material", "rarity": "EPIC", "family": "CRAFTING"},
        {"id": 4, "name": "Rare Stone 2", "kind": "material", "rarity": "RARE", "family": "CRAFTING"},
    ])

    # Filter should still be RARE, so only the Rare Stone 2 shows.
    visible = view.visible_items()
    assert len(visible) == 1
    assert visible[0]["id"] == 4


def test_set_items_with_mode_filter(qapp: QApplication) -> None:
    """box_loot mode must drop gear items from the swap, keeping only
    materials (gear has its own picker)."""
    view = BoxLootView(items=[], mode="box_loot")
    view.set_items([
        {"id": 10, "name": "Sword", "kind": "gear"},
        {"id": 11, "name": "Ruby", "kind": "material", "family": "DECORATION"},
        {"id": 12, "name": "Soulstone", "kind": "material", "family": "SOULSTONE"},
    ])
    # box_loot mode keeps materials only.
    assert {it["id"] for it in view._all_items} == {11, 12}


def test_row_label_shows_rarity_and_family(qapp: QApplication) -> None:
    """Arsenal directive: rows must surface rarity + family inline so the
    user can scan the list without hovering every item. Tooltip-only
    metadata was the 'looks like all other items' complaint."""
    view = BoxLootView(
        items=[
            {"id": 1, "name": "Bronze Ingot", "kind": "material",
             "rarity": "UNCOMMON", "family": "CRAFTING"},
        ],
        mode="materials",
    )
    # Row 0 is the family header ("── Crafting ──"); the data row is next.
    data_row = next(
        i for i in range(view.list_widget.count())
        if view.list_widget.item(i).data(0x0100) is not None
    )
    text = view.list_widget.item(data_row).text()
    assert "UNCOMMON" in text, f"rarity missing from row: {text!r}"
    assert "Crafting" in text, f"family missing from row: {text!r}"
    assert "Bronze Ingot" in text