"""Stage 1: orchestrate the existing scraper to refresh JSON caches."""
from __future__ import annotations

import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

SECONDS_PER_DAY = 86400

# End-game gear rarities only. LEGENDARY excluded from binary bundle scope.
# IMMORTAL through COSMIC = 6 rarities. ~780-1560 gear items total.
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


def _gear_combos() -> list[tuple[str, str]]:
    """Return [(category, end_game_grade), ...] combos to scrape."""
    from tbh_desktop.scraper import GEAR_CATEGORIES
    return [(cat, grade) for cat in GEAR_CATEGORIES for grade in ENDGAME_GEAR_GRADES]


def _material_combos() -> list[tuple[str, str]]:
    from tbh_desktop.scraper import FAMILY_ORDER, RARITY_ORDER
    return [(fam, rar) for fam in FAMILY_ORDER for rar in RARITY_ORDER]


def _gear_cache_path(out_dir: Path, cat: str, grade: str) -> Path:
    return out_dir / "gear" / cat / f"{grade}.json"


def _material_cache_path(out_dir: Path, family: str, rarity: str) -> Path:
    return out_dir / "item" / family / f"{rarity}.json"


def run_scrape(out_dir: Path, *, resume: bool, max_cache_age_days: int) -> dict:
    """Refresh all scrape caches under *out_dir*. Returns stats dict."""
    from tbh_desktop.scraper import refresh_gear_full, refresh_material_details, fetch_drops_index

    started = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    combos_total = 0
    combos_done = 0
    combos_cached = 0
    combos_failed = 0
    items_total = 0

    # Gear combos
    gear_combos = _gear_combos()
    combos_total += len(gear_combos)
    try:
        for cat, grade in gear_combos:
            cache = _gear_cache_path(out_dir, cat, grade)
            if resume and cache_fresh(cache, max_cache_age_days):
                combos_cached += 1
                continue
            try:
                results = refresh_gear_full(
                    out_dir,
                    categories=[cat],
                    grades=[grade],
                    cancel_event=None,
                )
                key = f"{cat}_{grade}"
                items_total += len(results.get(key, []))
                combos_done += 1
            except Exception as exc:
                log.warning("gear combo %s/%s failed: %s", cat, grade, exc)
                combos_failed += 1
    except Exception as exc:
        log.warning("gear scrape stage aborted: %s", exc)
        combos_failed += len(gear_combos) - combos_done - combos_cached

    # Materials
    try:
        drops_index = fetch_drops_index(out_dir / "drops_index.json")
        items_total += len(drops_index)
        refreshed = refresh_material_details(out_dir / "item", drops_index)
        combos_total += 1
        combos_done += 1
        log.info("material enrichment: %d items", refreshed)
    except Exception as exc:
        log.warning("material scrape stage failed: %s", exc)
        combos_total += 1
        combos_failed += 1

    return {
        "combos_total": combos_total,
        "combos_done": combos_done,
        "combos_cached": combos_cached,
        "combos_failed": combos_failed,
        "items_total": items_total,
        "duration_s": round(time.time() - started, 1),
    }
