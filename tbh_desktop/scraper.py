"""Fetch + parse gear wiki and box pages; cache to JSON."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

try:
    from cloakbrowser import launch as _stealth_launch
except ImportError:
    _stealth_launch = None  # type: ignore[assignment]
from playwright.sync_api import sync_playwright

from tbh_desktop.paths import DESKTOP_DIR

log = logging.getLogger(__name__)

GEAR_URL = "https://taskbarhero.wiki/gear"
ITEMS_URL = "https://taskbarhero.org/en/items"
BOX_URL_TEMPLATE = "https://taskbarhero.org/en/items/chests/{box_id}-{slug}/"
BOX_SLUG_CACHE = DESKTOP_DIR / "box_slug_cache.json"
ID_RE = re.compile(r"/items/[^/]*?(\d+)-")
GEAR_IMG_ID_RE = re.compile(
    r"/(?:HELMET|ARMOR|GLOVES|BOOTS|SWORD|BOW|STAFF|SCEPTER|CROSSBOW|AXE|SHIELD|OFFHAND)_(\d+)\.png",
    re.IGNORECASE,
)
MATERIAL_IMG_ID_RE = re.compile(r"/Item_(\d+)\.png", re.IGNORECASE)
CHEST_SLUG_RE = re.compile(r"/chests/(\d+)-([\w-]+)/")


def parse_gear_page(html: str) -> list[dict[str, Any]]:
    """Parse gear wiki HTML, return list of obtainable gear dicts.

    Real structure: each gear card is an <a class="entity-card">. Cards whose
    class list contains "is-deleted" are no longer obtainable and are skipped.
    Inside each card:
      - .entity-card-name  -> name
      - .entity-card-tag   -> rarity (e.g. "Common")
      - .entity-card-meta  -> "Lv<level> | <type>" — split on "|" into level/type.
    ID is extracted from href via ID_RE (e.g. /items/300001-long-sword -> 300001).

    Each dict: {id, name, rarity, type, level}. level is the part before "|" in
    .entity-card-meta (e.g. "Lv1"); "" if missing.

    Limitation: the live page returns ~60 cards on first paint (~22 obtainable,
    ~38 is-deleted). The full ~5760-item list requires infinite-scroll / pagination
    which is NOT implemented here — only the first batch is parsed.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    for card in soup.select("a.entity-card"):
        if "is-deleted" in card.get("class", []):
            continue
        href = card.get("href", "")
        m = ID_RE.search(href)
        if not m:
            continue
        name_el = card.select_one(".entity-card-name")
        rarity_el = card.select_one(".entity-card-tag")
        meta_el = card.select_one(".entity-card-meta")
        meta_text = meta_el.get_text(strip=True) if meta_el else ""
        if "|" in meta_text:
            level, gear_type = meta_text.split("|", 1)
            level = level.strip()
            gear_type = gear_type.strip()
        else:
            level = ""
            gear_type = meta_text.strip()
        items.append(
            {
                "id": int(m.group(1)),
                "name": name_el.get_text(strip=True) if name_el else "",
                "rarity": rarity_el.get_text(strip=True) if rarity_el else "",
                "type": gear_type,
                "level": level,
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
    """Convert a box name to URL slug. e.g. 'Normal Monster Box Lv80' -> 'normal-monster-box-lv80'.

    Naive heuristic kept as fallback when wiki items-page lookup is unavailable.
    """
    return name.strip().lower().replace(" ", "-")


def _load_slug_cache(cache_path: Path) -> dict[str, str]:
    if not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_slug_cache(cache_path: Path, mapping: dict[str, str]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(cache_path)


def resolve_box_id_slug(
    box_id: int, cache_path: Path | None = None
) -> str | None:
    """Resolve a box id to its exact wiki URL slug via the items page.

    Caches the full id->slug map to ``cache_path`` (default BOX_SLUG_CACHE) so
    repeat lookups skip the network. Returns the slug or None if not found / on
    error (caller should fall back to a heuristic).
    """
    cache_path = cache_path or BOX_SLUG_CACHE
    try:
        cache = _load_slug_cache(cache_path)
        key = str(box_id)
        if key in cache:
            return cache[key]

        resp = requests.get(ITEMS_URL, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find the "Stage chests" heading, then the next table.
        chests_heading = soup.find(
            lambda tag: tag.name in ("h2", "h3")
            and "stage chests" in tag.get_text(strip=True).lower()
        )
        table = (
            chests_heading.find_next("table")
            if chests_heading is not None
            else soup.find("table")
        )
        if table is None:
            return None

        for tr in table.select("tr[data-id]"):
            row_id = tr.get("data-id")
            a = tr.find("a", href=True)
            if not a or not row_id:
                continue
            m = CHEST_SLUG_RE.search(a["href"])
            if m and m.group(1) == row_id:
                cache[row_id] = m.group(2)

        _write_slug_cache(cache_path, cache)
        return cache.get(key)
    except Exception as exc:
        log.warning("box slug lookup for %s failed: %s", box_id, exc)
        return None


# ---------------------------------------------------------------------------
# G3 — playwright-based full gear scraper (per category x grade)
# ---------------------------------------------------------------------------

# Cache slug -> wiki chip label.
GEAR_CATEGORIES = ("weapon", "offhand", "armor", "accessory")
CATEGORY_CHIPS = {
    "weapon": "Weapon",
    "offhand": "Off-hand",
    "armor": "Armor",
    "accessory": "Accessory",
}
GRADE_CHIPS = {
    "legendary": "Legendary",
    "immortal": "Immortal",
    "arcana": "Arcana",
    "beyond": "Beyond",
    "celestial": "Celestial",
    "divine": "Divine",
    "cosmic": "Cosmic",
}
LEGENDARY_UP_GRADES = tuple(GRADE_CHIPS.keys())

# CSS selectors for the wiki /gear filter row + LOAD MORE button.
CHIP_SELECTOR = ".gear-chip"
LOAD_MORE_SELECTOR = "button.border-2.font-dos"
OBTAINABLE_CHECKBOX_SELECTOR = ".gear-filter-row input[type=checkbox]"
# The Obtainable-only checkbox is visually overlaid by a
# <span class="gear-toggle-box"> that intercepts pointer events, so .check()
# on the input times out. The wrapper span is the real Svelte click target.
TOGGLE_BOX_SELECTOR = ".gear-toggle-box"


def _select_gear_filters(
    page: Any,
    category_slug: str,
    grade_slug: str,
    obtainable_only: bool = True,
) -> None:
    """Select Type + Rarity chips and (optionally) the Obtainable-only checkbox
    on the wiki /gear page before loading more cards.

    Uses ``page.locator(...).filter(has_text=label).click()`` so the chip is
    matched by visible text rather than positional index.
    """
    category_label = CATEGORY_CHIPS[category_slug]
    grade_label = GRADE_CHIPS[grade_slug]

    # Type chip (weapon/armor/...). The chip text equals the label exactly.
    page.locator(CHIP_SELECTOR).filter(has_text=category_label).click()
    # Rarity chip.
    page.locator(CHIP_SELECTOR).filter(has_text=grade_label).click()
    if obtainable_only:
        # The checkbox input is overlaid by .gear-toggle-box (intercepts
        # pointer events); .check() times out. Click the visible wrapper
        # instead, but only when not already checked (avoid toggling it off).
        cb = page.locator(OBTAINABLE_CHECKBOX_SELECTOR)
        if not cb.is_checked():
            page.locator(TOGGLE_BOX_SELECTOR).click()


def scrape_gear_batch(page: Any, max_clicks: int = 50) -> list[dict[str, Any]]:
    """Load all gear cards on the current page, clicking LOAD MORE until the
    button disappears or ``max_clicks`` is reached.

    Parses ``page.content()`` with :func:`parse_gear_page` (which skips
    ``is-deleted`` cards) and dedups items by id across LOAD MORE batches.

    Returns a list of obtainable gear dicts ``{id, name, rarity, type, level}``.
    """
    items: list[dict[str, Any]] = []
    seen: set[int] = set()

    def _absorb() -> None:
        for it in parse_gear_page(page.content()):
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            items.append(it)

    _absorb()
    for _ in range(max_clicks):
        btn = page.query_selector(LOAD_MORE_SELECTOR)
        if btn is None:
            break
        btn.click()
        # Give the client-side batch swap time to settle before re-parsing.
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        _absorb()
    return items


def refresh_gear_full(
    out_dir: Path,
    categories: list[str] | None = None,
    grades: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Scrape full Legendary+ obtainable gear per (category, grade) using
    playwright (headless chromium) and write one cache file per combo.

    For each ``(category, grade)``:
      - navigate to ``GEAR_URL``
      - select Type chip = category, Rarity chip = grade, Obtainable-only
      - click LOAD MORE until exhausted
      - write ``out_dir/gear_{category}_{grade}.json``

    On per-combo error (or playwright launch failure) falls back to the
    existing cache file for that combo, preserving it. Returns a dict keyed by
    ``"{category}_{grade}"`` -> items.
    """
    cats = list(categories) if categories is not None else list(GEAR_CATEGORIES)
    grads = list(grades) if grades is not None else list(LEGENDARY_UP_GRADES)
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, list[dict[str, Any]]] = {}

    def _cache_path(cat: str, grade: str) -> Path:
        return out_dir / f"gear_{cat}_{grade}.json"

    def _fallback(cat: str, grade: str) -> list[dict[str, Any]]:
        items = read_gear_cache(_cache_path(cat, grade))
        log.warning("gear %s/%s fell back to cache (%d items)", cat, grade, len(items))
        return items

    try:
        if _stealth_launch is not None:
            # CloakBrowser: stealth Chromium with human-like input, anti-detect.
            browser = _stealth_launch(headless=True, humanize=True)
        else:
            # Fallback to stock Playwright if cloakbrowser not installed.
            browser = sync_playwright().start().chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            for cat in cats:
                for grade in grads:
                    key = f"{cat}_{grade}"
                    try:
                        page.goto(GEAR_URL)
                        _select_gear_filters(page, cat, grade, obtainable_only=True)
                        items = scrape_gear_batch(page)
                        write_gear_cache(_cache_path(cat, grade), items)
                        result[key] = items
                        log.info("gear %s/%s scraped %d items", cat, grade, len(items))
                    except Exception as exc:
                        log.warning("gear %s/%s scrape failed: %s", cat, grade, exc)
                        result[key] = _fallback(cat, grade)
        finally:
            browser.close()
    except Exception as exc:
        # browser launch / browser-level failure: fall back every combo.
        log.warning("browser launch failed (%s); falling back to caches", exc)
        for cat in cats:
            for grade in grads:
                key = f"{cat}_{grade}"
                result[key] = _fallback(cat, grade)

    return result


def refresh_gear(cache_path: Path) -> list[dict[str, Any]]:
    """Fetch gear wiki, parse, cache. Fall back to existing cache on error."""
    try:
        resp = requests.get(GEAR_URL, timeout=30)
        resp.raise_for_status()
        items = parse_gear_page(resp.text)
        write_gear_cache(cache_path, items)
        return items
    except Exception as exc:
        log.warning("gear refresh failed: %s", exc)
        return read_gear_cache(cache_path)


def refresh_box_loot(
    cache_dir: Path,
    box_id: int,
    slug_cache_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Resolve slug via items page, fetch box page, parse loot, cache.

    Falls back to existing box cache if slug lookup fails or the fetch errors.
    """
    slug = resolve_box_id_slug(box_id, cache_path=slug_cache_path)
    if slug is None:
        log.warning("box %s: slug not found on items page, using cache", box_id)
        return read_box_cache(cache_dir, box_id)
    try:
        url = BOX_URL_TEMPLATE.format(box_id=box_id, slug=slug)
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        loot = parse_box_page(resp.text)
        write_box_cache(cache_dir, box_id, loot)
        return loot
    except Exception as exc:
        log.warning("box %s refresh failed: %s", box_id, exc)
        return read_box_cache(cache_dir, box_id)
