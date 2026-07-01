"""Gear cache helpers used by the desktop picker (read-only).

Jul 2026 — tbh.city migration: the legacy wiki scrapers (gear / box /
drops index / CloakBrowser launcher) are retired. The active data path
is ``dev_tools.scrape_pipeline.scrape_stage.run_scrape`` which fetches
items + stages from tbh.city. This module now only exposes small
helpers used by the desktop widget layer:

* ``derive_item_image_url`` — backfill image URLs for entries that the
  scraper produced without an image src.
* ``read_gear_cache`` / ``write_gear_cache`` — read/write the per-combo
  gear JSON cache files produced by the tbh.city pipeline.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tbh_desktop.paths import DESKTOP_DIR


# Re-exported so the desktop tests still find a constant for the gear
# cache directory if they need to mock it.
BOX_SLUG_CACHE = DESKTOP_DIR / "box_slug_cache.json"  # noqa: F841 - legacy alias


# Image-path folder -> slot type label (title-cased).
_IMAGE_FOLDER_TO_SLOT: dict[str, str] = {
    "sword":    "Sword",
    "bow":      "Bow",
    "staff":    "Staff",
    "scepter":  "Scepter",
    "crossbow": "Crossbow",
    "axe":      "Axe",
    "hatchet":  "Hatchet",
    "shield":   "Shield",
    "offhand":  "Offhand",
    "helmet":   "Helmet",
    "armor":    "Armor",
    "gloves":   "Gloves",
    "boots":    "Boots",
}
_IMAGE_FOLDER_RE = re.compile(
    r"/game/gear/([a-z]+)/[A-Z_0-9]+\.png", re.IGNORECASE
)

# ItemId prefix -> (slot folder, TYPE name) for deriving gear image URLs.
# Verified 2026-06-29 against taskbarhero.wiki: derived URLs return 200
# for all obtainable gear.
_ITEM_ID_TO_GEAR_URL: dict[str, tuple[str, str]] = {
    "30": ("sword", "SWORD"),
    "31": ("bow", "BOW"),
    "32": ("staff", "STAFF"),
    "33": ("scepter", "SCEPTER"),
    "34": ("crossbow", "CROSSBOW"),
    "35": ("axe", "AXE"),
    "40": ("shield", "SHIELD"),
    "41": ("arrow", "ARROW"),
    "42": ("orb", "ORB"),
    "50": ("helmet", "HELMET"),
    "51": ("armor", "ARMOR"),
    "52": ("gloves", "GLOVES"),
    "53": ("boots", "BOOTS"),
    "60": ("amulet", "AMULET"),
}

# Box icons live under /game/items/boxes/. The wiki serves the base-variant
# image regardless of tier.
_BOX_IMG_URL = "https://taskbarhero.wiki/game/items/boxes/Item_{id}.png"
# Materials/gems/soulstones/etc. all live under /game/items/materials/.
_MATERIAL_IMG_URL = "https://taskbarhero.wiki/game/items/materials/Item_{id}.png"
_GEAR_IMG_URL = "https://taskbarhero.wiki/game/gear/{slot}/{TYPE}_{id}.png"


def _slot_type_from_image(image_url: str) -> str:
    """Extract the gear slot type ('Sword', 'Bow', ...) from its image URL.

    Returns '' if the URL doesn't match the expected /game/gear/<folder>/ pattern.
    """
    if not image_url:
        return ""
    m = _IMAGE_FOLDER_RE.search(image_url)
    if not m:
        return ""
    folder = m.group(1).lower()
    return _IMAGE_FOLDER_TO_SLOT.get(folder, folder.capitalize())


def derive_item_image_url(item_id: int) -> str:
    """Best-guess image URL for an item, derived purely from its numeric ID.

    Used to backfill ``image`` fields on entries that the scraper produced
    without an image src. The wiki always serves these paths for
    obtainable items — verified 2026-06-29.

    Examples (all return 200 on taskbarhero.wiki):
      derive_item_image_url(505041) → helmet/HELMET_505041.png
      derive_item_image_url(141001) → materials/Item_141001.png

    Returns "" if the ID doesn't match a known prefix.
    """
    s = str(int(item_id)).zfill(6)  # ensure 6 digits
    if len(s) != 6:
        return ""
    prefix = s[:2]
    if prefix in _ITEM_ID_TO_GEAR_URL:
        slot, type_name = _ITEM_ID_TO_GEAR_URL[prefix]
        return _GEAR_IMG_URL.format(slot=slot, TYPE=type_name, id=s)
    # Box ids (9xxxxx).
    if s.startswith("9"):
        base_id = (int(s) // 10000) * 10000 + 11
        return _BOX_IMG_URL.format(id=str(base_id).zfill(6))
    # Materials / consumables / soulstones.
    first = s[0]
    if first in ("1", "2"):
        return _MATERIAL_IMG_URL.format(id=s)
    return ""


def write_gear_cache(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def read_gear_cache(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


# ---------------------------------------------------------------------------
# Legacy stubs (kept so old import sites keep loading; tests verify these
# return [] because the underlying wiki data sources are retired).
# ---------------------------------------------------------------------------

def parse_drops_page(html: str) -> list[dict[str, Any]]:
    """Legacy stub — no longer used. Returns [].

    Pre-Dec-2026 the drops index came from taskbarhero.org's
    /en/tools/drops/ page. The tbh.city migration reads from the items
    index JSON instead (``items_normalized.json``).
    """
    return []