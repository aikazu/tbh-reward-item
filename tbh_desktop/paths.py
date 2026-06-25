"""Path resolution for TBH desktop app."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
CONFIG_PATH = SRC_DIR / "config.json"
RUN_PROXY_PATH = SRC_DIR / "run_proxy.py"
DESKTOP_DIR = Path(__file__).resolve().parent
GEAR_CACHE = DESKTOP_DIR / "gear_cache.json"
GEAR_CACHE_DIR = DESKTOP_DIR / "gear_cache"
BOX_LOOT_CACHE_DIR = DESKTOP_DIR / "box_loot_cache"