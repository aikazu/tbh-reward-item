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

RUN_PROXY_PATH = SRC_DIR / "run_proxy.py"
DESKTOP_DIR = Path(__file__).resolve().parent
GEAR_DIR = DESKTOP_DIR / "gear"
GEAR_INDEX = GEAR_DIR / "index.json"
ITEM_DIR = DESKTOP_DIR / "item"
ITEM_INDEX = ITEM_DIR / "index.json"
# Backwards-compat alias — older call sites still use this name.
GEAR_CACHE_DIR = GEAR_DIR
BOX_LOOT_CACHE_DIR = DESKTOP_DIR / "box_loot_cache"
ITEM_DETAIL_CACHE = DESKTOP_DIR / "item_detail_cache.json"
BOX_DROP_MAP_CACHE = DESKTOP_DIR / "box_drop_map.json"
DROPS_INDEX_CACHE = DESKTOP_DIR / "drops_index.json"
IMAGES_DIR = DESKTOP_DIR / "images"
MANIFEST_PATH = DESKTOP_DIR / "manifest.json"