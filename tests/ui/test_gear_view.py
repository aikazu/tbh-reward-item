"""Tests for the extracted GearView (non-dialog, embeddable widget)."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.gear_picker import GearView


@pytest.fixture
def fake_cache(tmp_path: Path) -> Path:
    """Build a tiny gear cache matching the layout GearView reads."""
    cat_dir = tmp_path / "gear" / "weapon"
    cat_dir.mkdir(parents=True)
    (cat_dir / "rare.json").write_text(
        '[{"id": 100, "name": "Test Sword", "rarity": "RARE"}]'
    )
    return tmp_path


def test_gear_view_loads_with_cache(qapp: QApplication, fake_cache: Path) -> None:
    view = GearView(fake_cache)
    assert view.size().isValid()


def test_gear_view_filter_rebuilds(qapp: QApplication, fake_cache: Path) -> None:
    view = GearView(fake_cache)
    view.set_category("Weapon")
    view.set_grade("Rare")
    items = view.visible_items()
    assert any(i.get("id") == 100 for i in items)


def test_gear_view_no_cache_renders_empty_state(
    qapp: QApplication, tmp_path: Path
) -> None:
    view = GearView(tmp_path)
    items = view.visible_items()
    assert items == []
    assert view.empty_state_visible() is True