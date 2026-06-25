# TBH Desktop App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PySide6 desktop GUI that edits `src/config.json` (rules + port), picks replacement reward IDs from gear wiki + per-box loot tables, and runs/stops the mitmproxy with a real-time log viewer.

**Architecture:** App lives in `tbh_desktop/` at repo root, imports `src.tbh_reward_hook` for config schema/validation only. Scraper module fetches gear wiki + box pages, caches to JSON. Proxy runner spawns `src/run_proxy.py` as subprocess, streams stdout via Qt signals. Config editor mutates a raw dict (preserving advanced fields), saves atomically with backup.

**Tech Stack:** Python 3, PySide6, requests, pytest. Reuses existing `src/tbh_reward_hook.py` (`ProxyConfig`, `QueueRule`, `RangeRule`).

**Spec:** `docs/superpowers/specs/2026-06-25-desktop-app-design.md`

---

## File Structure

```
tbh_desktop/
├── __init__.py
├── main.py                  # QApplication entry
├── config_io.py             # load/save config.json as raw dict + validate via ProxyConfig
├── scraper.py               # fetch+parse gear wiki + box pages, cache to JSON
├── proxy_runner.py          # subprocess + stdout reader thread + Qt signals
├── paths.py                 # resolve repo root + cache paths
├── gear_cache.json          # generated, gitignored
├── box_loot_cache/          # generated, gitignored
└── ui/
    ├── __init__.py
    ├── main_window.py       # QMainWindow, toolbar, splitter
    ├── config_editor.py     # QWidget: rules table + range section
    ├── gear_picker.py       # QDialog multi-select gear
    ├── box_loot_picker.py   # QDialog multi-select box loot
    └── log_panel.py         # QPlainTextEdit log viewer
tests/
├── conftest.py              # fixtures: tmp config, sample HTML
├── fixtures/
│   ├── gear_page.html       # sample wiki gear HTML
│   └── box_page.html        # sample box page HTML
├── test_config_io.py
├── test_scraper.py
└── test_proxy_runner.py
requirements-desktop.txt     # PySide6, requests
.gitignore                   # add cache entries
```

---

## Task 0: Project scaffold + deps

**Files:**
- Create: `tbh_desktop/__init__.py`
- Create: `tbh_desktop/paths.py`
- Create: `requirements-desktop.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Create package init**

```python
# tbh_desktop/__init__.py
"""TBH Reward Proxy desktop GUI."""
```

- [ ] **Step 2: Create paths module**

```python
# tbh_desktop/paths.py
"""Path resolution for TBH desktop app."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
CONFIG_PATH = SRC_DIR / "config.json"
RUN_PROXY_PATH = SRC_DIR / "run_proxy.py"
DESKTOP_DIR = Path(__file__).resolve().parent
GEAR_CACHE = DESKTOP_DIR / "gear_cache.json"
BOX_LOOT_CACHE_DIR = DESKTOP_DIR / "box_loot_cache"
```

- [ ] **Step 3: Create requirements file**

```
# requirements-desktop.txt
PySide6>=6.6
requests>=2.31
```

- [ ] **Step 4: Update .gitignore**

Add to existing `.gitignore`:

```
# Desktop app generated caches
tbh_desktop/gear_cache.json
tbh_desktop/box_loot_cache/
```

- [ ] **Step 5: Install deps**

Run: `pip install -r requirements-desktop.txt`
Expected: PySide6 + requests installed successfully.

- [ ] **Step 6: Commit**

```bash
git add tbh_desktop/__init__.py tbh_desktop/paths.py requirements-desktop.txt .gitignore
git commit -m "feat(desktop): scaffold package, paths, deps"
```

---

## Task 1: config_io — load raw dict

**Files:**
- Create: `tbh_desktop/config_io.py`
- Create: `tests/conftest.py`
- Create: `tests/test_config_io.py`

- [ ] **Step 1: Write conftest fixture**

```python
# tests/conftest.py
"""Shared test fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_config_dict() -> dict:
    return {
        "listen_port": 8877,
        "only_post": True,
        "require_boxes_marker": True,
        "url_contains": ["/backend-function/base/v1"],
        "specific_queue_rules": [
            {
                "enabled": True,
                "name": "White box",
                "item_id": 910801,
                "replacement_reward_item_ids": [406171],
            }
        ],
        "range_replacement": {
            "enabled": True,
            "name": "Range replacement",
            "match_min_item_id": 500000,
            "match_max_item_id": 950000,
            "replacement_reward_item_ids": [605041, 615041],
        },
    }


@pytest.fixture
def config_file(tmp_path: Path, sample_config_dict: dict) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict, indent=4), encoding="utf-8")
    return p
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_config_io.py
"""Tests for config_io."""
from __future__ import annotations

from pathlib import Path

import pytest

from tbh_desktop import config_io


def test_load_config_returns_raw_dict(config_file: Path) -> None:
    data = config_io.load_config(config_file)
    assert isinstance(data, dict)
    assert data["listen_port"] == 8877
    assert data["only_post"] is True
    # advanced field preserved
    assert data["url_contains"] == ["/backend-function/base/v1"]


def test_load_config_missing_file_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    data = config_io.load_config(missing)
    assert data == {}


def test_load_config_invalid_json_returns_empty(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    data = config_io.load_config(bad)
    assert data == {}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_config_io.py -v`
Expected: FAIL with `ImportError` (module not found).

- [ ] **Step 4: Implement load_config**

```python
# tbh_desktop/config_io.py
"""Load/save src/config.json as raw dict; validate via ProxyConfig."""
from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from tbh_desktop.paths import REPO_ROOT, SRC_DIR

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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_config_io.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add tbh_desktop/config_io.py tests/conftest.py tests/test_config_io.py
git commit -m "feat(desktop): config_io load raw dict"
```

---

## Task 2: config_io — validate + save atomic with backup

**Files:**
- Modify: `tbh_desktop/config_io.py`
- Modify: `tests/test_config_io.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_io.py`:

```python
def test_save_config_writes_valid_json(tmp_path: Path, sample_config_dict: dict) -> None:
    target = tmp_path / "config.json"
    config_io.save_config(target, sample_config_dict)
    reloaded = config_io.load_config(target)
    assert reloaded == sample_config_dict


def test_save_config_creates_backup(tmp_path: Path, sample_config_dict: dict) -> None:
    target = tmp_path / "config.json"
    target.write_text('{"old": true}', encoding="utf-8")
    config_io.save_config(target, sample_config_dict)
    backup = target.with_suffix(".json.bak")
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8")) == {"old": True}


def test_save_config_rejects_invalid_does_not_overwrite(tmp_path: Path) -> None:
    import json
    target = tmp_path / "config.json"
    original = {"listen_port": 1234, "specific_queue_rules": "not-a-list"}
    target.write_text(json.dumps(original), encoding="utf-8")
    # invalid: specific_queue_rules must be list. ProxyConfig.load should reject.
    result = config_io.save_config(target, {"listen_port": 9999, "specific_queue_rules": "bad"})
    assert result.ok is False
    # original preserved
    assert json.loads(target.read_text(encoding="utf-8"))["listen_port"] == 1234


def test_validate_config_returns_true_for_valid(sample_config_dict: dict) -> None:
    assert config_io.validate_config(sample_config_dict) is True


def test_validate_config_returns_false_for_invalid() -> None:
    assert config_io.validate_config({"specific_queue_rules": "nope"}) is False
```

Add import at top of test file: `import json` (already there for the rejection test).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config_io.py -v`
Expected: FAIL — `save_config`, `validate_config` not defined.

- [ ] **Step 3: Implement validate_config + save_config**

Append to `tbh_desktop/config_io.py`:

```python
from dataclasses import dataclass


@dataclass
class SaveResult:
    ok: bool
    error: str | None = None


def validate_config(data: dict[str, Any]) -> bool:
    """Return True if data parses as a valid ProxyConfig."""
    try:
        ProxyConfig.load(data)
        return True
    except Exception:
        return False


def save_config(path: Path, data: dict[str, Any]) -> SaveResult:
    """Validate, backup, atomic-write config. Restore from backup if validation fails post-write."""
    if not validate_config(data):
        return SaveResult(ok=False, error="config failed ProxyConfig validation")

    # Backup existing file before overwrite.
    if path.exists():
        backup = path.with_suffix(".json.bak")
        shutil.copy2(path, backup)

    # Atomic write: temp file + rename.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

    # Validate the written file round-trips.
    reloaded = load_config(path)
    if not validate_config(reloaded):
        # Restore from backup if it exists.
        backup = path.with_suffix(".json.bak")
        if backup.exists():
            shutil.copy2(backup, path)
        return SaveResult(ok=False, error="written config failed re-validation; restored backup")
    return SaveResult(ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config_io.py -v`
Expected: 5 new + 3 old = 8 PASS.

Note: the rejection test relies on `ProxyConfig.load` rejecting `specific_queue_rules: "bad"`. Verify by running; if ProxyConfig is lenient, adjust the invalid fixture to a shape that truly fails (e.g. missing `range_replacement`). Inspect `src/tbh_reward_hook.py:120-185` for actual validation strictness.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/config_io.py tests/test_config_io.py
git commit -m "feat(desktop): config_io validate + atomic save with backup"
```

---

## Task 3: scraper — parse gear wiki HTML

**Files:**
- Create: `tests/fixtures/gear_page.html`
- Create: `tests/test_scraper.py`
- Create: `tbh_desktop/scraper.py`

- [ ] **Step 1: Create gear page fixture**

Save a minimal but representative HTML sample to `tests/fixtures/gear_page.html`. Structure reflects the real wiki card grid (verify against a real fetch — see Risk note). Sample:

```html
<!DOCTYPE html>
<html><body>
<div class="gear-grid">
  <a class="gear-card obtainable" href="/items/300001-long-sword">
    <img src="/game/gear/sword/SWORD_300001.png" alt="Long Sword"/>
    <span class="rarity">Common</span>
    <span class="name">Long Sword</span>
    <span class="type">Sword</span>
  </a>
  <a class="gear-card" href="/items/300002-short-sword">
    <img src="/game/gear/sword/SWORD_300002.png" alt="Short Sword"/>
    <span class="rarity">Common</span>
    <span class="name">Short Sword</span>
    <span class="type">Sword</span>
  </a>
</div>
</body></html>
```

Note: real selector may differ. Before writing the parser, fetch `https://taskbarhero.wiki/gear` once and confirm whether gear cards are in static HTML or JS-rendered. If JS-rendered, this task blocks — escalate per Risk in spec. The fixture above assumes static cards with `obtainable` marker class.

- [ ] **Step 2: Write failing test**

```python
# tests/test_scraper.py
"""Tests for scraper."""
from __future__ import annotations

from pathlib import Path

import pytest

from tbh_desktop import scraper

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_gear_page_returns_obtainable_only() -> None:
    html = (FIXTURES / "gear_page.html").read_text(encoding="utf-8")
    items = scraper.parse_gear_page(html)
    # Long Sword is obtainable; Short Sword is not (no obtainable class).
    ids = [i["id"] for i in items]
    assert 300001 in ids
    assert 300002 not in ids
    long_sword = next(i for i in items if i["id"] == 300001)
    assert long_sword["name"] == "Long Sword"
    assert long_sword["rarity"] == "Common"
    assert long_sword["type"] == "Sword"


def test_parse_gear_page_extracts_id_from_href() -> None:
    html = (FIXTURES / "gear_page.html").read_text(encoding="utf-8")
    items = scraper.parse_gear_page(html)
    assert items[0]["id"] == 300001
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_scraper.py -v`
Expected: FAIL — `scraper` module not found.

- [ ] **Step 4: Implement parse_gear_page**

```python
# tbh_desktop/scraper.py
"""Fetch + parse gear wiki and box pages; cache to JSON."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

GEAR_URL = "https://taskbarhero.wiki/gear"
BOX_URL_TEMPLATE = "https://taskbarhero.org/en/items/chests/{box_id}-{slug}/"
ID_RE = re.compile(r"/items/[^/]*?(\d+)-")


def parse_gear_page(html: str) -> list[dict[str, Any]]:
    """Parse gear wiki HTML, return list of obtainable gear dicts.

    Each dict: {id, name, rarity, type}. Only cards marked obtainable are returned.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    for card in soup.select(".gear-card"):
        if "obtainable" not in card.get("class", []):
            continue
        href = card.get("href", "")
        m = ID_RE.search(href)
        if not m:
            continue
        name_el = card.select_one(".name")
        rarity_el = card.select_one(".rarity")
        type_el = card.select_one(".type")
        items.append(
            {
                "id": int(m.group(1)),
                "name": name_el.get_text(strip=True) if name_el else "",
                "rarity": rarity_el.get_text(strip=True) if rarity_el else "",
                "type": type_el.get_text(strip=True) if type_el else "",
            }
        )
    return items
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_scraper.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/gear_page.html tests/test_scraper.py tbh_desktop/scraper.py
git commit -m "feat(desktop): scraper parse gear wiki HTML"
```

Note: add `beautifulsoup4` to `requirements-desktop.txt` if not already present. Run `pip install beautifulsoup4` and add the line:

```
beautifulsoup4>=4.12
```

---

## Task 4: scraper — parse box page loot table

**Files:**
- Create: `tests/fixtures/box_page.html`
- Modify: `tests/test_scraper.py`
- Modify: `tbh_desktop/scraper.py`

- [ ] **Step 1: Create box page fixture**

`tests/fixtures/box_page.html` — reflects real box page structure (verified via earlier fetch of `910801` page). Loot table is an HTML table:

```html
<!DOCTYPE html>
<html><body>
<h1>910801 · Normal Monster Box Lv80</h1>
<h2>Loot table</h2>
<table><tbody>
<tr><th>Name</th><th>Rate</th></tr>
<tr>
  <td><img src="/assets/tbhdb/game/gear/helmet/HELMET_500017.png"/> <strong>Dimensional Helmet</strong></td>
  <td>7.9%</td>
</tr>
<tr>
  <td><img src="/assets/tbhdb/game/items/materials/Item_141001.png"/> <a href="/en/items/materials/141001-bronze-ingot/">Bronze Ingot</a></td>
  <td>1.5%</td>
</tr>
</tbody></table>
</body></html>
```

- [ ] **Step 2: Write failing test**

Append to `tests/test_scraper.py`:

```python
def test_parse_box_page_returns_loot_with_ids() -> None:
    html = (FIXTURES / "box_page.html").read_text(encoding="utf-8")
    loot = scraper.parse_box_page(html)
    ids = [l["id"] for l in loot]
    # gear id from image path HELMET_500017.png
    assert 500017 in ids
    # material id from href 141001-bronze-ingot
    assert 141001 in ids
    helmet = next(l for l in loot if l["id"] == 500017)
    assert helmet["name"] == "Dimensional Helmet"
    assert helmet["rate"] == "7.9%"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_scraper.py::test_parse_box_page_returns_loot_with_ids -v`
Expected: FAIL — `parse_box_page` not defined.

- [ ] **Step 4: Implement parse_box_page**

Append to `tbh_desktop/scraper.py`:

```python
GEAR_IMG_ID_RE = re.compile(r"/(?:HELMET|ARMOR|GLOVES|BOOTS|SWORD|BOW|STAFF|SCEPTER|CROSSBOW|AXE|SHIELD|OFFHAND)_(\d+)\.png", re.IGNORECASE)
MATERIAL_IMG_ID_RE = re.compile(r"/Item_(\d+)\.png", re.IGNORECASE)
HREF_ID_RE = re.compile(r"/items/[^/]*?(\d+)-")


def parse_box_page(html: str) -> list[dict[str, Any]]:
    """Parse box page HTML, return loot table items.

    Each dict: {id, name, rate}. ID extracted from gear image path, material image
    path, or href. Only rows inside the 'Loot table' section are returned.
    """
    soup = BeautifulSoup(html, "html.parser")
    loot: list[dict[str, Any]] = []
    # Find the Loot table heading, then the next table after it.
    loot_heading = soup.find(lambda tag: tag.name in ("h2", "h3") and "loot table" in tag.get_text(strip=True).lower())
    start = loot_heading if loot_heading is not None else soup
    table = start.find_next("table") if loot_heading is not None else soup.find("table")
    if table is None:
        return loot
    for row in table.select("tbody > tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue  # header row
        name_cell = cells[0]
        rate = cells[1].get_text(strip=True)
        name = name_cell.get_text(strip=True)
        item_id = _extract_item_id(name_cell)
        if item_id is None:
            continue
        loot.append({"id": item_id, "name": name, "rate": rate})
    return loot


def _extract_item_id(cell: Any) -> int | None:
    # Try gear image path.
    for img in cell.find_all("img"):
        src = img.get("src", "")
        m = GEAR_IMG_ID_RE.search(src)
        if m:
            return int(m.group(1))
        m = MATERIAL_IMG_ID_RE.search(src)
        if m:
            return int(m.group(1))
    # Try href.
    for a in cell.find_all("a"):
        href = a.get("href", "")
        m = HREF_ID_RE.search(href)
        if m:
            return int(m.group(1))
    return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_scraper.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/box_page.html tests/test_scraper.py tbh_desktop/scraper.py
git commit -m "feat(desktop): scraper parse box loot table"
```

---

## Task 5: scraper — cache layer + box slug resolution

**Files:**
- Modify: `tbh_desktop/scraper.py`
- Modify: `tests/test_scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_scraper.py`:

```python
def test_cache_gear_round_trip(tmp_path: Path) -> None:
    cache = tmp_path / "gear_cache.json"
    items = [{"id": 1, "name": "X", "rarity": "Common", "type": "Sword"}]
    scraper.write_gear_cache(cache, items)
    loaded = scraper.read_gear_cache(cache)
    assert loaded == items


def test_cache_box_loot_round_trip(tmp_path: Path) -> None:
    cache_dir = tmp_path / "box_loot_cache"
    cache_dir.mkdir()
    loot = [{"id": 500017, "name": "Helmet", "rate": "7.9%"}]
    scraper.write_box_cache(cache_dir, 910801, loot)
    loaded = scraper.read_box_cache(cache_dir, 910801)
    assert loaded == loot


def test_read_gear_cache_missing_returns_empty(tmp_path: Path) -> None:
    assert scraper.read_gear_cache(tmp_path / "nope.json") == []


def test_read_box_cache_missing_returns_empty(tmp_path: Path) -> None:
    assert scraper.read_box_cache(tmp_path / "box_loot_cache", 910801) == []


def test_resolve_box_slug_from_name() -> None:
    # Normal Monster Box Lv80 -> normal-monster-box-lv80
    assert scraper.resolve_box_slug("Normal Monster Box Lv80") == "normal-monster-box-lv80"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scraper.py -v`
Expected: FAIL — cache + slug functions not defined.

- [ ] **Step 3: Implement cache + slug**

Append to `tbh_desktop/scraper.py`:

```python
def write_gear_cache(path: Path, items: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def read_gear_cache(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def write_box_cache(cache_dir: Path, box_id: int, loot: list[dict[str, Any]]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{box_id}.json").write_text(
        json.dumps(loot, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_box_cache(cache_dir: Path, box_id: int) -> list[dict[str, Any]]:
    p = cache_dir / f"{box_id}.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def resolve_box_slug(name: str) -> str:
    """Convert a box name to URL slug. e.g. 'Normal Monster Box Lv80' -> 'normal-monster-box-lv80'."""
    return name.strip().lower().replace(" ", "-")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scraper.py -v`
Expected: 8 PASS (3 old + 5 new).

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/scraper.py tests/test_scraper.py
git commit -m "feat(desktop): scraper cache layer + box slug resolution"
```

---

## Task 6: scraper — fetch live + cache orchestration

**Files:**
- Modify: `tbh_desktop/scraper.py`
- Modify: `tests/test_scraper.py`

- [ ] **Step 1: Write failing test (monkeypatch requests)**

Append to `tests/test_scraper.py`:

```python
from unittest.mock import patch


def test_refresh_gear_fetches_parses_caches(tmp_path: Path) -> None:
    cache = tmp_path / "gear_cache.json"
    html = (FIXTURES / "gear_page.html").read_text(encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status = lambda: None
        items = scraper.refresh_gear(cache)
    assert 300001 in [i["id"] for i in items]
    # cache written
    assert scraper.read_gear_cache(cache) == items


def test_refresh_gear_falls_back_to_cache_on_error(tmp_path: Path) -> None:
    cache = tmp_path / "gear_cache.json"
    cached = [{"id": 99, "name": "Cached", "rarity": "Common", "type": "Sword"}]
    scraper.write_gear_cache(cache, cached)
    with patch("tbh_desktop.scraper.requests.get", side_effect=Exception("network")):
        items = scraper.refresh_gear(cache)
    assert items == cached


def test_refresh_box_loot_fetches_parses_caches(tmp_path: Path) -> None:
    cache_dir = tmp_path / "box_loot_cache"
    html = (FIXTURES / "box_page.html").read_text(encoding="utf-8")
    with patch("tbh_desktop.scraper.requests.get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status = lambda: None
        loot = scraper.refresh_box_loot(cache_dir, 910801, "normal-monster-box-lv80")
    assert 500017 in [l["id"] for l in loot]
    assert scraper.read_box_cache(cache_dir, 910801) == loot
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scraper.py -v`
Expected: FAIL — `refresh_gear`, `refresh_box_loot` not defined.

- [ ] **Step 3: Implement refresh functions**

Append to `tbh_desktop/scraper.py`:

```python
def refresh_gear(cache_path: Path) -> list[dict[str, Any]]:
    """Fetch gear wiki, parse, cache. Fall back to existing cache on error."""
    try:
        resp = requests.get(GEAR_URL, timeout=30)
        resp.raise_for_status()
        items = parse_gear_page(resp.text)
        write_gear_cache(cache_path, items)
        return items
    except Exception as exc:
        log.warning("gear refresh failed: %s", exc)
        return read_gear_cache(cache_path)


def refresh_box_loot(cache_dir: Path, box_id: int, slug: str) -> list[dict[str, Any]]:
    """Fetch box page, parse loot, cache. Fall back to existing cache on error."""
    try:
        url = BOX_URL_TEMPLATE.format(box_id=box_id, slug=slug)
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        loot = parse_box_page(resp.text)
        write_box_cache(cache_dir, box_id, loot)
        return loot
    except Exception as exc:
        log.warning("box %s refresh failed: %s", box_id, exc)
        return read_box_cache(cache_dir, box_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scraper.py -v`
Expected: 11 PASS.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/scraper.py tests/test_scraper.py
git commit -m "feat(desktop): scraper live fetch + cache fallback"
```

---

## Task 7: proxy_runner — subprocess + stdout stream

**Files:**
- Create: `tbh_desktop/proxy_runner.py`
- Create: `tests/test_proxy_runner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_proxy_runner.py
"""Tests for proxy_runner."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tbh_desktop import proxy_runner


def test_runner_emits_log_lines(qtbot) -> None:
    runner = proxy_runner.ProxyRunner()
    lines: list[str] = []
    runner.log_line.connect(lines.append)
    with patch("tbh_desktop.proxy_runner.subprocess.Popen") as mock_popen:
        proc = MagicMock()
        proc.stdout = iter(["[TBH] hello\n", "[TBH] world\n"])
        proc.poll.return_value = 0
        mock_popen.return_value = proc
        runner.start()
    qtbot.waitUntil(lambda: "[TBH] hello" in lines, timeout=2000)
    assert "[TBH] hello" in lines


def test_running_signal_toggles(qtbot) -> None:
    runner = proxy_runner.ProxyRunner()
    states: list[bool] = []
    runner.running.connect(states.append)
    with patch("tbh_desktop.proxy_runner.subprocess.Popen") as mock_popen:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.poll.return_value = 0
        mock_popen.return_value = proc
        runner.start()
    qtbot.waitUntil(lambda: True in states, timeout=2000)
    assert True in states
```

Note: `qtbot` fixture requires `pytest-qt`. Add to `requirements-desktop.txt`:

```
pytest-qt>=4.3
```

Run `pip install pytest-qt`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_proxy_runner.py -v`
Expected: FAIL — module not found / qtbot errors.

- [ ] **Step 3: Implement ProxyRunner**

```python
# tbh_desktop/proxy_runner.py
"""Run src/run_proxy.py as subprocess, stream stdout via Qt signals."""
from __future__ import annotations

import subprocess
import sys
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from tbh_desktop.paths import REPO_ROOT, RUN_PROXY_PATH


class ProxyRunner(QObject):
    log_line = Signal(str)
    running = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.is_running():
            return
        self._proc = subprocess.Popen(
            [sys.executable, str(RUN_PROXY_PATH)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.running.emit(True)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self.log_line.emit(line.rstrip("\n"))
        self._proc.wait()
        self.running.emit(False)

    def stop(self) -> None:
        if not self.is_running() or self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self.running.emit(False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_proxy_runner.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/proxy_runner.py tests/test_proxy_runner.py requirements-desktop.txt
git commit -m "feat(desktop): proxy_runner subprocess + stdout stream"
```

---

## Task 8: log_panel widget

**Files:**
- Create: `tbh_desktop/ui/__init__.py`
- Create: `tbh_desktop/ui/log_panel.py`

- [ ] **Step 1: Create ui package init**

```python
# tbh_desktop/ui/__init__.py
"""TBH desktop UI widgets."""
```

- [ ] **Step 2: Implement LogPanel**

```python
# tbh_desktop/ui/log_panel.py
"""Read-only log viewer with FIFO cap."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QPlainTextEdit


class LogPanel(QPlainTextEdit):
    MAX_LINES = 10_000

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Built-in FIFO cap — oldest blocks dropped automatically. No manual trim.
        self.setMaximumBlockCount(self.MAX_LINES)
        self.setStyleSheet(
            "QPlainTextEdit { background: #1e1e1e; color: #d4d4d4; font-family: monospace; font-size: 12px; }"
        )

    def append_log(self, line: str) -> None:
        self.appendPlainText(line)

    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        menu = self.createStandardContextMenu()
        clear_action = QAction("Clear", self)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)
        menu.exec(event.globalPos())
```

Note: `setMaximumBlockCount` is QPlainTextEdit's built-in FIFO — when block count exceeds the limit, the oldest blocks are discarded automatically. This replaces any manual cursor-based trimming.

- [ ] **Step 3: Smoke test**

Run:
```bash
python -c "from PySide6.QtWidgets import QApplication; app=QApplication([]); from tbh_desktop.ui.log_panel import LogPanel; p=LogPanel(); p.append_log('test'); print('ok', p.toPlainText())"
```
Expected: prints `ok test`.

- [ ] **Step 4: Commit**

```bash
git add tbh_desktop/ui/__init__.py tbh_desktop/ui/log_panel.py
git commit -m "feat(desktop): log_panel widget"
```

---

## Task 9: gear_picker dialog

**Files:**
- Create: `tbh_desktop/ui/gear_picker.py`

- [ ] **Step 1: Implement GearPicker**

```python
# tbh_desktop/ui/gear_picker.py
"""Dialog to pick gear reward IDs from cached gear list."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class GearPicker(QDialog):
    def __init__(self, gear_items: list[dict[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pick gear")
        self.resize(400, 500)
        self._all = gear_items

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name or id...")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate(gear_items)

    def _populate(self, items: list[dict[str, Any]]) -> None:
        self.list_widget.clear()
        for item in items:
            text = f'{item["id"]} · {item["name"]} ({item.get("rarity", "")})'
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item["id"])
            self.list_widget.addItem(list_item)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        if not text:
            self._populate(self._all)
            return
        filtered = [
            i for i in self._all if text in i["name"].lower() or text in str(i["id"])
        ]
        self._populate(filtered)

    def selected_ids(self) -> list[int]:
        return [
            item.data(Qt.ItemDataRole.UserRole) for item in self.list_widget.selectedItems()
        ]
```

- [ ] **Step 2: Smoke test**

Run:
```bash
python -c "
from PySide6.QtWidgets import QApplication
app=QApplication([])
from tbh_desktop.ui.gear_picker import GearPicker
items=[{'id':300001,'name':'Long Sword','rarity':'Common'}]
p=GearPicker(items)
print('ok', p.selected_ids())
"
```
Expected: prints `ok []`.

- [ ] **Step 3: Commit**

```bash
git add tbh_desktop/ui/gear_picker.py
git commit -m "feat(desktop): gear_picker dialog"
```

---

## Task 10: box_loot_picker dialog

**Files:**
- Create: `tbh_desktop/ui/box_loot_picker.py`

- [ ] **Step 1: Implement BoxLootPicker**

```python
# tbh_desktop/ui/box_loot_picker.py
"""Dialog to pick reward IDs from a box's loot table."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class BoxLootPicker(QDialog):
    def __init__(
        self, box_id: int, loot_items: list[dict[str, Any]], parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Pick from box {box_id} loot")
        self.resize(400, 500)
        self._all = loot_items

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Box {box_id} — loot table:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name or id...")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate(loot_items)

    def _populate(self, items: list[dict[str, Any]]) -> None:
        self.list_widget.clear()
        for item in items:
            text = f'{item["id"]} · {item["name"]} ({item.get("rate", "")})'
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item["id"])
            self.list_widget.addItem(list_item)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        if not text:
            self._populate(self._all)
            return
        filtered = [
            i for i in self._all if text in i["name"].lower() or text in str(i["id"])
        ]
        self._populate(filtered)

    def selected_ids(self) -> list[int]:
        return [
            item.data(Qt.ItemDataRole.UserRole) for item in self.list_widget.selectedItems()
        ]
```

- [ ] **Step 2: Smoke test**

Run:
```bash
python -c "
from PySide6.QtWidgets import QApplication
app=QApplication([])
from tbh_desktop.ui.box_loot_picker import BoxLootPicker
loot=[{'id':500017,'name':'Dimensional Helmet','rate':'7.9%'}]
p=BoxLootPicker(910801, loot)
print('ok', p.selected_ids())
"
```
Expected: prints `ok []`.

- [ ] **Step 3: Commit**

```bash
git add tbh_desktop/ui/box_loot_picker.py
git commit -m "feat(desktop): box_loot_picker dialog"
```

---

## Task 11: config_editor widget

**Files:**
- Create: `tbh_desktop/ui/config_editor.py`

- [ ] **Step 1: Implement ConfigEditor**

```python
# tbh_desktop/ui/config_editor.py
"""Editor for specific_queue_rules + range_replacement + port, operating on raw dict."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


COL_ENABLED = 0
COL_NAME = 1
COL_ITEM_ID = 2
COL_REPLACEMENT = 3


class ConfigEditor(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: dict[str, Any] = {}

        layout = QVBoxLayout(self)

        # Specific Queue Rules
        layout.addWidget(QLabel("Specific Queue Rules"))
        self.rules_table = QTableWidget(0, 4)
        self.rules_table.setHorizontalHeaderLabels(
            ["Enabled", "Name", "Item ID", "Replacement IDs"]
        )
        header = self.rules_table.horizontalHeader()
        header.setSectionResizeMode(COL_REPLACEMENT, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.rules_table)

        rules_buttons = QHBoxLayout()
        btn_add = QPushButton("Add rule")
        btn_remove = QPushButton("Remove rule")
        self.btn_pick_box = QPushButton("Pick from box loot")
        self.btn_pick_gear_rule = QPushButton("Pick gear")
        for b in (btn_add, btn_remove, self.btn_pick_box, self.btn_pick_gear_rule):
            rules_buttons.addWidget(b)
        rules_buttons.addStretch()
        layout.addLayout(rules_buttons)
        btn_add.clicked.connect(self._add_rule)
        btn_remove.clicked.connect(self._remove_rule)

        # Range Replacement
        layout.addWidget(QLabel("Range Replacement"))
        range_form = QFormLayout()
        self.range_enabled = QCheckBox("enabled")
        self.range_min = QLineEdit()
        self.range_max = QLineEdit()
        self.range_ids = QLineEdit()
        self.btn_pick_gear_range = QPushButton("Pick gear")
        range_form.addRow("Enabled", self.range_enabled)
        range_form.addRow("match_min_item_id", self.range_min)
        range_form.addRow("match_max_item_id", self.range_max)
        range_form.addRow("replacement IDs", self.range_ids)
        range_form.addRow("", self.btn_pick_gear_range)
        layout.addLayout(range_form)

        layout.addStretch()

    def load(self, data: dict[str, Any]) -> None:
        self._data = data
        rules = data.get("specific_queue_rules", []) or []
        self.rules_table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            self._set_rule_row(row, rule)
        rng = data.get("range_replacement", {}) or {}
        self.range_enabled.setChecked(bool(rng.get("enabled", False)))
        self.range_min.setText(str(rng.get("match_min_item_id", "")))
        self.range_max.setText(str(rng.get("match_max_item_id", "")))
        self.range_ids.setText(self._ids_to_text(rng.get("replacement_reward_item_ids", [])))

    def _set_rule_row(self, row: int, rule: dict[str, Any]) -> None:
        enabled_item = QTableWidgetItem()
        enabled_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        enabled_item.setCheckState(
            Qt.CheckState.Checked if rule.get("enabled") else Qt.CheckState.Unchecked
        )
        self.rules_table.setItem(row, COL_ENABLED, enabled_item)
        self.rules_table.setItem(row, COL_NAME, QTableWidgetItem(str(rule.get("name", ""))))
        self.rules_table.setItem(row, COL_ITEM_ID, QTableWidgetItem(str(rule.get("item_id", ""))))
        self.rules_table.setItem(
            row, COL_REPLACEMENT,
            QTableWidgetItem(self._ids_to_text(rule.get("replacement_reward_item_ids", []))),
        )

    def _add_rule(self) -> None:
        row = self.rules_table.rowCount()
        self.rules_table.insertRow(row)
        self._set_rule_row(row, {"enabled": False, "name": "", "item_id": "", "replacement_reward_item_ids": []})

    def _remove_rule(self) -> None:
        row = self.rules_table.currentRow()
        if row >= 0:
            self.rules_table.removeRow(row)

    def selected_rule_item_id(self) -> int | None:
        row = self.rules_table.currentRow()
        if row < 0:
            return None
        text = self.rules_table.item(row, COL_ITEM_ID).text().strip()
        try:
            return int(text)
        except ValueError:
            return None

    def add_ids_to_selected_rule(self, ids: list[int]) -> None:
        row = self.rules_table.currentRow()
        if row < 0:
            return
        existing = self._text_to_ids(self.rules_table.item(row, COL_REPLACEMENT).text())
        merged = existing + [i for i in ids if i not in existing]
        self.rules_table.item(row, COL_REPLACEMENT).setText(self._ids_to_text(merged))

    def add_ids_to_range(self, ids: list[int]) -> None:
        existing = self._text_to_ids(self.range_ids.text())
        merged = existing + [i for i in ids if i not in existing]
        self.range_ids.setText(self._ids_to_text(merged))

    def dump(self) -> dict[str, Any]:
        """Return updated raw dict preserving advanced fields."""
        data = dict(self._data)
        rules = []
        for row in range(self.rules_table.rowCount()):
            rules.append(
                {
                    "enabled": self.rules_table.item(row, COL_ENABLED).checkState()
                    == Qt.CheckState.Checked,
                    "name": self.rules_table.item(row, COL_NAME).text(),
                    "item_id": int(self.rules_table.item(row, COL_ITEM_ID).text() or 0),
                    "replacement_reward_item_ids": self._text_to_ids(
                        self.rules_table.item(row, COL_REPLACEMENT).text()
                    ),
                }
            )
        data["specific_queue_rules"] = rules
        data["range_replacement"] = {
            "enabled": self.range_enabled.isChecked(),
            "name": (data.get("range_replacement") or {}).get("name", "Range replacement"),
            "match_min_item_id": int(self.range_min.text() or 0),
            "match_max_item_id": int(self.range_max.text() or 0),
            "replacement_reward_item_ids": self._text_to_ids(self.range_ids.text()),
        }
        return data

    @staticmethod
    def _ids_to_text(ids: list[Any]) -> str:
        return ", ".join(str(i) for i in (ids or []))

    @staticmethod
    def _text_to_ids(text: str) -> list[int]:
        out: list[int] = []
        for part in (text or "").replace(",", " ").split():
            try:
                out.append(int(part))
            except ValueError:
                continue
        return out
```

Note: requires `from PySide6.QtCore import Qt` import — add at top of file. Verify enum access (`Qt.ItemFlag.ItemIsUserCheckable`, `Qt.CheckState.Checked`) matches installed PySide6.

- [ ] **Step 2: Fix imports**

Ensure the top of `tbh_desktop/ui/config_editor.py` includes:

```python
from PySide6.QtCore import Qt
```

- [ ] **Step 3: Smoke test**

Run:
```bash
python -c "
from PySide6.QtWidgets import QApplication
app=QApplication([])
from tbh_desktop.ui.config_editor import ConfigEditor
e=ConfigEditor()
e.load({'specific_queue_rules':[{'enabled':True,'name':'White','item_id':910801,'replacement_reward_item_ids':[406171]}],'range_replacement':{'enabled':True,'match_min_item_id':500000,'match_max_item_id':950000,'replacement_reward_item_ids':[605041]}})
d=e.dump()
print('ok', d['specific_queue_rules'][0]['item_id'], d['range_replacement']['match_min_item_id'])
"
```
Expected: prints `ok 910801 500000`.

- [ ] **Step 4: Commit**

```bash
git add tbh_desktop/ui/config_editor.py
git commit -m "feat(desktop): config_editor widget"
```

---

## Task 12: main_window wiring

**Files:**
- Create: `tbh_desktop/ui/main_window.py`
- Create: `tbh_desktop/main.py`

- [ ] **Step 1: Implement MainWindow**

```python
# tbh_desktop/ui/main_window.py
"""Main window: toolbar, splitter (editor + log), proxy runner wiring."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QLineEdit,
    QWidget,
    QHBoxLayout,
)

from tbh_desktop import config_io, scraper
from tbh_desktop.paths import BOX_LOOT_CACHE_DIR, CONFIG_PATH, GEAR_CACHE
from tbh_desktop.proxy_runner import ProxyRunner
from tbh_desktop.ui.config_editor import ConfigEditor
from tbh_desktop.ui.box_loot_picker import BoxLootPicker
from tbh_desktop.ui.gear_picker import GearPicker
from tbh_desktop.ui.log_panel import LogPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TBH Reward Proxy")
        self.resize(1000, 700)

        self.runner = ProxyRunner()
        self.runner.log_line.connect(self._on_log)
        self.runner.running.connect(self._on_running)

        self.editor = ConfigEditor()
        self.log_panel = LogPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.log_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self._build_toolbar()
        self.setStatusBar(QStatusBar())

        self._reload_config()

        # Wire editor buttons
        self.editor.btn_pick_box.clicked.connect(self._pick_box_loot)
        self.editor.btn_pick_gear_rule.clicked.connect(lambda: self._pick_gear(target="rule"))
        self.editor.btn_pick_gear_range.clicked.connect(lambda: self._pick_gear(target="range"))

    def _build_toolbar(self) -> None:
        bar = self.addToolBar("main")
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_refresh_gear = QPushButton("Refresh gear")
        self.btn_save = QPushButton("Save config")
        self.port_edit = QLineEdit()
        self.port_edit.setFixedWidth(70)
        self.port_edit.setPlaceholderText("port")
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: red;")

        for w in (self.btn_start, self.btn_stop, self.btn_refresh_gear, self.btn_save, self.port_edit, self.status_dot):
            bar.addWidget(w)

        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_refresh_gear.clicked.connect(self._refresh_gear)
        self.btn_save.clicked.connect(self._save)

    def _reload_config(self) -> None:
        self._data = config_io.load_config(CONFIG_PATH)
        self.editor.load(self._data)
        self.port_edit.setText(str(self._data.get("listen_port", 8877)))

    def _on_log(self, line: str) -> None:
        self.log_panel.append_log(line)

    def _on_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.status_dot.setStyleSheet("color: green;" if running else "color: red;")

    def _start(self) -> None:
        self.runner.start()

    def _stop(self) -> None:
        self.runner.stop()

    def _refresh_gear(self) -> None:
        items = scraper.refresh_gear(GEAR_CACHE)
        self._on_log(f"Gear refreshed: {len(items)} items")

    def _save(self) -> None:
        data = self.editor.dump()
        data["listen_port"] = int(self.port_edit.text() or 8877)
        result = config_io.save_config(CONFIG_PATH, data)
        if result.ok:
            self._on_log("Config saved.")
            self._data = data
        else:
            self._on_log(f"Config save FAILED: {result.error}")

    def _pick_gear(self, target: str) -> None:
        items = scraper.read_gear_cache(GEAR_CACHE)
        if not items:
            self._on_log("No gear cache. Click 'Refresh gear' first.")
            return
        dlg = GearPicker(items, self)
        if dlg.exec():
            ids = dlg.selected_ids()
            if target == "rule":
                self.editor.add_ids_to_selected_rule(ids)
            else:
                self.editor.add_ids_to_range(ids)

    def _pick_box_loot(self) -> None:
        box_id = self.editor.selected_rule_item_id()
        if box_id is None:
            self._on_log("Select a rule row with a valid item_id first.")
            return
        # Resolve slug from rule name; fall back to generic.
        row = self.editor.rules_table.currentRow()
        name = self.editor.rules_table.item(row, 1).text() if row >= 0 else ""
        slug = scraper.resolve_box_slug(name) if name else str(box_id)
        loot = scraper.refresh_box_loot(BOX_LOOT_CACHE_DIR, box_id, slug)
        if not loot:
            self._on_log(f"No loot for box {box_id} (slug={slug}). Check box_id/name.")
            return
        dlg = BoxLootPicker(box_id, loot, self)
        if dlg.exec():
            self.editor.add_ids_to_selected_rule(dlg.selected_ids())

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.runner.is_running():
            self.runner.stop()
        super().closeEvent(event)
```

- [ ] **Step 2: Implement entry point**

```python
# tbh_desktop/main.py
"""TBH desktop app entry point."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Smoke test (launch + close)**

Run:
```bash
timeout 3 python -m tbh_desktop.main 2>&1 | head -5
```
Expected: window launches, no traceback. `timeout` kills after 3s.

- [ ] **Step 4: Commit**

```bash
git add tbh_desktop/ui/main_window.py tbh_desktop/main.py
git commit -m "feat(desktop): main_window wiring + entry point"
```

---

## Task 13: Manual verification end-to-end

**Files:** none (manual)

- [ ] **Step 1: Run full unit test suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 2: Verify real gear wiki scrape**

Run:
```bash
python -c "
from tbh_desktop import scraper
from tbh_desktop.paths import GEAR_CACHE
items = scraper.refresh_gear(GEAR_CACHE)
print('gear items:', len(items))
if items: print('sample:', items[0])
"
```
Expected: prints count > 0 and a sample dict. If 0, the wiki is JS-rendered — escalate per spec Risk (try mitmproxy-assisted fetch or alternative source).

- [ ] **Step 3: Verify real box loot scrape**

Run:
```bash
python -c "
from tbh_desktop import scraper
from tbh_desktop.paths import BOX_LOOT_CACHE_DIR
loot = scraper.refresh_box_loot(BOX_LOOT_CACHE_DIR, 910801, 'normal-monster-box-lv80')
print('loot items:', len(loot))
if loot: print('sample:', loot[0])
"
```
Expected: prints count > 0 with gear + material IDs. If 0, check slug/URL pattern.

- [ ] **Step 4: Launch app, edit config, save, verify hot-reload**

Run: `python -m tbh_desktop.main`
- Edit a rule, click Save config, observe "Config saved." in log.
- Click Start, observe proxy loads and `[TBH]` messages stream.
- Click Stop, observe status dot turns red.

- [ ] **Step 5: Commit final state**

```bash
git add -A
git commit -m "test(desktop): verify e2e scrape + app launch"
```
(Only if any verification artifacts changed; otherwise skip.)

---

## Self-Review Notes

- **Spec coverage**: config_io (Tasks 1-2), scraper gear (3), box loot (4), cache+slug (5), live fetch (6), proxy_runner (7), log_panel (8), gear_picker (9), box_loot_picker (10), config_editor (11), main_window+entry (12), e2e (13). All spec components covered.
- **Placeholder scan**: Two `# type: ignore[override]` and explicit verify-notes (PySide6 enum paths) are flagged in-place with concrete fallbacks, not "TBD".
- **Type consistency**: `selected_ids()` returns `list[int]` in both pickers (uses `selectedItems()` — returns QListWidgetItem list, `.data(UserRole)` yields int); `add_ids_to_selected_rule`/`add_ids_to_range` consume `list[int]`; `refresh_*` returns `list[dict[str,Any]]`; cache functions consistent. `SaveResult` used in config_io + main_window.
- **Pre-exec fixes applied**: (a) picker `selected_ids` switched from buggy `selectedIndexes()`+`item(i)` to `selectedItems()`; (b) log_panel `_trim` removed — replaced with built-in `setMaximumBlockCount` FIFO (no manual cursor/enum manipulation).
- **Known verification points**: PySide6 enum access paths (`Qt.ItemFlag.*`, `Qt.CheckState.*`, `QHeaderView.ResizeMode.*`), gear wiki static-HTML assumption (Task 13 step 2 gates this), box slug pattern (Task 13 step 3), `ProxyConfig.load` strictness on invalid `specific_queue_rules` (Task 2 step 4 note).
