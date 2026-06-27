"""Tests for ItemBrowser: tabs, filter_for_context, signals, empty states."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.active_target import RangeTarget, RuleTarget
from tbh_desktop.ui.item_browser import FilterContext, FilterScope, ItemBrowser


@pytest.fixture
def fake_gear_cache(tmp_path: Path) -> Path:
    cat = tmp_path / "gear" / "weapon"
    cat.mkdir(parents=True)
    (cat / "rare.json").write_text('[{"id": 100, "name": "Test Sword", "rarity": "RARE"}]')
    return tmp_path


@pytest.fixture
def fake_drops_index(tmp_path: Path) -> Path:
    cache = tmp_path / "drops_index.json"
    cache.write_text('[{"id": 1, "name": "Minor Ruby", "rarity": "COMMON", "family": "gem"}]')
    return cache


def test_item_browser_has_six_tabs(qapp: QApplication, fake_gear_cache, fake_drops_index) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,  # any existing path is fine
    )
    assert browser.tab_count() == 6


def test_item_browser_none_context_shows_banner(
    qapp: QApplication, fake_gear_cache, fake_drops_index,
) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,
    )
    browser.filter_for_context(None)
    assert browser.banner_visible() is True
    assert browser.grid_enabled() is False


def test_item_browser_rule_target_with_box_id_activates_box_loot(
    qapp: QApplication, fake_gear_cache, fake_drops_index,
) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,
    )
    ctx = FilterContext(box_id=42, box_name="Test", level=10, scope=FilterScope.GEAR_FOR_BOX)
    browser.filter_for_context(ctx)
    assert browser.active_tab() == "Gear (scoped)"


def test_item_browser_range_target_keeps_gear_all_visible(
    qapp: QApplication, fake_gear_cache, fake_drops_index,
) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,
    )
    browser.filter_for_context(FilterContext(box_id=None, box_name=None, level=None, scope=FilterScope.GEAR_ALL))
    assert browser.grid_enabled() is True


def test_item_browser_pick_emits_signal(
    qapp: QApplication, fake_gear_cache, fake_drops_index,
) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,
    )
    browser.filter_for_context(FilterContext(box_id=None, box_name=None, level=None, scope=FilterScope.BROWSE_ALL))
    captured: list[int] = []
    browser.item_picked.connect(lambda i: captured.append(i))
    browser._emit_pick_for_test(99)
    assert captured == [99]