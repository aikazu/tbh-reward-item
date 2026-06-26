"""Tests for scraper."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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
    # New G5 fields: image + rarity_color from .entity-card-art and --rc
    assert long_sword["image"] == "https://taskbarhero.wiki/game/gear/sword/SWORD_300001.png"
    assert long_sword["rarity_color"] == "#e4e4e4"
    iron_shield = next(i for i in items if i["id"] == 300002)
    assert iron_shield["name"] == "Iron Shield"
    assert iron_shield["rarity"] == "Uncommon"
    assert iron_shield["type"] == "Shield"
    assert iron_shield["level"] == "Lv5"
    assert iron_shield["rarity_color"] == "#a0e4a4"


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
    # G5: box_id/box_name stamping (default 0/"" when not passed)
    assert helmet["box_id"] == 0
    assert helmet["box_name"] == ""


def test_parse_box_page_stamps_box_id_and_name() -> None:
    """When box_id/box_name are passed to parse_box_page, they're stamped on
    every loot entry — needed to build the per-item drop map."""
    html = (FIXTURES / "box_page.html").read_text(encoding="utf-8")
    loot = scraper.parse_box_page(html, box_id=910801, box_name="Normal Monster Box Lv80")
    assert all(l["box_id"] == 910801 for l in loot)
    assert all(l["box_name"] == "Normal Monster Box Lv80" for l in loot)


def test_parse_box_page_classifies_kind_and_extracts_image() -> None:
    """parse_box_page now tags each loot entry with kind (gear vs material)
    and the image URL. Gear entry comes from HELMET_*.png regex; material
    entry from Item_*.png regex."""
    html = (FIXTURES / "box_page.html").read_text(encoding="utf-8")
    loot = scraper.parse_box_page(html, box_id=910801, box_name="Test Box")
    helmet = next(l for l in loot if l["id"] == 500017)
    bronze = next(l for l in loot if l["id"] == 141001)
    # ID-range verification: 5xxxxx = armor (gear)
    assert helmet["kind"] == "gear"
    assert "HELMET_500017" in helmet["image"]
    # 1xxxxx = material
    assert bronze["kind"] == "material"
    assert "Item_141001" in bronze["image"]


def test_parse_box_page_kind_fallback_by_id_range() -> None:
    """When no image matches, kind is inferred from the item ID prefix."""
    # Minimal HTML with an href but no <img> — kind must fall back to id range.
    html = """<html><body>
    <h2>Loot table</h2>
    <table><tbody>
    <tr><td><a href="/items/123456789-test">Mystery</a></td><td>5%</td></tr>
    </tbody></table></body></html>"""
    loot = scraper.parse_box_page(html)
    assert loot[0]["id"] == 123456789
    # No image src matched — fall back to ID range.
    assert loot[0]["kind"] == "material"


def test_parse_drops_page_extracts_table_rows() -> None:
    """parse_drops_page reads data-* attributes from each <tr> in the
    /en/tools/drops/ table."""
    html = (FIXTURES / "drops_page_mini.html").read_text(encoding="utf-8")
    items = scraper.parse_drops_page(html)
    assert len(items) >= 20
    # Spot-check fields
    ruby = next((it for it in items if it["id"] == 110001), None)
    assert ruby is not None
    assert ruby["name"] == "Minor Ruby"
    assert ruby["kind"] == "material"
    assert ruby["rarity"] == "COMMON"
    assert ruby["family"] == "DECORATION"


def test_parse_drops_page_round_trip() -> None:
    """write_drops_index + read_drops_index preserves items as a list."""
    import tempfile
    html = (FIXTURES / "drops_page_mini.html").read_text(encoding="utf-8")
    items = scraper.parse_drops_page(html)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "drops.json"
        scraper.write_drops_index(p, items)
        loaded = scraper.read_drops_index(p)
        assert loaded == items
        # Missing file → []
        assert scraper.read_drops_index(Path(tmp) / "missing.json") == []


def test_box_loot_picker_filters_gear() -> None:
    """BoxLootPicker skips items with kind == 'gear'."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    from tbh_desktop.ui.box_loot_picker import BoxLootPicker
    items = [
        {"id": 110001, "name": "Minor Ruby", "kind": "material", "rarity": "COMMON", "family": "DECORATION"},
        {"id": 910011, "name": "Box Lv1", "kind": "stage-box", "rarity": "COMMON", "family": "Normal Monster"},
        {"id": 303011, "name": "Long Sword", "kind": "gear", "rarity": "Common", "family": ""},
    ]
    dlg = BoxLootPicker(items=items)
    # Only non-gear shown
    selectable = [
        dlg.list_widget.item(i)
        for i in range(dlg.list_widget.count())
        if dlg.list_widget.item(i).data(__import__("PySide6").QtCore.Qt.ItemDataRole.UserRole) is not None
    ]
    assert len(selectable) == 2
    ids = {item.data(__import__("PySide6").QtCore.Qt.ItemDataRole.UserRole) for item in selectable}
    assert ids == {110001, 910011}


def test_box_loot_picker_sorts_by_family_then_rarity() -> None:
    """Items grouped: rarity COMMON → COSMIC within each family."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    from tbh_desktop.ui.box_loot_picker import BoxLootPicker
    items = [
        {"id": 200, "name": "X", "kind": "material", "rarity": "LEGENDARY", "family": "DECORATION"},
        {"id": 100, "name": "Y", "kind": "material", "rarity": "COMMON", "family": "CRAFTING"},
        {"id": 300, "name": "Z", "kind": "material", "rarity": "COMMON", "family": "DECORATION"},
    ]
    dlg = BoxLootPicker(items=items)
    # First selectable item should be id=100 (CRAFTING COMMON comes first).
    selectable_ids = [
        dlg.list_widget.item(i).data(__import__("PySide6").QtCore.Qt.ItemDataRole.UserRole)
        for i in range(dlg.list_widget.count())
        if dlg.list_widget.item(i).data(__import__("PySide6").QtCore.Qt.ItemDataRole.UserRole) is not None
    ]
    assert selectable_ids == [100, 300, 200]  # CRAFTING COMMON → DECORATION COMMON → DECORATION LEGENDARY


def test_build_box_drop_map_groups_by_item() -> None:
    """Two boxes dropping the same item → that item maps to a 2-entry list."""
    loot = [
        {"id": 500017, "name": "Dimensional Helmet", "rate": "7.9%", "box_id": 910801, "box_name": "Box80"},
        {"id": 500017, "name": "Dimensional Helmet", "rate": "12.0%", "box_id": 910901, "box_name": "Box90"},
        {"id": 141001, "name": "Bronze Ingot", "rate": "1.5%", "box_id": 910801, "box_name": "Box80"},
    ]
    drop_map = scraper.build_box_drop_map(loot)
    assert set(drop_map.keys()) == {500017, 141001}
    assert len(drop_map[500017]) == 2
    # Sorted by box_id ascending.
    assert drop_map[500017][0]["box_id"] == 910801
    assert drop_map[500017][1]["box_id"] == 910901


def test_box_drop_cache_round_trip(tmp_path: Path) -> None:
    """write_box_drop_cache + read_box_drop_cache preserves keys as ints."""
    cache = tmp_path / "drop_map.json"
    drop_map = {500017: [{"box_id": 910801, "box_name": "Box80", "rate": "7.9%"}]}
    scraper.write_box_drop_cache(cache, drop_map)
    loaded = scraper.read_box_drop_cache(cache)
    assert loaded == drop_map
    # Missing file → empty dict
    assert scraper.read_box_drop_cache(tmp_path / "missing.json") == {}
    # Invalid JSON → empty dict (no crash)
    bad = tmp_path / "bad.json"
    bad.write_text("not json {")
    assert scraper.read_box_drop_cache(bad) == {}


def test_parse_item_detail_extracts_flavor_and_stats() -> None:
    """parse_item_detail extracts meta description as flavor and <dl> pairs as stats."""
    html = (FIXTURES / "item_detail.html").read_text(encoding="utf-8")
    detail = scraper.parse_item_detail(html)
    assert "flavor" in detail
    assert "sturdy iron blade" in detail["flavor"]
    assert "stats" in detail
    assert detail["stats"]["Attack"] == "+3"
    assert detail["stats"]["Required Level"] == "1"


def test_parse_item_detail_empty_on_minimal_html() -> None:
    """Empty HTML → empty dict (no crash)."""
    assert scraper.parse_item_detail("") == {}
    assert scraper.parse_item_detail("<html><body><p>Nothing here.</p></body></html>") == {}


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


def test_select_gear_filters_clicks_chips_and_toggle() -> None:
    """_select_gear_filters clicks the Type chip, Rarity chip, and toggles the
    Obtainable-only checkbox via its .gear-toggle-box wrapper.

    The checkbox itself is overlaid by a <span class="gear-toggle-box"> that
    intercepts pointer events, so .check() on the input times out (30s). The
    wrapper span is the real Svelte click target — click that instead, and only
    when the checkbox is not already checked.
    """
    page = MagicMock(name="page")
    locator = MagicMock(name="locator")
    locator.filter.return_value = locator
    locator.is_checked.return_value = False
    page.locator.return_value = locator

    scraper._select_gear_filters(page, "weapon", "legendary", obtainable_only=True)

    # chips + the toggle-box wrapper clicked via locator(...).click()
    assert locator.click.called
    # the broken .check() path must NOT be used
    locator.check.assert_not_called()
    # is_checked consulted so we don't double-toggle an already-on checkbox
    assert locator.is_checked.called
    selectors = [c.args[0] for c in page.locator.call_args_list if c.args]
    assert ".gear-toggle-box" in selectors


def test_select_gear_filters_skips_toggle_when_already_checked() -> None:
    """If the Obtainable-only checkbox is already checked, do not click the
    toggle again (would turn it off)."""
    page = MagicMock(name="page")
    locator = MagicMock(name="locator")
    locator.filter.return_value = locator
    locator.is_checked.return_value = True
    page.locator.return_value = locator

    scraper._select_gear_filters(page, "weapon", "legendary", obtainable_only=True)

    # only chip clicks (2), no toggle-box click for the checkbox
    toggle_calls = [c for c in page.locator.call_args_list if c.args and c.args[0] == ".gear-toggle-box"]
    assert toggle_calls == []


def test_refresh_gear_full_writes_per_category_grade(tmp_path: Path) -> None:
    """refresh_gear_full writes one cache file per (category, grade) combo and
    returns a dict keyed by '{cat}_{grade}'."""
    out_dir = tmp_path / "gear_cache"

    # Fake browser: patch _stealth_launch so launch returns a context with
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

    with patch("tbh_desktop.scraper._stealth_launch", return_value=browser):
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
    """If browser launch raises, existing cache files are preserved and
    their items returned (per-combo fallback)."""
    out_dir = tmp_path / "gear_cache"
    out_dir.mkdir(parents=True)
    cached = [{"id": 777, "name": "Cached Legendary", "rarity": "Legendary", "type": "Sword"}]
    scraper.write_gear_cache(out_dir / "gear_weapon_legendary.json", cached)

    def _boom(*_a, **_k):
        raise RuntimeError("browser launch failed")

    with patch("tbh_desktop.scraper._stealth_launch", side_effect=_boom):
        result = scraper.refresh_gear_full(
            out_dir,
            categories=["weapon"],
            grades=["legendary"],
        )

    # existing cache preserved + returned.
    assert scraper.read_gear_cache(out_dir / "gear_weapon_legendary.json") == cached
    assert result["weapon_legendary"] == cached


def test_scrape_one_combo_retries_after_iframe_failure(tmp_path: Path) -> None:
    """When the first attempt fails (simulated iframe overlay on the chip click
    that the inner _select_gear_filters JS-dispatch fallback can't recover from,
    or a transient page.goto failure), _scrape_one_combo strips iframes and
    retries at the per-combo level. Second attempt succeeds and writes the cache."""
    from unittest.mock import MagicMock

    page = MagicMock(name="page")
    # Simulate transient failure: first goto raises (e.g. Cloudflare challenge
    # midway through navigation); second goto succeeds.
    goto_count = {"n": 0}

    def fake_goto(url: Any) -> None:
        goto_count["n"] += 1
        if goto_count["n"] == 1:
            raise Exception("transient: Cloudflare challenge")

    page.goto.side_effect = fake_goto

    def fake_locator(sel: Any) -> Any:
        loc = MagicMock()
        loc.filter.return_value = loc
        loc.click.return_value = None
        loc.is_checked.return_value = True
        return loc

    page.locator.side_effect = fake_locator
    page.evaluate.return_value = None  # iframe strip is a no-op in mock

    # Don't need real network — make scrape_gear_batch return one fake item.
    original = scraper.scrape_gear_batch
    scraper.scrape_gear_batch = lambda page, max_clicks=50: [
        {"id": 999, "name": "Test", "rarity": "Legendary", "type": "ATK+5", "level": "Lv1",
         "image": "", "rarity_color": ""},
    ]
    try:
        out_dir = tmp_path / "cache"
        out_dir.mkdir()
        result = scraper._scrape_one_combo(
            page, "weapon", "legendary", out_dir=out_dir
        )
        assert result is not None, "should succeed on retry"
        assert len(result) == 1
        assert result[0]["id"] == 999
        # Cache file written
        cache_file = out_dir / "gear_weapon_legendary.json"
        assert cache_file.exists()
        # page.goto called twice (initial + retry)
        assert goto_count["n"] == 2
        # page.evaluate called at least once for iframe strip
        assert page.evaluate.called
    finally:
        scraper.scrape_gear_batch = original


def test_scrape_one_combo_returns_none_after_two_failures(tmp_path: Path) -> None:
    """If BOTH attempts fail, returns None so caller can fall back to cache."""
    from unittest.mock import MagicMock

    page = MagicMock(name="page")
    page.goto.return_value = None

    def fake_locator(sel: Any) -> Any:
        loc = MagicMock()
        loc.filter.return_value = loc
        loc.click.side_effect = Exception("always fails")
        loc.is_checked.return_value = True
        return loc

    page.locator.side_effect = fake_locator
    page.evaluate.return_value = None

    out_dir = tmp_path / "cache"
    out_dir.mkdir()
    result = scraper._scrape_one_combo(
        page, "weapon", "legendary", out_dir=out_dir
    )
    assert result is None
    # page.goto called exactly twice
    assert page.goto.call_count == 2
    # No cache file written
    assert not (out_dir / "gear_weapon_legendary.json").exists()
