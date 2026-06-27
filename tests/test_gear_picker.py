"""Tests for GearPicker (G3: category+grade+level filters from cache dir)."""
from __future__ import annotations

import json

import pytest

from tbh_desktop.ui.gear_picker import GearPicker


def _write_cache(cache_dir, cat: str, grade: str, items: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"gear_{cat}_{grade}.json").write_text(
        json.dumps(items), encoding="utf-8"
    )


def _sample_item(item_id: int, name: str, level: str) -> dict:
    return {
        "id": item_id,
        "name": name,
        "rarity": "legendary",
        "type": "weapon",
        "level": level,
    }


def test_picker_builds_list_from_default_filters(qtbot, tmp_path):
    cache = tmp_path / "gear_cache"
    _write_cache(cache, "weapon", "legendary", [_sample_item(1, "Sword", "Lv65")])
    _write_cache(cache, "offhand", "immortal", [_sample_item(2, "Shield", "Lv70")])

    dlg = GearPicker(cache, None)
    qtbot.addWidget(dlg)

    # Default filters (All/All/1-100) -> union of both files.
    assert dlg.list_widget.count() == 2


def test_picker_filter_category(qtbot, tmp_path):
    cache = tmp_path / "gear_cache"
    _write_cache(cache, "weapon", "legendary", [_sample_item(1, "Sword", "Lv65")])
    _write_cache(cache, "offhand", "immortal", [_sample_item(2, "Shield", "Lv70")])

    dlg = GearPicker(cache, None)
    qtbot.addWidget(dlg)

    # Select category = Weapon.
    idx = dlg.category.findText("Weapon")
    dlg.category.setCurrentIndex(idx)

    assert dlg.list_widget.count() == 1
    assert "Sword" in dlg.list_widget.item(0).text()


def test_picker_filter_grade(qtbot, tmp_path):
    cache = tmp_path / "gear_cache"
    _write_cache(cache, "weapon", "legendary", [_sample_item(1, "Sword", "Lv65")])
    _write_cache(cache, "offhand", "immortal", [_sample_item(2, "Shield", "Lv70")])

    dlg = GearPicker(cache, None)
    qtbot.addWidget(dlg)

    # Select grade = Immortal (category stays All).
    idx = dlg.grade.findText("Immortal")
    dlg.grade.setCurrentIndex(idx)

    assert dlg.list_widget.count() == 1
    assert "Shield" in dlg.list_widget.item(0).text()


def test_picker_filter_level_range(qtbot, tmp_path):
    cache = tmp_path / "gear_cache"
    _write_cache(
        cache,
        "weapon",
        "legendary",
        [_sample_item(1, "LowBlade", "Lv1"), _sample_item(2, "HighBlade", "Lv80")],
    )

    dlg = GearPicker(cache, None)
    qtbot.addWidget(dlg)

    # Default ("All"/"All") shows both.
    assert dlg.list_widget.count() == 2

    # Level dropdowns are QComboBox populated with distinct cache levels
    # ([All, Lv1, Lv80]); pick by userData so the test is data-driven.
    # Min=Lv1 excludes nothing (Lv1 is the floor); max=Lv80 keeps both.
    dlg.level_min.setCurrentIndex(dlg.level_min.findData(1))
    assert dlg.list_widget.count() == 2

    # Tighten the range: min=Lv1, max=Lv80 — both items still match.
    dlg.level_max.setCurrentIndex(dlg.level_max.findData(80))
    assert dlg.list_widget.count() == 2

    # Raise the floor so Lv1 is excluded -> only Lv80 remains. The cleanest
    # way to express "exclude everything below 50" with cache-derived
    # dropdowns is to pick the smallest cache level that satisfies the
    # constraint — here Lv80 itself.
    dlg.level_min.setCurrentIndex(dlg.level_min.findData(80))
    assert dlg.list_widget.count() == 1
    assert "HighBlade" in dlg.list_widget.item(0).text()

    assert dlg.list_widget.count() == 1
    assert "HighBlade" in dlg.list_widget.item(0).text()


def test_picker_search_filter(qtbot, tmp_path):
    cache = tmp_path / "gear_cache"
    _write_cache(
        cache,
        "weapon",
        "legendary",
        [
            _sample_item(100, "Dragon Sword", "Lv65"),
            _sample_item(200, "Iron Axe", "Lv65"),
        ],
    )

    dlg = GearPicker(cache, None)
    qtbot.addWidget(dlg)

    assert dlg.list_widget.count() == 2

    # Type "dragon" -> only Dragon Sword visible (not hidden).
    dlg.search.setText("dragon")
    visible = [
        dlg.list_widget.item(i)
        for i in range(dlg.list_widget.count())
        if not dlg.list_widget.item(i).isHidden()
    ]
    assert len(visible) == 1
    assert "Dragon Sword" in visible[0].text()

    # Search by id substring.
    dlg.search.setText("200")
    visible = [
        dlg.list_widget.item(i)
        for i in range(dlg.list_widget.count())
        if not dlg.list_widget.item(i).isHidden()
    ]
    assert len(visible) == 1
    assert "Iron Axe" in visible[0].text()


def test_picker_selected_ids_returns_data(qtbot, tmp_path):
    cache = tmp_path / "gear_cache"
    _write_cache(
        cache,
        "weapon",
        "legendary",
        [_sample_item(11, "Alpha", "Lv65"), _sample_item(22, "Beta", "Lv65")],
    )

    dlg = GearPicker(cache, None)
    qtbot.addWidget(dlg)

    # Select both items.
    dlg.list_widget.item(0).setSelected(True)
    dlg.list_widget.item(1).setSelected(True)

    ids = dlg.selected_ids()
    assert sorted(ids) == [11, 22]


def test_picker_empty_cache_dir_shows_empty_list(qtbot, tmp_path):
    cache = tmp_path / "gear_cache"
    cache.mkdir(parents=True, exist_ok=True)

    dlg = GearPicker(cache, None)
    qtbot.addWidget(dlg)

    assert dlg.list_widget.count() == 0


def test_picker_empty_string_level_treated_as_zero(qtbot, tmp_path):
    """Empty level string -> parsed as 0. With a min filter of Lv1, the
    Lv0 item is excluded; with no min filter ("All"), it is included.
    Document this behaviour: an empty level field is treated as 0.
    """
    cache = tmp_path / "gear_cache"
    _write_cache(
        cache,
        "weapon",
        "legendary",
        [{"id": 5, "name": "NoLevel", "rarity": "legendary", "type": "weapon", "level": ""}],
    )

    dlg = GearPicker(cache, None)
    qtbot.addWidget(dlg)

    # Add an item with a real level so the level dropdowns have a non-zero
    # option to filter by — without this, the only distinct level is 0 and
    # the test cannot demonstrate the "min=1 excludes Lv0" behaviour.
    cache_weapon = cache / "gear_weapon_legendary.json"
    items = json.loads(cache_weapon.read_text(encoding="utf-8"))
    items.append({"id": 6, "name": "Lv1Item", "rarity": "legendary",
                  "type": "weapon", "level": "Lv1"})
    cache_weapon.write_text(json.dumps(items), encoding="utf-8")
    # Trigger a rebuild with the new cache file.
    dlg._view._rebuild()

    # Default ("All") shows both items.
    assert dlg.list_widget.count() == 2

    # Min filter = Lv1 -> only the Lv1 item remains (Lv0 excluded).
    dlg.level_min.setCurrentIndex(dlg.level_min.findData(1))
    assert dlg.list_widget.count() == 1
    assert "Lv1Item" in dlg.list_widget.item(0).text()

    # Reset min to "All" (no filter) -> both items shown again.
    dlg.level_min.setCurrentIndex(0)
    assert dlg.list_widget.count() == 2
