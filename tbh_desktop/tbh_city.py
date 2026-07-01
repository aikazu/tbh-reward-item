"""Fetch + parse tbh.city (Next.js SSR) into JSON caches.

tbh.city is a community datamined wiki for Task Bar Hero. It exposes the
full item/stage/drop dataset embedded in the HTML's Next.js flight payload
(self.__next_f.push), so we get:

* Every item (gear + material) with id/name/grade/icon/stat_types/hero_class
  from ``/items`` (5875 entries, single page).
* Every stage (120 entries: 3 acts x 10 stages x 4 difficulties, with boss
  variants) from ``/stages`` (single page).
* Per-stage drop tables (monster_pool, boss_pool, first_clear) with weighted
  item_id entries from ``/stages/<id>`` (120 detail pages).
* Per-item stats (BASE/INHERENT stat rolls + alchemy_gold + cube_exp) from
  ``/items/<id>`` (5875 detail pages).

Image assets live at ``https://tbh.city/sprites/sharedassets0/<FILE>.png``
where <FILE> comes from the item's ``icon`` field (already includes the
relative path).

This module is the canonical source for new scrape workflows. The old
wiki-based gear scraper (taskbarhero.wiki) and box-page scraper
(taskbarhero.org/en/items/chests) remain for fallback / migration but are
no longer the active path.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

# tbh.city base URL — Next.js SSR renders the data inline; no JSON API needed.
BASE_URL = "https://tbh.city"
ITEMS_URL = f"{BASE_URL}/items"
STAGES_URL = f"{BASE_URL}/stages"
ITEM_DETAIL_URL_TEMPLATE = f"{BASE_URL}/items/{{item_id}}"
STAGE_DETAIL_URL_TEMPLATE = f"{BASE_URL}/stages/{{stage_id}}"

# Image CDN prefix (item.icon is relative — strip leading 'sprites/' if present).
SPRITE_PREFIX = f"{BASE_URL}/sprites/sharedassets0/"

# User-Agent — tbh.city returns 200 to plain curl but a real browser UA
# avoids occasional bot-block on detail pages.
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

REQUEST_TIMEOUT = 30

# Rarity ranking — used to filter gear to "Legendary and up" per user request.
RARITY_ORDER: tuple[str, ...] = (
    "COMMON", "UNCOMMON", "RARE",
    "LEGENDARY", "IMMORTAL", "ARCANA", "BEYOND",
    "CELESTIAL", "DIVINE", "COSMIC",
)
LEGENDARY_UP_RARITIES: frozenset[str] = frozenset(RARITY_ORDER[3:])

# Item id prefix -> (slot folder, TYPE prefix used in icon filename). Mirrors
# the existing scraper._ITEM_ID_TO_GEAR_URL so the picker / image cache
# sees the same shapes regardless of source.
ITEM_ID_TO_GEAR_URL: dict[str, tuple[str, str]] = {
    "30": ("sword", "SWORD"),
    "31": ("bow", "BOW"),
    "32": ("staff", "STAFF"),
    "33": ("scepter", "SCEPTER"),
    "34": ("crossbow", "CROSSBOW"),
    "35": ("axe", "AXE"),
    "40": ("shield", "SHIELD"),
    "41": ("arrow", "ARROW"),
    "42": ("orb", "ORB"),
    "43": ("tome", "TOME"),
    "44": ("bolt", "BOLT"),
    "45": ("hatchet", "HATCHET"),
    "50": ("helmet", "HELMET"),
    "51": ("armor", "ARMOR"),
    "52": ("gloves", "GLOVES"),
    "53": ("boots", "BOOTS"),
    "60": ("amulet", "AMULET"),
    "61": ("earing", "EARING"),
    "62": ("ring", "RING"),
    "63": ("bracer", "BRACER"),
}


# ---------------------------------------------------------------------------
# Low-level: extract JSON values from Next.js flight payload chunks
# ---------------------------------------------------------------------------

_NEXT_F_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.DOTALL)


def _split_flight_chunks(html: str) -> list[str]:
    """Return the raw payload chunks from a Next.js SSR HTML page."""
    return _NEXT_F_RE.findall(html)


def _decode_chunk(chunk: str) -> str:
    """Reverse the JS string escapes that Next.js applies to each chunk.

    The page wraps the chunk in a JS string literal (so ``\\`` → one backslash,
    ``\\"`` → one quote), then HTML escapes the whole script body (so
    ``\\"`` becomes ``\\\\\\"`` etc.). Our regex captures the inner JS-string
    contents, which are still in JS-escape form. Two replacements undo it.
    """
    return chunk.replace('\\"', '"').replace('\\\\', '\\')


def _balanced_slice(text: str, start: int) -> tuple[Any, int]:
    """Parse a JSON value starting at *start* (which must point at the
    opening ``[`` or ``{``). Returns ``(value, end_index_after_close)``.

    Tracks nesting depth and skips over string contents (including escape
    sequences) so commas / brackets inside strings don't confuse the parser.
    """
    opener = text[start]
    if opener == '[':
        closer = ']'
    elif opener == '{':
        closer = '}'
    else:
        raise ValueError(f"expected [ or {{ at {start}, got {opener!r}")
    depth = 0
    in_str = False
    escape = False
    for j in range(start, len(text)):
        ch = text[j]
        if escape:
            escape = False
            continue
        if in_str:
            if ch == '\\':
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[start:j + 1]), j + 1
    raise ValueError(f"unterminated JSON value starting at {start}")


def _find_top_level_key(decoded_chunks: list[str], key: str) -> Any:
    """Walk decoded payload chunks, find the first balanced value at the
    JSON top level (no leading quote-bound prefix) for *key*.

    tbh.city payloads always start each chunk with an index prefix like
    ``"1f:"`` or ``"abc:"`` then the array/object literal. The key itself
    can appear at any depth; we only care about the first balanced value
    after the first ``"<key>":`` literal we find inside an object.
    """
    needle = f'"{key}":'
    for chunk in decoded_chunks:
        idx = chunk.find(needle)
        if idx < 0:
            continue
        start = idx + len(needle)
        # Skip whitespace.
        while start < len(chunk) and chunk[start] in ' \t\n\r':
            start += 1
        if start >= len(chunk):
            continue
        if chunk[start] not in ('[', '{'):
            continue
        try:
            value, _ = _balanced_slice(chunk, start)
            return value
        except (ValueError, json.JSONDecodeError) as exc:
            log.debug("balanced parse for key %r failed: %s", key, exc)
            continue
    return None


# ---------------------------------------------------------------------------
# Stage list (single-page index of all 120 stages)
# ---------------------------------------------------------------------------

def fetch_stages_index(*, force: bool = False) -> list[dict[str, Any]]:
    """Fetch and parse the stage index from /stages.

    Returns a list of stage dicts: {id, act, stage_no, name, type,
    difficulty, boss_id, expected_gold, expected_exp}. Returns [] on
    network failure (caller can fall back to a previous cache).
    """
    try:
        resp = requests.get(STAGES_URL, headers={"User-Agent": DEFAULT_UA}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("fetch_stages_index network failure: %s", exc)
        return []
    chunks = [_decode_chunk(c) for c in _split_flight_chunks(resp.text)]
    stages = _find_top_level_key(chunks, "stages")
    if not isinstance(stages, list):
        log.warning("fetch_stages_index: 'stages' array not found")
        return []
    return stages


def write_stages_index(path: Path, stages: list[dict[str, Any]]) -> None:
    """Persist the stages index. Includes fetched_at + raw list."""
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(stages),
        "stages": stages,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_stages_index(path: Path) -> list[dict[str, Any]]:
    """Load stages index. Returns [] on missing/invalid file."""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, dict) and isinstance(payload.get("stages"), list):
        return payload["stages"]
    return []


# ---------------------------------------------------------------------------
# Stage detail (drop tables per stage)
# ---------------------------------------------------------------------------

def fetch_stage_detail(stage_id: int) -> dict[str, Any]:
    """Fetch and parse a single stage detail page.

    Returns a dict with: id, act, stage_no, name (multi-lang), difficulty,
    type, drops (with monster_pool / boss_pool / first_clear), boss,
    monsters, waves, expected_gold, expected_exp. Returns {} on network
    failure or parse error.
    """
    try:
        resp = requests.get(
            STAGE_DETAIL_URL_TEMPLATE.format(stage_id=stage_id),
            headers={"User-Agent": DEFAULT_UA},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("fetch_stage_detail(%s) network failure: %s", stage_id, exc)
        return {}
    chunks = [_decode_chunk(c) for c in _split_flight_chunks(resp.text)]
    stage = _find_top_level_key(chunks, "stage")
    if not isinstance(stage, dict):
        log.warning("fetch_stage_detail(%s): 'stage' object not found", stage_id)
        return {}
    return stage


def flatten_stage_drops(stage: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a stage's drop tables into a single list of
    ``{item_id, weight, source, group, hero_condition, is_dlc_hero}``.

    *source* is one of ``"monster"``, ``"boss"``, or ``"first_clear"`` —
    tells the picker where the item came from inside this stage so the
    "Drops from" column can group rows usefully.

    Duplicate item_ids across pools (or across pool entries) are kept as
    separate rows. The item-detail stage source count uses these weights,
    not summed probabilities — preserves per-pool granularity.
    """
    out: list[dict[str, Any]] = []
    drops = stage.get("drops") or {}
    if not isinstance(drops, dict):
        return out

    pool_map = (
        ("monster", drops.get("monster_pool")),
        ("boss", drops.get("boss_pool")),
        ("first_clear", drops.get("first_clear")),
    )
    for source, pool in pool_map:
        if not isinstance(pool, list):
            continue
        for entry in pool:
            if not isinstance(entry, dict):
                continue
            for row in entry.get("entries") or []:
                if not isinstance(row, dict):
                    continue
                item_id = row.get("item_id")
                if not isinstance(item_id, int):
                    continue
                out.append({
                    "item_id": item_id,
                    "weight": row.get("weight", 0),
                    "source": source,
                    "group": row.get("group"),
                    "hero_condition": row.get("hero_condition"),
                    "is_dlc_hero": bool(row.get("is_dlc_hero", False)),
                    "drop_type": row.get("drop_type"),
                })
    return out


def write_stage_cache(stage_dir: Path, stage_id: int, data: dict[str, Any]) -> None:
    """Write one JSON file per stage: ``<stage_dir>/<id>.json``.

    The file contains the raw stage payload (verbatim from tbh.city) plus
    a ``flattened_drops`` array for fast iteration by consumers that don't
    need the full pool structure.
    """
    stage_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["flattened_drops"] = flatten_stage_drops(data)
    p = stage_dir / f"{stage_id}.json"
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def read_stage_cache(stage_dir: Path, stage_id: int) -> dict[str, Any]:
    """Load a cached stage payload. {} on missing/invalid."""
    p = stage_dir / f"{stage_id}.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Item list (single-page index of all 5875 items)
# ---------------------------------------------------------------------------

def fetch_items_index(*, force: bool = False) -> list[dict[str, Any]]:
    """Fetch and parse the item index from /items.

    Returns a list of item dicts: {id, name, icon, grade, type, gear_id,
    stat_types, source_count, obtainable_in_live_game, only_torment_drops,
    is_market_tradable, hero_class, drop_cooldown, unique_mod}. The list
    includes ALL items (gear + material) — callers filter by type / grade.
    Returns [] on network failure.
    """
    try:
        resp = requests.get(ITEMS_URL, headers={"User-Agent": DEFAULT_UA}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("fetch_items_index network failure: %s", exc)
        return []
    chunks = [_decode_chunk(c) for c in _split_flight_chunks(resp.text)]
    items = _find_top_level_key(chunks, "items")
    if not isinstance(items, list):
        log.warning("fetch_items_index: 'items' array not found")
        return []
    return items


def write_items_index(path: Path, items: list[dict[str, Any]]) -> None:
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(items),
        "items": items,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_items_index(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    return []


def _name_to_en(name: Any) -> str:
    """Pull the English display name out of an item/stage name field.

    tbh.city stores names as a multi-lang dict like
    ``{"en": "Long Sword", "es": "Espada Larga", ...}``. Fall back to the
    dict's first string value, then to ``str(name)`` so callers always
    get a usable string even for unusual shapes.
    """
    if isinstance(name, dict):
        val = name.get("en")
        if isinstance(val, str) and val:
            return val
        for v in name.values():
            if isinstance(v, str) and v:
                return v
    if isinstance(name, str):
        return name
    return str(name)


def _normalize_item_for_cache(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw tbh.city item into the shape the desktop pickers
    expect (matching the old wiki scraper output as closely as possible).

    Key mapping:
      * id, name (en), grade, type, icon
      * rarity = grade (lowercased for the existing UI's rarity_color logic)
      * stat_types: list[str] of stat codes (raw from tbh.city)
      * base_stats / inherent_stats: only present after item-detail scrape
      * image: absolute URL derived from icon
      * obtainable, only_torment, market_tradable: booleans
    """
    icon = str(item.get("icon") or "")
    image_url = ""
    if icon:
        # Strip leading "sprites/" if present, then prefix with CDN.
        if icon.startswith("/"):
            image_url = BASE_URL + icon
        elif icon.startswith("sprites/"):
            image_url = SPRITE_PREFIX + icon[len("sprites/"):]
        else:
            image_url = SPRITE_PREFIX + icon
    return {
        "id": int(item.get("id") or 0),
        "name": _name_to_en(item.get("name")),
        "grade": str(item.get("grade") or ""),
        "rarity": str(item.get("grade") or "").capitalize(),
        "type": str(item.get("type") or ""),
        "icon": icon,
        "image": image_url,
        "stat_types": list(item.get("stat_types") or []),
        "unique_mod": item.get("unique_mod"),
        "gear_id": item.get("gear_id"),
        # Categorization fields populated below — gear gets a slot_category
        # (Weapon / Off-hand / Armor / Accessory), material gets a family
        # (Crafting / Decoration / Soulstone / etc.). See the helper
        # functions below for the exact rules.
        "slot_category": "",
        "slot_type": "",
        "family": "",
        "hero_class": item.get("hero_class"),
        "source_count": int(item.get("source_count") or 0),
        "obtainable": bool(item.get("obtainable_in_live_game", False)),
        "only_torment": bool(item.get("only_torment_drops", False)),
        "market_tradable": bool(item.get("is_market_tradable", False)),
        "drop_cooldown": item.get("drop_cooldown"),
    }


# ─── Categorization helpers ─────────────────────────────────────────
# tbh.city's /items list doesn't expose slot_type, slot_category, or
# material family directly. We derive them:
#   * slot_type       — slot-specific ("Sword", "Helmet", ...) via
#                       ``detect_slot_type`` (icon path) or
#                       ``detect_slot_type_from_id`` (ID prefix fallback).
#   * slot_category   — coarse group ("Weapon" / "Off-hand" /
#                       "Armor" / "Accessory") from the ID prefix. Picker
#                       chips use this for the 4-category filter.
#   * family          — material category ("Crafting" / "Decoration" /
#                       "Soulstone" / etc.) via name + stat_types
#                       heuristic (tbh.city doesn't carry an explicit
#                       family field — see scrape_stage notes).

# ID prefix (2 digits) → slot_category. Mirrors _ITEM_ID_TO_GEAR_URL
# below but in the 4-bucket picker shape.
_SLOT_PREFIX_TO_CATEGORY: dict[str, str] = {
    "30": "Weapon", "31": "Weapon", "32": "Weapon", "33": "Weapon",
    "34": "Weapon", "35": "Weapon", "45": "Weapon",  # hatchet
    "40": "Off-hand", "41": "Off-hand", "42": "Off-hand",
    "43": "Off-hand", "44": "Off-hand",  # tome, bolt
    "50": "Armor", "51": "Armor", "52": "Armor", "53": "Armor",
    "60": "Accessory", "61": "Accessory", "62": "Accessory", "63": "Accessory",
    "64": "Accessory", "65": "Accessory", "66": "Accessory", "67": "Accessory",
    "68": "Accessory", "69": "Accessory",
}
_DEFAULT_SLOT_CATEGORY = "Unknown"


def _slot_category_from_id(item_id: int) -> str:
    """Coarse slot bucket (Weapon / Off-hand / Armor / Accessory) from
    the item id prefix. Returns ``"Unknown"`` for unrecognised prefixes.
    """
    s = str(int(item_id)).zfill(6)
    if len(s) < 2:
        return _DEFAULT_SLOT_CATEGORY
    return _SLOT_PREFIX_TO_CATEGORY.get(s[:2], _DEFAULT_SLOT_CATEGORY)


# Material family detection — name-keyword heuristic used as
# fallback for materials tbh.city doesn't tag with an explicit
# ``family`` field. (Most items arrive already tagged; this only
# fires when the scrape missed the field.)
#
# Jul 2026: SOULSTONE + OFFERING keywords dropped because
# tbh.city's items_normalized.json never produces items in
# those families (per user feedback — don't scrape / show them).
# CRAFTING was the v1 wiki default; tbh.city doesn't tag items
# as CRAFTING either, so it's only the catch-all label for
# items that arrive without an explicit family field.
_MATERIAL_FAMILY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("DECORATION", (
        "ruby", "sapphire", "topaz", "emerald", "amethyst", "opal",
        "diamond", "pearl", "quartz", "garnet", "jade", "amber",
        "turquoise", "lapis", "obsidian", "coral", "crystal",
    )),
    ("ENGRAVING", ("engraving", "engraved", "etching", "etched")),
    ("INSCRIPTION", ("inscription", "scroll", "rune")),
)
# Items that don't match any keyword + don't carry an explicit
# family field land here. Empty string rather than "CRAFTING"
# — the picker chip row dropped CRAFTING in Jul 2026 and the
# user wants no reference to the legacy family name in code
# or tests. Downstream code that needs a non-empty family
# label should default to "DECORATION" (or any visible chip).
_DEFAULT_MATERIAL_FAMILY = ""


def _material_family(name: str, stat_types: list[str]) -> str:
    """Infer a material family from the item's English name.

    tbh.city's items payload carries an explicit ``family`` field
    in most cases — this heuristic is the fallback used when the
    field is missing. Detects 3 families (Deco / Engraving /
    Inscription); falls through to an empty string for anything
    that doesn't match a known keyword. Jul 2026: SOULSTONE +
    OFFERING + CRAFTING were dropped entirely from the keyword
    table + default — the user doesn't want any reference to
    those legacy family names anywhere in the code.
    """
    name_lower = (name or "").lower()
    if name_lower:
        for family, keywords in _MATERIAL_FAMILY_KEYWORDS:
            for kw in keywords:
                if kw in name_lower:
                    return family
    # stat_types fallback — e.g. SoulstoneRefine stat → SOULSTONE
    for family, keywords in _MATERIAL_FAMILY_KEYWORDS:
        for kw in keywords:
            if any(kw in s.lower() for s in stat_types):
                return family
    return _DEFAULT_MATERIAL_FAMILY


def _apply_categories(item: dict[str, Any]) -> dict[str, Any]:
    """Populate slot_category / slot_type / family on a normalized item
    in-place. Returns the same dict for convenience.
    """
    if not isinstance(item, dict):
        return item
    item_type = item.get("type") or ""
    if item_type == "GEAR":
        # slot_type = detailed ("Sword", "Helmet", ...); falls back to ""
        # when neither icon nor id carries the slot signal.
        item["slot_type"] = detect_slot_type(item.get("icon") or "") or detect_slot_type_from_id(int(item.get("id") or 0))
        item["slot_category"] = _slot_category_from_id(int(item.get("id") or 0))
        item["family"] = ""  # not meaningful for gear
    elif item_type == "MATERIAL":
        item["slot_type"] = ""
        item["slot_category"] = ""
        item["family"] = _material_family(
            item.get("name") or "",
            list(item.get("stat_types") or []),
        )
    else:
        item["slot_type"] = ""
        item["slot_category"] = ""
        item["family"] = ""
    return item


def normalize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Vector wrapper around :func:`_normalize_item_for_cache` that also
    applies the slot_category / family categorization.
    """
    return [_apply_categories(_normalize_item_for_cache(it)) for it in items if isinstance(it, dict)]


# ---------------------------------------------------------------------------
# Item detail (BASE / INHERENT stats + alchemy/cube values)
# ---------------------------------------------------------------------------

def fetch_item_detail(item_id: int) -> dict[str, Any]:
    """Fetch and parse a single item detail page from tbh.city.

    Returns a dict with: id, name (en), grade, type, base_stats,
    inherent_stats, unique_mod, alchemy_gold, cube_exp, hero_class. The
    stage source list (which stages drop this item) is also embedded in
    the detail page — preserved as ``stage_sources``.

    Returns {} on network failure or parse error. Pages where the item
    doesn't exist return {} (HTTP 200 with a "not found" page — handled
    by the empty ``item`` block).
    """
    try:
        resp = requests.get(
            ITEM_DETAIL_URL_TEMPLATE.format(item_id=item_id),
            headers={"User-Agent": DEFAULT_UA},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("fetch_item_detail(%s) network failure: %s", item_id, exc)
        return {}
    chunks = [_decode_chunk(c) for c in _split_flight_chunks(resp.text)]
    item = _find_top_level_key(chunks, "item")
    if not isinstance(item, dict):
        return {}
    # Light normalization — pass through the stat rolls verbatim, just
    # convert name to en-only.
    return {
        "id": int(item.get("ItemKey") or item_id),
        "name": _name_to_en(item.get("NameKey") or item.get("name")),
        "grade": str(item.get("GRADE") or ""),
        "type": str(item.get("ITEMTYPE") or ""),
        "gear_type": str(item.get("GEARTYPE") or ""),
        "parts": str(item.get("PARTS") or ""),
        "hero_class": item.get("hero_class"),
        "base_stats": list(item.get("base_stats") or []),
        "inherent_stats": list(item.get("inherent_stats") or []),
        "unique_mod": item.get("unique_mod"),
        "alchemy_gold": item.get("alchemy_gold"),
        "cube_exp": item.get("cube_exp"),
        "material": item.get("material"),
        "stage_sources": list(item.get("drop_sources") or []),
        "stat_types": list(item.get("stat_types") or []),
    }


# ---------------------------------------------------------------------------
# Reverse map: item_id -> stage sources (replaces the old box_drop_map.json)
# ---------------------------------------------------------------------------

def build_stage_drop_map(stage_dir: Path, stages_index: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """Aggregate cached stage payloads into a reverse index:
    ``{item_id: [{stage_id, source, weight, group, ...}, ...]}``.

    Each list is sorted by ``(source, stage_id)`` so monster drops appear
    before boss drops, and within each source by stage id for stable
    display. This replaces ``box_drop_map.json`` in the desktop UI — the
    picker's "Drops from" column now shows stages instead of boxes.
    """
    drop_map: dict[int, list[dict[str, Any]]] = {}
    for stage in stages_index:
        sid = stage.get("id")
        if not isinstance(sid, int):
            continue
        cached = read_stage_cache(stage_dir, sid)
        if not cached:
            continue
        # The cache already flattens, but re-derive in case the file is
        # from an older schema.
        rows = cached.get("flattened_drops") or flatten_stage_drops(cached)
        for row in rows:
            iid = row.get("item_id")
            if not isinstance(iid, int):
                continue
            entry = dict(row)
            entry["stage_id"] = sid
            entry["stage_name"] = _name_to_en(stage.get("name"))
            entry["act"] = stage.get("act")
            entry["stage_no"] = stage.get("stage_no")
            entry["difficulty"] = stage.get("difficulty")
            drop_map.setdefault(iid, []).append(entry)
    for item_id in drop_map:
        drop_map[item_id].sort(key=lambda r: (r.get("source", ""), r.get("stage_id", 0)))
    return drop_map


def write_stage_drop_map(path: Path, drop_map: dict[int, list[dict[str, Any]]]) -> None:
    serializable = {str(iid): rows for iid, rows in drop_map.items()}
    payload = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "drops": serializable}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Pool drop-key index. Stage details nest their drops under named
# pools (monster_pool / boss_pool / first_clear); each pool entry has
# a ``drop_key`` (e.g. ``9100111``) that's shared across multiple
# stages in the same act+difficulty band. To enforce "replacement must
# drop in the rule's pool" we need the inverse map: drop_key -> set of
# item_ids that pool can yield. Build it once from the per-stage
# detail cache.
# ---------------------------------------------------------------------------

def build_pool_drop_key_map(stage_dir: Path) -> dict[int, list[int]]:
    """Walk every ``<stage_dir>/<id>.json`` and produce
    ``{drop_key: [item_id, ...]}`` by flattening the monster_pool,
    boss_pool, and first_clear pools per stage.

    The same drop_key can appear across many stages (e.g. Act 1
    stages 1-9 Normal all share monster_pool 9100111); we union the
    item_ids from every stage that references each drop_key so the
    desktop picker's "pool scope" is the full set of items that
    can drop in that pool across the entire game.
    """
    out: dict[int, list[int]] = {}
    if not stage_dir.exists():
        return out
    for path in stage_dir.glob("*.json"):
        try:
            stage = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(stage, dict):
            continue
        drops = stage.get("drops") or {}
        if not isinstance(drops, dict):
            continue
        for pool_name in ("monster_pool", "boss_pool", "first_clear"):
            pool = drops.get(pool_name) or []
            if not isinstance(pool, list):
                continue
            for entry in pool:
                if not isinstance(entry, dict):
                    continue
                drop_key = entry.get("drop_key")
                if not isinstance(drop_key, int):
                    continue
                seen: set[int] = set(out.get(drop_key, []))
                for row in entry.get("entries") or []:
                    if not isinstance(row, dict):
                        continue
                    iid = row.get("item_id")
                    if isinstance(iid, int) and iid not in seen:
                        seen.add(iid)
                if seen:
                    out[drop_key] = sorted(seen)
    return out


def write_pool_drop_key_map(
    path: Path, pool_map: dict[int, list[int]],
) -> None:
    """Persist the pool drop-key map (companion to stage_drop_map.json)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {str(k): v for k, v in pool_map.items()}
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pool_drops": serializable,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_pool_drop_key_map(path: Path) -> dict[int, list[int]]:
    """Load the pool drop-key map. Empty dict when absent."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("pool_drops") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[int, list[int]] = {}
    for k, v in raw.items():
        try:
            dk = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, list):
            out[dk] = [int(i) for i in v if isinstance(i, int) or (isinstance(i, str) and i.isdigit())]
    return out


def read_stage_drop_map(path: Path) -> dict[int, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[int, list[dict[str, Any]]] = {}
    drops = payload.get("drops") if isinstance(payload, dict) else None
    if not isinstance(drops, dict):
        return {}
    for k, v in drops.items():
        try:
            iid = int(k)
        except (ValueError, TypeError):
            continue
        if isinstance(v, list):
            out[iid] = v
    return out


# ---------------------------------------------------------------------------
# Convenience: build the per-(cat, grade) gear cache files from items index
# ---------------------------------------------------------------------------

# Slot detection from the icon path (matches tbh.city's naming).
_ICON_SLOT_RE = re.compile(
    r"/(SWORD|BOW|STAFF|SCEPTER|CROSSBOW|AXE|HATCHET|SHIELD|OFFHAND|"
    r"ARROW|ORB|TOME|BOLT|HELMET|ARMOR|GLOVES|BOOTS|AMULET|EARING|RING|BRACER)"
    r"_\d+\.png",
    re.IGNORECASE,
)
_ICON_SLOT_TO_TYPE: dict[str, str] = {
    "SWORD": "Sword", "BOW": "Bow", "STAFF": "Staff", "SCEPTER": "Scepter",
    "CROSSBOW": "Crossbow", "AXE": "Axe", "HATCHET": "Hatchet",
    "SHIELD": "Shield", "OFFHAND": "Offhand", "ARROW": "Arrow", "ORB": "Orb",
    "TOME": "Tome", "BOLT": "Bolt",
    "HELMET": "Helmet", "ARMOR": "Armor", "GLOVES": "Gloves", "BOOTS": "Boots",
    "AMULET": "Amulet", "EARING": "Earring", "RING": "Ring", "BRACER": "Bracer",
}


def detect_slot_type(icon: str) -> str:
    """Pull the slot type ("Sword", "Helmet", ...) from an icon path.

    tbh.city icons are named like ``sprites/sharedassets0/SWORD_300001.png``
    or ``.../HELMET_500011.png``. The slot is the uppercase prefix before
    the underscore. Returns "" if the icon doesn't match the expected
    pattern — caller falls back to id-prefix lookup.
    """
    if not icon:
        return ""
    m = _ICON_SLOT_RE.search(icon)
    if not m:
        return ""
    return _ICON_SLOT_TO_TYPE.get(m.group(1).upper(), "")


def detect_slot_type_from_id(item_id: int) -> str:
    """Slot type from the numeric item id prefix. Used as fallback when
    the icon path doesn't carry the slot info."""
    s = str(int(item_id)).zfill(6)
    if len(s) != 6:
        return ""
    prefix = s[:2]
    slot, _type_name = ITEM_ID_TO_GEAR_URL.get(prefix, ("", ""))
    return slot.capitalize() if slot else ""


def split_gear_by_slot_and_grade(
    items: list[dict[str, Any]],
    *,
    obtainable_only: bool = True,
    min_grade: str = "LEGENDARY",
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group gear items into ``{(slot_slug, grade): [item, ...]}`` for the
    existing per-(cat, grade) JSON cache files.

    *items* must already be :func:`normalize_items`-shaped (not raw tbh.city
    payload). Slot slug is one of ``weapon | offhand | armor | accessory`` —
    matches the existing picker chip labels.
    """
    slot_map = {
        # Weapons
        "Sword": "weapon", "Bow": "weapon", "Staff": "weapon",
        "Scepter": "weapon", "Crossbow": "weapon", "Axe": "weapon",
        "Hatchet": "weapon",
        # Off-hand
        "Shield": "offhand", "Arrow": "offhand", "Orb": "offhand",
        "Tome": "offhand", "Bolt": "offhand",
        # Armor
        "Helmet": "armor", "Armor": "armor", "Gloves": "armor", "Boots": "armor",
        # Accessory
        "Amulet": "accessory", "Earring": "accessory", "Ring": "accessory",
        "Bracer": "accessory",
    }
    grades = frozenset(RARITY_ORDER)
    min_idx = RARITY_ORDER.index(min_grade) if min_grade in grades else 0
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in items:
        if it.get("type") != "GEAR":
            continue
        if obtainable_only and not it.get("obtainable"):
            continue
        grade = (it.get("grade") or "").upper()
        if grade not in grades:
            continue
        if RARITY_ORDER.index(grade) < min_idx:
            continue
        # Determine slot.
        slot_type = it.get("slot_type") or detect_slot_type(it.get("icon", ""))
        if not slot_type:
            slot_type = detect_slot_type_from_id(it.get("id", 0))
        cat = slot_map.get(slot_type, "weapon")
        grade_slug = grade.lower()
        out.setdefault((cat, grade_slug), []).append(it)
    # Stable sort inside each bucket by id.
    for key in out:
        out[key].sort(key=lambda it: it.get("id", 0))
    return out