# TBH Desktop Redesign — Design

Date: 2026-06-27
Status: Draft (pending review)

## Goal

Redesign the TBH Reward Proxy desktop GUI (PySide6/Qt) around a **Dark RPG inventory** aesthetic. The tool helps a TaskBarHero player (idle RPG game in the Windows taskbar) override drop-box loot via a mitmproxy addon. The redesign must make it easy and pleasant to:

1. Edit `config.json` rules (specific_queue_rules + range_replacement) without modal round-trips.
2. Browse the in-game item catalog (gear, materials, boxes) in a permanent **Item browser** panel on the right.
3. Pick replacement reward IDs by clicking items in the Item browser, watching selections land in the active rule without losing context.
4. Run/stop the proxy, scrape data, copy Steam launch options — all reachable from a vertical icon rail.

Scope: full — every UI module under `tbh_desktop/ui/`: `main_window`, `config_editor`, `gear_picker`, `box_loot_picker`, `box_picker`, `log_panel`, `theme`. No module is left as a "rare path" or deferred. Labels are plain English; only visual styling carries the RPG theme.

## Context

Project TBH is a mitmproxy addon (`src/tbh_reward_hook.py`) that rewrites `rewardItemId` responses for TaskBarHero. The current desktop GUI (`tbh_desktop/`) was designed for engineers running the proxy on demand; the user is now a gamer who curates drop tables daily. Concrete UX pain points observed in the code:

- Toolbar crams 8 widgets on one row with thin separators; status dot sits next to a port input next to action buttons.
- Pickers are modal `QDialog`s — picking a reward means losing the rule list, the log, and the active selection state.
- The rules list is a 4-column `QTableWidget` with flat styling; rarity is invisible, and replacement IDs are a comma string with no preview.
- Existing code already added a `→ Pick target` banner to address "I selected row 2 but data went to row 1" — a sign that the table interaction was ambiguous.
- The log panel is a fixed right pane; it competes with the editor for horizontal space rather than acting as a debug surface.

The visual system is already Catppuccin Mocha (`theme.py`). The redesign keeps that base palette and layers an **RPG inventory** overlay (rarity colors, item cards, ornate frames, display-grade typography) while keeping every label plain.

## Visual system

### Palette additions (extend `MOCHA` dict in `theme.py`)

```python
RARITY = {
    "COMMON":    "#6c7086",  # overlay0
    "UNCOMMON":  "#a6e3a1",  # green
    "RARE":      "#89b4fa",  # blue
    "EPIC":      "#cba6f7",  # mauve
    "LEGENDARY": "#f9e2af",  # yellow
    "MYTHIC":    "#f38ba8",  # red
}
# Each rarity gets a 12% alpha tint for card backgrounds.
def rarity_tint(hex: str) -> str: ...  # alpha-blend with MOCHA["mantle"]
```

Existing `MOCHA` dict stays intact. `RARITY` is exported alongside it. Rule cards and item browser items read from this map; the picker never hard-codes colors.

### Typography

- **Display / panel titles:** `Cinzel` (Google Fonts, free, Roman-classical). Used for group-box titles, section headers, and the app title bar fallback. Falls back to serif if Cinzel is missing on the system.
- **Log / monospace:** `JetBrains Mono` (already a candidate in `log_panel_style`). Promote to required for any code-like surface (replacement IDs preview, port field).
- **Body / labels:** keep Qt default sans (system), with `font-weight: 500` for emphasis (already in QSS).

The QSS font-family is a list so missing fonts degrade gracefully:

```css
font-family: "Cinzel", "Trajan Pro", "Cormorant Garamond", serif;
```

### Item card

`QFrame` subclass `ItemCard` renders a single in-game item (gear/material/box). Spec:

- Size: 96×96 px (gear with icon), 88×40 px (chip for material in a rule preview).
- Border: 1 px solid `RARITY[rarity]`, radius 8 px.
- Background: `rarity_tint(rarity)` when hovered, `MOCHA["mantle"]` otherwise.
- Selected state: 2 px `MOCHA["blue"]` border, `MOCHA["surface0"]` background.
- Icon: 64×64 from `ImageCache`, fallback to a tinted silhouette SVG.
- Layout (vertical): icon centered, name below truncated to one line with `…`, rarity text 10px in matching color.

Renders via custom `QStyledItemDelegate` in the Item browser list view. Rule cards reuse the same delegate for the inline "selected IDs" chip row.

### Ornament

Small SVG corner filigree (4-piece triangle + dot motif, 16×16 px) drawn at the top-left of: left rail, Item browser panel, log dock title bar. Implemented as a `QLabel` with an inline SVG, not an image asset (keeps the repo lean). Subtle — opacity 0.35, color `MOCHA["overlay1"]`.

## Layout composition

```
┌────┬────────────────────────────┬──────────────┐
│ R  │  Specific Queue Rules      │              │
│ A  │  ┌──────────────────────┐  │              │
│ I  │  │ rule card 1 (active) │  │   I T E M S  │
│ L  │  ├──────────────────────┤  │              │
│    │  │ rule card 2          │  │  [tab bar]   │
│ 60 │  ├──────────────────────┤  │              │
│ px │  │ rule card 3          │  │  item cards  │
│    │  └──────────────────────┘  │  in grid     │
│    │                            │              │
│    │  Range Replacement         │              │
│    │  ┌──────────────────────┐  │              │
│    │  │ enabled · min · max  │  │              │
│    │  │ ids: chips + pick…   │  │              │
│    │  └──────────────────────┘  │              │
├────┴────────────────────────────┴──────────────┤
│ log dock (collapsible, default shown)         │
└───────────────────────────────────────────────┘
```

Concrete sizes and behavior:

- **Left rail:** 60 px fixed width, full height. Icon-only `QPushButton`s with `objectName` so the existing QSS (`#btn_start`, `#btn_stop`) keeps working. Top: Start + Stop. Middle: Save, Reset, Scrape Data, Check Data, Copy Steam. Bottom: status dot + port `QLineEdit` (vertical stack). All buttons 44×44 with 8 px gaps, tooltip = full label.
- **Center column:** single `QWidget` with `QVBoxLayout`. Top = `RuleListView` (card list). Bottom = range replacement form. Stretch 3:1 between them.
- **Right item browser:** `QWidget` with 320 px preferred width, user-resizable. Top: tab bar (`Browse all` | `Box loot` | `Gear (scoped)` | `Gear (all)` | `Drops index` | `Boxes`). Body: filtered item grid (3 cols at 320 px, 4–5 at wider). Bottom: thin `status_label` showing "42 items" / "no cache — Scrape Data".
- **Bottom log dock:** `QDockWidget` wrapping existing `LogPanel`, default docked bottom, collapsible, toggleable from rail.

Default window: 1400×800. Minimum window: 1280×720. Below 1100 px the item browser becomes a toggleable overlay (button on rail). Below 1280 px the center column is squeezed but all zones remain visible.

## Components

### New files

- `tbh_desktop/ui/left_rail.py` — `LeftRail(QWidget)`. Holds icon buttons. Emits `action(Action)` where `Action` is a `StrEnum` (`START`, `STOP`, `SAVE`, `RESET`, `SCRAPE`, `CHECK_DATA`, `COPY_STEAM`, `TOGGLE_LOG`, `TOGGLE_ITEMS`). `MainWindow` connects to these.
- `tbh_desktop/ui/rule_card.py` — `RuleCard(QFrame)`. One rule. Renders enabled checkbox, name `QLineEdit`, item_id `QLineEdit`, **three Pick buttons** (`Pick box`, `Pick loot`, `Pick gear`), and replacement IDs as a wrap of `ItemCard` chips with × buttons. The Pick buttons are part of every card so the user can drive the Item browser from the rule they care about. Emits `pick_box_id`, `pick_box_loot`, `pick_gear`, `remove`, `edited`. `set_active(bool)` for active state (drives the persistent left border highlight).
- `tbh_desktop/ui/rule_list.py` — `RuleListView(QListView)`. `QListView` with a custom delegate that draws one `RuleCard` per row. Owns the `QStandardItemModel` of rules. API mirrors the parts of `ConfigEditor` that the rest of the app calls: `load(data)`, `dump()`, `selected_rule_item_id()`, `add_ids_to_selected_rule(ids)`, `add_ids_to_range(ids)`, `set_selected_rule_item_id(box_id, level)`, `selected_rule_level()`, `set_active_target(target: ActiveTarget)` where `ActiveTarget` is a `Union[RuleTarget, RangeTarget]`.
- `tbh_desktop/ui/item_browser.py` — `ItemBrowser(QWidget)`. Tabs, filter, item grid. Emits `item_picked(item_id)`, `items_picked(item_ids)`. Exposes `filter_for_context(context: FilterContext | None)`. `FilterContext` is a frozen dataclass with fields: `box_id: int | None`, `box_name: str | None`, `level: int | None`, `scope: FilterScope` where `FilterScope` is an enum (`BOX_LOOT`, `GEAR_FOR_BOX`, `GEAR_ALL`, `DROPS_INDEX`, `BROWSE_ALL`, `BOXES`). When `context is None` (no active target), the item browser shows the `BROWSE_ALL` tab disabled with a banner "Select a rule or the Range form to pick rewards". When context is set, the appropriate tab activates and pre-applied filters match the existing `GearPicker` / `BoxLootPicker` behavior (level tolerance ±5, "Only show gear from this box" pre-checked).

  Tabs and their content:
  - **Browse all** — combined view of all gear + drops index items, no filter. Default tab when no active target.
  - **Box loot** — items in the active rule's box loot table. Hidden when no `box_id`.
  - **Gear (scoped)** — gear filtered to active rule's box loot names + level tolerance. Hidden when no `box_id`.
  - **Gear (all)** — every gear item, no filter. Always visible.
  - **Drops index** — materials + stage boxes from the wiki drops index. Always visible.
  - **Boxes** — every box from `BOX_SLUG_CACHE`; selecting one writes the box id into the active rule and triggers the loot refresh. Always visible.
- `tbh_desktop/ui/item_card.py` — `ItemCard(QFrame)`. Standalone widget. `set_data(item_dict)`, `set_selected(bool)`, `set_compact(bool)`. Used by `RuleListView` delegate and `ItemBrowser`.
- `tbh_desktop/ui/active_target.py` — small module with `ActiveTarget`, `RuleTarget`, `RangeTarget` dataclasses. A typed union describes what the Item browser should write to when the user picks an item.

### Rewritten files

- `tbh_desktop/ui/main_window.py` — composes the four zones: rail (left), editor+range (center), item browser (right), log dock (bottom). Wires `LeftRail.action → existing slots` (start/stop/save/reset/scrape/check/copy/toggle-log/toggle-items). Wires `RuleListView.rule_selected → ItemBrowser.filter_for_context + set_active_target`. Wires `ItemBrowser.item_picked → RuleListView.add_ids_to_active_target`. Wires `RangeForm.focused → RuleListView.set_active_target(RangeTarget())`. Preserves every signal-based connection already in use (`runner.log_line`, `runner.running`, `gear_scraper.*`). Default window 1400×800; minimum 1280×720; center column minimum 540.
- `tbh_desktop/ui/config_editor.py` — becomes a thin container: `RuleListView` (top) + `RangeForm` (bottom). `dump()` and `load()` kept on this class as the public API (the rest of the app already calls `editor.load(data)` / `editor.dump()`); they delegate to `RuleListView` internally. The `active_row_label` banner is removed — the active rule is now shown by a persistent left border on the `RuleCard` and the Pick buttons live on each card.
- `tbh_desktop/ui/gear_picker.py` — refactored to expose a `GearView(QWidget)` that `ItemBrowser` embeds. The file is rewritten as a module containing the view + its filter logic. Old `QDialog` wrapper stays as a thin shim that opens `GearView` inside a dialog (kept only so legacy callers compile; not shown in the redesigned app).
- `tbh_desktop/ui/box_loot_picker.py` — same pattern: extract `BoxLootView(QWidget)` for the Item browser; keep the dialog as a fallback shim.
- `tbh_desktop/ui/box_picker.py` — same pattern: extract `BoxView(QWidget)` for the Item browser. The current dialog is keyed by `BOX_SLUG_CACHE` (a small slug→id map); the Item browser version renders one card per box with a search field and "select" action. Old dialog wrapper stays as a shim.
- `tbh_desktop/ui/theme.py` — add `RARITY`, `rarity_tint`, `apply_ornament(widget)`, expand QSS with item-card rules, button-group rules for the rail, and typography rules for `Cinzel` / `JetBrains Mono`. Existing `MOCHA` and `apply_theme` API preserved.
- `tbh_desktop/ui/log_panel.py` — works as-is. The dock wrapper handles visibility/collapse.

### Untouched

- `tbh_desktop/proxy_runner.py`, `tbh_desktop/gear_scraper_runner.py`, `tbh_desktop/config_io.py`, `tbh_desktop/scraper.py` — all untouched. Signals and public APIs preserved.

## Active target state machine

A single in-memory `ActiveTarget` describes where Item browser picks write to. Implemented as a typed union with two members:

```python
@dataclass(frozen=True)
class RuleTarget:
    row: int            # row index in RuleListView
    rule_index: int     # index into config.specific_queue_rules
    box_id: int | None
    level: int | None

@dataclass(frozen=True)
class RangeTarget:
    pass                # writes to config.range_replacement.replacement_reward_item_ids

ActiveTarget = RuleTarget | RangeTarget
```

Transitions:

- `RuleListView.selection_changed(row)` → `ActiveTarget = RuleTarget(...)` for that row. Item browser shows tabs/filters for the rule.
- `RangeForm.focused()` (any field gets focus) → `ActiveTarget = RangeTarget()`. Item browser shows `GEAR_ALL` or `DROPS_INDEX` tabs only (others are dimmed).
- Clicking a new `RuleCard` replaces the target. Switching back to a rule from the range form re-enables all tabs.
- If neither is active (e.g. on app start before any selection), `ActiveTarget = None` and the Item browser shows a "Select a rule or the Range form to pick rewards" banner; the grid is disabled.

`MainWindow` holds the current `ActiveTarget` and routes `ItemBrowser.item_picked` → `RuleListView.add_ids_to_active_target(ids)`. `RuleListView` translates the union into either `add_ids_to_selected_rule` or `add_ids_to_range` based on the target type. The persistent left border on the active `RuleCard` (rule mode) and a left border on the Range form (range mode) visualize the state.

## Data flow

```
LeftRail.action(START)
  → MainWindow._start()                  [unchanged]
  → ProxyRunner.start()                  [unchanged]
  → runner.running → MainWindow._on_running
  → _on_running updates status dot + start/stop button enabled

RuleListView.rule_selected(row, rule)
  → MainWindow.active_target = RuleTarget(...)
  → ItemBrowser.filter_for_context(box_id=rule.item_id, level=rule.level, scope=GEAR_FOR_BOX)
  → ItemBrowser switches tab + applies pre-filters

RangeForm.focused()
  → MainWindow.active_target = RangeTarget()
  → ItemBrowser.filter_for_context(scope=GEAR_ALL | DROPS_INDEX)

ItemBrowser.item_picked(item_id)
  → MainWindow routes by active_target type
  → if RuleTarget: RuleListView.add_ids_to_selected_rule([item_id])
  → if RangeTarget: RuleListView.add_ids_to_range([item_id])
  → chips render in real time via QStandardItem.dataChanged

GearScraperRunner.finished(total, n_files)
  → MainWindow._on_gear_scraped
  → log line + ItemBrowser.refresh() (re-reads from cache)
```

Thread safety:

- All non-GUI threads still emit via Qt signals (existing `_ThreadLogBridge` pattern). No new worker threads introduced in this redesign.
- `ItemBrowser.refresh()` is called from the GUI thread; if the cache is large (gear ≈ 2000 items), it runs in a one-shot `QTimer.singleShot(0, …)` to keep the slot stack shallow.

## Error handling

- **Config save failure** (existing `config_io.save_config` returns `Result`): `RuleListView` paints the affected card's left border red and logs the error. Card stays editable.
- **Empty item browser (no cache)**: body renders a centered empty-state with a `Run Scrape Data` button that calls `LeftRail.action(SCRAPE)`.
- **Picker cancelled**: `ItemBrowser.item_picked` is never emitted; rule card state unchanged.
- **Filter that yields zero results**: body shows "No items match. [Clear filters]".
- **Window resized below 1100 px**: item browser switches to overlay mode; rail gains a `TOGGLE_ITEMS` button. Overlay is a `QFrame` with the browser body reparented into it.
- **No active target** (initial state, or after a target deselects): item browser shows a banner; the grid renders disabled, with `Browse all` tab visible but inert.

## Testing

Existing tests must keep passing without modification of their public APIs:

- `tests/test_config_io.py` — depends on `config_io.load_config` / `save_config` signatures. Unchanged.
- `tests/test_scraper.py` — depends on `scraper` module. Unchanged.
- `tests/test_proxy_runner.py` — depends on `ProxyRunner` signals. Unchanged.

New tests:

- `tests/ui/test_rule_card.py` — `RuleCard` enabled toggle, chip add/remove, name/item_id edit, signal emission, `set_active` toggles border.
- `tests/ui/test_rule_list.py` — `RuleListView.load(dump()) == data` (round-trip), selection change → `rule_selected` signal, `add_ids_to_active_target` with `RuleTarget` appends to that row, with `RangeTarget` appends to the range form, dedupes both.
- `tests/ui/test_item_browser.py` — `filter_for_context` with `box_id=42, level=10` activates the box-loot tab and pre-checks the "Only show gear from this box" filter. Empty cache → empty state visible. `None` context → banner visible, grid disabled.
- `tests/ui/test_left_rail.py` — `action` enum emitted on each button click, disabled state follows proxy running flag.
- `tests/ui/test_active_target.py` — state machine transitions: selection sets `RuleTarget`, focus on range form sets `RangeTarget`, neither is set on app start.
- `tests/ui/test_main_window_smoke.py` — launch `MainWindow` in offscreen mode, verify all four zones exist (`left_rail`, `rule_list`, `item_browser`, `log_dock`), screenshot saved to `tests/ui/_artifacts/main_window.png` for visual review.

Test framework: `pytest-qt` (already a dev dep). No Playwright (Qt, not browser). Visual smoke screenshot is reviewed manually; no pixel-diff in v1.

## Migration

- `ConfigEditor` keeps `load(data)` and `dump()` signatures → no call site changes outside `main_window.py` and tests.
- `theme.apply_theme` signature unchanged → `main.py` startup untouched.
- `MOCHA` dict keys unchanged → no other QSS breaks.
- New dependency: `Cinzel` and `JetBrains Mono` fonts bundled under `tbh_desktop/ui/fonts/` with `Qt.QFontDatabase.addApplicationFont`. Bundled because the target machine may not have them. Total size ≤ 200 KB each.
- Old picker dialogs (`GearPicker`, `BoxLootPicker`, `BoxPicker`) remain as thin dialog wrappers around their `*View` widgets, so any external test or import keeps working. They are not used by the redesigned app.

## Out of scope (v1)

- Multi-window / multi-monitor support.
- Theme switcher (light mode, alternate palettes).
- i18n beyond the existing Indonesian tooltips.
- Plugin system for custom pickers.
- Undo/redo for rule edits.
- Drag-and-drop between rule cards and the Item browser (picking is by click for v1).
