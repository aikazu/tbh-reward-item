"""Dialog to pick gear reward IDs from per-category×grade cache files.

G4: rebuilds the list from ``GEAR_CACHE_DIR/gear_{cat}_{grade}.json`` files
matching the current Category/Grade/Level-range filters. Search box and
multi-select behaviour preserved from the original flat-list picker.

New in G4:
  - Optional ``box_loot`` list: when supplied, only gear whose ``name``
    matches one of the loot item names is shown (so the picker is scoped to
    the box the user is editing).  A "Show all gear" checkbox toggles this.
  - Optional ``level_hint``: pre-sets the level dropdowns to bracket the
    box's level (±5 tolerance) so the picker opens pre-filtered.

G5:
  - Replaced the level min/max spinboxes (continuous 0-100) with two
    dropdowns that list only the distinct levels actually present in the
    cache for the current category+grade filter. Avoids picking a level
    that no gear has.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.gear_filters import CATEGORY_DISPLAY, GRADE_DISPLAY
from tbh_desktop.paths import BOX_DROP_MAP_CACHE
from tbh_desktop.scraper import read_box_drop_cache, read_gear_cache
from tbh_desktop.ui.image_cache import ImageCache

# Inject the "All" pseudo-option (None slug means no filter).
_CATEGORY_DISPLAY: dict[str, str | None] = {"All": None, **CATEGORY_DISPLAY}
_GRADE_DISPLAY: dict[str, str | None] = {"All": None, **GRADE_DISPLAY}

# Level tolerance when a level_hint is supplied (± this many level).
_LEVEL_TOLERANCE = 5

# Compact stat-name -> short label for inline rendering. Avoids printing
# full "Attack Damage BASE" lines per stat — the row is a single list line.
_STAT_SHORT: dict[str, str] = {
    "Attack Damage": "ATK",
    "Attack Speed": "ASPD",
    "Critical Rate": "CRIT",
    "Critical Damage": "CD",
    "Cooldown Reduction": "CDR",
    "Max HP": "HP",
    "Defense": "DEF",
}


def _short_stat_name(name: str) -> str:
    """Return the short label for *name* (e.g. 'Attack Damage' -> 'ATK').
    Falls back to a stripped title-case version if no mapping exists.
    """
    if name in _STAT_SHORT:
        return _STAT_SHORT[name]
    # Title-case first 2 words, e.g. "Some Cool Stat" -> "Some Cool".
    parts = name.split()
    return " ".join(parts[:2]) if len(parts) > 2 else name


def _format_stats_compact(stats: list[dict[str, str]] | None) -> str:
    """Format a per-item stats list as a single inline row.

    Example output: ``ATK +1,656 · ASPD +3.10/s · ATK +397 (inh) · CD +132.1% (inh)``.

    BASE stats are shown without a suffix; INHERENT ones are tagged ``(inh)``
    so the breakdown is visible without hovering (per user request).
    Returns '' if no stats are present.
    """
    if not stats:
        return ""
    parts: list[str] = []
    for s in stats:
        name = s.get("name", "").strip()
        value = s.get("value", "").strip()
        kind = s.get("kind", "").strip()
        if not name or not value:
            continue
        short = _short_stat_name(name)
        if kind == "inherent":
            parts.append(f"{short} {value} (inh)")
        else:
            parts.append(f"{short} {value}")
    return " · ".join(parts)


class GearView(QWidget):
    """Embeddable gear list with filters. No dialog chrome.

    Filter behaviour matches what `GearPicker` exposed as a modal:
    - Category / Grade dropdowns (with "All" option)
    - Level min / Level max dropdowns populated from the cache
    - Optional box_loot scoping (when supplied, filters to loot names)
    - Search box (filters by case-insensitive substring on name)

    Public API:
    - ``set_category(name)`` / ``set_grade(name)`` — set dropdown by display
      name and trigger a rebuild.
    - ``visible_items() -> list[dict]`` — items currently shown (after all
      filters).
    - ``selected_ids() -> list[int]`` — ids of currently selected rows.
    - ``empty_state_visible() -> bool`` — true when no items AND the cache
      directory does not exist (i.e. nothing to show).
    """

    def __init__(
        self,
        cache_dir: Path,
        parent: QWidget | None = None,
        *,
        box_loot: list[dict[str, Any]] | None = None,
        level_hint: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._cache_dir = Path(cache_dir)

        # Build a set of GEAR names from the box loot table (if given).
        # Gear cache stores "Long Sword", loot stores "Dimensional Sword" etc.
        # Match on case-insensitive name equality. CRITICAL: we filter to
        # kind=="gear" first — otherwise material names (e.g. "Minor Ruby")
        # would clutter _loot_names and never match anything in the gear
        # cache, but more importantly the user reading the picker sees a
        # scoped-by-this-box filter that actually shows gear from any
        # category sharing a base name.
        self._loot_names: set[str] | None = None
        if box_loot:
            self._loot_names = {
                str(it.get("name", "")).strip().lower()
                for it in box_loot
                if str(it.get("kind", "")).lower() == "gear" and it.get("name")
            }
            # If the loot names are empty after filtering, treat as None.
            if not self._loot_names:
                self._loot_names = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ── Filters group ─────────────────────────────────────────────────
        filters_group = QGroupBox("Filters")
        filters_layout = QVBoxLayout(filters_group)
        filters_layout.setSpacing(8)

        # Category + Grade row
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Category:"))
        self.category = QComboBox()
        self.category.addItems(list(_CATEGORY_DISPLAY.keys()))
        self.category.currentTextChanged.connect(self._rebuild)
        filter_row.addWidget(self.category)
        filter_row.addSpacing(12)
        filter_row.addWidget(QLabel("Grade:"))
        self.grade = QComboBox()
        self.grade.addItems(list(_GRADE_DISPLAY.keys()))
        self.grade.currentTextChanged.connect(self._rebuild)
        filter_row.addWidget(self.grade)
        filter_row.addStretch()
        filters_layout.addLayout(filter_row)

        # Level row — two discrete dropdowns populated from levels that
        # actually appear in the cache (e.g. Lv1 / Lv5 / Lv10 / ...). Avoids
        # the "spinbox lets you pick Lv47 even though no gear has that level"
        # problem. "All" is always the first option (= no level filter).
        level_row = QHBoxLayout()
        level_row.addWidget(QLabel("Level:"))
        self.level_min = QComboBox()
        self.level_min.setToolTip("Lowest level to show (from cache) — 'All' = no minimum")
        self.level_min.currentIndexChanged.connect(self._rebuild)
        level_row.addWidget(self.level_min)
        level_row.addWidget(QLabel("–"))
        self.level_max = QComboBox()
        self.level_max.setToolTip("Highest level to show (from cache) — 'All' = no maximum")
        self.level_max.currentIndexChanged.connect(self._rebuild)
        level_row.addWidget(self.level_max)
        level_row.addStretch()
        filters_layout.addLayout(level_row)

        # Pre-populate level dropdowns with distinct levels from cache files.
        # "All" is the first entry (index 0); subsequent entries are sorted by
        # numeric level. Repopulated on filter changes via _rebuild since
        # adding a category filter changes which levels are visible.
        self._populate_level_options()

        # "Match box loot" checkbox — only visible when box loot was supplied.
        self.match_box_check = QCheckBox("Only show gear from this box")
        if self._loot_names is not None:
            self.match_box_check.setChecked(True)
            self.match_box_check.setToolTip(
                "Hanya tampilkan gear yang ada di loot box yang dipilih."
            )
            filters_layout.addWidget(self.match_box_check)
            self.match_box_check.toggled.connect(self._rebuild)
        else:
            self.match_box_check.setVisible(False)

        layout.addWidget(filters_group)

        # ── Search ────────────────────────────────────────────────────────
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name or id…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_search)
        layout.addWidget(self.search)

        # ── Scope banner (only shown when box_loot was supplied) ──────────
        # Tells the user which item names from the box loot table are being
        # used as the filter, and warns when the gear cache has no matches
        # (which would make the picker look empty). Removes the "different
        # boxes show the same content" confusion by making the scoping
        # visible.
        self.scope_banner = QLabel()
        self.scope_banner.setWordWrap(True)
        self.scope_banner.setStyleSheet(
            "color: #f0c674; font-size: 11px; padding: 6px 8px; "
            "background: rgba(240, 198, 116, 0.08); border-radius: 4px;"
        )
        self.scope_banner.setVisible(False)
        layout.addWidget(self.scope_banner)

        # ── List + count ───────────────────────────────────────────────────
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        # Bigger icon size so gear thumbs are readable. Default is 16x16 in
        # most styles; set an explicit size since QSize.width() can return -1
        # on some styles and then *3 would also be negative.
        self.list_widget.setIconSize(QSize(48, 48))
        # Two-line rows (name + stats). Word-wrap so long stat rows don't
        # stretch the dialog horizontally.
        self.list_widget.setWordWrap(True)
        layout.addWidget(self.list_widget)

        # Async image cache (per-view). Icon-ready signals land on the GUI
        # thread via Qt.AutoConnection; we apply them by item_id match.
        self._image_cache = ImageCache(self)
        self._image_cache.icon_ready.connect(self._apply_icon)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #7f849c; font-size: 11px;")
        layout.addWidget(self.count_label)

        # Apply level hint to dropdowns before initial population.
        if level_hint is not None and level_hint > 0:
            self._apply_level_hint(level_hint)

        # Initial population.
        self._rebuild()

    # ---------------------------------------------------------- public API
    def set_category(self, name: str) -> None:
        """Set the Category dropdown by display name (e.g. 'Weapon').

        Falls back to a case-insensitive match if the display name isn't in
        the dropdown's known set, so callers can pass through user input.
        Triggers a rebuild so the list reflects the new filter.
        """
        idx = self._find_dropdown_index(self.category, name)
        if idx >= 0:
            self.category.setCurrentIndex(idx)
            # setCurrentIndex already fires currentTextChanged -> _rebuild,
            # but be explicit in case the dropdown was already at this index.
            self._rebuild()

    def set_grade(self, name: str) -> None:
        """Set the Grade dropdown by display name (e.g. 'Rare').

        Falls back to a case-insensitive match if the display name isn't in
        the dropdown's known set, so callers can pass through user input.
        Triggers a rebuild so the list reflects the new filter.
        """
        idx = self._find_dropdown_index(self.grade, name)
        if idx >= 0:
            self.grade.setCurrentIndex(idx)
            self._rebuild()

    @staticmethod
    def _find_dropdown_index(combo: QComboBox, name: str) -> int:
        """Return the index whose text matches *name*, or -1.

        Prefers exact match, then case-insensitive match. Allows programmatic
        setters to pass display names that aren't in the predefined chip map
        (e.g. 'Rare' when the chip map only has 'Legendary' / 'Immortal' / …).
        """
        idx = combo.findText(name)
        if idx >= 0:
            return idx
        needle = name.strip().lower()
        for i in range(combo.count()):
            if combo.itemText(i).strip().lower() == needle:
                return i
        return -1

    def visible_items(self) -> list[dict]:
        """Return the raw item dicts currently rendered in the list.

        Each entry has at least ``id`` and ``name``. Order matches the
        visible list order. Hidden items (filtered by search) are excluded.
        """
        items: list[dict] = []
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            if li.isHidden():
                continue
            item_id = li.data(Qt.ItemDataRole.UserRole)
            # We don't keep a parallel dict, so reconstruct the minimal dict
            # from the rendered text + stored id. Tests only need id + name.
            text = li.text()
            name = text.split(" · ", 1)[1] if " · " in text else ""
            items.append({"id": item_id, "name": name})
        return items

    def empty_state_visible(self) -> bool:
        """True when no items are currently shown in the list.

        This covers both "cache missing" and "cache present but filters
        exclude everything" — callers can render a generic empty-state
        message either way and let the user adjust filters if needed.
        """
        return self.list_widget.count() == 0

    def selected_ids(self) -> list[int]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
        ]

    # ------------------------------------------------------------------ filters
    def _load_items_for_filters(self) -> list[dict]:
        """Glob cache files matching the current category+grade and merge them,
        deduping by id. Returns the raw item dicts (before level filtering).

        Cache layout (since G8): ``{cache_dir}/{category}/{rarity}.json``.
        e.g. ``gear/weapon/legendary.json``.
        """
        cat_slug = _CATEGORY_DISPLAY.get(self.category.currentText())
        grade_slug = _GRADE_DISPLAY.get(self.grade.currentText())

        seen: set[int] = set()
        merged: list[dict] = []
        if not self._cache_dir.exists():
            return merged

        # Build candidate file paths based on the cat/grade filter.
        candidate_paths: list[Path] = []
        cats = [cat_slug] if cat_slug else ["weapon", "offhand", "armor", "accessory"]
        grades = (
            [grade_slug]
            if grade_slug
            else ["legendary", "immortal", "arcana", "beyond", "celestial", "divine", "cosmic"]
        )
        for c in cats:
            for g in grades:
                # Try the canonical layout ({cache_dir}/{cat}/{grade}.json)
                # first, then fall back to the nested-prefix layout
                # ({cache_dir}/gear/{cat}/{grade}.json) used by some callers,
                # then to the legacy flat layout ({cache_dir}/gear_{cat}_{grade}.json).
                for prefix in ("", "gear"):
                    p = self._cache_dir / prefix / c / f"{g}.json"
                    if p.exists():
                        candidate_paths.append(p)
                flat = self._cache_dir / f"gear_{c}_{g}.json"
                if flat.exists():
                    candidate_paths.append(flat)
        # Also pick up any *.json under any subdir (forward-compat).
        if not candidate_paths:
            candidate_paths = sorted(self._cache_dir.glob("*/*.json"))
            if not candidate_paths:
                # Last-chance: search one level deeper (covers the
                # gear/{cat}/{rarity}.json layout the spec test uses).
                candidate_paths = sorted(self._cache_dir.glob("*/*/*.json"))

        for path in sorted(candidate_paths):
            for item in read_gear_cache(path):
                item_id = item.get("id")
                if item_id is None or item_id in seen:
                    continue
                seen.add(item_id)
                merged.append(item)
        return merged

    def _rebuild(self) -> None:
        """Populate the list widget from cache files, applying the level range
        and (optionally) the box-loot name filter.  Search visibility is
        reapplied afterwards via :meth:`_apply_search`.
        """
        # Repopulate level dropdowns — distinct levels depend on the current
        # category+grade filter, so the available options may shrink/grow.
        self._populate_level_options()
        # currentData() returns None for the "All" pseudo-entry.
        lo = self.level_min.currentData()
        hi = self.level_max.currentData()

        match_box = (
            self._loot_names is not None and self.match_box_check.isChecked()
        )
        loot_names: set[str] = self._loot_names or set()

        self.list_widget.clear()
        # Lazy-load box drop map once per rebuild. May be empty if no
        # box_drop_map.json has been generated yet — that's fine, tooltips
        # just won't show the "Drops from" line.
        drop_map = self._get_box_drop_map()
        for item in self._load_items_for_filters():
            name = item.get("name")
            if name is None:
                continue
            level = self._parse_level(str(item.get("level", "")))
            if lo is not None and level < lo:
                continue
            if hi is not None and level > hi:
                continue
            if match_box and str(name).strip().lower() not in loot_names:
                continue
            # Stats field comes from the per-combo cache file (stamped at
            # scrape time by scraper._enrich_items_with_stats). No separate
            # detail cache; just read what _load_items_for_filters gave us.
            line1 = f"{item.get('id')} · {name} ({item.get('rarity', '')})"
            stats_line = _format_stats_compact(item.get("stats"))
            text = f"{line1}\n{stats_line}" if stats_line else line1
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item.get("id"))
            # Style per-item: rarity color as background tint + tooltip with drops.
            rarity_color = str(item.get("rarity_color", "")).strip()
            if rarity_color:
                bg = self._tinted_bg(rarity_color)
                list_item.setBackground(QBrush(QColor(bg)))
            image_url = str(item.get("image", "")).strip()
            if image_url:
                list_item.setToolTip(self._build_tooltip(item, drop_map))
                # Async fetch the icon (lands later via _apply_icon).
                item_id_int = int(item.get("id", 0))
                if item_id_int:
                    self._image_cache.request(image_url, item_id_int)
            else:
                list_item.setToolTip(self._build_tooltip(item, drop_map))
            self.list_widget.addItem(list_item)
        self._apply_search(self.search.text())
        self._update_count()

        # Update the scoped-loot banner so the user sees exactly which item
        # names were extracted from the box — and warns when no gear in the
        # cache matches any of them (so the picker would show 0 items).
        self._update_scope_banner()

    def _update_count(self) -> None:
        visible = sum(1 for i in range(self.list_widget.count())
                      if not self.list_widget.item(i).isHidden())
        total = self.list_widget.count()
        if visible == total:
            self.count_label.setText(f"{total} items")
        else:
            self.count_label.setText(f"{visible} of {total} items")

    def _update_scope_banner(self) -> None:
        """Render the box-loot scope banner.

        Shows the gear names extracted from the box loot table so the user
        understands WHY certain items appear (and others don't). Warns when
        the scope is on but the list is empty — the most common cause is
        the box's gear names not matching any gear cache entries (e.g. the
        loot uses base ids whose rarity variants live under different names).
        """
        if self._loot_names is None:
            self.scope_banner.setVisible(False)
            return
        match_box = self.match_box_check.isChecked()
        names_sorted = sorted(self._loot_names)
        if not names_sorted:
            self.scope_banner.setVisible(False)
            return
        # Cap displayed names to keep the banner tidy (full set in tooltip).
        preview = ", ".join(names_sorted[:6])
        if len(names_sorted) > 6:
            preview += f", … (+{len(names_sorted) - 6} more)"
        visible_count = sum(
            1 for i in range(self.list_widget.count())
            if not self.list_widget.item(i).isHidden()
        )
        if not match_box:
            text = (
                f"📦 Box loot scope OFF — checkbox below to filter. "
                f"Box drops these gear: {preview}"
            )
            color = "#8a92a6"  # grey when scope disabled
        elif visible_count == 0:
            text = (
                f"⚠ No gear cache entries match the box's loot names. "
                f"Box drops: {preview}. "
                f"Try 'Scrape gear' or uncheck the scope filter."
            )
            color = "#e06c75"  # red warning
        else:
            text = (
                f"📦 Showing {visible_count} gear from box loot "
                f"({len(names_sorted)} unique names): {preview}"
            )
            color = "#98c379"  # green when scope working
        self.scope_banner.setText(text)
        # Keep background tint, override only text color.
        self.scope_banner.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 6px 8px; "
            f"background: rgba(127, 132, 156, 0.08); border-radius: 4px;"
        )
        self.scope_banner.setToolTip(
            "Box loot gear names (case-insensitive match):\n  • "
            + "\n  • ".join(names_sorted)
        )
        self.scope_banner.setVisible(True)

    # -------------------------------------------------------------- level ops
    def _populate_level_options(self) -> None:
        """Populate the level_min / level_max dropdowns with distinct levels
        present in the cache files matching the current category+grade filter.

        "All" is always the first option (UserData=None = no filter). Other
        entries are sorted by numeric level, lowest to highest. Preserves the
        current selection where possible.
        """
        levels = self._collect_levels()
        # Block signals so re-populating doesn't fire _rebuild recursively.
        for combo, current in (
            (self.level_min, self.level_min.currentData()),
            (self.level_max, self.level_max.currentData()),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("All", None)  # userData=None = no filter
            for lv in levels:
                combo.addItem(f"Lv{lv}", lv)
            # Restore previous selection if that level still exists.
            if current is not None and current in levels:
                idx = combo.findData(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def _collect_levels(self) -> list[int]:
        """Distinct levels across all cache files matching the current
        category+grade filter, sorted ascending.
        """
        levels: set[int] = set()
        for item in self._load_items_for_filters():
            levels.add(self._parse_level(str(item.get("level", ""))))
        return sorted(levels)

    def _apply_level_hint(self, level: int) -> None:
        """Pick dropdowns nearest to *level* (within _LEVEL_TOLERANCE). If no
        exact-or-close level exists in the dropdowns yet, pick the closest.
        """
        levels = self._collect_levels()
        if not levels:
            return
        # Pick the closest level to (level - tolerance) and (level + tolerance).
        target_lo = max(1, level - _LEVEL_TOLERANCE)
        target_hi = min(100, level + _LEVEL_TOLERANCE)
        lo = min(levels, key=lambda lv: abs(lv - target_lo))
        hi = min(levels, key=lambda lv: abs(lv - target_hi))
        # If both clamps land on the same level, expand hi to the next level
        # up so the dropdowns always represent a non-empty bracket.
        if lo == hi:
            higher = [lv for lv in levels if lv > lo]
            if higher:
                hi = higher[0]
            else:
                # Nothing higher — fall back to "All" on hi (no upper bound).
                hi = None
        self.level_min.setCurrentIndex(self.level_min.findData(lo))
        if hi is not None:
            self.level_max.setCurrentIndex(self.level_max.findData(hi))
        else:
            # -1 = "All" entry, which has userData=None
            self.level_max.setCurrentIndex(0)

    # ----------------------------------------------------------- styling/tooltip
    @staticmethod
    def _tinted_bg(rarity_color: str) -> QColor:
        """Return a soft background tint derived from a rarity hex color.

        Mixes the rarity color with a near-transparent alpha so the dark theme
        stays readable. Common = grey, Uncommon = green, etc.
        """
        try:
            base = QColor(rarity_color)
        except Exception:
            return QColor(60, 60, 70)
        # If the rarity color is very light (greyscale), return as-is but
        # with low alpha so it doesn't blow out the text.
        lightness = (base.red() + base.green() + base.blue()) / 3
        if lightness > 200:
            return QColor(80, 80, 90, 120)
        return QColor(base.red(), base.green(), base.blue(), 70)

    def _get_box_drop_map(self) -> dict[int, list[dict[str, Any]]]:
        """Lazy-load the box drop map (cached to disk). Empty dict if absent."""
        return read_box_drop_cache(BOX_DROP_MAP_CACHE)

    def _apply_icon(self, item_id: int, icon) -> None:
        """Apply an icon to the matching list item when the async fetch lands.

        Linear scan is fine — the list is typically a few hundred items at
        most, and icons arrive one at a time on the GUI thread.
        """
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            if li.data(Qt.ItemDataRole.UserRole) == item_id:
                li.setIcon(icon)
                break

    def _build_tooltip(
        self, item: dict[str, Any], drop_map: dict[int, list[dict[str, Any]]]
    ) -> str:
        """Compose a multi-line HTML tooltip with item info + drop sources.

        Format:
          <b>{name}</b> · {rarity} · {level}<br>
          <i>{type}</i><br>
          <br>
          {flavor if known}<br>
          <br>
          <b>Drops from:</b><br>
          · {box_name} (Lv-{level_hint}, {rate})<br>
          · ...
        Returns plain "id · name" if no extra info is available.
        """
        item_id = item.get("id", 0)
        name = item.get("name", "")
        rarity = item.get("rarity", "")
        level = item.get("level", "")
        gear_type = item.get("type", "")
        lines = [f"<b>{name}</b> · {rarity} · {level}"]
        if gear_type:
            lines.append(f"<i>{gear_type}</i>")
        # Drops from — most useful info for the user's "where to grind" question.
        drops = drop_map.get(int(item_id), []) if isinstance(item_id, int) else []
        if drops:
            lines.append("")
            lines.append("<b>Drops from:</b>")
            for d in drops[:5]:  # cap at 5 to keep tooltip manageable
                box_name = d.get("box_name") or f"Box {d.get('box_id', '?')}"
                box_id = d.get("box_id", "?")
                rate = d.get("rate", "")
                lines.append(f"· {box_name} (#{box_id}, {rate})")
            if len(drops) > 5:
                lines.append(f"· …and {len(drops) - 5} more")
        else:
            lines.append("")
            lines.append("<i>(Drop source not in cache — re-scrape boxes to populate)</i>")
        return "<br>".join(lines).replace("<br><br><br>", "<br><br>")

    @staticmethod
    def _parse_level(meta_level: str) -> int:
        """Parse ``"Lv65"`` -> 65. Empty/unparseable -> 0 (excluded when min>=1).
        """
        s = meta_level.strip()
        if s.startswith("Lv"):
            s = s[2:].strip()
        try:
            return int(s)
        except ValueError:
            return 0

    def _apply_search(self, text: str) -> None:
        """Toggle item visibility by name/id substring. Empty text shows all."""
        text = text.strip().lower()
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            item_id = list_item.data(Qt.ItemDataRole.UserRole)
            # item text is "id · name (rarity)"; match against name and id.
            label = list_item.text()
            name = label.split(" · ", 1)[1] if " · " in label else ""
            match = text in name.lower() or text in str(item_id)
            list_item.setHidden(not match if text else False)
        self._update_count()


class GearPicker(QDialog):
    """Thin dialog shim around :class:`GearView`. Kept so legacy callers
    (and the existing test suite) continue to compile unchanged.

    All UI attributes (``category``, ``grade``, ``level_min``, ``level_max``,
    ``match_box_check``, ``search``, ``scope_banner``, ``list_widget``,
    ``count_label``) are exposed via property forwarding to the embedded
    ``GearView``, so existing tests that poke them directly still pass.
    """

    def __init__(
        self,
        cache_dir: Path,
        parent=None,
        *,
        box_loot: list[dict[str, Any]] | None = None,
        level_hint: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pick gear")
        self.resize(540, 640)

        self._view = GearView(
            cache_dir, self, box_loot=box_loot, level_hint=level_hint
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self._view)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------------------------------------------------------- forwarded API
    # Each attribute is forwarded to the embedded GearView so legacy callers
    # (including the existing test suite) can interact with the picker the
    # same way they did before the extraction.
    @property
    def category(self) -> QComboBox:
        return self._view.category

    @property
    def grade(self) -> QComboBox:
        return self._view.grade

    @property
    def level_min(self) -> QComboBox:
        return self._view.level_min

    @property
    def level_max(self) -> QComboBox:
        return self._view.level_max

    @property
    def match_box_check(self) -> QCheckBox:
        return self._view.match_box_check

    @property
    def search(self) -> QLineEdit:
        return self._view.search

    @property
    def scope_banner(self) -> QLabel:
        return self._view.scope_banner

    @property
    def list_widget(self) -> QListWidget:
        return self._view.list_widget

    @property
    def count_label(self) -> QLabel:
        return self._view.count_label

    def selected_ids(self) -> list[int]:
        return self._view.selected_ids()
