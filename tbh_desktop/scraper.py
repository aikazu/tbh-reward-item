"""Fetch + parse gear wiki and box pages; cache to JSON."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

GEAR_URL = "https://taskbarhero.wiki/gear"
BOX_URL_TEMPLATE = "https://taskbarhero.org/en/items/chests/{box_id}-{slug}/"
ID_RE = re.compile(r"/items/[^/]*?(\d+)-")


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
