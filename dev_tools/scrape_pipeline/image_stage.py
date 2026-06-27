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


def run_bundle(json_root: Path, out_root: Path, *, workers: int = 4) -> dict:
    """Collect image URLs from *json_root*, download + convert to *out_root*/images/.

    Returns stats dict consumed by manifest.write_manifest.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time as _time

    started = _time.time()
    items = collect_images(json_root)
    images_total = len(items)
    downloaded = 0
    skipped = 0
    failed = 0
    bytes_total = 0
    images_dir = out_root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    def _task(iid: int, url: str) -> tuple[str, int, int]:
        dest = images_dir / f"{iid}.webp"
        try:
            result = _process_one_image(iid, url, dest)
            if result == "skipped":
                return ("skipped", 0, 0)
            size = dest.stat().st_size if dest.exists() else 0
            return ("downloaded", size, 0)
        except Exception as exc:
            log.warning("image %s failed: %s", iid, exc)
            return ("failed", 0, 1)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_task, iid, url) for iid, url in items.items()]
        for fut in as_completed(futures):
            status, size, err = fut.result()
            if status == "downloaded":
                downloaded += 1
                bytes_total += size
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1

    return {
        "images_total": images_total,
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "bytes_total": bytes_total,
        "duration_s": round(_time.time() - started, 1),
    }
