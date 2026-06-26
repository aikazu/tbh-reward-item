"""Single source of truth for gear category and grade slugs/labels.

Both ``scraper.py`` (wiki chip-click driver) and ``ui/gear_picker.py``
(filter dropdowns) must agree on which categories and grades exist.
Centralizing here avoids drift when a new grade is added.
"""
from __future__ import annotations

# Slug -> chip label shown on the wiki.
CATEGORY_CHIPS: dict[str, str] = {
    "weapon": "Weapon",
    "offhand": "Off-hand",
    "armor": "Armor",
    "accessory": "Accessory",
}
GRADE_CHIPS: dict[str, str] = {
    "legendary": "Legendary",
    "immortal": "Immortal",
    "arcana": "Arcana",
    "beyond": "Beyond",
    "celestial": "Celestial",
    "divine": "Divine",
    "cosmic": "Cosmic",
}

# Slug tuples (preserve insertion order for deterministic iteration).
GEAR_CATEGORIES: tuple[str, ...] = tuple(CATEGORY_CHIPS.keys())
LEGENDARY_UP_GRADES: tuple[str, ...] = tuple(GRADE_CHIPS.keys())

# Inverse maps (display label -> slug) for the picker dropdowns.
CATEGORY_DISPLAY: dict[str, str] = {v: k for k, v in CATEGORY_CHIPS.items()}
GRADE_DISPLAY: dict[str, str] = {v: k for k, v in GRADE_CHIPS.items()}
