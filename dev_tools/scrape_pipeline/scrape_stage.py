"""Stage 1: orchestrate the existing scraper to refresh JSON caches."""
from __future__ import annotations

import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

SECONDS_PER_DAY = 86400


def cache_fresh(path: Path, max_age_days: int) -> bool:
    """Return True if *path* exists and its mtime is within *max_age_days*."""
    if not path.exists():
        return False
    age_s = time.time() - path.stat().st_mtime
    return age_s <= max_age_days * SECONDS_PER_DAY
