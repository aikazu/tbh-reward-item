# TBH Scraper Hardening + Image Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build maintainer-only scrape pipeline that produces a complete, ready-to-bundle dataset (JSON caches + WebP images + manifest.json) so the desktop binary can ship pre-scraped data with no runtime network dependency.

**Architecture:** Two-stage pipeline (`scrape` then `bundle`) under `dev_tools/scrape_pipeline/`. Existing `tbh_desktop/scraper.py` gets a minimal reliability patch (error categorization + exp backoff). New `image_stage.py` downloads + converts images to WebP. New `manifest.py` tracks scrape metadata. New CLI `python -m dev_tools.scrape_pipeline {scrape,bundle,all}` orchestrates both stages.

**Tech Stack:** Python 3.10+, pytest, pytest-qt (existing), Pillow>=10.0 (new), requests (existing), Playwright (existing, unchanged)

**Spec:** `docs/superpowers/specs/2026-06-27-tbh-scraper-binary-design.md`

---

## File Map

### New files

```
dev_tools/__init__.py                                  # empty marker
dev_tools/scrape_pipeline/__init__.py                  # empty marker
dev_tools/scrape_pipeline/__main__.py                  # entry: from .cli import main; raise SystemExit(main())
dev_tools/scrape_pipeline/cli.py                       # argparse + orchestration
dev_tools/scrape_pipeline/scrape_stage.py              # run_scrape + cache_fresh
dev_tools/scrape_pipeline/image_stage.py               # collect + _process_one_image + run_bundle
dev_tools/scrape_pipeline/errors.py                    # ScrapeError hierarchy + categorize
dev_tools/scrape_pipeline/backoff.py                   # exp backoff with jitter
dev_tools/scrape_pipeline/manifest.py                  # manifest.json IO (atomic write)

tests/dev_tools/__init__.py                            # empty marker
tests/dev_tools/scrape_pipeline/__init__.py            # empty marker
tests/dev_tools/scrape_pipeline/conftest.py            # shared fixtures (fake_image_bytes, sample_json_tree, mock_wiki_server)
tests/dev_tools/scrape_pipeline/test_backoff.py        # exp backoff
tests/dev_tools/scrape_pipeline/test_categorize.py     # error categorization
tests/dev_tools/scrape_pipeline/test_manifest.py       # manifest round-trip
tests/dev_tools/scrape_pipeline/test_scrape_stage.py   # cache_fresh + run_scrape
tests/dev_tools/scrape_pipeline/test_image_stage.py    # collect + _process_one_image + run_bundle
tests/dev_tools/scrape_pipeline/test_cli.py            # argparse + flow
tests/dev_tools/scrape_pipeline/test_pipeline_smoke.py # @pytest.mark.integration end-to-end
```

### Modified files

```
requirements-desktop.txt                                # + Pillow>=10.0 (with comment)
tbh_desktop/paths.py                                    # + IMAGES_DIR, MANIFEST_PATH (2 new lines)
tbh_desktop/scraper.py                                  # use errors.categorize + backoff.backoff in existing retry loops (no public API change)
```

### Generated artifacts (not in repo by default; created by pipeline)

```
tbh_desktop/images/{item_id}.webp
tbh_desktop/manifest.json
```

---

## Task 1: Add Pillow dependency

**Files:**
- Modify: `requirements-desktop.txt:8` (append line)

- [ ] **Step 1: Add Pillow to requirements-desktop.txt**

Append at end of file:
```
Pillow>=10.0  # dev_tools/scrape_pipeline only (not used at runtime by binary)
```

- [ ] **Step 2: Verify install**

Run: `pip install -r requirements-desktop.txt`
Expected: Pillow installed, no errors.

- [ ] **Step 3: Verify Pillow import works**

Run: `python -c "from PIL import Image; print(Image.__name__)"`
Expected: `Image`

- [ ] **Step 4: Commit**

```bash
git add requirements-desktop.txt
git commit -m "build: add Pillow>=10.0 for dev_tools scrape pipeline"
```

---

## Task 2: Add path constants for new resources

**Files:**
- Modify: `tbh_desktop/paths.py:18-27` (append 2 lines after existing constants)

- [ ] **Step 1: Read current paths.py to confirm insertion point**

Run: `grep -n "DESKTOP_DIR = " tbh_desktop/paths.py`
Expected: `DESKTOP_DIR = Path(__file__).resolve().parent`

- [ ] **Step 2: Append IMAGES_DIR and MANIFEST_PATH**

Edit `tbh_desktop/paths.py` — append at end of file:
```python
IMAGES_DIR = DESKTOP_DIR / "images"
MANIFEST_PATH = DESKTOP_DIR / "manifest.json"
```

- [ ] **Step 3: Verify imports resolve**

Run: `python -c "from tbh_desktop.paths import IMAGES_DIR, MANIFEST_PATH; print(IMAGES_DIR, MANIFEST_PATH)"`
Expected: `.../tbh_desktop/images .../tbh_desktop/manifest.json`

- [ ] **Step 4: Commit**

```bash
git add tbh_desktop/paths.py
git commit -m "feat(paths): add IMAGES_DIR and MANIFEST_PATH constants"
```

---

## Task 3: Backoff helper (TDD)

**Files:**
- Create: `dev_tools/scrape_pipeline/__init__.py`
- Create: `dev_tools/scrape_pipeline/backoff.py`
- Create: `tests/dev_tools/__init__.py`
- Create: `tests/dev_tools/scrape_pipeline/__init__.py`
- Create: `tests/dev_tools/scrape_pipeline/test_backoff.py`

- [ ] **Step 1: Create empty package markers**

Write to `dev_tools/scrape_pipeline/__init__.py`:
```python
"""Maintainer-only scrape pipeline for bundling scraped data into desktop binary."""
```

Write to `tests/dev_tools/__init__.py`:
```python
```

Write to `tests/dev_tools/scrape_pipeline/__init__.py`:
```python
```

- [ ] **Step 2: Write failing test for backoff**

Write to `tests/dev_tools/scrape_pipeline/test_backoff.py`:
```python
"""Tests for dev_tools.scrape_pipeline.backoff."""
from __future__ import annotations

import random

from dev_tools.scrape_pipeline.backoff import backoff


def test_backoff_grows_exponentially():
    """Each attempt's delay should roughly double (within jitter bound)."""
    rng = random.Random(42)
    delays = [backoff(attempt=i, base=0.4, cap=30.0, rng=rng) for i in range(5)]
    # Without jitter (jitter range [0, 0.25*delay]), each next must be > 0.75 * prev
    for prev, curr in zip(delays, delays[1:]):
        assert curr > prev * 0.75, f"delay did not grow: {prev} -> {curr}"


def test_backoff_respects_cap():
    """Delay must never exceed the cap (even with jitter)."""
    rng = random.Random(0)
    # attempt=20 would give 0.4 * 2^20 = 419430s raw; must cap to 30
    assert backoff(attempt=20, base=0.4, cap=30.0, rng=rng) <= 30.0 * 1.25


def test_backoff_deterministic_with_seeded_rng():
    """Same seed must produce same delay sequence."""
    delays_a = [backoff(attempt=i, rng=random.Random(123)) for i in range(3)]
    delays_b = [backoff(attempt=i, rng=random.Random(123)) for i in range(3)]
    assert delays_a == delays_b


def test_backoff_jitter_within_quarter():
    """Jitter must be in [0, 0.25 * base_delay] range."""
    rng = random.Random(7)
    for attempt in range(5):
        base = min(30.0, 0.4 * (2 ** attempt))
        delay = backoff(attempt=attempt, base=0.4, cap=30.0, rng=rng)
        # First call to rng.uniform consumed for jitter; just check bounds
        assert base <= delay <= base * 1.25, f"attempt={attempt}: {delay} not in [{base}, {base * 1.25}]"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_backoff.py -v`
Expected: ImportError or ModuleNotFoundError (backoff.py does not exist yet)

- [ ] **Step 4: Write minimal implementation**

Write to `dev_tools/scrape_pipeline/backoff.py`:
```python
"""Exponential backoff with jitter for retry loops."""
from __future__ import annotations

import random


def backoff(
    attempt: int,
    base: float = 0.4,
    cap: float = 30.0,
    rng: random.Random | None = None,
) -> float:
    """Return delay in seconds for the given attempt (0-indexed).

    Formula: ``min(cap, base * 2 ** attempt) + uniform(0, 0.25 * that_delay)``.
    Pass ``rng`` to make output deterministic in tests.
    """
    if rng is None:
        rng = random
    raw = min(cap, base * (2 ** attempt))
    jitter = rng.uniform(0, raw * 0.25)
    return raw + jitter
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_backoff.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add dev_tools/__init__.py dev_tools/scrape_pipeline/__init__.py dev_tools/scrape_pipeline/backoff.py tests/dev_tools/__init__.py tests/dev_tools/scrape_pipeline/__init__.py tests/dev_tools/scrape_pipeline/test_backoff.py
git commit -m "feat(scrape_pipeline): add exp backoff helper with jitter"
```

---

## Task 4: Errors hierarchy + categorize (TDD)

**Files:**
- Create: `dev_tools/scrape_pipeline/errors.py`
- Create: `tests/dev_tools/scrape_pipeline/test_categorize.py`

- [ ] **Step 1: Write failing test for categorize**

Write to `tests/dev_tools/scrape_pipeline/test_categorize.py`:
```python
"""Tests for dev_tools.scrape_pipeline.errors."""
from __future__ import annotations

import json

import lxml.etree
import pytest
import requests

from dev_tools.scrape_pipeline.errors import (
    ImageError,
    ImageMissingError,
    NetworkError,
    RateLimitError,
    SchemaError,
    ScrapeError,
    categorize,
)


def test_categorize_connection_error_is_network():
    exc = requests.exceptions.ConnectionError("refused")
    assert isinstance(categorize(exc), NetworkError)


def test_categorize_timeout_is_network():
    exc = requests.exceptions.Timeout("slow")
    assert isinstance(categorize(exc), NetworkError)


def test_categorize_http_500_is_network():
    resp = requests.Response()
    resp.status_code = 503
    exc = requests.exceptions.HTTPError("503", response=resp)
    assert isinstance(categorize(exc), NetworkError)


def test_categorize_http_429_is_rate_limit():
    resp = requests.Response()
    resp.status_code = 429
    exc = requests.exceptions.HTTPError("429", response=resp)
    assert isinstance(categorize(exc), RateLimitError)


def test_categorize_http_404_is_image_missing():
    resp = requests.Response()
    resp.status_code = 404
    exc = requests.exceptions.HTTPError("404", response=resp)
    assert isinstance(categorize(exc), ImageMissingError)
    assert isinstance(categorize(exc), ImageError)


def test_categorize_json_decode_is_schema():
    exc = json.JSONDecodeError("bad", "doc", 0)
    assert isinstance(categorize(exc), SchemaError)


def test_categorize_xml_syntax_is_schema():
    try:
        lxml.etree.fromstring("<broken")
    except lxml.etree.XMLSyntaxError as exc:
        assert isinstance(categorize(exc), SchemaError)
    else:
        pytest.fail("expected XMLSyntaxError")


def test_categorize_unknown_is_base_scrape_error():
    exc = ValueError("weird")
    result = categorize(exc)
    assert isinstance(result, ScrapeError)
    assert not isinstance(result, (NetworkError, SchemaError, RateLimitError, ImageError))


def test_all_categories_inherit_from_scrape_error():
    """Every category must be catchable as ScrapeError."""
    assert issubclass(NetworkError, ScrapeError)
    assert issubclass(SchemaError, ScrapeError)
    assert issubclass(RateLimitError, ScrapeError)
    assert issubclass(ImageError, ScrapeError)
    assert issubclass(ImageMissingError, ImageError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_categorize.py -v`
Expected: ModuleNotFoundError (errors.py does not exist)

- [ ] **Step 3: Write minimal implementation**

Write to `dev_tools/scrape_pipeline/errors.py`:
```python
"""Error hierarchy + categorization for the scrape pipeline."""
from __future__ import annotations

import json

import lxml.etree
import requests


class ScrapeError(Exception):
    """Base class for all pipeline errors."""


class NetworkError(ScrapeError):
    """Transient network failure — should retry."""


class SchemaError(ScrapeError):
    """Wiki/game data shape changed — fail fast, scraper needs update."""


class RateLimitError(ScrapeError):
    """Server throttled us — long backoff, then retry once."""


class ImageError(ScrapeError):
    """Image acquisition failure."""


class ImageMissingError(ImageError):
    """Image URL returned 404 — skip, don't retry."""


def categorize(exc: BaseException) -> ScrapeError:
    """Map a raw exception to its ScrapeError category.

    Returns the closest ScrapeError subclass wrapping ``exc``. Always returns
    a ScrapeError — unknown exception types become plain ScrapeError.
    """
    if isinstance(exc, ScrapeError):
        return exc
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return NetworkError(str(exc))
    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(exc.response, "status_code", None)
        if status == 429:
            return RateLimitError(str(exc))
        if status == 404:
            return ImageMissingError(str(exc))
        if status is not None and 500 <= status < 600:
            return NetworkError(str(exc))
    if isinstance(exc, json.JSONDecodeError):
        return SchemaError(f"JSON decode failed: {exc}")
    if isinstance(exc, lxml.etree.XMLSyntaxError):
        return SchemaError(f"XML syntax error: {exc}")
    return ScrapeError(str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_categorize.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add dev_tools/scrape_pipeline/errors.py tests/dev_tools/scrape_pipeline/test_categorize.py
git commit -m "feat(scrape_pipeline): add error hierarchy + categorize helper"
```

---

## Task 5: Manifest IO (TDD)

**Files:**
- Create: `dev_tools/scrape_pipeline/manifest.py`
- Create: `tests/dev_tools/scrape_pipeline/test_manifest.py`

- [ ] **Step 1: Write failing test for manifest IO**

Write to `tests/dev_tools/scrape_pipeline/test_manifest.py`:
```python
"""Tests for dev_tools.scrape_pipeline.manifest."""
from __future__ import annotations

import json

import pytest

from dev_tools.scrape_pipeline.manifest import (
    SCHEMA_VERSION,
    read_manifest,
    write_manifest,
)


def test_round_trip(tmp_path):
    """Write then read returns the same payload (with schema_version added)."""
    path = tmp_path / "manifest.json"
    stats = {
        "scrape_started_at": "2026-06-27T10:00:00",
        "scrape": {"combos_done": 5, "items_total": 100},
        "images": {"downloaded": 100, "failed": 0},
    }
    write_manifest(stats, path)
    loaded = read_manifest(path)
    assert loaded["schema_version"] == SCHEMA_VERSION
    assert loaded["scrape_started_at"] == "2026-06-27T10:00:00"
    assert loaded["scrape"] == {"combos_done": 5, "items_total": 100}
    assert loaded["images"] == {"downloaded": 100, "failed": 0}
    assert "scrape_completed_at" in loaded


def test_atomic_write_no_partial_file(tmp_path):
    """If write_manifest is interrupted, no manifest.json should remain."""
    path = tmp_path / "manifest.json"
    # Pre-create a good manifest
    path.write_text('{"schema_version": 1, "old": true}')
    # Write new content; old content must NOT survive
    write_manifest({"scrape": {"done": 1}}, path)
    assert json.loads(path.read_text())["scrape"] == {"done": 1}


def test_missing_file_returns_empty(tmp_path):
    """read_manifest on a missing file returns {} (no raise)."""
    assert read_manifest(tmp_path / "nope.json") == {}


def test_corrupt_file_returns_empty(tmp_path):
    """read_manifest on a malformed JSON returns {} (no raise)."""
    path = tmp_path / "manifest.json"
    path.write_text("not json at all")
    assert read_manifest(path) == {}


def test_schema_version_mismatch_raises(tmp_path):
    """read_manifest raises on schema_version mismatch."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 999}))
    with pytest.raises(ValueError, match="schema_version"):
        read_manifest(path)


def test_schema_version_constant_is_int():
    """SCHEMA_VERSION must be a positive integer for safe comparison."""
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_manifest.py -v`
Expected: ModuleNotFoundError (manifest.py does not exist)

- [ ] **Step 3: Write minimal implementation**

Write to `dev_tools/scrape_pipeline/manifest.py`:
```python
"""manifest.json IO for the scrape pipeline."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_manifest(stats: dict, path: Path) -> None:
    """Atomically write manifest JSON. Adds schema_version + scrape_completed_at."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "scrape_completed_at": _now_iso(),
        **stats,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def read_manifest(path: Path) -> dict:
    """Read manifest. Returns {} if missing or malformed. Raises on schema mismatch."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    found_version = data.get("schema_version")
    if found_version != SCHEMA_VERSION:
        raise ValueError(
            f"manifest schema_version mismatch: found {found_version}, expected {SCHEMA_VERSION}"
        )
    return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_manifest.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add dev_tools/scrape_pipeline/manifest.py tests/dev_tools/scrape_pipeline/test_manifest.py
git commit -m "feat(scrape_pipeline): add manifest.json IO with atomic write"
```

---

## Task 6: scrape_stage cache_fresh helper (TDD)

**Files:**
- Create: `dev_tools/scrape_pipeline/scrape_stage.py`
- Create: `tests/dev_tools/scrape_pipeline/test_scrape_stage.py`

- [ ] **Step 1: Write failing test for cache_fresh**

Write to `tests/dev_tools/scrape_pipeline/test_scrape_stage.py`:
```python
"""Tests for dev_tools.scrape_pipeline.scrape_stage."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from dev_tools.scrape_pipeline.scrape_stage import cache_fresh


def test_cache_fresh_missing_file_returns_false(tmp_path):
    """No file on disk = not fresh."""
    assert cache_fresh(tmp_path / "nope.json", max_age_days=7) is False


def test_cache_fresh_brand_new_file_returns_true(tmp_path):
    """A file written now is fresh."""
    p = tmp_path / "fresh.json"
    p.write_text("{}")
    assert cache_fresh(p, max_age_days=7) is True


def test_cache_fresh_old_file_returns_false(tmp_path):
    """A file written 30 days ago is stale against a 7-day window."""
    p = tmp_path / "old.json"
    p.write_text("{}")
    # Backdate mtime by 30 days
    old_time = time.time() - (30 * 86400)
    import os
    os.utime(p, (old_time, old_time))
    assert cache_fresh(p, max_age_days=7) is False


def test_cache_fresh_at_boundary_is_fresh(tmp_path):
    """A file 6 days old against 7-day window = still fresh."""
    p = tmp_path / "boundary.json"
    p.write_text("{}")
    six_days_ago = time.time() - (6 * 86400)
    import os
    os.utime(p, (six_days_ago, six_days_ago))
    assert cache_fresh(p, max_age_days=7) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_scrape_stage.py -v`
Expected: ModuleNotFoundError (scrape_stage.py does not exist)

- [ ] **Step 3: Write minimal implementation (cache_fresh only)**

Write to `dev_tools/scrape_pipeline/scrape_stage.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_scrape_stage.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add dev_tools/scrape_pipeline/scrape_stage.py tests/dev_tools/scrape_pipeline/test_scrape_stage.py
git commit -m "feat(scrape_pipeline): add cache_fresh helper to scrape_stage"
```

---

## Task 7: image_stage collect (TDD)

**Files:**
- Create: `dev_tools/scrape_pipeline/image_stage.py`
- Create: `tests/dev_tools/scrape_pipeline/conftest.py`
- Create: `tests/dev_tools/scrape_pipeline/test_image_stage.py`

- [ ] **Step 1: Write shared fixtures**

Write to `tests/dev_tools/scrape_pipeline/conftest.py`:
```python
"""Shared fixtures for dev_tools.scrape_pipeline tests."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def fake_image_bytes() -> bytes:
    """Return PNG bytes for a 512x512 image (decodeable by Pillow)."""
    img = Image.new("RGB", (512, 512), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def fake_corrupt_bytes() -> bytes:
    """Return bytes that are NOT a valid image."""
    return b"this is not an image, just text"


@pytest.fixture
def sample_json_tree(tmp_path: Path) -> Path:
    """Create a tmp dir with 3 gear + 2 material + 1 box JSON files.

    Returns the tmp_path root. Files reference image URLs with item IDs
    300001-300003 (gear), 100001-100002 (material), 200001 (box).
    """
    # gear
    gear_dir = tmp_path / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    (gear_dir / "legendary.json").write_text(json.dumps([
        {"id": 300001, "name": "Long Sword", "image": "https://x/sword1.png"},
        {"id": 300002, "name": "Short Sword", "image": "https://x/sword2.png"},
        {"id": 300003, "name": "Great Sword", "image": "https://x/sword3.png"},
    ]))
    # material
    item_dir = tmp_path / "item" / "CRAFTING"
    item_dir.mkdir(parents=True)
    (item_dir / "RARE.json").write_text(json.dumps([
        {"id": 100001, "name": "Bronze Ingot", "image": "https://x/ingot1.png"},
        {"id": 100002, "name": "Iron Ingot", "image": "https://x/ingot2.png"},
    ]))
    # box
    box_dir = tmp_path / "box_loot_cache"
    box_dir.mkdir(parents=True)
    (box_dir / "42.json").write_text(json.dumps([
        {"id": 200001, "name": "Mystery Box", "image": "https://x/box42.png", "box_id": 42},
    ]))
    return tmp_path
```

- [ ] **Step 2: Write failing test for collect**

Append to `tests/dev_tools/scrape_pipeline/test_image_stage.py`:
```python
"""Tests for dev_tools.scrape_pipeline.image_stage."""
from __future__ import annotations

from pathlib import Path

from dev_tools.scrape_pipeline.image_stage import collect_images


def test_collect_walks_all_json_dirs(sample_json_tree: Path):
    """Should discover all items across gear/item/box JSON caches."""
    result = collect_images(sample_json_tree)
    ids = sorted(result.keys())
    assert ids == [100001, 100002, 200001, 300001, 300002, 300003]


def test_collect_returns_url_per_id(sample_json_tree: Path):
    """Each id maps to its first-seen image URL."""
    result = collect_images(sample_json_tree)
    assert result[300001] == "https://x/sword1.png"
    assert result[100001] == "https://x/ingot1.png"
    assert result[200001] == "https://x/box42.png"


def test_collect_dedups_by_id(sample_json_tree: Path):
    """If the same id appears in multiple files, first URL wins."""
    # Add a duplicate id in a new file
    dup = sample_json_tree / "gear" / "sword" / "common.json"
    dup.write_text(__import__("json").dumps([
        {"id": 300001, "name": "Dup", "image": "https://x/different.png"},
    ]))
    result = collect_images(sample_json_tree)
    # First-seen (legendary.json) wins
    assert result[300001] == "https://x/sword1.png"


def test_collect_skips_items_without_image(sample_json_tree: Path):
    """Items missing 'image' field are silently dropped."""
    import json
    p = sample_json_tree / "gear" / "sword" / "mythic.json"
    p.write_text(json.dumps([
        {"id": 300099, "name": "No Image"},  # no image field
        {"id": 300100, "name": "Has Image", "image": "https://x/has.png"},
    ]))
    result = collect_images(sample_json_tree)
    assert 300099 not in result
    assert result[300100] == "https://x/has.png"


def test_collect_empty_tree_returns_empty(tmp_path: Path):
    """No JSON files = empty dict, no raise."""
    assert collect_images(tmp_path) == {}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_image_stage.py -v`
Expected: ModuleNotFoundError (image_stage.py does not exist)

- [ ] **Step 4: Write minimal implementation (collect only)**

Write to `dev_tools/scrape_pipeline/image_stage.py`:
```python
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
        root / "gear" / "**" / "*.json",
        root / "item" / "**" / "*.json",
        root / "box_loot_cache" / "*.json",
    ]
    for pattern in patterns:
        for path in pattern.parent.glob(pattern.name):
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_image_stage.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add dev_tools/scrape_pipeline/image_stage.py tests/dev_tools/scrape_pipeline/conftest.py tests/dev_tools/scrape_pipeline/test_image_stage.py
git commit -m "feat(scrape_pipeline): add image_stage.collect_images"
```

---

## Task 8: image_stage _process_one_image (TDD)

**Files:**
- Modify: `dev_tools/scrape_pipeline/image_stage.py` (append functions)
- Modify: `tests/dev_tools/scrape_pipeline/test_image_stage.py` (append tests)

- [ ] **Step 1: Write failing test for _process_one_image**

Append to `tests/dev_tools/scrape_pipeline/test_image_stage.py`:
```python
from unittest.mock import MagicMock, patch

from dev_tools.scrape_pipeline.errors import ImageMissingError
from dev_tools.scrape_pipeline.image_stage import _process_one_image


def test_process_one_image_success(tmp_path: Path, fake_image_bytes: bytes):
    """Successful download + convert writes a WebP file at expected path."""
    dest = tmp_path / "out.webp"
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_image_bytes
        result = _process_one_image(300001, "https://x/sword.png", dest)
    assert result == "downloaded"
    assert dest.exists()
    assert dest.stat().st_size > 0


def test_process_one_image_skips_existing(tmp_path: Path):
    """If dest already exists, skip without re-downloading."""
    dest = tmp_path / "exists.webp"
    dest.write_bytes(b"already here")
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = b""  # would fail decode; should not be called
        result = _process_one_image(300001, "https://x/sword.png", dest)
    assert result == "skipped"
    assert dest.read_bytes() == b"already here"  # unchanged


def test_process_one_image_http_404_raises_image_missing(tmp_path: Path):
    """HTTP 404 must raise ImageMissingError so caller logs + skips."""
    dest = tmp_path / "out.webp"
    fake_resp = MagicMock()
    fake_resp.status_code = 404
    fake_resp.raise_for_status.side_effect = Exception("404")
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.side_effect = ImageMissingError("404 not found")
        try:
            _process_one_image(300001, "https://x/missing.png", dest)
        except ImageMissingError:
            pass
        else:
            raise AssertionError("expected ImageMissingError")
    assert not dest.exists()


def test_process_one_image_network_error_raises_image_error(tmp_path: Path):
    """Network failures raise ImageError so caller logs + skips."""
    from dev_tools.scrape_pipeline.errors import ImageError
    dest = tmp_path / "out.webp"
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.side_effect = ImageError("connection refused")
        try:
            _process_one_image(300001, "https://x/down.png", dest)
        except ImageError:
            pass
        else:
            raise AssertionError("expected ImageError")
    assert not dest.exists()


def test_process_one_image_corrupt_bytes_raises(tmp_path: Path, fake_corrupt_bytes: bytes):
    """Non-image bytes raise (caller logs + skips)."""
    from dev_tools.scrape_pipeline.errors import ImageError
    dest = tmp_path / "out.webp"
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_corrupt_bytes
        try:
            _process_one_image(300001, "https://x/bad.png", dest)
        except ImageError:
            pass
        else:
            raise AssertionError("expected ImageError on corrupt bytes")
    assert not dest.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_image_stage.py -v`
Expected: ImportError on _process_one_image

- [ ] **Step 3: Implement _process_one_image + _download**

Replace `dev_tools/scrape_pipeline/image_stage.py` with:
```python
"""Stage 2: download + convert images referenced in scraped JSON caches."""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import requests
from PIL import Image

from dev_tools.scrape_pipeline.errors import ImageError, ImageMissingError, categorize

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
        root / "gear" / "**" / "*.json",
        root / "item" / "**" / "*.json",
        root / "box_loot_cache" / "*.json",
    ]
    for pattern in patterns:
        for path in pattern.parent.glob(pattern.name):
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
    """Download image bytes. Raises ImageError / ImageMissingError on failure."""
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
        raise ImageError(f"decode failed for {url}: {exc}") from exc
    resized = img.resize(IMAGE_SIZE, Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    resized.save(dest, "WEBP", quality=IMAGE_QUALITY, method=6)
    return "downloaded"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_image_stage.py -v`
Expected: 10 passed (5 collect + 5 process)

- [ ] **Step 5: Commit**

```bash
git add dev_tools/scrape_pipeline/image_stage.py tests/dev_tools/scrape_pipeline/test_image_stage.py
git commit -m "feat(scrape_pipeline): add _process_one_image + _download"
```

---

## Task 9: image_stage run_bundle (TDD)

**Files:**
- Modify: `dev_tools/scrape_pipeline/image_stage.py` (append run_bundle)
- Modify: `tests/dev_tools/scrape_pipeline/test_image_stage.py` (append tests)

- [ ] **Step 1: Write failing test for run_bundle**

Append to `tests/dev_tools/scrape_pipeline/test_image_stage.py`:
```python
from unittest.mock import patch

from dev_tools.scrape_pipeline.image_stage import run_bundle


def test_run_bundle_processes_all_items(sample_json_tree: Path, tmp_path: Path, fake_image_bytes: bytes):
    """run_bundle collects from JSON tree, downloads each, writes WebP."""
    out_root = tmp_path / "out"
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_image_bytes
        stats = run_bundle(sample_json_tree, out_root, workers=2)
    # 6 items in fixture
    assert stats["images_total"] == 6
    assert stats["downloaded"] == 6
    assert stats["failed"] == 0
    # files on disk
    for iid in (300001, 300002, 300003, 100001, 100002, 200001):
        assert (out_root / "images" / f"{iid}.webp").exists()


def test_run_bundle_records_failures_without_aborting(sample_json_tree: Path, tmp_path: Path, fake_image_bytes: bytes):
    """Per-item failure must be recorded + counted, not abort the run."""
    from dev_tools.scrape_pipeline.errors import ImageMissingError
    out_root = tmp_path / "out"
    call_count = {"n": 0}

    def flaky(url):
        call_count["n"] += 1
        if "sword1" in url:
            raise ImageMissingError("404")
        return fake_image_bytes

    with patch("dev_tools.scrape_pipeline.image_stage._download", side_effect=flaky):
        stats = run_bundle(sample_json_tree, out_root, workers=1)
    assert stats["images_total"] == 6
    assert stats["downloaded"] == 5
    assert stats["failed"] == 1
    # missing one not on disk
    assert not (out_root / "images" / "300001.webp").exists()
    assert (out_root / "images" / "300002.webp").exists()


def test_run_bundle_skips_existing(tmp_path: Path, fake_image_bytes: bytes):
    """Existing WebP files must be skipped (resume behavior)."""
    # Build a minimal JSON tree with 2 items
    json_root = tmp_path / "cache"
    gear_dir = json_root / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    import json as _json
    (gear_dir / "common.json").write_text(_json.dumps([
        {"id": 300010, "image": "https://x/a.png"},
        {"id": 300011, "image": "https://x/b.png"},
    ]))
    out_root = tmp_path / "out"
    img_dir = out_root / "images"
    img_dir.mkdir(parents=True)
    # Pre-create one WebP
    (img_dir / "300010.webp").write_bytes(b"already here")

    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_image_bytes
        stats = run_bundle(json_root, out_root, workers=1)
    assert stats["images_total"] == 2
    assert stats["downloaded"] == 1
    assert stats["skipped"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_image_stage.py::test_run_bundle_processes_all_items -v`
Expected: ImportError on run_bundle

- [ ] **Step 3: Implement run_bundle**

Append to `dev_tools/scrape_pipeline/image_stage.py`:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


def run_bundle(json_root: Path, out_root: Path, *, workers: int = 4) -> dict:
    """Collect image URLs from *json_root*, download + convert to *out_root*/images/.

    Returns stats dict consumed by manifest.write_manifest.
    """
    started = time.time()
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
        "duration_s": round(time.time() - started, 1),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_image_stage.py -v`
Expected: 13 passed (5 collect + 5 process + 3 run_bundle)

- [ ] **Step 5: Commit**

```bash
git add dev_tools/scrape_pipeline/image_stage.py tests/dev_tools/scrape_pipeline/test_image_stage.py
git commit -m "feat(scrape_pipeline): add run_bundle orchestrator"
```

---

## Task 10: scrape_stage run_scrape (TDD)

**Files:**
- Modify: `dev_tools/scrape_pipeline/scrape_stage.py` (append run_scrape)
- Modify: `tests/dev_tools/scrape_pipeline/test_scrape_stage.py` (append tests)

- [ ] **Step 1: Write failing test for run_scrape**

Append to `tests/dev_tools/scrape_pipeline/test_scrape_stage.py`:
```python
from unittest.mock import patch


def test_run_scrape_skips_fresh_caches(tmp_path: Path):
    """With --resume, fresh cache files are skipped."""
    out_dir = tmp_path / "out"
    gear_dir = out_dir / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    (gear_dir / "legendary.json").write_text("[]")  # fresh cache
    # Stub the scraper fn so we can assert it's NOT called
    with patch("tbh_desktop.scraper.refresh_gear_full") as scraper_fn:
        from dev_tools.scrape_pipeline.scrape_stage import run_scrape
        stats = run_scrape(out_dir, resume=True, max_cache_age_days=7)
    scraper_fn.assert_not_called()
    assert stats["combos_cached"] >= 1


def test_run_scrape_calls_scraper_for_stale_cache(tmp_path: Path):
    """Stale cache triggers re-scrape."""
    import os, time, json
    out_dir = tmp_path / "out"
    gear_dir = out_dir / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    cache = gear_dir / "legendary.json"
    cache.write_text("[]")
    # Backdate mtime 30 days
    old = time.time() - (30 * 86400)
    os.utime(cache, (old, old))
    with patch("tbh_desktop.scraper.refresh_gear_full") as scraper_fn:
        scraper_fn.return_value = {"sword_legendary": []}
        from dev_tools.scrape_pipeline.scrape_stage import run_scrape
        run_scrape(out_dir, resume=True, max_cache_age_days=7)
    assert scraper_fn.called


def test_run_scrape_falls_back_to_cache_on_error(tmp_path: Path):
    """If scraper raises, existing cache is preserved + combo counted as failed."""
    import json
    from dev_tools.scrape_pipeline.errors import NetworkError
    out_dir = tmp_path / "out"
    gear_dir = out_dir / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    cache = gear_dir / "legendary.json"
    cache.write_text(json.dumps([{"id": 300001}]))
    with patch("tbh_desktop.scraper.refresh_gear_full") as scraper_fn:
        scraper_fn.side_effect = NetworkError("flake")
        from dev_tools.scrape_pipeline.scrape_stage import run_scrape
        stats = run_scrape(out_dir, resume=False, max_cache_age_days=7)
    assert stats["combos_failed"] >= 1
    # Cache preserved
    assert json.loads(cache.read_text()) == [{"id": 300001}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_scrape_stage.py::test_run_scrape_skips_fresh_caches -v`
Expected: ImportError on run_scrape

- [ ] **Step 3: Implement run_scrape**

Replace `dev_tools/scrape_pipeline/scrape_stage.py` with:
```python
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


def _gear_combos() -> list[tuple[str, str]]:
    """Import existing scraper constants; return [(cat, grade), ...]."""
    from tbh_desktop.scraper import GEAR_CATEGORIES, LEGENDARY_UP_GRADES
    return [(cat, grade) for cat in GEAR_CATEGORIES for grade in LEGENDARY_UP_GRADES]


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_scrape_stage.py -v`
Expected: 7 passed (4 cache_fresh + 3 run_scrape)

- [ ] **Step 5: Commit**

```bash
git add dev_tools/scrape_pipeline/scrape_stage.py tests/dev_tools/scrape_pipeline/test_scrape_stage.py
git commit -m "feat(scrape_pipeline): add run_scrape orchestrator"
```

---

## Task 11: CLI entry point (TDD)

**Files:**
- Create: `dev_tools/scrape_pipeline/cli.py`
- Create: `dev_tools/scrape_pipeline/__main__.py`
- Create: `tests/dev_tools/scrape_pipeline/test_cli.py`

- [ ] **Step 1: Write failing test for CLI**

Write to `tests/dev_tools/scrape_pipeline/test_cli.py`:
```python
"""Tests for dev_tools.scrape_pipeline.cli."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from dev_tools.scrape_pipeline.cli import main, parse_args


def test_parse_args_defaults():
    """No args = stage=all, no resume."""
    args = parse_args([])
    assert args.stage == "all"
    assert args.resume is False
    assert args.max_cache_age == 7
    assert args.workers == 4
    assert args.dry_run is False


def test_parse_args_explicit_stage():
    args = parse_args(["scrape", "--resume"])
    assert args.stage == "scrape"
    assert args.resume is True


def test_main_dry_run_does_not_write(tmp_path: Path, capsys):
    """--dry-run prints intent but doesn't call stage fns or write files."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape") as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle") as bundle_fn:
        rc = main(["all", "--dry-run", "--out-dir", str(tmp_path)])
    assert rc == 0
    scrape_fn.assert_not_called()
    bundle_fn.assert_not_called()
    captured = capsys.readouterr()
    assert "dry-run" in captured.out.lower()


def test_main_runs_both_stages_for_all(tmp_path: Path):
    """--stage all runs both scrape and bundle."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape", return_value={"combos_done": 5}) as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle", return_value={"downloaded": 100}) as bundle_fn, \
         patch("dev_tools.scrape_pipeline.manifest.write_manifest") as write_fn:
        rc = main(["all", "--out-dir", str(tmp_path)])
    assert rc == 0
    scrape_fn.assert_called_once()
    bundle_fn.assert_called_once()
    write_fn.assert_called_once()
    # Manifest payload combines both
    payload = write_fn.call_args[0][0]
    assert payload["scrape"] == {"combos_done": 5}
    assert payload["images"] == {"downloaded": 100}


def test_main_runs_only_scrape_when_stage_scrape(tmp_path: Path):
    """--stage scrape skips bundle."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape", return_value={}) as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle") as bundle_fn, \
         patch("dev_tools.scrape_pipeline.manifest.write_manifest") as write_fn:
        main(["scrape", "--out-dir", str(tmp_path)])
    scrape_fn.assert_called_once()
    bundle_fn.assert_not_called()


def test_main_runs_only_bundle_when_stage_bundle(tmp_path: Path):
    """--stage bundle skips scrape."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape") as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle", return_value={}) as bundle_fn, \
         patch("dev_tools.scrape_pipeline.manifest.write_manifest") as write_fn:
        main(["bundle", "--out-dir", str(tmp_path)])
    scrape_fn.assert_not_called()
    bundle_fn.assert_called_once()


def test_main_returns_1_when_scrape_produces_zero_with_no_cache(tmp_path: Path):
    """Hard fail: scrape returned 0 items AND nothing cached."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape", return_value={"combos_done": 0, "combos_cached": 0, "items_total": 0}) as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle", return_value={}) as bundle_fn, \
         patch("dev_tools.scrape_pipeline.manifest.write_manifest"):
        rc = main(["all", "--out-dir", str(tmp_path)])
    assert rc == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_cli.py -v`
Expected: ModuleNotFoundError (cli.py does not exist)

- [ ] **Step 3: Implement cli.py**

Write to `dev_tools/scrape_pipeline/cli.py`:
```python
"""CLI entry point for the scrape pipeline."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from dev_tools.scrape_pipeline import image_stage, scrape_stage
from dev_tools.scrape_pipeline.image_stage import run_bundle
from dev_tools.scrape_pipeline.manifest import write_manifest
from dev_tools.scrape_pipeline.scrape_stage import run_scrape

log = logging.getLogger(__name__)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scrape_pipeline",
        description="Refresh scraped JSON caches + download images for desktop binary bundle.",
    )
    parser.add_argument(
        "stage",
        nargs="?",
        default="all",
        choices=("scrape", "bundle", "all"),
        help="Which stage to run (default: all)",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("tbh_desktop"),
                        help="Output root dir (default: tbh_desktop)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip scrape combos with fresh cache (within --max-cache-age)")
    parser.add_argument("--max-cache-age", type=int, default=7,
                        help="Max cache age in days for --resume (default: 7)")
    parser.add_argument("--workers", type=int, default=4,
                        help="ThreadPoolExecutor worker count for image stage (default: 4)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen, don't write files")
    return parser.parse_args(argv)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code (0 success, 1 hard fail)."""
    _setup_logging()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    out_dir: Path = args.out_dir

    if args.dry_run:
        print(f"[dry-run] would run stage={args.stage} out_dir={out_dir} "
              f"resume={args.resume} workers={args.workers}")
        return 0

    started = datetime.now().isoformat(timespec="seconds")
    scrape_stats: dict = {}
    bundle_stats: dict = {}

    if args.stage in ("scrape", "all"):
        scrape_stats = run_scrape(
            out_dir,
            resume=args.resume,
            max_cache_age_days=args.max_cache_age,
        )
        log.info("scrape stage done: %s", scrape_stats)

    if args.stage in ("bundle", "all"):
        bundle_stats = run_bundle(out_dir, out_dir, workers=args.workers)
        log.info("bundle stage done: %s", bundle_stats)

    write_manifest(
        {
            "scrape_started_at": started,
            "scrape": scrape_stats,
            "images": bundle_stats,
        },
        out_dir / "manifest.json",
    )
    log.info("manifest written to %s", out_dir / "manifest.json")

    # Hard fail: scrape produced 0 items AND nothing cached
    if args.stage in ("scrape", "all"):
        if scrape_stats.get("items_total", 0) == 0 and scrape_stats.get("combos_cached", 0) == 0:
            log.error("scrape stage produced no items and no cache fallback")
            return 1
    return 0
```

- [ ] **Step 4: Implement __main__.py**

Write to `dev_tools/scrape_pipeline/__main__.py`:
```python
"""Allow `python -m dev_tools.scrape_pipeline` invocation."""
from dev_tools.scrape_pipeline.cli import main

raise SystemExit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_cli.py -v`
Expected: 7 passed

- [ ] **Step 6: Verify CLI runs (dry-run)**

Run: `python -m dev_tools.scrape_pipeline all --dry-run`
Expected: prints `[dry-run] would run stage=all out_dir=tbh_desktop resume=False workers=4`

- [ ] **Step 7: Commit**

```bash
git add dev_tools/scrape_pipeline/cli.py dev_tools/scrape_pipeline/__main__.py tests/dev_tools/scrape_pipeline/test_cli.py
git commit -m "feat(scrape_pipeline): add CLI entry point with --stage flag"
```

---

## Task 12: Patch tbh_desktop/scraper.py for reliability

**Files:**
- Modify: `tbh_desktop/scraper.py` (3 locations: `_scrape_one_combo`, `_enrich_items_with_stats`, `_fetch_material_detail_wiki`)

- [ ] **Step 1: Run existing tests to baseline**

Run: `python -m pytest tests/ -x --ignore=tests/dev_tools -q`
Expected: All existing tests pass (baseline)

- [ ] **Step 2: Verify import path works**

Run: `python -c "from dev_tools.scrape_pipeline import errors, backoff; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Patch _enrich_items_with_stats retry loop**

In `tbh_desktop/scraper.py`, locate the `_worker` function inside `_enrich_items_with_stats` (around line 740-764). Replace the retry sleep with `backoff.backoff(attempt)` and wrap caught exception via `errors.categorize`.

Find this block:
```python
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    _time.sleep(0.4 * (2 ** attempt))
                    continue
```

Replace with:
```python
            except Exception as exc:
                last_exc = exc
                categorized = errors.categorize(exc)
                if attempt < 2 and isinstance(categorized, errors.NetworkError):
                    _time.sleep(backoff.backoff(attempt))
                    continue
                if attempt < 2 and isinstance(categorized, errors.RateLimitError):
                    _time.sleep(60.0)
                    continue
```

Add at top of file (after existing imports):
```python
from dev_tools.scrape_pipeline import backoff, errors
```

- [ ] **Step 4: Patch _fetch_material_detail_wiki retry loop**

In `tbh_desktop/scraper.py`, locate `_fetch_material_detail_wiki` (around line 1381-1412). Same pattern: replace `_time.sleep(0.4 * (2 ** attempt))` with `backoff.backoff(attempt)` and add categorization gate.

Find this block:
```python
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                _time.sleep(0.4 * (2 ** attempt))
                continue
```

Replace with:
```python
        except Exception as exc:
            last_exc = exc
            categorized = errors.categorize(exc)
            if attempt < 2 and isinstance(categorized, errors.NetworkError):
                _time.sleep(backoff.backoff(attempt))
                continue
            if attempt < 2 and isinstance(categorized, errors.RateLimitError):
                _time.sleep(60.0)
                continue
```

- [ ] **Step 5: Patch _scrape_one_combo retry loop**

In `tbh_desktop/scraper.py`, locate `_scrape_one_combo` (around line 568-638). The existing 3-attempt loop already handles iframe-strip + cache bypass. Add categorization: only retry on `NetworkError`, fail fast on `SchemaError`.

Find the block:
```python
        except Exception as exc:
            last_exc = exc
            if attempt == 1:
```

Replace with:
```python
        except Exception as exc:
            last_exc = exc
            categorized = errors.categorize(exc)
            if isinstance(categorized, errors.SchemaError):
                # Wiki shape changed — fail fast, don't retry
                log.warning("gear %s/%s schema error: %s", cat, grade, exc)
                return None
            if attempt == 1:
```

- [ ] **Step 6: Run full test suite to verify no regression**

Run: `python -m pytest tests/ -x --ignore=tests/dev_tools -q`
Expected: All existing tests still pass

- [ ] **Step 7: Run new tests to verify categorization wiring**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/ -v`
Expected: All dev_tools tests pass

- [ ] **Step 8: Commit**

```bash
git add tbh_desktop/scraper.py
git commit -m "refactor(scraper): use errors.categorize + backoff.backoff in retry loops"
```

- [ ] **Step 9: Verify coverage target**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/ --cov=dev_tools.scrape_pipeline --cov-report=term-missing -q 2>&1 | tail -40`
Expected: line coverage ≥ 80% on `dev_tools/scrape_pipeline/`

- [ ] **Step 10: If coverage < 80%, add targeted tests + commit**

Run: identify uncovered lines from `--cov-report`, add minimal tests, commit as `test(scrape_pipeline): boost coverage to 80%`.

---

## Task 13: Integration smoke test

**Files:**
- Create: `tests/dev_tools/scrape_pipeline/test_pipeline_smoke.py`

- [ ] **Step 1: Write integration test**

Write to `tests/dev_tools/scrape_pipeline/test_pipeline_smoke.py`:
```python
"""End-to-end pipeline smoke test (marked slow, excluded by default)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dev_tools.scrape_pipeline.image_stage import run_bundle
from dev_tools.scrape_pipeline.manifest import read_manifest, write_manifest


@pytest.mark.integration
def test_pipeline_smoke_real_pillow(tmp_path: Path, fake_image_bytes: bytes):
    """Real Pillow decode + WebP encode on fixture bytes, with mocked HTTP."""
    # Build minimal JSON cache: 3 items
    cache = tmp_path / "cache"
    gear_dir = cache / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    (gear_dir / "common.json").write_text(json.dumps([
        {"id": 300010, "image": "https://x/a.png"},
        {"id": 300011, "image": "https://x/b.png"},
        {"id": 300012, "image": "https://x/c.png"},
    ]))
    out_root = tmp_path / "out"

    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_image_bytes
        stats = run_bundle(cache, out_root, workers=2)

    assert stats["images_total"] == 3
    assert stats["downloaded"] == 3
    assert stats["failed"] == 0

    # Verify WebP files actually decodeable + correct size
    from PIL import Image
    for iid in (300010, 300011, 300012):
        path = out_root / "images" / f"{iid}.webp"
        assert path.exists()
        with Image.open(path) as img:
            assert img.size == (256, 256)
            assert img.format == "WEBP"

    # Manifest round-trip
    manifest_path = out_root / "manifest.json"
    write_manifest({"scrape": {}, "images": stats}, manifest_path)
    loaded = read_manifest(manifest_path)
    assert loaded["images"] == stats
```

- [ ] **Step 2: Run integration test**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_pipeline_smoke.py -v -m integration`
Expected: 1 passed

- [ ] **Step 3: Verify it skips without -m flag**

Run: `python -m pytest tests/dev_tools/scrape_pipeline/test_pipeline_smoke.py -v`
Expected: 1 deselected (marker respected)

- [ ] **Step 4: Commit**

```bash
git add tests/dev_tools/scrape_pipeline/test_pipeline_smoke.py
git commit -m "test(scrape_pipeline): add integration smoke test"
```

---

## Task 14: Run actual full scrape (one-shot, time-boxed)

**Files:**
- Generate: `tbh_desktop/manifest.json`
- Generate: `tbh_desktop/images/{item_id}.webp` (potentially thousands)

- [ ] **Step 1: Dry-run to preview**

Run: `python -m dev_tools.scrape_pipeline all --dry-run`
Expected: prints intent, no files written

- [ ] **Step 2: Run scrape stage first (allows cancel if wiki is down)**

Run: `python -m dev_tools.scrape_pipeline scrape --resume 2>&1 | tee /tmp/scrape.log`
Expected: scrape completes (may take 30-60 minutes for full wiki); logs show per-combo done

- [ ] **Step 3: Verify scrape output**

Run: `ls tbh_desktop/gear/sword/ | head; echo "---"; ls tbh_desktop/item/CRAFTING/ 2>/dev/null | head`
Expected: JSON cache files present for each combo

- [ ] **Step 4: Run bundle stage**

Run: `python -m dev_tools.scrape_pipeline bundle --workers 4 2>&1 | tee /tmp/bundle.log`
Expected: images downloaded, manifest.json written

- [ ] **Step 5: Verify bundle output**

Run: `cat tbh_desktop/manifest.json`
Expected: JSON with schema_version=1, non-zero counts

Run: `ls tbh_desktop/images/ | wc -l`
Expected: count matches `images.downloaded` in manifest

- [ ] **Step 6: Sample-verify one image opens**

Run: `python -c "from PIL import Image; img = Image.open('$(ls tbh_desktop/images/*.webp | head -1)'); print(img.size, img.format)"`
Expected: `(256, 256) WEBP`

- [ ] **Step 7: Commit populated data + manifest**

```bash
git add tbh_desktop/manifest.json tbh_desktop/images/ tbh_desktop/gear/ tbh_desktop/item/ tbh_desktop/box_loot_cache/ tbh_desktop/box_drop_map.json tbh_desktop/drops_index.json tbh_desktop/box_slug_cache.json
git commit -m "chore(data): populate scraped caches + WebP images + manifest.json"
```

---

## Task 15: Final verification

**Files:** none modified

- [ ] **Step 1: Run complete test suite**

Run: `python -m pytest tests/ -q`
Expected: All tests pass (existing + new)

- [ ] **Step 2: Run pyright / linter (project default)**

Run: `python -m pyright tbh_desktop/dev_tools_scrape_pipeline/ 2>&1 | tail -20`
Expected: no errors (or warnings only matching existing project baseline)

- [ ] **Step 3: Verify CLI help text**

Run: `python -m dev_tools.scrape_pipeline --help`
Expected: usage info printed, exits 0

- [ ] **Step 4: Confirm git tree clean**

Run: `git status --short`
Expected: no uncommitted changes

- [ ] **Step 5: Final summary commit (no-op if clean)**

If there are any pending tweaks:
```bash
git commit -m "chore(scrape_pipeline): final cleanup after first full run"
```

Otherwise skip this step.

---

## Done Criteria

- [ ] All 15 tasks checked off
- [ ] `python -m pytest tests/` passes (existing + new)
- [ ] `tbh_desktop/manifest.json` exists with `schema_version=1`
- [ ] `tbh_desktop/images/{item_id}.webp` populated
- [ ] `python -m dev_tools.scrape_pipeline --help` works
- [ ] Branch state committed; no uncommitted changes

**Next spec (separate):** PyInstaller spec + AppImage/.exe build, leveraging the populated `tbh_desktop/` bundle as `--add-data` source.
