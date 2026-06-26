"""Fetch + parse gear wiki and box pages; cache to JSON."""
from __future__ import annotations

import json
import logging
import re
import threading
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
      - .entity-card-art img    -> image URL (e.g. /game/gear/sword/SWORD_300001.png)
      - .entity-card-name       -> name
      - .entity-card-tag        -> rarity text (e.g. "Common")
      - .entity-card-meta       -> "Lv<level> | <type>" — split on "|" into level/type.
      - style="--rc:#RRGGBB"    -> rarity color (root <a> attribute) for theming.
    ID is extracted from href via ID_RE (e.g. /items/300001-long-sword -> 300001).

    Each dict: {id, name, rarity, type, level, image, rarity_color}.
    level is the part before "|" in .entity-card-meta (e.g. "Lv1"); "" if missing.
    image is the absolute URL (wiki-relative paths resolved to https://taskbarhero.wiki).
    rarity_color is "#RRGGBB" or "" if the wiki didn't set it.

    Limitation: the live page returns ~60 cards on first paint (~22 obtainable,
    ~38 is-deleted). The full ~5760-item list requires infinite-scroll / pagination
    which is NOT implemented here — only the first batch is parsed.
    """
    soup = BeautifulSoup(html, "lxml")
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
        # Image — prefer the explicit gear art <img>, fall back to first <img>.
        img_el = card.select_one(".entity-card-art img") or card.select_one("img")
        image_url = str(img_el.get("src", "")) if img_el else ""
        if image_url.startswith("/"):
            image_url = "https://taskbarhero.wiki" + image_url
        # Rarity color from CSS variable on the root <a>.
        rarity_color = ""
        style_attr = str(card.get("style", ""))
        rc_match = re.search(r"--rc:\s*(#[0-9a-fA-F]+)", style_attr)
        if rc_match:
            rarity_color = rc_match.group(1).lower()
        items.append(
            {
                "id": int(m.group(1)),
                "name": name_el.get_text(strip=True) if name_el else "",
                "rarity": rarity_el.get_text(strip=True) if rarity_el else "",
                "type": gear_type,
                "level": level,
                "image": image_url,
                "rarity_color": rarity_color,
            }
        )
    return items


def parse_box_page(html: str, box_id: int = 0, box_name: str = "") -> list[dict[str, Any]]:
    """Parse box page HTML, return loot table items.

    Each dict: {id, name, rate, box_id, box_name, kind, image}. ID extracted from
    gear image path, material image path, or href. Only rows inside the 'Loot
    table' section are returned.

    The box_id/box_name args are stamped onto every loot entry so the caller can
    build a reverse map (item_id -> boxes) without having to re-derive them.
    Pass them when you know them (e.g. from the URL you scraped); default 0/"".

    *kind* is one of "gear" / "material" / "other", derived from which image
    regex matched the src attribute. The BoxLootPicker uses this to filter
    out gear (which lives in its own GearPicker dialog) and keep only
    materials / consumables / quest items.
    """
    soup = BeautifulSoup(html, "lxml")
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
        # Look for an image to classify as gear vs material + capture URL.
        kind = "other"
        image_url = ""
        for img in name_cell.find_all("img"):
            src = str(img.get("src", ""))
            if GEAR_IMG_ID_RE.search(src):
                kind = "gear"
                image_url = src
                break
            if MATERIAL_IMG_ID_RE.search(src):
                kind = "material"
                image_url = src
                break
        # Normalize wiki-relative URLs to absolute.
        if image_url.startswith("/"):
            image_url = "https://taskbarhero.wiki" + image_url
        # Fall back to href if no image — classify by ID range.
        if not image_url:
            href = name_cell.find("a")
            if href is not None:
                href_str = str(href.get("href", ""))
                image_url = href_str
        item_id = _extract_item_id(name_cell)
        if item_id is None:
            continue
        # ID-range fallback when no image matched.
        # TBH ID prefixes (verified against /game/gear cache):
        #   3xxxxx = weapon  · 4xxxxx = offhand  · 5xxxxx = armor  · 6xxxxx = accessory
        #   1xxxxx = material · 2xxxxx = consumable/other
        if kind == "other":
            first_digit = str(item_id)[0]
            if first_digit in ("3", "4", "5", "6"):
                kind = "gear"
            elif first_digit in ("1", "2"):
                kind = "material"
        loot.append({
            "id": item_id,
            "name": name,
            "rate": rate,
            "box_id": box_id,
            "box_name": box_name,
            "kind": kind,
            "image": image_url,
        })
    return loot


def build_box_drop_map(loot_entries: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """Group flat loot entries by item_id. Returns {item_id: [loot_dict, ...]}.

    Each input loot dict must have id, box_id, box_name, rate. Output is sorted
    by box_id ascending for stable display order. Used to populate the gear
    picker's 'Drops from' column.
    """
    drop_map: dict[int, list[dict[str, Any]]] = {}
    for entry in loot_entries:
        drop_map.setdefault(entry["id"], []).append(entry)
    # Sort each item's drop list by box_id for deterministic rendering.
    for drops in drop_map.values():
        drops.sort(key=lambda d: (d.get("box_id", 0), d.get("box_name", "")))
    return drop_map


def write_box_drop_cache(path: Path, drop_map: dict[int, list[dict[str, Any]]]) -> None:
    """Persist the drop map to JSON. Keys are coerced to strings (JSON limitation)."""
    serializable = {str(item_id): drops for item_id, drops in drop_map.items()}
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def read_box_drop_cache(path: Path) -> dict[int, list[dict[str, Any]]]:
    """Load the drop map from JSON. Returns {} on missing or invalid file."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    result: dict[int, list[dict[str, Any]]] = {}
    for k, v in raw.items():
        try:
            item_id = int(k)
        except (ValueError, TypeError):
            continue
        if isinstance(v, list):
            result[item_id] = v
    return result


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
        soup = BeautifulSoup(resp.text, "lxml")

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

# Slugs and chip labels live in tbh_desktop.gear_filters (single source of
# truth shared with the picker UI). Re-exported here for backwards compat.
from tbh_desktop.gear_filters import (  # noqa: E402, F401
    GEAR_CATEGORIES,
    CATEGORY_CHIPS,
    GRADE_CHIPS,
    LEGENDARY_UP_GRADES,
)

# CSS selectors for the wiki /gear filter row + LOAD MORE button.
CHIP_SELECTOR = ".gear-chip"
LOAD_MORE_SELECTOR = "button.border-2.font-dos"
OBTAINABLE_CHECKBOX_SELECTOR = ".gear-filter-row input[type=checkbox]"
# The Obtainable-only checkbox is visually overlaid by a
# <span class="gear-toggle-box"> that intercepts pointer events, so .check()
# on the input times out. The wrapper span is the real Svelte click target.
TOGGLE_BOX_SELECTOR = ".gear-toggle-box"


def _strip_overlay_iframes(page: Any) -> None:
    """Remove any <iframe> covering the page so subsequent clicks don't hit
    a pointer_events check failure. Cloudflare / ad iframes occasionally
    overlay the wiki on cold scrapes. Safe no-op when no iframes are present.
    """
    page.evaluate(
        """() => {
            for (const f of document.querySelectorAll('iframe')) {
                try { f.remove(); } catch (e) {}
            }
        }"""
    )


def _cache_path(out_dir: Path, cat: str, grade: str) -> Path:
    """Per-combo cache file path. Module-level so _scrape_one_combo can reuse it."""
    return out_dir / f"gear_{cat}_{grade}.json"


def _force_click(page: Any, selector: str, *, has_text: str | None = None) -> None:
    """Click via JS dispatchEvent('click') so we bypass Playwright's
    pointer_events visibility check. Used as a fallback when the normal
    locator-based click fails because an iframe / overlay covers the target.

    For text-matched chips, we resolve the matching element with a JS query
    (instead of locator.has_text which isn't supported in dispatchEvent land)
    and call .click() on it — Playwright still dispatches a real mouse event
    when you call .click() on a Locator, so the wiki's Svelte handlers fire.
    """
    if has_text is not None:
        # JS: find first element matching selector whose text contains has_text,
        # then dispatch a click. We use 'mousedown' + 'mouseup' + 'click' to
        # cover libs that listen for any of those.
        page.evaluate(
            """([sel, txt]) => {
                const all = Array.from(document.querySelectorAll(sel));
                const el = all.find(e => (e.textContent || '').trim().includes(txt));
                if (!el) throw new Error('no match for ' + sel + ' with text ' + txt);
                ['mousedown', 'mouseup', 'click'].forEach(ev =>
                    el.dispatchEvent(new MouseEvent(ev, {bubbles: true, cancelable: true, view: window}))
                );
            }""",
            [selector, has_text],
        )
    else:
        page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) throw new Error('no match for ' + sel);
                ['mousedown', 'mouseup', 'click'].forEach(ev =>
                    el.dispatchEvent(new MouseEvent(ev, {bubbles: true, cancelable: true, view: window}))
                );
            }""",
            selector,
        )


def _select_gear_filters(
    page: Any,
    category_slug: str,
    grade_slug: str,
    obtainable_only: bool = True,
) -> None:
    """Select Type + Rarity chips and (optionally) the Obtainable-only checkbox
    on the wiki /gear page before loading more cards.

    Uses ``page.locator(...).filter(has_text=label).click()`` so the chip is
    matched by visible text rather than positional index. Falls back to a
    JS-dispatched click via :func:`_force_click` when an iframe overlay blocks
    the normal click (Playwright raises ``pointer_events`` error).
    """
    category_label = CATEGORY_CHIPS[category_slug]
    grade_label = GRADE_CHIPS[grade_slug]

    def _click_chip(label: str) -> None:
        try:
            page.locator(CHIP_SELECTOR).filter(has_text=label).click()
        except Exception:
            # Iframe/overlay covered the chip. Strip overlays and retry with
            # JS-dispatched click — bypasses the pointer_events check.
            log.info("gear chip click via locator failed (%s); retrying via JS dispatch", label)
            _strip_overlay_iframes(page)
            _force_click(page, CHIP_SELECTOR, has_text=label)

    _click_chip(category_label)
    _click_chip(grade_label)
    if obtainable_only:
        # The checkbox input is overlaid by .gear-toggle-box (intercepts
        # pointer events); .check() times out. Click the visible wrapper
        # instead, but only when not already checked (avoid toggling it off).
        cb = page.locator(OBTAINABLE_CHECKBOX_SELECTOR)
        if not cb.is_checked():
            try:
                page.locator(TOGGLE_BOX_SELECTOR).click()
            except Exception:
                log.info("obtainable toggle click via locator failed; retrying via JS dispatch")
                _strip_overlay_iframes(page)
                _force_click(page, TOGGLE_BOX_SELECTOR)


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


def _scrape_one_combo(
    page: Any,
    cat: str,
    grade: str,
    *,
    out_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[dict[str, Any]] | None:
    """Scrape a single (cat, grade) combo with one iframe-strip retry.

    Returns the parsed items list on success. Returns None to signal the caller
    should fall back to the cache for this combo (logged as warning either way).
    Most failures are transient iframe overlays; the retry strips them and
    re-navigates. If the retry also fails, the caller falls back to cache.
    """
    cache_path = _cache_path(out_dir, cat, grade)
    for attempt in (1, 2):
        if cancel_event is not None and cancel_event.is_set():
            return None
        try:
            page.goto(GEAR_URL)
            _select_gear_filters(page, cat, grade, obtainable_only=True)
            items = scrape_gear_batch(page)
            write_gear_cache(cache_path, items)
            log.info("gear %s/%s scraped %d items", cat, grade, len(items))
            return items
        except Exception as exc:
            if attempt == 1:
                # Strip overlay iframes (Cloudflare / ads) and retry. This
                # fixes the "element is covered by <IFRAME>" pointer_events
                # failure that fires sporadically on cold scrapes.
                log.info(
                    "gear %s/%s attempt 1 failed (%s); stripping iframes and retrying",
                    cat, grade, exc,
                )
                try:
                    _strip_overlay_iframes(page)
                except Exception:
                    pass
                continue
            log.warning("gear %s/%s scrape failed: %s", cat, grade, exc)
            return None
    return None  # unreachable; loop has 2 iterations max


def refresh_gear_full(
    out_dir: Path,
    categories: list[str] | None = None,
    grades: list[str] | None = None,
    cancel_event: threading.Event | None = None,
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

    If *cancel_event* is set (e.g. by ``GearScraperRunner.stop()``), the loop
    bails early and the browser is closed by this function's own ``finally``.
    The browser is owned by the scrape thread that called this function —
    callers from other threads must NOT call ``browser.close()`` themselves
    (race with the in-progress close).
    """
    cats = list(categories) if categories is not None else list(GEAR_CATEGORIES)
    grads = list(grades) if grades is not None else list(LEGENDARY_UP_GRADES)
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, list[dict[str, Any]]] = {}

    def _fallback(cat: str, grade: str) -> list[dict[str, Any]]:
        items = read_gear_cache(_cache_path(out_dir, cat, grade))
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
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    key = f"{cat}_{grade}"
                    items = _scrape_one_combo(page, cat, grade, out_dir=out_dir, cancel_event=cancel_event)
                    if items is not None:
                        result[key] = items
                if cancel_event is not None and cancel_event.is_set():
                    break
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


def parse_item_detail(html: str) -> dict[str, Any]:
    """Parse an item detail page (e.g. /items/300001-long-sword).

    Extracts the wiki-provided flavor description and a stats dict. Field names
    in the stats dict are whatever the wiki uses (varies per item type).
    Returns an empty dict if the page has no parseable content.

    The parser is intentionally lenient — many fields are missing or differently
    named across item types (gear / material / consumable). Empty/missing fields
    are silently skipped. Used to populate the picker's "more info" tooltip.
    """
    soup = BeautifulSoup(html, "lxml")
    result: dict[str, Any] = {}

    # Flavor text: <meta name="description"> is the cheapest reliable source.
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc is not None:
        content = meta_desc.get("content", "")
        if isinstance(content, str):
            content = content.strip()
            if content:
                result["flavor"] = content

    # Stats: look for a <dl> or table with "Stats"/"Bonuses" heading, then
    # collect the dt/dd pairs (or table rows) under it. Best-effort: if the
    # page doesn't follow that structure, stats stays empty.
    def _stats_heading(tag: Any) -> bool:
        if tag.name not in ("h2", "h3", "h4"):
            return False
        # Match words like "Stats", "Bonuses", "Effects" — \b doesn't work
        # for "Stats" because of the trailing 's'. Use explicit alternation.
        return bool(
            re.search(
                r"\b(?:stats?|bonuses?|effects?)\b",
                tag.get_text(strip=True),
                re.IGNORECASE,
            )
        )

    stats_heading = soup.find(_stats_heading)
    if stats_heading is not None:
        stats: dict[str, str] = {}
        # Try <dl> format first.
        dl = stats_heading.find_next("dl")
        if dl is not None:
            for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
                k = dt.get_text(strip=True)
                v = dd.get_text(strip=True)
                if k:
                    stats[k] = v
        if stats:
            result["stats"] = stats

    return result


ITEM_DETAIL_URL_TEMPLATE = "https://taskbarhero.org/en/items/{slug}/"

DROPS_URL = "https://taskbarhero.org/en/tools/drops/"

# Family ordering for the picker (rarity→family). Used to group items so the
# box loot picker presents them in a stable, intuitive order.
FAMILY_ORDER: tuple[str, ...] = (
    "CRAFTING",
    "DECORATION",
    "ENGRAVING",
    "INSCRIPTION",
    "OFFERING",
    "SOULSTONE",
)

RARITY_ORDER: tuple[str, ...] = (
    "COMMON",
    "UNCOMMON",
    "RARE",
    "LEGENDARY",
    "IMMORTAL",
    "ARCANA",
    "BEYOND",
    "CELESTIAL",
    "DIVINE",
    "COSMIC",
)


def parse_drops_page(html: str) -> list[dict[str, Any]]:
    """Parse /en/tools/drops/ HTML and extract every item row.

    Returns a list of dicts: {id, name, kind, rarity, family, search_text}.
    The table rows have ``data-id``, ``data-name``, ``data-kind``,
    ``data-rarity``, ``data-family``, ``data-search`` attributes that we
    parse via BeautifulSoup. Used to populate the BoxLootPicker with ALL
    non-gear items (materials, stage boxes, consumables) instead of having
    the user pick a box first.
    """
    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, Any]] = []
    for tr in soup.select("tr[data-id]"):
        item_id_str = str(tr.get("data-id", "")).strip()
        if not item_id_str.isdigit():
            continue
        name = str(tr.get("data-name", "")).strip()
        if not name:
            continue
        items.append({
            "id": int(item_id_str),
            "name": name,
            "kind": str(tr.get("data-kind", "other")).strip(),
            "rarity": str(tr.get("data-rarity", "COMMON")).strip(),
            "family": str(tr.get("data-family", "")).strip(),
            "search_text": str(tr.get("data-search", "")).strip(),
        })
    return items


def write_drops_index(path: Path, items: list[dict[str, Any]]) -> None:
    """Persist the parsed drops index. Keys are stringified ints (JSON limit)."""
    payload = {
        "fetched_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_drops_index(path: Path) -> list[dict[str, Any]]:
    """Load the drops index. Returns [] if missing or invalid."""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    return []


def fetch_drops_index(cache_path: Path, *, force: bool = False) -> list[dict[str, Any]]:
    """Fetch /en/tools/drops/ and cache the parsed result.

    Returns the cached items if cache exists and ``force`` is False. On
    network failure, falls back to whatever's in the cache (even if stale).
    """
    if not force:
        cached = read_drops_index(cache_path)
        if cached:
            return cached
    try:
        resp = requests.get(DROPS_URL, timeout=30)
        resp.raise_for_status()
        items = parse_drops_page(resp.text)
        write_drops_index(cache_path, items)
        log.info("drops index: %d items cached", len(items))
        return items
    except Exception as exc:
        log.warning("drops index fetch failed: %s", exc)
        # Last resort: return stale cache if we have it.
        return read_drops_index(cache_path)


def fetch_item_detail(item_id: int, slug: str, cache_path: Path) -> dict[str, Any]:
    """Fetch item detail page and cache it. Returns empty dict on failure.

    cache_path is the path to the per-item cache JSON file (caller decides
    layout). Result is also cached to disk so subsequent calls are free.
    """
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8-sig"))
            if isinstance(cached, dict):
                return cached
        except (json.JSONDecodeError, OSError):
            pass
    try:
        url = ITEM_DETAIL_URL_TEMPLATE.format(slug=slug)
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        detail = parse_item_detail(resp.text)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(detail, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return detail
    except Exception as exc:
        log.warning("item detail fetch failed for %s: %s", item_id, exc)
        return {}


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
