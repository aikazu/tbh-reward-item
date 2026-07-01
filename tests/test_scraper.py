"""Tests for tbh_desktop.scraper — minimal helpers that survive the
Jul 2026 tbh.city migration.

The legacy wiki gear / box / drops scrapers are retired (see
``dev_tools.scrape_pipeline.scrape_stage`` for the active path). This
file covers only the small helpers still exported from
``tbh_desktop.scraper``:

* ``derive_item_image_url`` — ID → wiki image URL.
* ``read_gear_cache`` / ``write_gear_cache`` — per-combo JSON files.
* ``parse_drops_page`` — legacy stub returning [].
"""
from __future__ import annotations

from pathlib import Path


def test_derive_item_image_url_gear_slot() -> None:
    """Known gear prefixes return the wiki's /game/gear/<slot>/<FILE>_<id>.png URL."""
    from tbh_desktop.scraper import derive_item_image_url
    # 505041 → helmet/HELMET_505041.png
    assert derive_item_image_url(505041) == (
        "https://taskbarhero.wiki/game/gear/helmet/HELMET_505041.png"
    )


def test_derive_item_image_url_material() -> None:
    """1xxxxx / 2xxxxx return the materials CDN path."""
    from tbh_desktop.scraper import derive_item_image_url
    assert derive_item_image_url(141001) == (
        "https://taskbarhero.wiki/game/items/materials/Item_141001.png"
    )


def test_derive_item_image_url_unknown_prefix() -> None:
    """Out-of-range ids return '' (no URL can be derived)."""
    from tbh_desktop.scraper import derive_item_image_url
    assert derive_item_image_url(0) == ""
    assert derive_item_image_url(999) == ""


def test_derive_item_image_url_box_id() -> None:
    """9xxxxx ids return the box icon URL (uses floor(id, 10000) + 11)."""
    from tbh_desktop.scraper import derive_item_image_url
    assert derive_item_image_url(910011) == (
        "https://taskbarhero.wiki/game/items/boxes/Item_910011.png"
    )


def test_read_write_gear_cache_round_trip(tmp_path: Path) -> None:
    from tbh_desktop.scraper import read_gear_cache, write_gear_cache
    items = [
        {"id": 300001, "name": "Sword", "rarity": "LEGENDARY"},
        {"id": 505041, "name": "Helmet", "rarity": "LEGENDARY"},
    ]
    p = tmp_path / "weapon_legendary.json"
    write_gear_cache(p, items)
    assert read_gear_cache(p) == items


def test_read_gear_cache_missing_returns_empty(tmp_path: Path) -> None:
    from tbh_desktop.scraper import read_gear_cache
    assert read_gear_cache(tmp_path / "does_not_exist.json") == []


def test_parse_drops_page_returns_empty_after_migration() -> None:
    """Legacy stub. The tbh.city migration retired the wiki /en/tools/drops/
    page; pickers read items_normalized.json instead."""
    from tbh_desktop.scraper import parse_drops_page
    assert parse_drops_page("<html><body>anything</body></html>") == []


# ---------------------------------------------------------------------------
# Jul 2026 — item categorization (slot_category + material family).
# tbh.city doesn't expose slot_category or family fields directly; we
# derive them from the item id prefix and name keyword heuristic.
# ---------------------------------------------------------------------------

def test_slot_category_weapon() -> None:
    from tbh_desktop.tbh_city import _slot_category_from_id
    assert _slot_category_from_id(300001) == "Weapon"
    assert _slot_category_from_id(350001) == "Weapon"  # axe
    assert _slot_category_from_id(450001) == "Weapon"  # hatchet


def test_slot_category_offhand() -> None:
    from tbh_desktop.tbh_city import _slot_category_from_id
    assert _slot_category_from_id(410001) == "Off-hand"  # shield
    assert _slot_category_from_id(420001) == "Off-hand"  # orb
    assert _slot_category_from_id(430001) == "Off-hand"  # tome
    assert _slot_category_from_id(440001) == "Off-hand"  # bolt


def test_slot_category_armor() -> None:
    from tbh_desktop.tbh_city import _slot_category_from_id
    assert _slot_category_from_id(500001) == "Armor"
    assert _slot_category_from_id(530001) == "Armor"


def test_slot_category_accessory() -> None:
    from tbh_desktop.tbh_city import _slot_category_from_id
    assert _slot_category_from_id(605041) == "Accessory"
    assert _slot_category_from_id(659999) == "Accessory"
    assert _slot_category_from_id(639999) == "Accessory"


def test_slot_category_unknown_for_materials() -> None:
    """1xxxxx / 2xxxxx (materials) don't map to a slot category."""
    from tbh_desktop.tbh_city import _slot_category_from_id
    assert _slot_category_from_id(100001) == "Unknown"
    assert _slot_category_from_id(200001) == "Unknown"


def test_material_family_soulstone() -> None:
    from tbh_desktop.tbh_city import _material_family
    assert _material_family("Soulstone - Normal", []) == "SOULSTONE"
    assert _material_family("Soulstone - Torment", []) == "SOULSTONE"


def test_material_family_decoration_gems() -> None:
    from tbh_desktop.tbh_city import _material_family
    assert _material_family("Minor Ruby", []) == "DECORATION"
    assert _material_family("Obsidian Shard", []) == "DECORATION"
    assert _material_family("Lapis Lazuli", []) == "DECORATION"
    assert _material_family("Mystic Pearl", []) == "DECORATION"


def test_material_family_engraving() -> None:
    from tbh_desktop.tbh_city import _material_family
    assert _material_family("Engraved Plate", []) == "ENGRAVING"
    assert _material_family("Ancient Engraving", []) == "ENGRAVING"
    assert _material_family("Etched Rune", []) == "ENGRAVING"


def test_material_family_inscription() -> None:
    from tbh_desktop.tbh_city import _material_family
    assert _material_family("Mystic Scroll", []) == "INSCRIPTION"
    assert _material_family("Inscription of Power", []) == "INSCRIPTION"


def test_material_family_offering() -> None:
    from tbh_desktop.tbh_city import _material_family
    assert _material_family("Tribute of Valor", []) == "OFFERING"
    assert _material_family("Offering Stone", []) == "OFFERING"


def test_material_family_default_is_crafting() -> None:
    from tbh_desktop.tbh_city import _material_family
    assert _material_family("Bronze Ingot", []) == "CRAFTING"
    assert _material_family("Iron Sword", []) == "CRAFTING"
    assert _material_family("", []) == "CRAFTING"


def test_normalize_items_populates_categories() -> None:
    """End-to-end: normalize a hand-rolled GEAR + MATERIAL entry and
    check the categorization fields land where the picker expects them."""
    from tbh_desktop.tbh_city import normalize_items
    raw = [
        # GEAR — Sword (icon prefix → slot_type=Sword, id 30xxxxxx → Weapon)
        {"id": 300001, "name": {"en": "Long Sword"}, "grade": "COMMON",
         "icon": "sprites/sharedassets0/SWORD_300001.png", "type": "GEAR",
         "gear_id": 300001, "stat_types": [], "source_count": 0,
         "obtainable_in_live_game": True, "only_torment_drops": False,
         "is_market_tradable": True, "drop_cooldown": None,
         "hero_class": None, "unique_mod": None},
        # GEAR — Helmet
        {"id": 505041, "name": {"en": "Gold Helmet"}, "grade": "LEGENDARY",
         "icon": "sprites/sharedassets0/HELMET_505041.png", "type": "GEAR",
         "gear_id": 505041, "stat_types": [], "source_count": 0,
         "obtainable_in_live_game": True, "only_torment_drops": False,
         "is_market_tradable": True, "drop_cooldown": None,
         "hero_class": None, "unique_mod": None},
        # MATERIAL — Soulstone
        {"id": 190001, "name": {"en": "Soulstone - Normal"}, "grade": "LEGENDARY",
         "icon": "sprites/sharedassets0/Item_190001.png", "type": "MATERIAL",
         "gear_id": "", "stat_types": [], "source_count": 0,
         "obtainable_in_live_game": True, "only_torment_drops": False,
         "is_market_tradable": True, "drop_cooldown": None,
         "hero_class": None, "unique_mod": None},
    ]
    out = normalize_items(raw)
    assert out[0]["slot_category"] == "Weapon"
    assert out[0]["slot_type"] == "Sword"
    assert out[0]["family"] == ""
    assert out[1]["slot_category"] == "Armor"
    assert out[1]["slot_type"] == "Helmet"
    assert out[2]["slot_category"] == ""
    assert out[2]["family"] == "SOULSTONE"


# ---------------------------------------------------------------------------
# Jul 2026 — CatalogPopup filter chips: two independent axes (gear + item).
# ---------------------------------------------------------------------------

def test_catalog_popup_two_filter_axes(qapp, tmp_path) -> None:
    """The popup exposes two independent chip rows (Gear + Items) so
    a click on a Gear chip doesn't deselect an active Item chip.
    """
    from tbh_desktop.ui.catalog_popup import (
        CatalogContent,
        _GEAR_FILTERS,
        _ITEM_FILTERS,
    )
    # CatalogContent takes real cache paths but doesn't actually need
    # them to exist for this assertion — it just renders the chips on
    # init. Use tmp paths so it has somewhere to look.
    content = CatalogContent(
        gear_cache_dir=tmp_path / "gear",
        drops_index_path=tmp_path / "items.json",
        stage_drop_map_path=tmp_path / "sdm.json",
        stages_index_path=tmp_path / "stages.json",
    )
    try:
        gear_values = {str(b.property("filter_value") or "") for b in content._gear_filter_buttons}
        item_values = {str(b.property("filter_value") or "") for b in content._item_filter_buttons}
        assert gear_values == {label or "" for _, label in _GEAR_FILTERS}
        assert item_values == {label or "" for _, label in _ITEM_FILTERS}
        # Gear chips: All / Weapon / Off-hand / Armor / Accessory
        assert "" in gear_values
        assert "Weapon" in gear_values
        assert "Off-hand" in gear_values
        assert "Armor" in gear_values
        assert "Accessory" in gear_values
        # Item chips: All / Decoration / Engraving / Inscription
        # (Jul 2026: CRAFTING + OFFERING + SOULSTONE removed —
        # those material families don't appear in tbh.city's
        # items_normalized.json so the chips only ever showed an
        # empty filtered list).
        assert "" in item_values
        assert "DECORATION" in item_values
        assert "ENGRAVING" in item_values
        assert "INSCRIPTION" in item_values
        # Chip axes are independent — clicking a gear chip must not
        # affect the item chip selection (and vice versa).
        weapon_btn = next(b for b in content._gear_filter_buttons if b.property("filter_value") == "Weapon")
        decoration_btn = next(b for b in content._item_filter_buttons if b.property("filter_value") == "DECORATION")
        weapon_btn.click()
        decoration_btn.click()
        assert weapon_btn.isChecked() is True
        assert decoration_btn.isChecked() is True
        # Active filter values are independent too.
        assert content._active_filter("gear") == "Weapon"
        assert content._active_filter("item") == "DECORATION"
    finally:
        content.deleteLater()


def test_catalog_popup_axis_mode_filters_by_kind() -> None:
    """set_axis_mode('gear') must hide material items from the list
    (and vice versa). Without the kind-filter, picking gear would
    leak materials (Wood/Stone/Leather) into the result list — Jul
    2026 bug."""
    from pathlib import Path
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from tbh_desktop.ui.catalog_popup import CatalogPopup
    popup = CatalogPopup(
        gear_cache_dir=Path("tbh_desktop/gear"),
        drops_index_path=Path("tbh_desktop/items_normalized.json"),
        stage_drop_map_path=Path("tbh_desktop/stage_drop_map.json"),
        stages_index_path=Path("tbh_desktop/stages_index.json"),
    )
    popup.show()
    app.processEvents()
    popup.exec_for_replacement_scoped([], axis="gear")
    app.processEvents()
    from collections import Counter
    # Click 'Weapon' to scope gear axis to weapons
    for btn in popup.content._gear_filter_buttons:
        if btn.property("filter_value") == "Weapon":
            btn.click()
            break
    app.processEvents()
    kinds = []
    for i in range(popup.content.list_widget.count()):
        data = popup.content.list_widget.item(i).data(0x0100)
        if data:
            kinds.append(data.get("kind"))
    # All items in Pick-gear + Weapon scope must be gear, never
    # materials (Wood/Stone/Leather leak was the bug).
    assert "material" not in kinds, f"materials leaked: {Counter(kinds)}"
    assert kinds, "Weapon filter shouldn't be empty"
    """set_allowed_item_ids restricts the visible catalog to a fixed
    set of ids (used by main_window for pool-scoped replacement picks)."""
    from tbh_desktop.ui.catalog_popup import CatalogContent
    # Bare construction without QApplication — just exercise the
    # attribute + setter logic directly.
    assert hasattr(CatalogContent, "set_allowed_item_ids")