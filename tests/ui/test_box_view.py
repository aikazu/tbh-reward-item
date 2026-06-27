"""Tests for the extracted BoxView (non-dialog, embeddable widget)."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.box_picker import BoxView


@pytest.fixture
def slug_cache(tmp_path: Path) -> Path:
    cache = tmp_path / "box_slug_cache.json"
    cache.write_text(
        '{"boxes": [{"id": 100, "name": "Wooden Chest"}, '
        '{"id": 200, "name": "Iron Chest"}]}'
    )
    return cache


def test_box_view_renders(qapp: QApplication, slug_cache: Path) -> None:
    view = BoxView(slug_cache)
    assert view.size().isValid()


def test_box_view_filter_by_name(qapp: QApplication, slug_cache: Path) -> None:
    view = BoxView(slug_cache)
    view.set_name_filter("Iron")
    assert all("Iron" in b["name"] for b in view.visible_boxes())


def test_box_view_selected_box_id(qapp: QApplication, slug_cache: Path) -> None:
    view = BoxView(slug_cache)
    view.set_selected_box_id_for_test(200)
    assert view.selected_box_id() == 200
