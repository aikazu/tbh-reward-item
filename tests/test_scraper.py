"""Tests for scraper."""
from __future__ import annotations

from pathlib import Path

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


def test_parse_box_page_returns_loot_with_ids() -> None:
    html = (FIXTURES / "box_page.html").read_text(encoding="utf-8")
    loot = scraper.parse_box_page(html)
    ids = [l["id"] for l in loot]
    # gear id from image path HELMET_500017.png
    assert 500017 in ids
    # material id from href 141001-bronze-ingot
    assert 141001 in ids
    helmet = next(l for l in loot if l["id"] == 500017)
    assert helmet["name"] == "Dimensional Helmet"
    assert helmet["rate"] == "7.9%"


def test_cache_gear_round_trip(tmp_path: Path) -> None:
    cache = tmp_path / "gear_cache.json"
    items = [{"id": 1, "name": "X", "rarity": "Common", "type": "Sword"}]
    scraper.write_gear_cache(cache, items)
    loaded = scraper.read_gear_cache(cache)
    assert loaded == items


def test_cache_box_loot_round_trip(tmp_path: Path) -> None:
    cache_dir = tmp_path / "box_loot_cache"
    cache_dir.mkdir()
    loot = [{"id": 500017, "name": "Helmet", "rate": "7.9%"}]
    scraper.write_box_cache(cache_dir, 910801, loot)
    loaded = scraper.read_box_cache(cache_dir, 910801)
    assert loaded == loot


def test_read_gear_cache_missing_returns_empty(tmp_path: Path) -> None:
    assert scraper.read_gear_cache(tmp_path / "nope.json") == []


def test_read_box_cache_missing_returns_empty(tmp_path: Path) -> None:
    assert scraper.read_box_cache(tmp_path / "box_loot_cache", 910801) == []


def test_resolve_box_slug_from_name() -> None:
    # Normal Monster Box Lv80 -> normal-monster-box-lv80
    assert scraper.resolve_box_slug("Normal Monster Box Lv80") == "normal-monster-box-lv80"


from unittest.mock import patch


def test_refresh_gear_fetches_parses_caches(tmp_path: Path) -> None:
    cache = tmp_path / "gear_cache.json"
    html = (FIXTURES / "gear_page.html").read_text(encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status = lambda: None
        items = scraper.refresh_gear(cache)
    assert 300001 in [i["id"] for i in items]
    # cache written
    assert scraper.read_gear_cache(cache) == items


def test_refresh_gear_falls_back_to_cache_on_error(tmp_path: Path) -> None:
    cache = tmp_path / "gear_cache.json"
    cached = [{"id": 99, "name": "Cached", "rarity": "Common", "type": "Sword"}]
    scraper.write_gear_cache(cache, cached)
    with patch("tbh_desktop.scraper.requests.get", side_effect=Exception("network")):
        items = scraper.refresh_gear(cache)
    assert items == cached


def test_refresh_box_loot_fetches_parses_caches(tmp_path: Path) -> None:
    cache_dir = tmp_path / "box_loot_cache"
    html = (FIXTURES / "box_page.html").read_text(encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status = lambda: None
        loot = scraper.refresh_box_loot(cache_dir, 910801, "normal-monster-box-lv80")
    assert 500017 in [l["id"] for l in loot]
    assert scraper.read_box_cache(cache_dir, 910801) == loot
