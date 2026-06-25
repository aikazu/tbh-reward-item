"""Tests for scraper."""
from __future__ import annotations

from pathlib import Path

from tbh_desktop import scraper

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_gear_page_returns_obtainable_only() -> None:
    html = (FIXTURES / "gear_page.html").read_text(encoding="utf-8")
    items = scraper.parse_gear_page(html)
    # 300001 Long Sword + 300002 Iron Shield are obtainable; 300006 Heavy Blade
    # carries is-deleted class and must be skipped.
    ids = [i["id"] for i in items]
    assert len(items) == 2
    assert 300001 in ids
    assert 300002 in ids
    assert 300006 not in ids
    long_sword = next(i for i in items if i["id"] == 300001)
    assert long_sword["name"] == "Long Sword"
    assert long_sword["rarity"] == "Common"
    assert long_sword["type"] == "Sword"
    assert long_sword["level"] == "Lv1"
    iron_shield = next(i for i in items if i["id"] == 300002)
    assert iron_shield["name"] == "Iron Shield"
    assert iron_shield["rarity"] == "Uncommon"
    assert iron_shield["type"] == "Shield"
    assert iron_shield["level"] == "Lv5"


def test_parse_gear_page_extracts_id_from_href() -> None:
    html = (FIXTURES / "gear_page.html").read_text(encoding="utf-8")
    items = scraper.parse_gear_page(html)
    assert items[0]["id"] == 300001
    # all items have int ids parsed from href
    for i in items:
        assert isinstance(i["id"], int)


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
    slug_cache = tmp_path / "box_slug_cache.json"
    items_html = (FIXTURES / "items_page.html").read_text(encoding="utf-8")
    box_html = (FIXTURES / "box_page.html").read_text(encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        items_resp = type(
            "R", (), {"text": items_html, "raise_for_status": lambda self: None}
        )()
        box_resp = type(
            "R", (), {"text": box_html, "raise_for_status": lambda self: None}
        )()
        mock_get.side_effect = [items_resp, box_resp]
        loot = scraper.refresh_box_loot(cache_dir, 910801, slug_cache_path=slug_cache)
    assert 500017 in [l["id"] for l in loot]
    assert scraper.read_box_cache(cache_dir, 910801) == loot


def test_resolve_box_id_slug_from_items_page(tmp_path: Path) -> None:
    cache = tmp_path / "box_slug_cache.json"
    items_html = (FIXTURES / "items_page.html").read_text(encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        mock_get.return_value.text = items_html
        mock_get.return_value.raise_for_status = lambda: None
        slug = scraper.resolve_box_id_slug(910801, cache_path=cache)
    assert slug == "normal-monster-box-lv80"


def test_resolve_box_id_slug_uses_cache_file(tmp_path: Path) -> None:
    cache = tmp_path / "box_slug_cache.json"
    cache.write_text('{"910801": "cached-slug"}', encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        slug = scraper.resolve_box_id_slug(910801, cache_path=cache)
        mock_get.assert_not_called()
    assert slug == "cached-slug"


def test_resolve_box_id_slug_writes_cache_on_fetch(tmp_path: Path) -> None:
    cache = tmp_path / "box_slug_cache.json"
    items_html = (FIXTURES / "items_page.html").read_text(encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        mock_get.return_value.text = items_html
        mock_get.return_value.raise_for_status = lambda: None
        scraper.resolve_box_id_slug(910801, cache_path=cache)
    import json

    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data["910801"] == "normal-monster-box-lv80"
    # all rows cached, not just queried
    assert data["920001"] == "stage-boss-box-1"
    assert data["930002"] == "elite-monster-box-lv50"


def test_resolve_box_id_slug_not_found_returns_none(tmp_path: Path) -> None:
    cache = tmp_path / "box_slug_cache.json"
    items_html = (FIXTURES / "items_page.html").read_text(encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        mock_get.return_value.text = items_html
        mock_get.return_value.raise_for_status = lambda: None
        slug = scraper.resolve_box_id_slug(999999, cache_path=cache)
    assert slug is None


def test_refresh_box_loot_uses_slug_lookup(tmp_path: Path) -> None:
    cache_dir = tmp_path / "box_loot_cache"
    slug_cache = tmp_path / "box_slug_cache.json"
    items_html = (FIXTURES / "items_page.html").read_text(encoding="utf-8")
    box_html = (FIXTURES / "box_page.html").read_text(encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        # First call: items page (slug lookup). Second call: box page.
        items_resp = mock_get.return_value
        items_resp.text = items_html
        items_resp.raise_for_status = lambda: None
        # Configure side_effect to return items then box page
        box_resp = type("R", (), {"text": box_html, "raise_for_status": lambda self: None})()
        mock_get.side_effect = [items_resp, box_resp]
        loot = scraper.refresh_box_loot(cache_dir, 910801, slug_cache_path=slug_cache)
    assert 500017 in [l["id"] for l in loot]
    # box page fetched with correct slug-derived URL
    urls = [call.args[0] for call in mock_get.call_args_list]
    assert any("910801-normal-monster-box-lv80" in u for u in urls)


# ---------------------------------------------------------------------------
# G3 — playwright-based full gear scraper (per category x grade)
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock  # noqa: E402

GEAR_HTML = (FIXTURES / "gear_page.html").read_text(encoding="utf-8")


def _load_more_button_mock() -> MagicMock:
    """A fake LOAD MORE button element. ``click`` appends more cards by
    mutating shared state via closures wired by the caller."""
    return MagicMock(name="load_more_btn")


def test_scrape_gear_batch_parses_cards_and_clicks_load_more() -> None:
    """scrape_gear_batch parses cards from page.content(), clicks LOAD MORE
    until the button is gone, skips is-deleted, dedups by id."""
    page = MagicMock(name="page")
    # Two phases of page content: first 3 cards (2 obtainable + 1 deleted),
    # second click appends 1 new obtainable + repeats the first obtainable
    # (dedup by id).
    phase_a = GEAR_HTML
    phase_b = (
        GEAR_HTML
        + '<a href="/items/300099-arcane-blade" class="entity-card">'
        '<div class="entity-card-tag">Arcane</div>'
        '<div class="entity-card-name">Arcane Blade</div>'
        '<div class="entity-card-meta">Lv50 | Sword</div></a>'
    )
    contents = [phase_a, phase_b]

    def fake_content() -> str:
        # Always reflect the latest appended phase.
        return contents[-1]

    page.content.side_effect = fake_content

    # LOAD MORE button: first query returns a button whose click pops a phase
    # and appends to content; second query returns None (button gone).
    click_count = {"n": 0}

    def fake_query_selector(selector: str):
        # The scraper queries the LOAD MORE button via a CSS selector; the first
        # call returns a button whose click appends phase_b, subsequent calls
        # return None (button gone).
        if click_count["n"] == 0:
            btn = MagicMock(name="load_more_btn")

            def on_click(*a, **k):
                click_count["n"] += 1
                # After first click, append phase_b (simulating +60 cards).
                contents.append(phase_b)

            btn.click.side_effect = on_click
            return btn
        else:
            return None

    page.query_selector.side_effect = fake_query_selector
    page.wait_for_timeout = lambda *_a, **_k: None
    page.wait_for_load_state = lambda *_a, **_k: None

    items = scraper.scrape_gear_batch(page, max_clicks=10)

    ids = [i["id"] for i in items]
    # is-deleted 300006 skipped; 300099 appended; 300001 deduped.
    assert 300001 in ids
    assert 300002 in ids
    assert 300099 in ids
    assert 300006 not in ids
    # 300001 appears in both phases but listed once (dedup).
    assert ids.count(300001) == 1
    arcane = next(i for i in items if i["id"] == 300099)
    assert arcane["name"] == "Arcane Blade"
    assert arcane["rarity"] == "Arcane"
    # LOAD MORE was clicked at least once then stopped.
    assert click_count["n"] >= 1


def test_select_gear_filters_clicks_chips_and_checkbox() -> None:
    """_select_gear_filters clicks the Type chip, Rarity chip, and checks the
    Obtainable-only checkbox on the page."""
    page = MagicMock(name="page")

    # page.query_selector returns a clickable element per selector text match.
    def fake_query_selector(selector: str):
        # The scraper queries chips by visible text; return a mock element.
        el = MagicMock(name=f"el[{selector}]")
        el.click = MagicMock(name=f"click[{selector}]")
        return el

    page.query_selector.side_effect = fake_query_selector
    # page.locator(...).filter(has_text=...).click() pattern — provide a chain.
    locator = MagicMock(name="locator")
    locator.filter.return_value = locator
    locator.click = MagicMock(name="locator.click")
    locator.check = MagicMock(name="locator.check")
    page.locator.return_value = locator

    scraper._select_gear_filters(page, "weapon", "legendary", obtainable_only=True)

    # At least one click happened on a chip; checkbox checked.
    assert locator.click.called
    assert locator.check.called


def test_refresh_gear_full_writes_per_category_grade(tmp_path: Path) -> None:
    """refresh_gear_full writes one cache file per (category, grade) combo and
    returns a dict keyed by '{cat}_{grade}'."""
    out_dir = tmp_path / "gear_cache"

    # Fake playwright: patch sync_playwright so launch returns a context with
    # a page whose content() returns GEAR_HTML and selectors behave.
    page = MagicMock(name="page")
    page.content.return_value = GEAR_HTML
    page.query_selector.return_value = None  # no LOAD MORE button
    page.wait_for_timeout = lambda *_a, **_k: None
    page.wait_for_load_state = lambda *_a, **_k: None
    page.goto = MagicMock(name="goto")

    context = MagicMock(name="context")
    context.new_page.return_value = page
    context.close = MagicMock(name="close")

    browser = MagicMock(name="browser")
    browser.new_context.return_value = context
    browser.close = MagicMock(name="close")

    pw = MagicMock(name="playwright")
    pw.chromium.launch.return_value = browser

    class _CM:
        def __enter__(self):
            return pw

        def __exit__(self, *a):
            return False

    with patch("tbh_desktop.scraper.sync_playwright", return_value=_CM()):
        result = scraper.refresh_gear_full(
            out_dir,
            categories=["weapon", "offhand"],
            grades=["legendary", "immortal"],
        )

    # 4 cache files written (weapon x legendary/immortal, offhand x ...).
    expected = {
        "gear_weapon_legendary.json",
        "gear_weapon_immortal.json",
        "gear_offhand_legendary.json",
        "gear_offhand_immortal.json",
    }
    written = {p.name for p in out_dir.iterdir()}
    assert expected <= written
    assert set(result.keys()) == {"weapon_legendary", "weapon_immortal", "offhand_legendary", "offhand_immortal"}
    # each file parses back to the fixture's obtainable items.
    loaded = scraper.read_gear_cache(out_dir / "gear_weapon_legendary.json")
    assert 300001 in [i["id"] for i in loaded]
    assert 300006 not in [i["id"] for i in loaded]


def test_refresh_gear_full_falls_back_to_cache_on_error(tmp_path: Path) -> None:
    """If playwright launch raises, existing cache files are preserved and
    their items returned (per-combo fallback)."""
    out_dir = tmp_path / "gear_cache"
    out_dir.mkdir(parents=True)
    cached = [{"id": 777, "name": "Cached Legendary", "rarity": "Legendary", "type": "Sword"}]
    scraper.write_gear_cache(out_dir / "gear_weapon_legendary.json", cached)

    class _CM:
        def __enter__(self):
            raise RuntimeError("playwright launch failed")

        def __exit__(self, *a):
            return False

    with patch("tbh_desktop.scraper.sync_playwright", return_value=_CM()):
        result = scraper.refresh_gear_full(
            out_dir,
            categories=["weapon"],
            grades=["legendary"],
        )

    # existing cache preserved + returned.
    assert scraper.read_gear_cache(out_dir / "gear_weapon_legendary.json") == cached
    assert result["weapon_legendary"] == cached
