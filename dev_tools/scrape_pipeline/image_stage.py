"""Stage 2: download + convert images referenced in scraped JSON caches."""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

IMAGE_SIZE = (256, 256)
IMAGE_QUALITY = 70


def collect_images(root: Path) -> dict[int, str]:
    """Walk JSON caches under *root* and return {item_id: image_url}.

    Walks:
      - root/gear/**/*.json
      - root/item/**/*.json
      - root/box_loot_cache/*.json

    First-seen URL per id wins (dedup). Items without an "image" field
    are silently dropped.
    """
    result: dict[int, str] = {}
    patterns = [
        "gear/**/*.json",
        "item/**/*.json",
        "box_loot_cache/*.json",
    ]
    for pattern in patterns:
        for path in sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime):
            try:
                items = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("skip unreadable cache %s: %s", path, exc)
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                iid = item.get("id")
                url = item.get("image")
                if isinstance(iid, int) and isinstance(url, str) and url:
                    result.setdefault(iid, url)
    return result
