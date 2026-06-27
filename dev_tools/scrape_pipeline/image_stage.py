"""Stage 2: download + convert images referenced in scraped JSON caches."""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import requests
from PIL import Image

from dev_tools.scrape_pipeline.errors import ImageError, categorize

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


def _download(url: str, *, timeout: int = 30) -> bytes:
    """Download image bytes. Raises ImageError on failure."""
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        categorized = categorize(exc)
        if isinstance(categorized, ImageError):
            raise categorized from exc
        raise ImageError(f"download failed for {url}: {exc}") from exc


def _process_one_image(item_id: int, url: str, dest: Path) -> str:
    """Download + convert one image. Returns 'skipped' | 'downloaded'.

    Skips silently if dest already exists. On any failure, raises ImageError
    (or subclass) so the caller can log + continue without aborting.
    """
    if dest.exists():
        return "skipped"
    raw = _download(url)
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()  # force decode to fail fast on corrupt bytes
    except Exception as exc:
        raise ImageError(f"image {item_id}: decode failed for {url}: {exc}") from exc
    resized = img.resize(IMAGE_SIZE, Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    resized.save(dest, "WEBP", quality=IMAGE_QUALITY, method=6)
    return "downloaded"
