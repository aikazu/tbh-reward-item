"""Path resolution for TBH desktop app."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"

# Pull config paths from the shared src/config_setup module (single source
# of truth also used by the mitmproxy addon). Adds src/ to sys.path first.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
from config_setup import CONFIG_PATH  # noqa: E402

__all__ = [
    "REPO_ROOT",
    "SRC_DIR",
    "CONFIG_PATH",
    "RUN_PROXY_PATH",
    "DESKTOP_DIR",
    "GEAR_DIR",
    "ITEM_DIR",
    "GEAR_CACHE_DIR",
    # tbh.city-native caches (Jul 2026 migration; replaces box_*).
    "STAGES_DIR",
    "STAGES_INDEX_CACHE",
    "ITEMS_INDEX_CACHE",
    "STAGE_DROP_MAP_CACHE",
    "POOL_DROPS_CACHE",
    "DROPS_INDEX_CACHE",
    "IMAGES_DIR",
    "MANIFEST_PATH",
    "APP_ICON",
    "APP_ICON_SVG",
]

RUN_PROXY_PATH = SRC_DIR / "run_proxy.py"
DESKTOP_DIR = Path(__file__).resolve().parent
GEAR_DIR = DESKTOP_DIR / "gear"
ITEM_DIR = DESKTOP_DIR / "item"
# Backwards-compat alias — older call sites still use this name.
GEAR_CACHE_DIR = GEAR_DIR

# tbh.city-native caches (Jul 2026). Stages replace the old box_loot
# cache: each stage has its own JSON under STAGES_DIR, plus an index.
# The reverse drop_key → items map (POOL_DROPS_CACHE) is what the
# desktop picker actually reads for pool-scoped replacement
# candidate filtering.
STAGES_DIR = DESKTOP_DIR / "stages"
STAGES_INDEX_CACHE = DESKTOP_DIR / "stages_index.json"
ITEMS_INDEX_CACHE = DESKTOP_DIR / "items_index.json"
# Reverse item_id -> stage sources (used by the gear picker's
# "Drops from" column). Smaller than per-stage detail cache.
STAGE_DROP_MAP_CACHE = DESKTOP_DIR / "stage_drop_map.json"
# Pool drop-key index: drop_key (e.g. 9100111) → list of item_ids
# that pool can yield. Built from per-stage detail cache by
# scrape_stage; read by the desktop picker for pool-scoped
# replacement candidate filtering.
POOL_DROPS_CACHE = DESKTOP_DIR / "pool_drops.json"

# Jul 2026: items_normalized.json is the canonical drops index that
# pickers consume (replaces the legacy /en/tools/drops/ scraper output).
DROPS_INDEX_CACHE = DESKTOP_DIR / "items_normalized.json"
IMAGES_DIR = DESKTOP_DIR / "images"
MANIFEST_PATH = DESKTOP_DIR / "manifest.json"

# App identity assets (window/taskbar icon).
APP_ICON = DESKTOP_DIR / "ui" / "app_icon.png"
APP_ICON_SVG = DESKTOP_DIR / "ui" / "app_icon.svg"