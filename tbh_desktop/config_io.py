"""Load/save src/config.json as raw dict; validate via ProxyConfig."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from tbh_desktop.paths import SRC_DIR

# Import ProxyConfig from src for validation only.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
from tbh_reward_hook import ProxyConfig  # type: ignore[import-not-found]

log = logging.getLogger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    """Load config JSON as raw dict. Return {} if missing or invalid."""
    if not path.exists():
        log.warning("config not found: %s", path)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("config invalid (%s): %s", path, exc)
        return {}