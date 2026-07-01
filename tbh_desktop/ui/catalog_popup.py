"""Catalog popup — unified single-page catalog with stage-aware filtering.

Jul 2026: replaced box-based filtering with stage-based filtering.

Flow (the new "stage-first" UX)
-------------------------------

1. CatalogPopup is triggered from a rule card / range form.
2. A stage dropdown sits above the search box. Optional — defaults
   to "All stages" so users can still browse the full catalog.
3. Selecting a stage restricts the result list to items that drop
   from that stage (using ``stage_drop_map.json``).
4. Range replacement is unconstrained: pickers show ALL obtainable
   items regardless of stage (user can freely choose any item with
   ``obtainable_in_live_game=true`` as a replacement target).

Data sources
------------

* ``gear_cache_dir`` (``tbh_desktop/gear/<cat>/<grade>.json``) — LEG+
  obtainable gear split by slot + rarity (user-requested: Legendary
  ke atas only, obtainable-only checkbox applied).
* ``drops_index_path`` (``items_normalized.json``) — full tbh.city
  item index, normalized (115 MATERIAL + 5760 GEAR).
* ``stage_drop_map_path`` (``stage_drop_map.json``) — reverse map
  item_id -> [stage entries]. Drives the stage dropdown contents
  and the "filter by stage drops" behavior.

Layout
------

    CatalogPopup (QMenu)
      └── CatalogContent (QWidget)
            ├── Stage dropdown (All / Act 1 / Act 2 / Act 3 / Each stage)
            ├── QLineEdit   [search by name/id]
            ├── Filter row: [All] [Gear] [Materials]
            └── QListWidget  [rarity-tinted rows]
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QPoint,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
)
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from tbh_desktop.ui.theme import MOCHA, RARITY, rarity_tint
from PySide6.QtGui import QFont


# Catalog row font: 12pt for readability (was 10pt before — small
# text + gray-on-dark foreground made COMMON-tier rows nearly
# invisible). All rows share this font so the list has a uniform
# height regardless of which chip the user selects.
_ROW_FONT = QFont()
_ROW_FONT.setPointSize(12)


# Filter chips — two sections so gear and materials stay separated.
#   * Gear chips:   All / Weapon / Off-hand / Armor / Accessory
#     (slot_category from _SLOT_PREFIX_TO_CATEGORY in tbh_city.py).
#   * Item chips:   All / Crafting / Decoration / Engraving / Inscription /
#     Offering / Soulstone (material family from name + stat_types
#     heuristic — see _MATERIAL_FAMILY_KEYWORDS in tbh_city.py).
# The "kind" axis (gear vs material) is implicit in which section's
# chip row the user is interacting with; it isn't a separate chip.
_GEAR_FILTERS: list[tuple[str, str | None]] = [
    ("All",        None),
    ("Weapon",     "Weapon"),
    ("Off-hand",   "Off-hand"),
    ("Armor",      "Armor"),
    ("Accessory",  "Accessory"),
]
_ITEM_FILTERS: list[tuple[str, str | None]] = [
    ("All",          None),
    ("Crafting",     "CRAFTING"),
    ("Decoration",   "DECORATION"),
    ("Engraving",    "ENGRAVING"),
    ("Inscription",  "INSCRIPTION"),
    ("Offering",     "OFFERING"),
    ("Soulstone",    "SOULSTONE"),
]


# Stage dropdown grouping — act-level groups keep the dropdown short.
# "All stages" = no filter (range replacement flow). Picking a specific
# stage restricts the result list to items that drop there. Stage types
# (Normal / Boss / Act) match the rule_card's STAGE_TYPES enum.
_STAGE_GROUP_LABELS: dict[int, str] = {1: "Act 1", 2: "Act 2", 3: "Act 3"}

# Used in dropdown labels to distinguish stage kinds: regular stages get
# "#1", "#2", ... and act-boss stages get "Boss #10".
_STAGE_TYPE_LABEL: dict[str, str] = {
    "NORMAL": "stage",
    "BOSS": "boss stage",  # rare — single monster stage
    "ACTBOSS": "Boss",
}


class CatalogContent(QWidget):
    """Single-page catalog: stage dropdown + search + 3 filter chips + result list.

    Emits ``item_picked(int)`` when the user clicks a row. The picker
    carries no knowledge of the active rule — that's MainWindow's job.
    """

    item_picked = Signal(int)
    items_picked = Signal(list)

    def __init__(
        self,
        gear_cache_dir: Any,
        drops_index_path: Any,
        stage_drop_map_path: Any,
        stages_index_path: Any,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("catalog_content")
        self._gear_dir = Path(gear_cache_dir)
        self._drops_path = Path(drops_index_path)
        self._drop_map_path = Path(stage_drop_map_path)
        self._stages_index_path = Path(stages_index_path)

        self._all_items: list[dict[str, Any]] = []
        self._stage_drop_map: dict[int, list[dict[str, Any]]] = {}
        self._stages_index: list[dict[str, Any]] = []
        # When non-None, restrict the visible catalog to this id set.
        # main_window sets this for PoolRule replacement picks (so users
        # can't pick items that don't drop in the chosen pool). Pool
        # picker passes None so the full catalog stays browseable.
        self._allowed_item_ids: set[int] | None = None
        self._load_items()
        self._load_stage_data()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ---- Header -----------------------------------------------------
        title = QLabel("Catalog")
        title.setObjectName("panel_heading")
        title.setStyleSheet(
            f"color: {MOCHA['subtext']}; font-family: 'Cinzel', serif;"
            f" font-size: 11px; font-weight: 700; letter-spacing: 3px;"
            f" padding: 0 0 2px 0;"
        )
        outer.addWidget(title)

        # ---- Stage dropdown -------------------------------------------
        # Drives the "filter to items dropped by this stage" behavior.
        # Default is "All stages" (== no filter), which is the range
        # replacement flow.
        stage_row = QHBoxLayout()
        stage_row.setSpacing(6)
        stage_label = QLabel("Stage:")
        stage_label.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 10px;")
        stage_row.addWidget(stage_label)
        self.stage_combo = QComboBox()
        self.stage_combo.setMinimumWidth(220)
        self.stage_combo.setToolTip(
            "Filter items to those that drop from this stage.\n"
            "Use 'All stages' for range replacement (any obtainable item)."
        )
        self._populate_stage_combo()
        self.stage_combo.currentIndexChanged.connect(self._rebuild)
        stage_row.addWidget(self.stage_combo, stretch=1)
        outer.addLayout(stage_row)

        # ---- Search ----------------------------------------------------
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name or id…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._rebuild)
        outer.addWidget(self.search)

        # ---- Filter chips: two sections (Gear + Items) -----------------
        # Two independent rows so a click on a Gear chip doesn't
        # deselect the active Item chip (and vice versa). Each row has
        # its own radio-style selection. The section label above each
        # row makes it obvious which kind the chips belong to.
        # Each row is wrapped in a QWidget so the caller can show/hide
        # the whole axis when picking a single category (gear vs item).
        gear_section = QWidget()
        gear_section.setObjectName("catalog_gear_section")
        gear_chip_row = QHBoxLayout(gear_section)
        gear_chip_row.setContentsMargins(0, 0, 0, 0)
        gear_chip_row.setSpacing(6)
        gear_section_label = QLabel("Gear")
        gear_section_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 2px; padding-right: 6px;"
        )
        gear_chip_row.addWidget(gear_section_label)
        self._gear_filter_buttons: list[QPushButton] = []
        for label, slot_cat in _GEAR_FILTERS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("toolbar_zone", "secondary")
            btn.setProperty("filter_axis", "gear")
            btn.setProperty("filter_value", slot_cat or "")
            btn.setChecked(slot_cat is None)
            btn.clicked.connect(self._on_filter_clicked)
            gear_chip_row.addWidget(btn)
            self._gear_filter_buttons.append(btn)
        gear_chip_row.addStretch()
        outer.addWidget(gear_section)
        self._gear_section = gear_section

        item_section = QWidget()
        item_section.setObjectName("catalog_item_section")
        item_chip_row = QHBoxLayout(item_section)
        item_chip_row.setContentsMargins(0, 0, 0, 0)
        item_chip_row.setSpacing(6)
        item_section_label = QLabel("Items")
        item_section_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 2px; padding-right: 6px;"
        )
        item_chip_row.addWidget(item_section_label)
        self._item_filter_buttons: list[QPushButton] = []
        for label, family in _ITEM_FILTERS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("toolbar_zone", "secondary")
            btn.setProperty("filter_axis", "item")
            btn.setProperty("filter_value", family or "")
            btn.setChecked(family is None)
            btn.clicked.connect(self._on_filter_clicked)
            item_chip_row.addWidget(btn)
            self._item_filter_buttons.append(btn)
        item_chip_row.addStretch()
        outer.addWidget(item_section)
        self._item_section = item_section

        # ---- Stage filter chips visibility -------------------------------
        # The catalog popup is sometimes opened in two modes:
        #   * "gear" — only the Gear chip row is visible (the user
        #     is picking a gear replacement; they don't want to wade
        #     through materials).
        #   * "item" — only the Items chip row is visible (the user
        #     is picking a material replacement).
        #   * None    — both rows visible (legacy full catalog mode).
        self._axis_mode: str | None = None

        # ---- Result list ----------------------------------------------
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection
        )
        self.list_widget.setUniformItemSizes(True)
        # Parse inline HTML in each row's DisplayRole payload. Without
        # this QListWidget falls back to plain text and the user sees
        # raw '<span style="...">' literals (Jul 2026 bug).
        self.list_widget.setTextElideMode(Qt.TextElideMode.ElideRight)
        from PySide6.QtCore import Qt as _Qt
        # AutoFormattingText makes Qt detect simple markup at setText time.
        # RichText would force every item to be HTML. The default
        # DisplayRole we write is HTML, so set the view to accept that.
        self.list_widget.setWordWrap(False)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        self.list_widget.itemClicked.connect(self._on_click)
        outer.addWidget(self.list_widget, stretch=1)

        # ---- Status footer --------------------------------------------
        self.count_label = QLabel("0 items")
        self.count_label.setObjectName("catalog_count_label")
        # Higher contrast than MOCHA['overlay1'] (which sits at ~50%
        # luminance) — subtext is more readable against the dark base
        # and matches the row body text.
        self.count_label.setStyleSheet(
            f"color: {MOCHA['subtext']}; font-size: 11px; padding-top: 2px;"
        )
        outer.addWidget(self.count_label)

        self._rebuild()

    # ---- public API --------------------------------------------------
    def visible_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for i in range(self.list_widget.count()):
            data = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                items.append(data)
        return items

    def selected_ids(self) -> list[int]:
        return [
            it.data(Qt.ItemDataRole.UserRole)["id"]
            for it in self.list_widget.selectedItems()
            if isinstance(it.data(Qt.ItemDataRole.UserRole), dict)
        ]

    def set_stage_filter(self, stage_id: int | None) -> None:
        """Pre-select a stage from outside (e.g. when triggered from a rule)."""
        if stage_id is None:
            self.stage_combo.setCurrentIndex(0)
            return
        idx = self.stage_combo.findData(stage_id)
        if idx >= 0:
            self.stage_combo.setCurrentIndex(idx)

    def set_axis_mode(self, axis: str | None) -> None:
        """Hide one of the two chip rows so the popup pre-scopes to a
        single replacement category.

          * ``"gear"`` — only the Gear chip row is visible; the Items
            row is hidden entirely (no 'All materials' button visible
            either, so the user can't accidentally pick a material
            when picking gear).
          * ``"item"`` — only the Items chip row is visible; the Gear
            row is hidden.
          * ``None``    — both rows visible (legacy combined picker).

        The chip buttons also default to 'All' on the visible axis
        so the list starts unfiltered within that category.
        """
        self._axis_mode = axis
        self._gear_section.setVisible(axis != "item")
        self._item_section.setVisible(axis != "gear")
        # Reset chip state on both axes so no stale filter lingers.
        for btn in self._gear_filter_buttons:
            btn.setChecked(False)
        for btn in self._item_filter_buttons:
            btn.setChecked(False)
        # Pre-select "All" on whichever axis is visible.
        if axis == "gear" and self._gear_filter_buttons:
            self._gear_filter_buttons[0].setChecked(True)
        elif axis == "item" and self._item_filter_buttons:
            self._item_filter_buttons[0].setChecked(True)
        self._rebuild()

    def current_stage_id(self) -> int | None:
        data = self.stage_combo.currentData()
        return int(data) if isinstance(data, int) else None

    def set_allowed_item_ids(self, ids: list[int] | None) -> None:
        """Restrict the visible catalog to a fixed set of item ids.

        Used by ``main_window`` when the active target is a PoolRule:
        replacement IDs must be drawn from that pool's drop table
        (per user feedback), so the picker is scoped to the matching
        item_ids instead of the full catalog. ``None`` clears the
        restriction (range replacement flow + the pool picker itself).
        """
        self._allowed_item_ids: set[int] | None = (
            {int(i) for i in ids} if ids is not None else None
        )
        self._rebuild()

    # ---- data loading -----------------------------------------------
    def _load_items(self) -> None:
        """Merge gear cache + items_normalized.json into one flat catalog.

        Gear entries get kind="gear". Material entries get kind="material".
        No more "box" kind — boxes were a proxy for "which stages drop this"
        in the old taskbarhero.org world; the stage dropdown now provides
        that context directly.

        Jul 2026: the gear cache (``gear/<cat>/<rarity>.json``) and
        ``items_normalized.json`` both contain the LEG+ gear set — the
        cache was scraped before the tbh.city migration, the index
        after. We deduplicate by item id (first occurrence wins, gear
        cache wins over the index since it has the slot_category split
        the index doesn't carry), so the catalog list never shows the
        same item twice.
        """
        items: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        def _append(entry: dict[str, Any]) -> None:
            iid = int(entry.get("id", 0))
            if iid <= 0 or iid in seen_ids:
                return
            seen_ids.add(iid)
            items.append(entry)

        # Gear cache: one JSON per category in gear/<cat>/<rarity>.json.
        # Loaded FIRST so the gear cache's slot_category / slot_type
        # values win over the (rarity-only) info in items_normalized.
        if self._gear_dir.exists():
            for path in self._gear_dir.glob("*/*.json"):
                try:
                    entries = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(entries, list):
                    continue
                category = path.parent.name
                for e in entries:
                    if not isinstance(e, dict) or "id" not in e:
                        continue
                    _append({
                        "id": int(e["id"]),
                        "name": str(e.get("name", f"#{e['id']}")),
                        "kind": "gear",
                        "category": category,
                        "rarity": str(e.get("rarity", e.get("grade", "COMMON"))).upper(),
                        "obtainable": bool(e.get("obtainable", True)),
                        "slot_category": category.title(),  # gear/<cat>/<grade>.json — cat == weapon/offhand/...
                        "slot_type": str(e.get("type", "")),
                        "family": "",
                    })

        # Materials + any non-gear from items_normalized.json. Gear
        # items here are deduplicated against the cache above.
        if self._drops_path.exists():
            try:
                payload = json.loads(self._drops_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = []
            if isinstance(payload, dict):
                payload = payload.get("items", [])
            if isinstance(payload, list):
                for e in payload:
                    if not isinstance(e, dict) or "id" not in e:
                        continue
                    kind = str(e.get("type", "material")).lower()
                    # tbh.city normalizes 'GEAR' → type="GEAR", 'MATERIAL' → "MATERIAL"
                    kind = "gear" if kind == "gear" else "material"
                    _append({
                        "id": int(e["id"]),
                        "name": str(e.get("name", f"#{e['id']}")),
                        "kind": kind,
                        "rarity": str(e.get("grade", e.get("rarity", "COMMON"))).upper(),
                        "obtainable": bool(e.get("obtainable", True)),
                        "slot_category": "",  # materials don't have slots
                        "slot_type": "",
                        "family": str(e.get("family", "CRAFTING")).upper(),
                    })

        # Sort: rarity desc (COSMIC→COMMON), then by name.
        rarity_order = {
            "COSMIC": 0, "DIVINE": 1, "CELESTIAL": 2, "BEYOND": 3,
            "ARCANA": 4, "IMMORTAL": 5, "LEGENDARY": 6,
            "RARE": 7, "UNCOMMON": 8, "COMMON": 9,
        }
        items.sort(key=lambda it: (
            rarity_order.get(it.get("rarity", "COMMON"), 99),
            it.get("name", "").lower(),
        ))
        self._all_items = items

    def _load_stage_data(self) -> None:
        """Load stage_drop_map.json + stages_index.json for the dropdown."""
        if self._drop_map_path.exists():
            try:
                payload = json.loads(self._drop_map_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict):
                drops = payload.get("drops") or {}
                if isinstance(drops, dict):
                    for k, v in drops.items():
                        try:
                            self._stage_drop_map[int(k)] = v if isinstance(v, list) else []
                        except (ValueError, TypeError):
                            continue
        if self._stages_index_path.exists():
            try:
                payload = json.loads(self._stages_index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict):
                stages = payload.get("stages") or []
                if isinstance(stages, list):
                    self._stages_index = [s for s in stages if isinstance(s, dict)]

    def _populate_stage_combo(self) -> None:
        """Build the stage dropdown grouped by Act.

        Layout: [All stages] [Act 1 separator] [stage rows] ... [Act 3] ...
        Each entry stores the stage id in user data (or -act for separator).
        Empty stages (zero drops) are still listed so users can preview
        them; the rebuild filter handles the "only with drops" check
        separately.
        """
        self.stage_combo.clear()
        self.stage_combo.addItem("All stages", userData=None)
        by_act: dict[int, list[dict[str, Any]]] = {1: [], 2: [], 3: []}
        for s in self._stages_index:
            act = s.get("act")
            if act in by_act:
                by_act[act].append(s)
        from PySide6.QtGui import QStandardItem
        combo_model = self.stage_combo.model()
        for act in (1, 2, 3):
            if not by_act[act]:
                continue
            # Section header (non-selectable).
            self.stage_combo.addItem(f"── {_STAGE_GROUP_LABELS[act]} ──", userData=-act)
            sep_idx = self.stage_combo.count() - 1
            sep_item = combo_model.item(sep_idx)
            if isinstance(sep_item, QStandardItem):
                sep_item.setEnabled(False)
            by_act[act].sort(key=lambda s: (
                s.get("stage_no", 99),
                {"NORMAL": 0, "NIGHTMARE": 1, "HELL": 2, "TORMENT": 3}.get(s.get("difficulty", ""), 9),
            ))
            for s in by_act[act]:
                sid = s.get("id")
                if not isinstance(sid, int):
                    continue
                name = s.get("name") or {}
                if isinstance(name, dict):
                    name = name.get("en") or next(iter(name.values()), str(sid))
                diff = (s.get("difficulty") or "").title()
                type_lbl = "Boss" if s.get("type") == "ACTBOSS" else f"#{s.get('stage_no')}"
                label = f"{_STAGE_GROUP_LABELS[act]} {type_lbl} {name} ({diff})"
                self.stage_combo.addItem(label, userData=sid)

    # ---- rebuild + interactions --------------------------------------
    def _active_filter(self, axis: str) -> str:
        """Return the currently-selected value for one filter axis
        ("gear" or "item"). Empty string = "All".
        """
        buttons = (
            self._gear_filter_buttons if axis == "gear"
            else self._item_filter_buttons
        )
        for btn in buttons:
            if btn.isChecked():
                return str(btn.property("filter_value") or "")
        return ""

    def _on_filter_clicked(self) -> None:
        clicked = self.sender()
        # Radio-style within the clicked axis only — the other axis's
        # selection is preserved so users can scope both at once.
        for btn in self._gear_filter_buttons + self._item_filter_buttons:
            if btn.property("filter_axis") == clicked.property("filter_axis"):
                btn.setChecked(btn is clicked)
        self._rebuild()

    def _rebuild(self) -> None:
        # Two independent filter axes:
        #   * gear_axis ("Weapon" / "Off-hand" / "Armor" / "Accessory" / "")
        #   * item_axis ("CRAFTING" / "DECORATION" / ... / "")
        # Items with type=GEAR only respect the gear axis; items with
        # type=MATERIAL only respect the item axis. An item is visible
        # iff its own axis matches its filter (or the filter is empty).
        gear_axis = self._active_filter("gear")
        item_axis = self._active_filter("item")
        text = self.search.text().strip().lower()
        stage_id = self.current_stage_id()

        # Resolve the set of item_ids to include. ``_allowed_item_ids``
        # (set by main_window for pool-scoped replacement picks) wins
        # over the stage-derived filter.
        allowed_ids: set[int] | None
        if self._allowed_item_ids is not None:
            allowed_ids = set(self._allowed_item_ids)
        else:
            allowed_ids = None
            if isinstance(stage_id, int):
                entries = self._stage_drop_map.get(stage_id, [])
                allowed_ids = {
                    int(e["item_id"]) for e in entries
                    if isinstance(e, dict) and isinstance(e.get("item_id"), int)
                }
                if not allowed_ids:
                    allowed_ids = set()  # explicit empty so the filter rejects all

        self.list_widget.clear()
        shown = 0
        for it in self._all_items:
            # Apply the right axis based on the item's own kind. GEAR
            # items respect the gear_axis filter; MATERIAL items respect
            # the item_axis filter. Either axis empty = "show all".
            item_kind = str(it.get("kind", "")).lower()
            if item_kind == "gear" and gear_axis:
                if str(it.get("slot_category", "")) != gear_axis:
                    continue
            elif item_kind == "material" and item_axis:
                if str(it.get("family", "")).upper() != item_axis:
                    continue
            if allowed_ids is not None and int(it.get("id", -1)) not in allowed_ids:
                continue
            if text:
                hay_name = it.get("name", "").lower()
                hay_id = str(it.get("id", ""))
                if text not in hay_name and text not in hay_id:
                    continue
            self._add_row(it)
            shown += 1
        suffix = "" if allowed_ids is None else f" · stage #{stage_id}"
        self.count_label.setText(f"{shown} item{'s' if shown != 1 else ''}{suffix}")

    def _add_row(self, item: dict[str, Any]) -> None:
        """Render one item as a high-contrast row.

        Earlier revisions tried to use inline HTML (DisplayRole = markup)
        for per-row styling, but PySide6 6.11's default QListWidget
        delegate ignores the markup and dumps the raw `<span>` tags to
        the user — they end up staring at literal HTML in the catalog
        list. Render as plain text instead and apply colour via
        ``setForeground`` (one brush per item; Qt supports foreground
        colour on plain text rows out of the box).

        The previous version set ``setForeground(rarity_color)`` for
        the whole line, which made COMMON-tier rows (gray text) almost
        invisible on the dark Mocha base. Now we always render the
        body in the bright text color and use the rarity color only
        for the rarity bracket at the end of the line — so the line
        stays legible while still signalling rarity at a glance.
        """
        item_id = int(item.get("id", 0))
        name = str(item.get("name", f"#{item_id}"))
        rarity_raw = str(item.get("rarity", "COMMON")).upper()
        rarity_title = rarity_raw.title()
        rarity_color = RARITY.get(rarity_raw, RARITY["COMMON"])

        # Plain-text line: `   #id    name   [RARITY]`
        # (rarity bracket uses the rarity's accent color).
        list_item = QListWidgetItem(f"#{item_id:>6}   {name}   [{rarity_title}]")
        list_item.setData(Qt.ItemDataRole.UserRole, item)
        list_item.setData(
            Qt.ItemDataRole.ToolTipRole, self._format_tooltip(item),
        )
        # Make sure the view shows plain text — display role is plain
        # so Qt's default delegate renders it correctly. (An earlier
        # revision wrote HTML to DisplayRole and it leaked as literal
        # tags on screen; this is the safe path.)
        list_item.setFont(_ROW_FONT)
        # Render the rarity bracket in the rarity's accent colour by
        # setting the foreground to a neutral text color and then
        # attaching a QTextCharFormat via AccessibleTextRole + a
        # custom delegate would be overkill. Instead, lean on the
        # rarity color for the WHOLE row when the row is high-tier
        # (the original design), but ALWAYS legible for low tiers:
        rarity_rank = {
            "COMMON": 0, "UNCOMMON": 1, "RARE": 2,
            "LEGENDARY": 3, "IMMORTAL": 4, "ARCANA": 5, "BEYOND": 6,
            "CELESTIAL": 7, "DIVINE": 8, "COSMIC": 9,
        }
        rank = rarity_rank.get(rarity_raw, 0)
        if rank <= 2:
            # Low-tier rows: bright text for legibility, regardless of
            # rarity color (Common / Uncommon / Rare were near-invisible
            # in the previous gray-on-dark design).
            list_item.setForeground(QBrush(QColor(MOCHA["text"])))
        else:
            # High-tier rows: rarity color IS the text color — it's
            # bright enough on the dark base to stay legible, and the
            # color communicates the tier at a glance.
            list_item.setForeground(QBrush(QColor(rarity_color)))

        self.list_widget.addItem(list_item)

    def _format_tooltip(self, item: dict[str, Any]) -> str:
        lines = [f"<b>{item.get('name', '?')}</b> · id {item.get('id')}"]
        if item.get("rarity"):
            lines.append(f"Rarity: <b>{item['rarity'].title()}</b>")
        if item.get("kind"):
            lines.append(f"Kind: {item['kind'].title()}")
        return "<br>".join(lines)

    def _on_click(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and "id" in data:
            self.item_picked.emit(int(data["id"]))

    def _on_double_click(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and "id" in data:
            self.item_picked.emit(int(data["id"]))


class CatalogPopup(QMenu):
    """Toolbar-triggered catalog popup with single-page CatalogContent.

    The popup hosts a CatalogContent widget (stage dropdown + search +
    3 filter chips + flat result list) inside a QWidgetAction. Picking
    a row emits ``item_picked``. MainWindow routes that into the
    active-target store (specific rule or range replacement).
    """

    item_picked = Signal(int)
    items_picked = Signal(list)

    def __init__(
        self,
        gear_cache_dir: Any,
        drops_index_path: Any,
        stage_drop_map_path: Any,
        stages_index_path: Any,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("catalog_popup")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumSize(560, 460)
        self.setMaximumSize(800, 620)

        self.content = CatalogContent(
            gear_cache_dir=gear_cache_dir,
            drops_index_path=drops_index_path,
            stage_drop_map_path=stage_drop_map_path,
            stages_index_path=stages_index_path,
            parent=self,
        )
        self._action = QWidgetAction(self)
        self._action.setDefaultWidget(self.content)
        self.addAction(self._action)

        self.content.item_picked.connect(self._capture_single)
        self.content.items_picked.connect(self._capture_multi)

        # After-exec results — set by _capture_* and read by the caller.
        self.last_picked_id: int | None = None
        self.last_picked_ids: list[int] = []

    def _capture_single(self, item_id: int) -> None:
        self.last_picked_id = int(item_id)
        self.close()

    def _capture_multi(self, item_ids: list) -> None:
        self.last_picked_ids = [int(i) for i in item_ids]
        self.close()

    # ---- mode-aware exec helpers -----------------------------------
    def exec_for_replacement(self, axis: str | None = None) -> bool:
        """Show the popup, let the user multi-select replacement ids.
        Returns True if any pick was made; check ``last_picked_ids``.

        ``axis`` (Jul 2026) pre-selects a filter chip row so the user
        opens the picker pre-scoped to a single category:
          * ``"gear"`` — only the Gear chip row is active (slot
            categories: Weapon / Off-hand / Armor / Accessory).
          * ``"item"`` — only the Items chip row is active (family
            categories: Crafting / Decoration / Engraving / Inscription /
            Offering / Soulstone).
          * ``None``    — both rows active (legacy combined picker).

        The rule detail panel uses the two pre-scoped modes so the
        user never has to wade through a mixed catalog when they only
        want gear, or only materials.
        """
        self.last_picked_id = None
        self.last_picked_ids = []
        if axis in ("gear", "item"):
            self.content.set_axis_mode(axis)
        else:
            self.content.set_axis_mode(None)
        self.popup_at()
        return bool(self.last_picked_ids)

    def exec_for_replacement_scoped(
        self,
        allowed_item_ids: list[int],
        axis: str | None = None,
    ) -> bool:
        """Show the popup, let the user pick replacements from a fixed
        id set (e.g. items that drop in the active rule's pool).

        Per user feedback (Jul 2026): pool rules must draw their
        replacement IDs from that pool's drop table — replacement
        candidates are restricted to ``allowed_item_ids``. Pass an
        empty list to disable the picker (no items eligible).

        ``axis`` mirrors ``exec_for_replacement`` — pre-selects a
        single filter chip row (gear / item) so the user doesn't
        wade through a mixed catalog.
        """
        self.last_picked_id = None
        self.last_picked_ids = []
        self.content.set_allowed_item_ids(allowed_item_ids or None)
        if axis in ("gear", "item"):
            self.content.set_axis_mode(axis)
        else:
            self.content.set_axis_mode(None)
        self.popup_at()
        return bool(self.last_picked_ids)

    def sizeHint(self) -> QSize:  # noqa: ANN001
        return QSize(580, 500)

    def popup_at(self, global_pos: QPoint | None = None) -> None:
        if global_pos is None:
            global_pos = QCursor.pos()
        self.content.show()
        super().popup(global_pos)