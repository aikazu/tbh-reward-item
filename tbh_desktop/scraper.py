"""Fetch + parse gear wiki and box pages; cache to JSON."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

GEAR_URL = "https://taskbarhero.wiki/gear"
BOX_URL_TEMPLATE = "https://taskbarhero.org/en/items/chests/{box_id}-{slug}/"
ID_RE = re.compile(r"/items/[^/]*?(\d+)-")
GEAR_IMG_ID_RE = re.compile(
    r"/(?:HELMET|ARMOR|GLOVES|BOOTS|SWORD|BOW|STAFF|SCEPTER|CROSSBOW|AXE|SHIELD|OFFHAND)_(\d+)\.png",
    re.IGNORECASE,
)
MATERIAL_IMG_ID_RE = re.compile(r"/Item_(\d+)\.png", re.IGNORECASE)


def parse_gear_page(html: str) -> list[dict[str, Any]]:
    """Parse gear wiki HTML, return list of obtainable gear dicts.

    Each dict: {id, name, rarity, type}. Only cards marked obtainable are returned.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    for card in soup.select(".gear-card"):
        if "obtainable" not in card.get("class", []):
            continue
        href = card.get("href", "")
        m = ID_RE.search(href)
        if not m:
            continue
        name_el = card.select_one(".name")
        rarity_el = card.select_one(".rarity")
        type_el = card.select_one(".type")
        items.append(
            {
                "id": int(m.group(1)),
                "name": name_el.get_text(strip=True) if name_el else "",
                "rarity": rarity_el.get_text(strip=True) if rarity_el else "",
                "type": type_el.get_text(strip=True) if type_el else "",
            }
        )
    return items


def parse_box_page(html: str) -> list[dict[str, Any]]:
    """Parse box page HTML, return loot table items.

    Each dict: {id, name, rate}. ID extracted from gear image path, material image
    path, or href. Only rows inside the 'Loot table' section are returned.
    """
    soup = BeautifulSoup(html, "html.parser")
    loot: list[dict[str, Any]] = []
    # Find the Loot table heading, then the next table after it.
    loot_heading = soup.find(
        lambda tag: tag.name in ("h2", "h3")
        and "loot table" in tag.get_text(strip=True).lower()
    )
    table = (
        loot_heading.find_next("table")
        if loot_heading is not None
        else soup.find("table")
    )
    if table is None:
        return loot
    for row in table.select("tbody > tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue  # header row (th cells)
        name_cell = cells[0]
        rate = cells[1].get_text(strip=True)
        name = name_cell.get_text(strip=True)
        item_id = _extract_item_id(name_cell)
        if item_id is None:
            continue
        loot.append({"id": item_id, "name": name, "rate": rate})
    return loot


def _extract_item_id(cell: Any) -> int | None:
    # Try gear image path.
    for img in cell.find_all("img"):
        src = img.get("src", "")
        m = GEAR_IMG_ID_RE.search(src)
        if m:
            return int(m.group(1))
        m = MATERIAL_IMG_ID_RE.search(src)
        if m:
            return int(m.group(1))
    # Try href.
    for a in cell.find_all("a"):
        href = a.get("href", "")
        m = ID_RE.search(href)
        if m:
            return int(m.group(1))
    return None


def write_gear_cache(path: Path, items: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def read_gear_cache(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def write_box_cache(cache_dir: Path, box_id: int, loot: list[dict[str, Any]]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{box_id}.json").write_text(
        json.dumps(loot, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_box_cache(cache_dir: Path, box_id: int) -> list[dict[str, Any]]:
    p = cache_dir / f"{box_id}.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def resolve_box_slug(name: str) -> str:
    """Convert a box name to URL slug. e.g. 'Normal Monster Box Lv80' -> 'normal-monster-box-lv80'."""
    return name.strip().lower().replace(" ", "-")
