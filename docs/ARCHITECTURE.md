# TBH Reward Proxy — Architecture Documentation

**Last updated**: 2026-06-29
**Purpose**: Comprehensive reference so future sessions never guess about data sources, file structure, or component interactions.

---

## 1. Overview

Man-in-the-middle proxy that rewrites `rewardItemId` in **TaskBarHero** (Steam AppId 3678970, Windows Unity idle RPG) backend responses. mitmproxy addon + optional PySide6 desktop GUI.

**Stack**: Python 3.10+, mitmproxy, PySide6, requests/beautifulsoup4, CloakBrowser/Playwright (gear scrape), pytest.

**How it works (high-level)**:
1. mitmproxy intercepts HTTPS traffic between the game client and `api.thebackend.io`.
2. When the client opens boxes (`processBoxV2`), the server returns reward items.
3. The addon rewrites `rewardItemId` in the `boxes[]` array of the response to items the user configured.
4. The client displays the rewritten items in the box preview UI.
5. **CRITICAL LIMITATION**: The addon only rewrites the cosmetic `rewardItemId` field. The real inventory items (`added[]` array in the same response) are NOT modified. This causes desync when the user tries to craft/synthesize with items they see in the box preview but don't actually have.

---

## 2. Directory Structure

```
TBH/
├── src/                                # mitmproxy addon (core proxy logic)
│   ├── tbh_reward_hook.py              # TBHRewardHook + RewardRewriter + TamperDetector + PendingTxRewriter
│   ├── tbh_proxy_config.py             # ProxyConfig / QueueRule / RangeRule data classes (pure data, no side effects)
│   ├── run_proxy.py                    # CLI launcher (finds mitmdump, handles --mode local)
│   ├── config_setup.py                 # ensure_config() — copies config.default.json → config.json on first run
│   ├── config.default.json             # seed template (committed)
│   └── config.json                     # generated on first run, hot-reloaded (NOT committed, gitignored)
├── tbh_desktop/                        # optional PySide6 GUI
│   ├── main.py                         # entry: QApplication + theme + MainWindow + SIGINT handler
│   ├── paths.py                        # path constants (re-exports from src/config_setup.py)
│   ├── config_io.py                    # load/save config.json (validate → atomic temp+rename → re-validate → restore .bak)
│   ├── proxy_runner.py                 # subprocess + process group SIGTERM/SIGKILL + stdout→Qt signal stream
│   ├── scraper.py                      # gear scrape (CloakBrowser) + box loot scrape (requests/bs4)
│   ├── gear_scraper_runner.py          # QObject thread wrapper around scraper.refresh_gear_full
│   ├── gear_filters.py                 # filtering helpers for gear data
│   ├── gear/                           # gear cache (scraped from taskbarhero.wiki via CloakBrowser)
│   │   ├── index.json                  # category→grade index
│   │   ├── weapon/{legendary,immortal,arcana,beyond,celestial,divine,cosmic}.json
│   │   ├── armor/{...}.json
│   │   ├── offhand/{...}.json
│   │   └── accessory/{...}.json
│   ├── box_loot_cache/                 # box loot tables (scraped from taskbarhero.wiki via requests/bs4)
│   │   └── {boxId}.json                # e.g. 910801.json, 920801.json
│   └── ui/
│       ├── main_window.py              # 4-zone layout + _ThreadLogBridge (cross-thread Qt signal bridge)
│       ├── left_rail.py                # 60px vertical Action icon rail
│       ├── config_editor.py            # wraps RuleListView + _RangeForm + _ProxyModeForm
│       ├── rule_list.py / rule_card.py # card-based rule list
│       ├── item_browser.py             # 6-tab right panel + FilterContext
│       ├── item_card.py                # rarity-bordered card widget
│       ├── gear_picker.py              # GearView (loads from tbh_desktop/gear/{cat}/{grade}.json)
│       ├── box_picker.py               # BoxView
│       ├── box_loot_picker.py          # BoxLootView
│       ├── active_target.py            # RuleTarget | RangeTarget union
│       ├── log_panel.py                # bottom dock, monospace
│       ├── theme.py                    # Catppuccin Mocha + rarity palette + ornament
│       ├── catalog_popup.py            # merge gear cache + drops index into flat catalog
│       ├── rule_detail_panel.py        # rule detail sidebar
│       └── image_cache.py              # async image loading/caching
├── scripts/                            # run_proxy, install_requirements, self_test, install_cert, remove_cert, launch_desktop
├── windows/                            # Windows equivalents + install_cert.bat
├── tests/                              # test_reward_rewriter.py, test_config_io.py, test_scraper.py, etc.
├── docs/                               # analysis docs + specs + plans (this file lives here)
│   ├── analysis/
│   │   ├── tbh-network-forensics.md    # network forensics (§1-§12, endpoints, DynamoDB, validation)
│   │   ├── strategy-b-tid-rewrite.md   # Strategy B implementation plan + status
│   │   └── capture-20260628-193055.md  # capture session analysis
│   └── ARCHITECTURE.md                 # THIS FILE
├── captures/                           # mitmproxy captures + derived data (gitignored except analysis)
│   ├── cap-*.flow                      # mitmproxy binary flow capture files
│   ├── dump-*.json                     # parsed/extracted JSON from captures
│   ├── item-catalog.json               # item catalog from game localization (511 items: materials, gems, consumables)
│   ├── suffix-pools.json               # suffix-grouped item pools (derived from item-catalog.json)
│   ├── real-reward-pool.json           # real reward pool from captures + catalog merge
│   └── tamper-events.jsonl             # TamperDetector log output (JSONL, one record per mismatch)
├── requirements.txt                    # mitmproxy
├── requirements-desktop.txt            # PySide6, requests, bs4, lxml, pytest-qt, playwright, cloakbrowser, Pillow
├── pytest.ini                          # -m "not integration" -p no:pytestqt
├── conftest.py                         # sys.path + _NoopQtBot stub + gui marker
├── pyrightconfig.json                  # pyright type-check config
├── CLAUDE.md                           # project context for AI agents
└── README.md / README.id.md            # user-facing docs (EN + ID)
```

---

## 3. Data Sources (CRITICAL — read this before assuming where data comes from)

### 3.1 `captures/item-catalog.json` — Game Localization Catalog

- **What**: 511 items extracted from the game's English localization bundle.
- **Where from**: Scraped/parsed from game client data (not from network captures).
- **Contains**: Materials (Copper Nugget, Leather, Iron Ingot), Gems/Crystals (Minor Ruby, Minor Topaz), Consumables, Soulstones, Anniversary Coins. **Does NOT contain gear/equipment.**
- **Structure**:
```json
{
  "meta": {"total_items": 511, ...},
  "categories": {"Gem / Crystal": [...], "Material (mid)": [...], ...},
  "catalog": [
    {
      "itemId": 110001,
      "itemKey": "110001",
      "name": "Minor Ruby",
      "localizationKey": "ItemName_110001",
      "numericId": 60714139914,
      "suffix": "001",
      "prefix": "110",
      "category": "Gem / Crystal",
      "description": "Common basic decoration"
    },
    ...
  ]
}
```
- **Use case**: Lookup for material/gem item names. Used by suffix-pools.json derivation.

### 3.2 `tbh_desktop/gear/{cat}/{grade}.json` — Gear Cache (SEPARATE FROM item-catalog.json!)

- **What**: Equipment/gear items organized by category × rarity grade.
- **Where from**: Scraped from `taskbarhero.wiki` using CloakBrowser (stealth Chromium, 58 C++ patches). Falls back to stock Playwright if CloakBrowser unavailable.
- **Contains**: Weapons (Sword, Bow, Staff, Scepter, Crossbow), Armor (Helmet, Chest, Gloves, Boots), Off-hand (Shield, Arrow, Orb), Accessories (Amulet, Ring). Grades: Legendary, Immortal, Arcana, Beyond, Celestial, Divine, Cosmic. **Lower grades (Common through Legendary-1) are NOT scraped.**
- **Categories**: `weapon/`, `armor/`, `offhand/`, `accessory/`
- **Grades per category**: `legendary.json`, `immortal.json`, `arcana.json`, `beyond.json`, `celestial.json`, `divine.json`, `cosmic.json`
- **Structure** (e.g. `armor/arcana.json`):
```json
[
  {
    "id": 505041,
    "name": "Knight Helmet",
    "rarity": "Arcana",
    "type": "Helmet",
    "level": "Lv15",
    "stat": "HP +34",
    "image": "https://taskbarhero.wiki/game/..."
  },
  ...
]
```
- **Use case**: This is what the **GearPicker** in the desktop GUI loads. When the user picks gear from the GUI, the IDs come from THESE files, not from `item-catalog.json`.
- **⚠️ DO NOT confuse with `captures/item-catalog.json`**. They are different data sources with different contents. `item-catalog.json` has materials/gems (511 items). `gear/` has equipment (varies per grade, e.g. 28 armor/arcana entries). An item like `505041` (Arcana Knight Helmet) exists in `gear/armor/arcana.json` but NOT in `item-catalog.json`.

### 3.3 `captures/suffix-pools.json` — Suffix-Grouped Pools

- **What**: Items from `item-catalog.json` grouped by `(category, tier)` and `(tier)` for suffix-matching.
- **Where from**: Derived from `item-catalog.json` (not independently scraped).
- **Use case**: Strategy A suffix-aware picker — find replacement items with matching suffix.

### 3.4 `captures/real-reward-pool.json` — Real Reward Pool

- **What**: Merged dataset from server captures + tamper reports + base catalog.
- **Where from**: Captures + catalog merge.
- **Use case**: Reference for what the server actually drops.

### 3.5 `tbh_desktop/box_loot_cache/{boxId}.json` — Box Loot Tables

- **What**: Loot table for each box type (what items each box can drop).
- **Where from**: Scraped from `taskbarhero.wiki` using requests + beautifulsoup4.
- **Files**: e.g. `910801.json` (Normal Box), `920801.json` (Stage Boss Box), `930901.json` (Act Boss Box), plus variant IDs like `910151.json`.
- **Use case**: BoxPicker / BoxLootPicker in the desktop GUI.

### 3.6 `captures/tamper-events.jsonl` — Tamper Detector Log

- **What**: Structured log of `TamperedItemIdDetected` reports sent by the game client.
- **Where from**: Written by `TamperDetector` in `src/tbh_reward_hook.py`. The detector reads the **REQUEST body** of POST `/data/gameLog/v2/TemperedItem/90` (the server replies 204 No Content with empty body — the mismatch data is in the request, not the response).
- **Structure** (one JSON object per line):
```json
{
  "ts": "2026-06-29T15:36:08+0700",
  "itemKey": "2103",
  "original_id": 315041,
  "original_rarity": "Arcana",
  "original_tier": "041",
  "used_id": 140004,
  "used_rarity": "Common",
  "used_tier": "004",
  "last3_preserved": false
}
```

### 3.7 `captures/cap-*.flow` — Mitmproxy Capture Files

- **What**: Binary mitmproxy flow capture files. Contains all HTTP requests/responses in a session.
- **How to read**: Use `from mitmproxy.io import FlowReader` to iterate flows programmatically.

### 3.8 `captures/dump-*.json` — Parsed Capture Dumps

- **What**: JSON extraction from capture flows, structured by query type.
- **Use case**: Offline analysis without needing mitmproxy installed.

### Summary Table

| Source | Type | Contains | Used By |
|--------|------|----------|---------|
| `captures/item-catalog.json` | JSON | 511 material/gem/consumable items | suffix-pools derivation, name lookup |
| `tbh_desktop/gear/{cat}/{grade}.json` | JSON | Equipment by category×grade | GearPicker (desktop GUI) |
| `captures/suffix-pools.json` | JSON | Suffix-grouped pools (from catalog) | Strategy A suffix picker |
| `captures/real-reward-pool.json` | JSON | Merged reward pool | Reference |
| `tbh_desktop/box_loot_cache/{boxId}.json` | JSON | Box loot tables | BoxPicker (desktop GUI) |
| `captures/tamper-events.jsonl` | JSONL | Tamper mismatch reports | TamperDetector output |
| `captures/cap-*.flow` | Binary | Full HTTP session capture | Forensic analysis |

**⚠️ KEY LESSON**: `item-catalog.json` ≠ gear cache. If an item ID is not found in `item-catalog.json`, check `tbh_desktop/gear/` before claiming "NOT IN CATALOG". Gear items (suffix 041, 031, 051, etc.) are only in the gear cache.

---

## 4. Proxy Addon Pipeline (`src/tbh_reward_hook.py`)

### 4.1 `TBHRewardHook.response(flow)` — Step by Step

```
response(flow) called by mitmproxy
│
├── 1. _reload_if_changed() — check config.json mtime, hot-reload if changed
│
├── 2. tamper_detector.maybe_log(flow) — PASSIVE: read TemperedItem REQUEST body,
│       parse mismatches, append to tamper-events.jsonl. Never modifies traffic.
│       Runs BEFORE URL/method filters (endpoint is different from processBoxV2).
│
├── 3. if config.rewrite_pending_tx:
│       pending_tx_rewriter.maybe_rewrite(flow) — Strategy B: rewrite
│       pendingTx.gid/.tid in SteamItemInfo/mine GET responses.
│       Runs BEFORE only_post/url_contains filters (SteamItemInfo is GET,
│       different endpoint than processBoxV2).
│
├── 4. Filter: only_post → if POST-only config and method != POST, return
├── 5. Filter: url_contains → if URL doesn't contain any marker, return
├── 6. Read response body
├── 7. Filter: require_boxes_marker → if "boxes" not in body, return
│
├── 8. rewriter.rewrite(body) — RewardRewriter: regex find "itemId":<n>
│       then "rewardItemId":<m>, replace with cycled replacement from config
│
├── 9. if modified_count > 0:
│       response.set_text(result.body)
│       for each detail:
│           log replacement
│           if config.rewrite_pending_tx:
│               pending_tx_rewriter.record_rewrite(old_rid, new_rid)
│       log total replacements
```

### 4.2 RewardRewriter — Regex Engine

- **Regex patterns** (`src/tbh_reward_hook.py:39-40`):
  - `ITEM_FIELD_RE`: matches `"itemId":<n>` (with optional backslash escaping for mitmproxy bodies)
  - `REWARD_FIELD_RE`: matches `"rewardItemId":<m>`
- **Rewrite logic** (`RewardRewriter.rewrite()`):
  1. For each `itemId` match, look up replacement via `_pick_replacement()`
  2. Search forward from itemId match for the nearest `rewardItemId`
  3. Replace the rewardItemId value with the cycled replacement
  4. Track `ReplacementDetail` (rule_name, item_id, old_rid, new_rid)
- **Priority**: Specific queue rules (exact itemId match) first, then range rule (itemId in [min, max]).
- **Cycling**: Each rule keeps its own index (`_queue_indexes` dict for specific, `_range_index` for range). Index increments per match, wraps modulo list length.
- **No match → pass-through**: If no rule matches an itemId, the response is untouched.

### 4.3 TamperDetector — Passive Mismatch Logger

- **Endpoint**: POST `/data/gameLog/v2/TemperedItem/90`
- **⚠️ CRITICAL**: Reads the **REQUEST body**, NOT the response. The server replies 204 No Content (empty body). The mismatch data (`{"data":{"mismatches":["<itemKey>:<orig>-><used>", ...]}}`) is sent BY the client TO the server.
- **Mismatch format**: `<itemKey>:<original_rewardItemId>-><used_rewardItemId>`
  - `original` = what the server actually minted (real rewardItemId)
  - `used` = what the client has cached (our rewritten rewardItemId)
- **Parsing**: `_parse_mismatch()` extracts itemKey, orig_id, used_id, decodes rarity (3rd digit) and tier (last 3 digits), checks if last3 preserved.
- **Output**: Appends to `captures/tamper-events.jsonl`, one JSON record per line.
- **Never modifies traffic** — pure passive monitor.

### 4.4 PendingTxRewriter (Strategy B) — gid/tid Rewrite

- **Purpose**: Rewrite `pendingTx.gid` and `pendingTx.tid` in `SteamItemInfo/mine` GET responses to match the rewritten `rewardItemId`, so the client validator sees consistent values.
- **Mapping**: `gid == rewardItemId`, `tid == gid * 1000 + 900` (offset verified from capture, `TID_OFFSET = 900`).
- **Session rewrite map**: `{original_rewardItemId: new_rewardItemId}`, populated by `record_rewrite()` called from `TBHRewardHook.response()` after each successful RewardRewriter run.
- **Regex approach**: `_GID_RE` and `_TID_RE` match DynamoDB format `"gid":{"N":"321111"}` and `"tid":{"N":"321111900"}`. Uses `\\?` escaping to handle both plain and escaped JSON.
- **Cross-entry bleed prevention**: For each gid match, searches for tid only within the slice up to the next gid match.
- **Config flag**: `rewrite_pending_tx` (default `false`, opt-in).
- **⚠️ Known limitation**: `pendingTx.L` may be empty `[]` by the time `SteamItemInfo/mine` is fetched — entries already consumed. In this case, nothing to rewrite.

### 4.5 Hot Reload

- **mtime-based**: `_reload_if_changed()` checks `config.json` mtime (nanosecond precision) on every `response()` call.
- **If mtime changed**: Reload config, rebuild `RewardRewriter`, log new state.
- **If config invalid**: Keep previous config, log `"kept previous config (config.json invalid)"`. Bad edit never breaks interception.
- **SIGHUP**: `_on_sighup()` sets mtime=0 to force re-check. Manual reload: `pkill -HUP -f mitmdump`.

### 4.6 Config Fallback

- `_safe_load_config()`: Wraps `ProxyConfig.load()` in try/except. Returns `None` on failure.
- `_empty_config()`: Returns a valid `ProxyConfig` with no rules (pass-through) if load fails.

---

## 5. Config System

### 5.1 Data Classes (`src/tbh_proxy_config.py`)

```python
class QueueRule:        # __slots__: enabled, name, item_id, replacement_reward_item_ids
class RangeRule:        # __slots__: enabled, name, match_min_item_id, match_max_item_id, replacement_reward_item_ids
class ProxyConfig:      # __slots__: listen_port, only_post, require_boxes_marker,
                        #           url_contains, specific_queue_rules, range_replacement,
                        #           rewrite_pending_tx
```

- All use `__slots__` for memory efficiency.
- `ProxyConfig.load(path)`: Static method, reads JSON, handles both camelCase and PascalCase keys via `_pick()`.
- `_as_int_list()`, `_as_str_tuple()`: Coerce various JSON types to typed Python collections.
- `rewrite_pending_tx`: Added for Strategy B, defaults to `False`.

### 5.2 Config File Lifecycle

- **`config.default.json`**: Seed template, committed to git. Contains comments (`_comment_*` keys) explaining each field.
- **`config.json`**: Generated from default on first run via `ensure_config()`. NOT committed (gitignored). This is what the addon reads and what the GUI edits.
- **`ensure_config()`** (`src/config_setup.py`): Copies `config.default.json` → `config.json` IF `config.json` doesn't exist. Does NOT merge new fields into existing files — if a new field is added to the default, existing `config.json` files won't get it until manually added or the file is deleted and regenerated.
- **ProxyConfig.load()** handles missing fields gracefully via `_pick()` with defaults, so old config.json files still work.

### 5.3 Hot Reload (Addon Side)

- Checked on every `response()` call via mtime comparison.
- No restart needed — save config from GUI → mtime bump → next request picks up new rules.

### 5.4 Atomic Save (Desktop Side — `tbh_desktop/config_io.py`)

```
save_config(path, data):
  1. validate_config(data) → ProxyConfig.load() on temp file
  2. Backup existing → config.json.bak
  3. Write → config.json.tmp
  4. Rename → config.json (atomic on POSIX)
  5. Re-validate written file
  6. If re-validation fails → restore from .bak
```

### 5.5 GUI Roundtrip (`tbh_desktop/ui/config_editor.py`)

- `ConfigEditor.load(data)`: Stashes fields the GUI doesn't edit into `_loaded_passthrough` dict (currently: `only_post`, `require_boxes_marker`, `url_contains`).
- `ConfigEditor.dump()`: Merges GUI-edited fields + passthrough fields. This prevents GUI saves from wiping fields the GUI doesn't have controls for.
- `_ProxyModeForm`: Edits `mode`, `local_process_name`, `rewrite_pending_tx` (checkbox). These go through `dump()`, NOT passthrough.
- **If you add a new config field**: Either add a GUI control for it, or add it to the `_loaded_passthrough` tuple. Otherwise GUI saves will wipe it.

### 5.6 `rewrite_pending_tx` Flag

- Default: `false` (Strategy B is opt-in).
- When `true`: addon intercepts `SteamItemInfo/mine` GET responses in addition to `processBoxV2` POST responses.
- GUI control: checkbox in `_ProxyModeForm` ("rewrite pendingTx (Strategy B)").

---

## 6. Desktop GUI Architecture

### 6.1 Entry Point (`tbh_desktop/main.py`)

- Creates `QApplication`, applies Catppuccin Mocha theme, instantiates `MainWindow`, installs SIGINT handler (Ctrl+C clean shutdown).
- `QT_QPA_PLATFORM=offscreen` must be exported on CachyOS (Xe GPU driver bug).

### 6.2 MainWindow (`tbh_desktop/ui/main_window.py`)

- 4-zone layout: Left rail (60px icons) | Config editor (center-left) | Item browser (right, 6 tabs) | Log panel (bottom dock).
- `_ThreadLogBridge`: QObject living on GUI thread. Worker threads (ProxyRunner, GearScraperRunner) call `bridge.log_line.emit(...)` instead of calling GUI methods directly. Qt's AutoConnection queues the signal across threads → slot runs on GUI thread. **This prevents HarfBuzz SIGSEGV** (see Gotchas).
- Tamper counter in status bar.

### 6.3 Config Editor (`tbh_desktop/ui/config_editor.py`)

- `ConfigEditor(QWidget)`: Composes `RuleListView` (top) + `_RangeForm` (bottom) + `_ProxyModeForm` (bottom) in a vertical splitter.
- `RuleListView`: Card-based list of specific queue rules. Each card shows box itemId, rule name, replacement IDs as chips.
- `_RangeForm`: Enabled checkbox, min/max itemId inputs, replacement IDs input + chips.
- `_ProxyModeForm`: Regular/Local radio buttons, process name input, Strategy B checkbox.

### 6.4 Gear Picker (`tbh_desktop/ui/gear_picker.py`)

- `GearView`: Loads gear data from `tbh_desktop/gear/{cat}/{grade}.json` files via `read_gear_cache()` from `scraper.py`.
- `GearPicker` is a thin `QDialog` wrapping `GearView` (dialog shim pattern — edit the View for behavior, dialog is just a modal shell).
- Displays gear items with name, rarity, type, level, stat, and image thumbnail.

### 6.5 Item Browser (`tbh_desktop/ui/item_browser.py`)

- 6-tab right panel: All items, Gear, Materials, Gems, Consumables, Soulstones (or similar categorization).
- `FilterContext`: Shared filter state across tabs.
- Uses `gear_cache_dir` to load gear data (same source as gear picker).

### 6.6 Proxy Runner (`tbh_desktop/proxy_runner.py`)

- Spawns mitmdump as subprocess with `start_new_session=True` (own process group).
- `stop()`: `os.killpg(pgid, SIGTERM)` → wait 3s → `SIGKILL` if still alive.
- stdout streamed to Qt signal via `_ThreadLogBridge`.

### 6.7 Scraper (`tbh_desktop/scraper.py`)

- `refresh_gear_full()`: Uses CloakBrowser (stealth Chromium) to scrape `taskbarhero.wiki` for gear data. Falls back to stock Playwright if CloakBrowser unavailable. Covers Legendary+ only.
- `read_gear_cache()`: Loads `tbh_desktop/gear/{cat}/{grade}.json` files.
- Box loot scrape: Uses requests + beautifulsoup4 to scrape box loot tables from `taskbarhero.wiki`.
- `read_box_drop_cache()`: Loads `tbh_desktop/box_loot_cache/{boxId}.json` files.

### 6.8 Thread Safety

- **HarfBuzz SIGSEGV**: `QPlainTextEdit.appendPlainText` called from `threading.Thread` → crash in `QTextEngine::shapeTextWithHarfbuzzNG` (PySide6 6.11 / Qt 6.11, ellipsis glyph).
- **Fix**: `_ThreadLogBridge` QObject on GUI thread. Workers emit signals, Qt queues them to GUI thread. All new background threads MUST go through a bridge.

---

## 7. Item ID Structure (ABCDEF)

All item IDs are 6 digits: `ABCDEF`.

### AB = Category (first 2 digits)

| AB  | Category              | Examples                        |
|-----|-----------------------|---------------------------------|
| 30  | Weapon — Sword        | Bastard Sword, Knight Sword     |
| 31  | Weapon — Bow          | Composite Bow                   |
| 32  | Weapon — Staff        | Witch Staff, Long Staff         |
| 33  | Weapon — Scepter      | Steel Scepter                   |
| 34  | Weapon — Crossbow     | Long Crossbow                   |
| 40  | Off-hand — Shield     | Heater Shield                   |
| 41  | Off-hand — Arrow      | Barbed Arrow                    |
| 42  | Off-hand — Orb        | Brilliant Orb                   |
| 50  | Armor — Helmet        | Knight Helmet                   |
| 51  | Armor — Chest         | Chain Mail, Iron Plate          |
| 52  | Armor — Gloves        | Knight Gloves                   |
| 53  | Armor — Boots         | Knight Boots, Iron Boots        |
| 60  | Accessory — Amulet    | Gold Amulet                     |
| 11  | Gem / Crystal         | Minor Ruby, Minor Topaz         |
| 14  | Material (mid)        | Copper Nugget, Leather, Iron Ingot |
| 16  | Anniversary Coin      | Kingdom 1st Anniversary Coin    |
| 19  | Soulstone             | Soulstone - Normal              |

### C = Rarity (3rd digit)

| C | Rarity     |
|---|------------|
| 0 | Common     |
| 1 | Uncommon   |
| 2 | Rare       |
| 3 | Legendary  |
| 4 | Immortal   |
| 5 | Arcana     |
| 6 | Beyond     |
| 7 | Celestial  |
| 8 | Divine     |
| 9 | Cosmic     |

### DEF = Tier + Variant (last 3 digits)

- `004` = Common tier, variant 4
- `041` = Arcana Lv15 gear (e.g. 505041 = Arcana Knight Helmet Lv15)
- `031` = Rare Lv15 gear variant
- `051` = Arcana Lv20 gear
- `071` = Arcana Lv30 gear
- `091` = Arcana Lv40 gear
- `111` = Arcana Lv50 gear

### Suffix (last 3) and Client Validation

- The client-side validator checks the **last 3 digits** of `rewardItemId`.
- If the original drop's last 3 differs from the rewritten value's last 3 → `TamperedItemIdDetected` report.
- Strategy A (suffix-aware picker): constrains replacements to same-suffix items → validator passes.
- Strategy B (pendingTx rewrite): rewrites `gid`/`tid` too → full evasion regardless of suffix.

### tid Mapping (DynamoDB pendingTx)

- `gid == rewardItemId` (the 6-digit item ID)
- `tid == gid * 1000 + 900`
- Example: gid=321111 → tid=321111900
- Offset 900 verified from capture (n=1, needs n>1 confirmation).

---

## 8. Network Architecture

### 8.1 API Hosts

| Host                     | Purpose                                      |
|--------------------------|----------------------------------------------|
| `api.thebackend.io`      | All gameplay RPCs + cheat telemetry log      |
| `gameinfo.thebackend.io` | UserInventory + SteamItemInfo (DynamoDB)     |
| `auth.thebackend.io`     | Federation auth (Steam ticket)               |

### 8.2 Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/backend-function/base/v1` | POST | processBoxV2, consume, exchange, processPending — gameplay RPCs |
| `/data/gameinfo/v3.3/union/SteamItemInfo/mine` | GET | Returns pendingTx, marketData, steamSlot (DynamoDB format) |
| `/data/gameLog/v2/TemperedItem/90` | POST | Client→server cheat report (TamperedItemIdDetected). **Request body contains mismatches, server replies 204 No Content.** |
| `/data/gameinfo/v3.3/union/UserInventory_14/mine` | GET | Player's owned items (paged) |

### 8.3 DynamoDB Response Format

`SteamItemInfo/mine` and other gameinfo endpoints return DynamoDB-formatted JSON:

```json
{
  "serverTime": "2026-06-28T12:51:45.043Z",
  "rows": [{
    "pendingTx": {
      "L": [
        {
          "M": {
            "op":  {"S": "additem"},
            "gid": {"N": "321111"},
            "tid": {"N": "321111900"},
            "qty": {"N": "1"},
            "rid": {"S": "17432693923082523668"},
            "sid": {"S": "76561198000000000"},
            "siid": {"S": ""}
          }
        }
      ]
    }
  }]
}
```

- `{"L": [...]}` = List
- `{"M": {...}}` = Map
- `{"N": "123"}` = Number (as string)
- `{"S": "str"}` = String

### 8.4 processBoxV2 Response Structure

The response is JSON with a nested `result` string (double-encoded):

```json
{
  "result": "{\n  \"message\": \"success\",\n  \"data\": {\n    \"added\": [...],\n    \"boxes\": [...]\n  }\n}"
}
```

**`added[]`** — REAL items the server minted into inventory:
```json
{"itemKey": "1792", "itemId": 341031}
```
- `itemId` here is the ACTUAL item the server gave. This is what crafting recipes check against.
- The addon does NOT rewrite this.

**`boxes[]`** — Pending box rewards (what the client displays):
```json
{
  "itemId": 910151,
  "itemKey": "2102",
  "claimableAt": "2026-06-29T08:47:04Z",
  "rewardItemId": 140004,
  "rewardItemKey": "2103",
  "isGet": false
}
```
- `rewardItemId` is what the addon REWRITES. This is cosmetic — what the client shows in the box preview UI.
- `rewardItemKey` is the key for the pending reward (used to claim/consume later).

### 8.5 The Desync Problem (Root Cause of Crafting Crash)

1. Addon rewrites `rewardItemId` in `boxes[]` → client displays e.g. Copper Nugget (140004).
2. But `added[]` in the same response shows the REAL item the server minted (e.g. 341031).
3. Client caches the rewritten `rewardItemId` as the expected reward.
4. When user tries to craft/synthesize using the item they THINK they have (Copper Nugget), they send `exchange` with the `itemKey`.
5. Server looks up the REAL itemId for that itemKey → it's NOT Copper Nugget → `"itemKey does not match recipe"` error → game crash.
6. Client also detects the mismatch between cached `rewardItemId` and real `added[].itemId` → sends `TamperedItemIdDetected` report.

---

## 9. Testing

### 9.1 pytest Configuration (`pytest.ini`)

```ini
addopts = -m "not integration" -p no:pytestqt
```
- `-m "not integration"`: Skip tests marked `@pytest.mark.integration`.
- `-p no:pytestqt`: Disable pytest-qt plugin (teardown hangs on Plasma Wayland).

### 9.2 conftest.py

- Adds `src/` to `sys.path` for imports.
- `_NoopQtBot`: Stub `qtbot` fixture — lets test collection succeed without spinning up `QApplication`.
- `gui` marker: `@pytest.mark.gui` for opt-in GUI tests (require real Qt event loop).

### 9.3 Test Files

- `tests/test_reward_rewriter.py`:
  - `TestSpecificRuleCycle`: cycle through replacements, disabled rule noop, empty replacements noop, pass-through.
  - `TestRangeRule`: range match/cycle, bounds checking, disabled noop.
  - `TestSpecificOverRange`: specific rule wins over range.
  - `TestDetailTracking`: ReplacementDetail captures old/new IDs.
  - `TestTamperDetector`: logs mismatch to JSONL, URL filter, empty mismatches, malformed entries. **Uses `flow.request.get_text` (not response!)**.
  - `TestPendingTxRewriter`: gid/tid rewrite, URL filter, empty map, multiple entries, unmapped gid pass-through, tid formula verification.

### 9.4 Self-Test

```bash
python3 src/tbh_reward_hook.py --self-test
```
- Uses **built-in fixtures** (hardcoded box IDs, reward IDs) — does NOT read live `config.json`.
- Tests: specific rule cycling, range rule, empty config pass-through, no-rule pass-through, Strategy B gid/tid rewrite.
- Update `run_self_test()` if changing rule logic.

### 9.5 pyright

- Config: `pyrightconfig.json`.
- 12 pre-existing errors in `scraper.py`, `box_picker.py`, `test_main_window.py`, `test_rule_card.py` — NOT in `tbh_reward_hook.py` or `tbh_proxy_config.py`.
- These are type annotation issues in code that was written before pyright was adopted.

### 9.6 Environment

- Always export `QT_QPA_PLATFORM=offscreen` on CachyOS (Xe GPU driver bug — applies even outside pytest).
- Terminal state persists across calls — activate venv once, reuse.

---

## 10. Gotchas & Known Issues

### HarfBuzz SIGSEGV from non-Qt threads
- **Symptom**: `QPlainTextEdit.appendPlainText` called from `threading.Thread` → crash in `QTextEngine::shapeTextWithHarfbuzzNG` (PySide6 6.11 / Qt 6.11, ellipsis glyph).
- **Fix**: `_ThreadLogBridge` QObject on GUI thread; worker threads emit signals. New background threads MUST go through a bridge.

### pytest-qt teardown hangs on Plasma Wayland
- **Symptom**: Kills DE under `QT_QPA_PLATFORM=offscreen`.
- **Fix**: `pytest.ini` has `-p no:pytestqt`. GUI tests marked `@pytest.mark.gui`. `_NoopQtBot` stub in `conftest.py`.

### Process group signaling (proxy kill)
- `ProxyRunner.start()` uses `start_new_session=True` so child forms its own process group.
- `stop()` calls `os.killpg(pgid, SIGTERM)` then escalates to `SIGKILL` after 3s.
- Without the group kill, `mitmdump` grandchild is orphaned holding the listen port.

### CloakBrowser fallback
- Gear scrape uses CloakBrowser (stealth Chromium, ~200 MB binary auto-downloaded, Ed25519-verified).
- If `cloakbrowser` not installed → falls back to stock Playwright (`playwright install chromium` required).
- Gear scrape covers Legendary+ only. Lower grades not scraped.

### rewardItemId rewrite is cosmetic-only (CAUSES CRAFTING CRASH)
- The addon rewrites `rewardItemId` in the `boxes[]` array of `processBoxV2` responses.
- But the `added[]` array in the SAME response carries the REAL itemIds that the server actually minted.
- The client uses `added[].itemId` for crafting recipes, NOT `rewardItemId`.
- When the user tries to craft with items they THINK they have (based on the rewritten `rewardItemId`), the server rejects it: `"itemKey does not match recipe"` → game crash.
- **This is the root cause of the synthesize/crafting crash.** Not yet fixed.

### TamperDetector must read REQUEST body
- The client POSTs mismatch data to `/data/gameLog/v2/TemperedItem/90`.
- The server replies **204 No Content** (empty body).
- The mismatch data is in the **REQUEST body**, not the response.
- Previously the detector read `flow.response.get_text()` → always empty → tamper-events.jsonl stayed at 0 bytes.
- **Fixed**: Now reads `flow.request.get_text()`.

### PendingTxRewriter: pendingTx may be empty
- `SteamItemInfo/mine` response may show `pendingTx.L = []` (empty list) if entries were already consumed by the time the client fetches.
- In this case, `PendingTxRewriter` has nothing to rewrite.
- Strategy B only works if SteamItemInfo is fetched BEFORE pendingTx entries are consumed.

### config.json existing files don't get new fields
- `ensure_config()` only copies `config.default.json` → `config.json` if the file doesn't exist.
- If a new field is added to the default, existing `config.json` files won't get it.
- `ProxyConfig.load()` handles missing fields via `_pick()` with defaults, so old configs still work — but the field won't appear in the file until manually added.

### Gear cache is SEPARATE from item-catalog.json
- `tbh_desktop/gear/{cat}/{grade}.json` = equipment scraped from taskbarhero.wiki (CloakBrowser).
- `captures/item-catalog.json` = materials/gems/consumables from game localization (511 items).
- **DO NOT use `item-catalog.json` to look up gear item names.** Use the gear cache files.
- If an item ID is not found in `item-catalog.json`, check `tbh_desktop/gear/` before claiming "NOT IN CATALOG".

### Pickers are dialog shims
- `GearPicker` / `BoxPicker` / `BoxLootPicker` are thin `QDialog`s wrapping extracted `*View` classes.
- Edit the `*View` for behavior; the dialog is just a modal shell.

### CA private key
- Never commit `~/.mitmproxy/mitmproxy-ca*.pem` or `.p12` files.
- Anyone with the key can sign any HTTPS cert for any client that trusts the CA.

### `--mode local` on Linux
- mitmproxy's local redirector uses a setuid helper (`mitmproxy-linux-redirector`), so mitmdump will prompt for `sudo` at startup.
- Run as root, or pre-elevate with `sudo -E ./scripts/run_proxy.sh --mode local --name <proc>`.
- Proton-launched games live inside a `pressure-vessel` container — verify process name with `pgrep -af TaskBarHero`.
