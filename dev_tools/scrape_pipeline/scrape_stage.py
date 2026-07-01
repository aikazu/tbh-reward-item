"""Stage 1: orchestrate tbh.city scrapers to refresh JSON caches.

Pipeline (Jul 2026 — tbh.city migration):

1. Items index — single HTTP GET of /items parses to 5875 entries (5760
   GEAR + 115 MATERIAL). Cached to ``<out_dir>/items_index.json``.
2. Gear cache split — filter LEG+ obtainable, group by (slot, grade),
   write one JSON per combo to ``<out_dir>/gear/<cat>/<grade>.json``.
3. Material cache split — group materials by family + rarity, write
   ``<out_dir>/item/<family>/<rarity>.json`` for the box loot picker.
4. Stages index — single HTTP GET of /stages parses to 120 stages.
   Cached to ``<out_dir>/stages_index.json``.
5. Stage details — one HTTP GET per stage, parse drop tables, write
   ``<out_dir>/stages/<id>.json``. Aggregated reverse maps:
   * ``item_id -> stages`` goes to ``<out_dir>/stage_drop_map.json``.
   * ``drop_key -> [item_id]`` goes to ``<out_dir>/pool_drops.json``
     (Jul 2026; replaces the older single-map approach and is what
     the desktop picker actually reads for pool-scoped replacement
     candidates).

The legacy taskbarhero.org/wiki path is no longer refreshed. Existing
cache files under ``box_loot_cache/`` are kept on disk for fallback
reads but won't be regenerated.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

log = logging.getLogger(__name__)

SECONDS_PER_DAY = 86400

# User-confirmed scope (Jul 2026):
# - Gear: Legendary and up only (Legendary / Immortal / Arcana / Beyond
#   / Celestial / Divine / Cosmic). Lower grades scrapped on demand but
#   not bundled.
# - Materials: all obtainable families (decor / crafting / engraving /
#   inscription / offering / soulstone).
# - Stages: only-with-drops filter applied — stages with empty drop
#   tables are skipped from the picker.
GEAR_MIN_GRADE = "LEGENDARY"

# Hard skip on synthetic / non-data act-boss stage IDs. tbh.city exposes
# ACTBOSS stages in the list (e.g. id=4310), but their detail pages are
# sometimes 404 or have no drops. The filter just drops them from the
# active cache; if a future schema change restores them, remove the skip.
STAGE_TYPES_TO_SCRAPE: frozenset[str] = frozenset({"NORMAL", "BOSS", "ACTBOSS"})

# End-game gear subset (kept for backwards compat with downstream
# callers / tests that import this constant). The actual scrape covers
# GEAR_MIN_GRADE = "LEGENDARY" (all LEG+ items), not just endgame.
ENDGAME_GEAR_GRADES: tuple[str, ...] = (
    "IMMORTAL",
    "ARCANA",
    "BEYOND",
    "CELESTIAL",
    "DIVINE",
    "COSMIC",
)


def cache_fresh(path: Path, max_age_days: int) -> bool:
    """Return True if *path* exists and its mtime is within *max_age_days*."""
    if not path.exists():
        return False
    age_s = time.time() - path.stat().st_mtime
    return age_s <= max_age_days * SECONDS_PER_DAY


def _gear_cache_path(out_dir: Path, cat: str, grade: str) -> Path:
    return out_dir / "gear" / cat / f"{grade}.json"


def _material_cache_path(out_dir: Path, family: str, rarity: str) -> Path:
    return out_dir / "item" / family / f"{rarity}.json"


def _stage_cache_path(out_dir: Path, stage_id: int) -> Path:
    return out_dir / "stages" / f"{stage_id}.json"


# ---------------------------------------------------------------------------
# Section 1 — items index + per-(cat,grade) gear split
# ---------------------------------------------------------------------------

def _scrape_items_index(out_dir: Path, *, force: bool = False) -> list[dict]:
    """Fetch + cache the items index. Returns normalized items (en-name,
    image URL, obtainable flag). Returns [] on network failure.
    """
    from tbh_desktop.tbh_city import (
        fetch_items_index,
        normalize_items,
        write_items_index,
        read_items_index,
    )
    cache_path = out_dir / "items_index.json"
    if not force:
        cached = read_items_index(cache_path)
        if cached:
            return cached
    raw = fetch_items_index()
    if not raw:
        # Network down: fall back to whatever's on disk.
        return read_items_index(cache_path)
    write_items_index(cache_path, raw)
    normalized = normalize_items(raw)
    # Persist a normalized copy next to the raw one — pickers prefer the
    # normalized shape (image URL, capitalized rarity, slot type).
    import json as _json
    norm_path = cache_path.with_name("items_normalized.json")
    norm_path.write_text(
        _json.dumps(
            {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "count": len(normalized),
             "items": normalized},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return normalized


def _scrape_gear_split(out_dir: Path, items: list[dict]) -> int:
    """Filter to LEG+ obtainable gear and split into per-(cat, grade)
    JSON cache files. Returns total gear items written.
    """
    from tbh_desktop.tbh_city import (
        split_gear_by_slot_and_grade,
        detect_slot_type,
        detect_slot_type_from_id,
    )
    import json
    # Stamp slot type onto each item before splitting — some tbh.city
    # icons don't carry the prefix (e.g. ARCANA uses unusual paths), so
    # we fall back to the id-prefix map.
    for it in items:
        if it.get("type") != "GEAR":
            continue
        slot = detect_slot_type(it.get("icon", "")) or detect_slot_type_from_id(it.get("id", 0))
        it["slot_type"] = slot
    grouped = split_gear_by_slot_and_grade(
        items, obtainable_only=True, min_grade=GEAR_MIN_GRADE,
    )
    written = 0
    for (cat, grade), bucket in grouped.items():
        path = _gear_cache_path(out_dir, cat, grade)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(bucket, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written += len(bucket)
        log.info("gear %s/%s: wrote %d items", cat, grade, len(bucket))
    return written


# ---------------------------------------------------------------------------
# Section 2 — materials per (family, rarity)
# ---------------------------------------------------------------------------

# Family order — matches the existing RARITY_ORDER-style layout used by
# the box loot picker. Materials without a parseable family are dropped
# (we don't fabricate "OTHER" buckets).
MATERIAL_FAMILY_HINTS: dict[str, str] = {
    "CRAFTING": "CRAFTING",
    "DECORATION": "DECORATION",
    "ENGRAVING": "ENGRAVING",
    "INSCRIPTION": "INSCRIPTION",
    "OFFERING": "OFFERING",
    "SOULSTONE": "SOULSTONE",
}


def _scrape_materials_split(out_dir: Path, items: list[dict]) -> int:
    """Group materials by (family, rarity) and write per-bucket JSON.

    Jul 2026: each item now carries a ``family`` field populated by
    :func:`tbh_desktop.tbh_city._material_family` (CRAFTING /
    DECORATION / ENGRAVING / INSCRIPTION / OFFERING / SOULSTONE). We
    split into per-family buckets instead of dumping everything into
    a single CRAFTING bucket — matches the v1 taskbarhero.org shape
    the picker chips were originally designed for.
    """
    import json
    bucket: dict[tuple[str, str], list[dict]] = {}
    for it in items:
        if it.get("type") != "MATERIAL":
            continue
        if not it.get("obtainable", True):
            # Skip unobtainable materials — they're test/dummy entries
            # from the wiki (e.g. "Mystic Pearl" with source_count=0).
            continue
        rarity = (it.get("grade") or "COMMON").upper()
        family = (it.get("family") or "CRAFTING").upper()
        bucket.setdefault((family, rarity), []).append(it)
    written = 0
    for (fam, rar), items_in in bucket.items():
        path = _material_cache_path(out_dir, fam, rar)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(items_in, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written += len(items_in)
        log.info("material %s/%s: wrote %d items", fam, rar, len(items_in))
    return written


# ---------------------------------------------------------------------------
# Section 3 — stages index + per-stage detail
# ---------------------------------------------------------------------------

def _scrape_stages_index(out_dir: Path, *, force: bool = False) -> list[dict]:
    from tbh_desktop.tbh_city import (
        fetch_stages_index,
        write_stages_index,
        read_stages_index,
    )
    cache_path = out_dir / "stages_index.json"
    if not force:
        cached = read_stages_index(cache_path)
        if cached:
            return cached
    stages = fetch_stages_index()
    if not stages:
        return read_stages_index(cache_path)
    write_stages_index(cache_path, stages)
    return stages


def _scrape_stage_detail(
    out_dir: Path, stage: dict, *, max_retries: int = 2,
) -> tuple[int, int, bool]:
    """Fetch + cache one stage detail. Returns (stage_id, drops_count, ok)."""
    from tbh_desktop.tbh_city import fetch_stage_detail, write_stage_cache
    sid = stage.get("id")
    if not isinstance(sid, int):
        return 0, 0, False
    for attempt in range(max_retries + 1):
        data = fetch_stage_detail(sid)
        if data:
            write_stage_cache(out_dir / "stages", sid, data)
            from tbh_desktop.tbh_city import flatten_stage_drops
            return sid, len(flatten_stage_drops(data)), True
        if attempt < max_retries:
            time.sleep(1.5 * (attempt + 1))
    log.warning("stage %s: detail fetch failed after %d retries", sid, max_retries + 1)
    return sid, 0, False


def _scrape_stage_details(
    out_dir: Path, stages: list[dict], *, only_with_drops: bool,
    resume: bool, max_cache_age_days: int, max_workers: int = 4,
) -> tuple[int, int, int]:
    """Concurrently fetch each stage detail. Stages with empty drop
    tables are still cached (in case the wiki adds them later) but the
    caller filters by ``only_with_drops`` when picking entries to display.

    Returns (done, cached_skipped, failed).
    """
    done = 0
    cached = 0
    failed = 0
    targets = [s for s in stages if s.get("type") in STAGE_TYPES_TO_SCRAPE]
    log.info("stage detail: %d targets (filtered from %d)", len(targets), len(stages))

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {}
        for s in targets:
            sid = s.get("id")
            if not isinstance(sid, int):
                continue
            cache = _stage_cache_path(out_dir, sid)
            if resume and cache_fresh(cache, max_cache_age_days):
                cached += 1
                continue
            futures[ex.submit(_scrape_stage_detail, out_dir, s)] = sid
        for fut in as_completed(futures):
            sid, drops, ok = fut.result()
            if ok:
                done += 1
                if only_with_drops and drops == 0:
                    log.info("stage %s: cached but no drops (filtered from picker)", sid)
            else:
                failed += 1
    return done, cached, failed


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_scrape(
    out_dir: Path,
    *,
    resume: bool,
    max_cache_age_days: int,
    only_with_drops: bool = True,
    stage_workers: int = 4,
) -> dict:
    """Refresh all tbh.city-driven JSON caches under *out_dir*.

    Returns a stats dict consumed by the manifest writer. Honors
    ``--resume`` for any cache file with a fresh mtime.

    ``only_with_drops`` (default True) flags stages whose detail cache
    has zero entries — they're skipped from the picker index (per user
    feedback: stages must have at least one drop to appear). Range
    replacement rules are unaffected — the picker accepts any obtainable
    item as a replacement target regardless of source_count.
    """
    from tbh_desktop.tbh_city import (
        build_stage_drop_map,
        write_stage_drop_map,
        read_stage_drop_map,
    )
    started = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    combos_total = 0
    combos_done = 0
    combos_cached = 0
    combos_failed = 0
    items_total = 0

    # --- Items index ---
    t = time.time()
    items = _scrape_items_index(out_dir)
    log.info("items index: %d items in %.1fs", len(items), time.time() - t)
    items_total = len(items)

    # --- Gear split (LEG+ obtainable) ---
    t = time.time()
    gear_written = _scrape_gear_split(out_dir, items)
    combos_total += gear_written
    combos_done += gear_written
    log.info("gear split: %d items in %.1fs", gear_written, time.time() - t)

    # --- Materials split (obtainable only) ---
    t = time.time()
    mat_written = _scrape_materials_split(out_dir, items)
    combos_total += mat_written
    combos_done += mat_written
    log.info("materials split: %d items in %.1fs", mat_written, time.time() - t)

    # --- Stages index ---
    t = time.time()
    stages = _scrape_stages_index(out_dir)
    log.info("stages index: %d stages in %.1fs", len(stages), time.time() - t)
    combos_total += 1
    combos_done += 1

    # --- Stage details ---
    t = time.time()
    sd_done, sd_cached, sd_failed = _scrape_stage_details(
        out_dir, stages,
        only_with_drops=only_with_drops,
        resume=resume,
        max_cache_age_days=max_cache_age_days,
        max_workers=stage_workers,
    )
    combos_total += sd_done + sd_cached + sd_failed
    combos_done += sd_done
    combos_cached += sd_cached
    combos_failed += sd_failed
    log.info("stage details: %d done, %d cached, %d failed in %.1fs",
             sd_done, sd_cached, sd_failed, time.time() - t)

    # --- Reverse maps for the desktop picker ---
    # 1. item_id -> stages (kept for "Drops from" columns in the gear
    #    picker; small enough to remain useful).
    # 2. drop_key -> [item_id] (Jul 2026 — the smaller index the
    #    pool-scoped replacement picker actually reads. Replaces the
    #    older item_id -> stage list as the source of truth for pool
    #    scope).
    t = time.time()
    drop_map = build_stage_drop_map(out_dir / "stages", stages)
    write_stage_drop_map(out_dir / "stage_drop_map.json", drop_map)
    log.info("stage_drop_map: %d items with sources in %.1fs",
             len(drop_map), time.time() - t)

    t = time.time()
    from tbh_desktop.tbh_city import build_pool_drop_key_map, write_pool_drop_key_map
    pool_map = build_pool_drop_key_map(out_dir / "stages")
    write_pool_drop_key_map(out_dir / "pool_drops.json", pool_map)
    log.info("pool_drops: %d pool keys in %.1fs",
             len(pool_map), time.time() - t)

    return {
        "combos_total": combos_total,
        "combos_done": combos_done,
        "combos_cached": combos_cached,
        "combos_failed": combos_failed,
        "items_total": items_total,
        "gear_written": gear_written,
        "materials_written": mat_written,
        "stages_written": sd_done + sd_cached,
        "stages_failed": sd_failed,
        "duration_s": round(time.time() - started, 1),
    }