# Desktop Flow Gaps Fix — Spec

Audited via graphify graph + live wiki trace (2026-06-26). Fixes 3 critical gaps + new gear picker requirements.

## G2 — Port desync (prompt save before start)

**Problem:** `MainWindow._save` writes `listen_port` to `src/config.json`. `Start` → `ProxyRunner.start()` spawns `run_proxy.py` which reads `config.json`. User edits port in UI without Save → proxy runs on old port, no warning.

**Fix (user chose: prompt Save dulu):**
- `main_window.py`: replace `btn_start.clicked.connect(self.runner.start)` with `self._start`.
- `_start()`:
  - Read current config `listen_port` via `config_io.load_config(CONFIG_PATH).get("listen_port", 8877)`.
  - If `self._parse_port() != saved_port`: `QMessageBox.question(self, "Unsaved port", "Port changed. Save config first?", Yes|No, Yes)`. Yes → call `self._save()` then `self.runner.start()`. No → abort (no start).
  - If port unchanged: `self.runner.start()` directly.

**TDD:** `tests/test_main_window.py` (new file, use pytest-qt qtbot) — test `_start` prompts when port differs, starts directly when same, saves+starts on Yes.

## G3 — Gear scraper (playwright, per kategori×grade)

**Problem:** `scraper.refresh_gear` uses `requests.get(GEAR_URL)` → only 60 SSR cards (mixed rarity). No way to click "LOAD MORE" (client-side). User needs full Legendary+ obtainable (200) split by category (Weapon/Off-hand/Armor/Accessory) × grade.

**Live findings:**
- Wiki `/gear` SSR = 60 cards. Raw HTML 7.7MB has 60 cards, full dataset NOT embedded.
- "LOAD MORE (N left)" button appends +60 per click, until exhausted.
- Filter row: Rarity chips (Common/Uncommon/Rare/Legendary/Immortal/Arcana/Beyond/Celestial/Divine/Cosmic), Type chips (Weapon/Off-hand/Armor/Accessory), Level slider (Min1 Max100), Find (Obtainable only checkbox).
- Grade hierarchy: Legendary < Immortal < Arcana < Beyond < Celestial < Divine < Cosmic. "Legendary ke atas" = all 7.
- Counts: Legendary 760 total (~200 obtainable), Immortal 760, Arcana 640, Beyond 560, Celestial 480, Divine 400, Cosmic 320.

**Fix (user chose: initial scrape button, data stored local, per kategori×grade):**
- `scraper.py`: new `refresh_gear_full(out_dir: Path, categories: list[str], grades: list[str])` using playwright.
  - Launch headless browser (user-chosen engine via playwright — chrome/chromium/camoufox/cloakbrowser).
  - For each (category, grade): navigate `/gear`, click Type chip = category, click Rarity chip = grade, check "Obtainable only", click "LOAD MORE" until button gone/counter 0, parse all `a.entity-card` (not is-deleted), extract {id, name, rarity, type, level}.
  - Write cache per kategori×grade: `out_dir/gear_{category}_{grade}.json`.
  - On error: fall back to existing cache file if present.
- Keep `parse_gear_page(html)` for parsing (used by playwright via page.content()).
- `requirements-desktop.txt`: add `playwright>=1.40`.
- Install note: user runs `playwright install chromium` (or chosen engine) separately.

**Cache structure:** `tbh_desktop/gear_cache/` (new dir, gitignored) with files `gear_weapon_legendary.json`, `gear_offhand_immortal.json`, etc.

**TDD:** `tests/test_scraper.py` — mock playwright page object, verify parse loop + cache write per file. Test fallback to cache on error.

## G3 — GearPicker UI (grade + level + kategori)

**Problem:** Current `GearPicker` shows flat list from single `gear_cache.json`. No grade/level/category filter.

**Fix:**
- `gear_picker.py`: `GearPicker.__init__(cache_dir: Path, parent)` instead of flat items list.
  - Dropdowns: Category (Weapon/Off-hand/Armor/Accessory/All), Grade (Legendary/Immortal/Arcana/Beyond/Celestial/Divine/Cosmic/All), Level range (min/max QSpinBox 1-100).
  - Build list from cache files matching selected filters. Recompute on filter change.
  - Multi-select list, search box, OK returns selected_ids.
- `main_window.py`:
  - `_refresh_gear` → call `scraper.refresh_gear_full(GEAR_CACHE_DIR, ALL_CATEGORIES, LEGENDARY_UP_GRADES)`. Show progress log per kategori×grade.
  - New "Scrape gear" button (replaces or augments "Refresh gear") triggers full scrape (slow, playwright). "Refresh" name → "Scrape gear".
  - `_pick_gear` → open `GearPicker(GEAR_CACHE_DIR, self)`, no cache check needed (reads local files).
- `paths.py`: `GEAR_CACHE = DESKTOP_DIR / "gear_cache.json"` → `GEAR_CACHE_DIR = DESKTOP_DIR / "gear_cache"`.

**TDD:** `tests/test_gear_picker.py` (new) — filter logic, list build from cache dir mock.

## G4 — Slug lookup via wiki items page

**Problem:** `resolve_box_slug(name)` naive (`lower().replace(" ","-")`). Box URL `/en/items/chests/{id}-{slug}/` needs exact slug — wrong slug → 404. e.g. "White box" heuristic may not match wiki slug.

**Live findings:**
- `/en/items` has "Stage chests" table, SSR full 59 chests. Each `<tr data-id="910801" data-name="...">` with `<a href="/en/items/chests/910801-normal-monster-box-lv80/">`.
- Search box filters rows by `data-search` (contains id + name).

**Fix (user chose: lookup slug via wiki items page):**
- `scraper.py`: new `resolve_box_id_slug(box_id: int) -> str | None`.
  - `requests.get("https://taskbarhero.org/en/items")`, parse "Stage chests" table, find `<tr data-id="{box_id}">`, extract slug from `<a href>` (regex `/chests/{id}-(?P<slug>[\w-]+)/`).
  - Cache map `box_id -> slug` in `tbh_desktop/box_slug_cache.json` (gitignored) to avoid refetch.
- `refresh_box_loot(cache_dir, box_id)`: drop `slug` param, internally call `resolve_box_id_slug(box_id)`. Fallback to `resolve_box_slug(name)` heuristic only if lookup fails.
- `main_window._pick_box_loot`: drop slug derivation from name; call `scraper.refresh_box_loot(BOX_LOOT_CACHE_DIR, box_id)`.

**TDD:** `tests/test_scraper.py` — `test_resolve_box_id_slug_from_items_page` (mock requests.get with fixture html), cache hit, not-found returns None.

## Execution order

1. G4 (slug lookup) — isolated, scraper.py + test.
2. G2 (port prompt) — main_window.py + new test_main_window.py.
3. G3 scraper (playwright) — scraper.py rewrite + requirements + test.
4. G3 picker UI — gear_picker.py + main_window.py wiring + paths.py + test_gear_picker.py.
5. Full test suite run + verify.

## Critical files

- `tbh_desktop/scraper.py` — G3, G4
- `tbh_desktop/paths.py` — G3 cache dir
- `tbh_desktop/ui/main_window.py` — G2, G3 wiring
- `tbh_desktop/ui/gear_picker.py` — G3 UI
- `tests/test_scraper.py` — G3, G4 tests
- `tests/test_main_window.py` — G2 test (new)
- `tests/test_gear_picker.py` — G3 UI test (new)
- `requirements-desktop.txt` — playwright
- `.gitignore` — new cache dirs

## Verification

- `cd . && .venv/bin/python -m pytest tests/ -v` — all green.
- Manual: run `python -m tbh_desktop.main`, test port prompt, scrape gear (needs playwright install), pick gear w/ filters, pick box loot (slug lookup).
