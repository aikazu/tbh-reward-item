# TBH Scraper Hardening + Image Pipeline — Design Spec

**Date**: 2026-06-27
**Status**: Draft — pending user review
**Scope**: Phase 1 (scraper reliability) + Phase 2 (image acquisition)

## 1. Scope

### In scope (this spec)

1. Scraper reliability improvements: error categorization, exponential backoff with jitter, resume-on-startup via cache mtime check
2. New image acquisition stage: download images referenced in scraped JSON, resize to 256×256, encode as WebP q=70
3. New manifest file (`tbh_desktop/manifest.json`) tracking scrape + image stats
4. New CLI entry point: `python -m dev_tools.scrape_pipeline {scrape,bundle,all}` with `--resume` / `--max-cache-age` / `--concurrency` / `--dry-run` flags

### Out of scope (separate specs, later phases)

- PyInstaller spec for `tbh-desktop` binary
- Linux AppImage build
- Windows `.exe` build
- GitHub Actions matrix CI
- Runtime path resolution in bundled binary (`sys._MEIPASS` handling)
- CA certificate install wizard for first-run
- Auto-update mechanism for binary or data

## 2. Goals & non-goals

### Goals

- Maintainer can run `scrape_full.py all --resume` and get a complete, ready-to-bundle dataset
- Pipeline is idempotent: re-running with fresh caches is a no-op for unchanged data
- Per-item failures are isolated and don't abort the whole pipeline
- Output is reproducible: same wiki state produces same byte-identical JSON caches + WebP files
- All new code has unit test coverage ≥ 80%

### Non-goals

- Real-time data updates (no streaming, no webhooks)
- Multi-source data merging (wiki is single source of truth)
- CDN switching (wiki URLs only, no game-CDN capture)
- User-facing scraper (this is maintainer-only tooling)

## 3. Architecture

### Module layout

```
dev_tools/scrape_pipeline/          # NEW: maintainer-only, NOT bundled into binary
├── __init__.py
├── __main__.py                     # entry: python -m dev_tools.scrape_pipeline
├── cli.py                          # argparse + flow orchestration
├── scrape_stage.py                 # wraps existing tbh_desktop/scraper.py
├── image_stage.py                  # download + WebP convert + resize
├── errors.py                       # ScrapeError hierarchy + categorization
├── backoff.py                      # exp backoff + jitter helper
└── manifest.py                     # manifest.json IO

tbh_desktop/
├── scraper.py                      # MODIFIED: use new errors.py + backoff.py
├── gear_scraper_runner.py          # UNCHANGED (still used by GUI scrape button)
├── paths.py                        # MODIFIED: + IMAGES_DIR, MANIFEST_PATH
├── gear/                           # UNCHANGED (existing cache layout)
├── item/                           # UNCHANGED
├── box_loot_cache/                 # UNCHANGED
├── box_drop_map.json               # UNCHANGED
├── drops_index.json                # UNCHANGED
├── box_slug_cache.json             # UNCHANGED
├── images/                         # NEW: {item_id}.webp files
└── manifest.json                   # NEW: versioning + scrape metadata
```

### Design principle

- `dev_tools/` is **outside** the PyInstaller bundle path. The GUI binary does not include scraping code or its dependencies (Pillow is allowed since it's already pulled by PySide6).
- Existing scraper public API is preserved. `tbh_desktop.scraper.refresh_gear_full(...)` and friends keep their signatures. Reliability changes are internal.

## 4. Data layout

### Bundled directory tree (what `--add-data` will eventually include)

```
tbh_desktop/
├── manifest.json                   # NEW: top-level metadata
├── gear/{category}/{rarity}.json   # existing: gear picker cache
├── item/{family}/{rarity}.json     # existing: material picker cache
├── box_loot_cache/{box_id}.json    # existing: per-box loot
├── box_drop_map.json               # existing: reverse map
├── drops_index.json                # existing: drops index with timestamp
├── box_slug_cache.json             # existing: slug lookup
└── images/{item_id}.webp           # NEW: local image cache
```

### Filename scheme

- Images: `images/{item_id}.webp` — flat lookup by integer id. IDs are unique across gear (3-6xxxxx), material (1xxxxx), stage box families. Verified against existing `_extract_item_id` and ID-prefix comments in `scraper.py:230-237`.

### Manifest schema (`tbh_desktop/manifest.json`)

```json
{
  "schema_version": 1,
  "scrape_started_at": "2026-06-27T10:00:00",
  "scrape_completed_at": "2026-06-27T10:45:00",
  "scrape": {
    "combos_total": 65,
    "combos_done": 64,
    "combos_cached": 50,
    "combos_failed": 1,
    "items_total": 5760
  },
  "images": {
    "images_total": 5760,
    "downloaded": 5750,
    "skipped": 0,
    "failed": 10,
    "bytes_total": 157286400
  }
}
```

Atomic write: write to `.tmp`, then `Path.replace()`. Schema version bump is a hard cut — readers must handle mismatch.

## 5. CLI surface

```
python -m dev_tools.scrape_pipeline all --resume
python -m dev_tools.scrape_pipeline scrape --max-cache-age 7
python -m dev_tools.scrape_pipeline bundle --concurrency 4
python -m dev_tools.scrape_pipeline all --dry-run
```

### Flags

| Flag | Default | Applies to | Meaning |
|------|---------|-----------|---------|
| `--stage {scrape,bundle,all}` | `all` | always | Which stage(s) to run |
| `--resume` | off | scrape | Skip combos whose cache file is fresher than `--max-cache-age` |
| `--max-cache-age N` | 7 | scrape | Max age in days for cache freshness (used with `--resume`) |
| `--workers N` | 4 | bundle | ThreadPoolExecutor worker count for image stage. Same flag used by scrape stage when re-exported for detail enrichment (forwarded as `max_workers` to existing scraper fns). |
| `--dry-run` | off | always | Print what would happen without writing files |

### Exit codes

- `0`: pipeline finished successfully. Soft per-item failures (recorded in manifest `failed` counts) do not raise the exit code — partial success is still success.
- `1`: hard failure (dependency missing, schema error, manifest write failed, scrape stage produced 0 items AND no cache fallback available, bundle stage produced 0 successful images AND at least one failure)
- `2`: reserved for future use (not used in v1)

## 6. Data flow

### Stage 1 — Scrape

```
cli.main()
  → scrape_stage.run_scrape(args)
    → for combo in GEAR_CATEGORIES × LEGENDARY_UP_GRADES:
        if --resume and cache_fresh(combo_cache, args.max_cache_age):
            combos_cached++; continue
        try:
            scraper.refresh_gear_full(out_dir=...)
            combos_done++
        except ScrapeError as e:
            log.warning("combo %s failed: %s", combo, e)
            combos_failed++
            # fall back to existing cache if available
    → for family in FAMILY_ORDER:
        for rarity in RARITY_ORDER:
            ... (similar pattern)
    → fetch_drops_index(force=--no-cache)
    → return {combos_total, combos_done, combos_cached, combos_failed, items_total, duration_s}
```

### Stage 2 — Bundle images

```
image_stage.run_bundle(args)
  → collect (id, image_url) tuples from JSON caches:
      - walk tbh_desktop/gear/**/*.json
      - walk tbh_desktop/item/**/*.json
      - walk tbh_desktop/box_loot_cache/*.json
    → dedup by id (first URL wins)
  → with ThreadPoolExecutor(args.concurrency) as ex:
      futures = [ex.submit(_process_one_image, id, url) for id, url in items]
      for fut in as_completed(futures):
          try:
              result = fut.result()
              if result == "skipped": skipped++
              elif result == "downloaded": downloaded++; bytes_total += size
          except ImageError as e:
              log.warning("image %s failed: %s", id, e)
              failed++
  → return {images_total, downloaded, skipped, failed, bytes_total, duration_s}

def _process_one_image(item_id, url):
    dest = tbh_desktop/images/{item_id}.webp
    if dest.exists(): return "skipped"
    raw = _download(url)               # raises ImageError on 404/network
    img = _decode(raw)                  # raises ImageError on corrupt
    resized = img.resize((256, 256), Image.LANCZOS)
    resized.save(dest, "WEBP", quality=70, method=6)
    return "downloaded"
```

### Final write

```
manifest.write_manifest({**scrape_stats, **image_stats, "scrape_completed_at": now})
```

## 7. Components detail

### `dev_tools/scrape_pipeline/cli.py`

Pure orchestration. No business logic. Imports the three stage modules + manifest, calls them in order based on `--stage`. Returns exit code.

### `dev_tools/scrape_pipeline/scrape_stage.py`

Wraps `tbh_desktop.scraper.refresh_gear_full`, `refresh_material_details`, `fetch_drops_index`. Adds:
- Cache freshness check using `Path.stat().st_mtime` vs current time minus `--max-cache-age` days
- Catches all `ScrapeError` per combo, logs, continues
- Returns stats dict consumed by manifest

### `dev_tools/scrape_pipeline/image_stage.py`

Two-phase: collect then process.
- **Collect**: `pathlib.Path.glob` over JSON caches, `json.loads`, extract `image` field, dedup by id into `dict[int, str]`
- **Process**: ThreadPoolExecutor with N workers. Per item: skip if exists, else download → decode → resize → save

### `dev_tools/scrape_pipeline/errors.py`

```python
class ScrapeError(Exception): pass
class NetworkError(ScrapeError): pass
class SchemaError(ScrapeError): pass
class RateLimitError(ScrapeError): pass
class ImageError(ScrapeError): pass
class ImageMissingError(ImageError): pass      # HTTP 404
class DependencyError(ScrapeError): pass      # Pillow missing etc.

def categorize(exc: Exception) -> ScrapeError:
    """Map a raw exception to its ScrapeError category."""
    if isinstance(exc, requests.exceptions.ConnectionError): return NetworkError(exc)
    if isinstance(exc, requests.exceptions.Timeout): return NetworkError(exc)
    if isinstance(exc, json.JSONDecodeError): return SchemaError(exc)
    if isinstance(exc, lxml.etree.XMLSyntaxError): return SchemaError(exc)
    if isinstance(exc, requests.exceptions.HTTPError):
        if exc.response.status_code == 429: return RateLimitError(exc)
        if exc.response.status_code == 404: return ImageMissingError(exc)
        if 500 <= exc.response.status_code < 600: return NetworkError(exc)
    return ScrapeError(exc)
```

### `dev_tools/scrape_pipeline/backoff.py`

```python
def backoff(attempt: int, base: float = 0.4, cap: float = 30.0, rng: random.Random | None = None) -> float:
    """Exponential backoff with jitter. attempt is 0-indexed."""
    rng = rng or random
    delay = min(cap, base * (2 ** attempt))
    jitter = rng.uniform(0, delay * 0.25)
    return delay + jitter
```

Inject `rng` for deterministic tests.

### `dev_tools/scrape_pipeline/manifest.py`

```python
SCHEMA_VERSION = 1

def write_manifest(stats: dict, path: Path) -> None:
    payload = {"schema_version": SCHEMA_VERSION, **stats, "scrape_completed_at": now_iso()}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    tmp.replace(path)

def read_manifest(path: Path) -> dict:
    # return {} on missing or unparseable
    # raise on schema_version mismatch
```

### `tbh_desktop/scraper.py` modifications

Replace existing inline `_time.sleep(0.4 * (2 ** attempt))` calls with `backoff.`<N>` from new module. Wrap caught exceptions via `errors.categorize(exc)`. Public API signatures preserved. Diff expected: ~50 lines changed across `_scrape_one_combo`, `_enrich_items_with_stats`, `_fetch_material_detail_wiki`.

### `tbh_desktop/paths.py` additions

```python
IMAGES_DIR = DESKTOP_DIR / "images"
MANIFEST_PATH = DESKTOP_DIR / "manifest.json"
```

No existing constants changed.

## 8. Error handling

### Error → behavior matrix

| Error | Category | Retry? | Behavior |
|-------|----------|--------|----------|
| `requests.ConnectionError` | NetworkError | 3x | exp backoff + jitter, then re-raise |
| `requests.Timeout` | NetworkError | 3x | exp backoff + jitter, then re-raise |
| HTTP 5xx | NetworkError | 3x | exp backoff + jitter, then re-raise |
| HTTP 429 | RateLimitError | 1x | 60s sleep + retry once, then re-raise |
| HTTP 404 (image) | ImageMissingError | No | Skip image, log INFO |
| `json.JSONDecodeError` | SchemaError | No | Fail fast, log ERROR, re-raise |
| `lxml.etree.XMLSyntaxError` | SchemaError | No | Fail fast, log ERROR, re-raise |
| Missing required field | SchemaError | No | Fail fast, log ERROR, re-raise |
| Pillow ImportError | DependencyError | No | Fail at CLI startup, log ERROR, exit 1 |
| WebP save fail | ImageError | No | Skip image, log WARNING |

### Logging policy

- Module logger: `logging.getLogger("dev_tools.scrape_pipeline")`
- Format: `%(asctime)s %(levelname)s %(name)s: %(message)s` (project default)
- No `print()` in pipeline code
- Levels:
  - **INFO**: stage start/end, per-combo done, per-image done
  - **WARNING**: per-item retries (with attempt count), fallbacks to cache, image failures
  - **ERROR**: hard fails (schema error, dependency missing)

## 9. Testing

### Unit tests (`tests/dev_tools/test_scrape_pipeline/`)

- `test_backoff.py` — table-driven: exp growth, cap respected, jitter bounded `[0, 0.25 * delay]`, deterministic with injected `random.Random(42)`
- `test_categorize.py` — table-driven: each exception type → expected category
- `test_manifest.py` — round-trip write/read, atomic-write (kill mid-write simulation), schema version mismatch raises, missing file returns `{}`
- `test_cache_fresh.py` — fresh/stale boundary, missing file returns False, mtime precision (1-second granularity)
- `test_image_stage_collect.py` — walks fixture JSON trees, dedup behavior, missing image field handling
- `test_image_stage_process.py` — `_process_one_image` with mocked `requests.get` + mocked `Pillow.Image`: success, HTTP 404, network error, corrupt bytes
- `test_scrape_stage.py` — `run_scrape` with mocked scraper fns: all success, partial fail + cache fallback, all fail (no cache)
- `test_cli.py` — argparse surface, `--stage`, `--resume`, `--dry-run` (dry-run doesn't write files)

### Integration test (slow, `@pytest.mark.integration`)

- `test_pipeline_smoke.py` — real Pillow, 5 sample items, mocked HTTP via `responses` lib
- Asserts: manifest written, image files exist, manifest counts match actual files

### Coverage target

- ≥ 80% line coverage on `dev_tools/scrape_pipeline/` (new code)
- `errors.categorize` table-driven test covers every category
- Existing `tbh_desktop/scraper.py` modifications exercised through `categorize` + `backoff` tests; no need for separate scraper tests

### Fixtures (`tests/dev_tools/conftest.py`)

- `tmp_path` (pytest built-in)
- `fake_image_bytes` — Pillow-generated 512×512 PNG bytes (8KB)
- `fake_corrupt_bytes` — invalid bytes that fail Pillow decode
- `sample_json_tree` — temp dir with 3 gear + 2 material + 1 box JSON files
- `mock_wiki_server` — `responses` mock returning predictable image bytes

### Existing tests

- Unchanged. No regression risk on `tbh_desktop/scraper.py` since public API preserved.

## 10. Dependencies

### New direct deps

- `Pillow>=10.0` — image decode + resize + WebP encode. PySide6 does NOT bundle Pillow; this is a new explicit dev dep. Pin `>=10.0` because WebP encoding quality/options stabilized there.

### No new transitive deps

- `requests` — already in project
- `pathlib`, `json`, `logging`, `argparse`, `concurrent.futures` — stdlib

## 11. Open questions / deferred decisions

- **Manifest versioning policy**: hard cut on schema break. Bump `SCHEMA_VERSION`, reader raises on mismatch.
- **WebP fallback**: not in v1. If a user reports display issues, address in a follow-up (likely add PNG mirror or runtime conversion). YAGNI for now.
- **Test execution speed**: integration test marked slow; CI can skip with `-m "not integration"` if needed.

## 12. Migration / rollout

### Phase 1 rollout (this spec)

1. Land `dev_tools/scrape_pipeline/` modules + tests
2. Land `tbh_desktop/scraper.py` reliability patch + tests
3. Land `tbh_desktop/paths.py` additions
4. Run `scrape_full.py all --resume` once to populate `tbh_desktop/images/` + `manifest.json`
5. Commit the populated `tbh_desktop/` data subtree to repo (so binary can be built without re-scraping)

### Future phases (separate specs)

- Phase 3: PyInstaller spec + `sys._MEIPASS` runtime resolution
- Phase 4: GitHub Actions matrix (Linux AppImage + Windows .exe)
- Phase 5: Data update mechanism (manual release vs auto-patch)
