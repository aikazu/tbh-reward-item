"""Tests for scraper."""
from __future__ import annotations

from pathlib import Path

import pytest

from tbh_desktop import scraper

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_gear_page_returns_obtainable_only() -> None:
    html = (FIXTURES / "gear_page.html").read_text(encoding="utf-8")
    items = scraper.parse_gear_page(html)
    # Long Sword is obtainable; Short Sword is not (no obtainable class).
    ids = [i["id"] for i in items]
    assert 300001 in ids
    assert 300002 not in ids
    long_sword = next(i for i in items if i["id"] == 300001)
    assert long_sword["name"] == "Long Sword"
    assert long_sword["rarity"] == "Common"
    assert long_sword["type"] == "Sword"


def test_parse_gear_page_extracts_id_from_href() -> None:
    html = (FIXTURES / "gear_page.html").read_text(encoding="utf-8")
    items = scraper.parse_gear_page(html)
    assert items[0]["id"] == 300001
