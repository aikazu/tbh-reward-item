"""Catalog popup — unified single-page catalog with filter chips.

Replaces the previous 6-tab ItemBrowser with a flat search-first
catalog. UX rationale:

- 6 tabs (Browse all / Box loot / Gear scoped / Gear all / Drops
  index / Boxes) forced the user to know which tab contained
  what they wanted. Most picks happen via search-by-name, so a
  tabbed nav is friction.
- A single search box + 4 filter chips (All / Gear / Materials /
  Boxes) covers every category without per-mode switching.
- Result list shows item name + ID + rarity + family inline so the
  user can identify each row at a glance.

Composition
-----------

    CatalogPopup (QMenu)
      └── CatalogContent (QWidget)
            ├── QLineEdit   [search by name/id]
            ├── Filter row: [All] [Gear] [Materials] [Boxes]
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
    QFont,
)
from PySide6.QtWidgets import (
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

from tbh_desktop.ui.theme import MOCHA, RARITY, chip_style, section_heading_style


# Filter categories — a single filter chip constrains the result
# list to items matching that kind. ``ALL`` shows everything.
_KIND_FILTERS: list[tuple[str, str | None]] = [
    ("All",       None),
    ("Gear",      "gear"),
    ("Materials", "material"),
    ("Boxes",     "box"),
]


class CatalogContent(QWidget):
    """Single-page catalog: search + 4 filter chips + flat result list."""

    item_picked = Signal(int)
    items_picked = Signal(list)

    def __init__(
        self,
        gear_cache_dir: Any,
        drops_index_path: Any,
        box_slug_cache_path: Any,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("catalog_content")
        self._gear_dir = Path(gear_cache_dir)
        self._drops_path = Path(drops_index_path)
        self._box_slug_path = Path(box_slug_cache_path)

        self._all_items: list[dict[str, Any]] = []
        self._load_items()

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

        # ---- Search -----------------------------------------------------
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name or id…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._rebuild)
        outer.addWidget(self.search)

        # ---- Filter chips ----------------------------------------------
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        self._filter_buttons: list[QPushButton] = []
        for label, kind in _KIND_FILTERS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("toolbar_zone", "secondary")
            btn.setProperty("kind_filter", kind or "all")
            btn.setChecked(kind is None)  # "All" starts selected
            btn.clicked.connect(self._on_filter_clicked)
            chip_row.addWidget(btn)
            self._filter_buttons.append(btn)
        chip_row.addStretch()
        outer.addLayout(chip_row)

        # ---- Result list ------------------------------------------------
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection
        )
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        # Single-click on a row emits a pick signal too — useful for
        # the user just selecting an item they want to add.
        self.list_widget.itemClicked.connect(self._on_click)
        outer.addWidget(self.list_widget, stretch=1)

        # ---- Status footer ---------------------------------------------
        self.count_label = QLabel("0 items")
        self.count_label.setObjectName("catalog_count_label")
        self.count_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; padding-top: 2px;"
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

    # ---- data loading ------------------------------------------------
    def _load_items(self) -> None:
        """Merge gear cache + drops index into one flat catalog."""
        items: list[dict[str, Any]] = []

        # Gear cache: one JSON per category in {cat}/{rarity}.json files.
        # Each entry has id / name / kind="gear" / rarity.
        if self._gear_dir.exists():
            for path in self._gear_dir.glob("*/*.json"):
                try:
                    entries = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(entries, list):
                    continue
                # Path like ``gear/weapon/legendary.json`` → category=weapon.
                category = path.parent.name
                for e in entries:
                    if not isinstance(e, dict) or "id" not in e:
                        continue
                    items.append({
                        "id": int(e["id"]),
                        "name": str(e.get("name", f"#{e['id']}")),
                        "kind": "gear",
                        "category": category,
                        "rarity": str(e.get("rarity", "COMMON")).upper(),
                    })

        # Drops index: flat list of materials + boxes. Each entry has
        # id / name / kind / rarity / family.
        if self._drops_path.exists():
            try:
                drops = json.loads(self._drops_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                drops = []
            if isinstance(drops, dict):
                drops = drops.get("items", [])
            if isinstance(drops, list):
                for e in drops:
                    if not isinstance(e, dict) or "id" not in e:
                        continue
                    items.append({
                        "id": int(e["id"]),
                        "name": str(e.get("name", f"#{e['id']}")),
                        "kind": str(e.get("kind", "material")).lower(),
                        "rarity": str(e.get("rarity", "COMMON")).upper(),
                        "family": str(e.get("family", "")),
                    })

        # Box slugs: each entry is id/slug/name; classify as "box".
        if self._box_slug_path.exists():
            try:
                boxes = json.loads(self._box_slug_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                boxes = []
            if isinstance(boxes, dict):
                boxes = list(boxes.values())
            if isinstance(boxes, list):
                for e in boxes:
                    if not isinstance(e, dict) or "id" not in e:
                        continue
                    items.append({
                        "id": int(e["id"]),
                        "name": str(e.get("name", e.get("slug", f"#{e['id']}"))),
                        "kind": "box",
                        "rarity": "COMMON",
                        "family": "",
                    })

        # Sort: rarity desc (COSMIC→COMMON), then by name.
        rarity_order = {
            "COSMIC": 0, "DIVINE": 1, "CELESTIAL": 2, "BEYOND": 3,
            "ARCANA": 4, "IMMORTAL": 5, "LEGENDARY": 6, "EPIC": 7,
            "RARE": 8, "UNCOMMON": 9, "MYTHIC": 10, "COMMON": 11,
        }
        items.sort(key=lambda it: (
            rarity_order.get(it.get("rarity", "COMMON"), 99),
            it.get("name", "").lower(),
        ))
        self._all_items = items

    # ---- rebuild + interactions --------------------------------------
    def _active_kind_filter(self) -> str | None:
        for btn in self._filter_buttons:
            if btn.isChecked():
                kind = btn.property("kind_filter")
                return None if kind == "all" else kind
        return None

    def _on_filter_clicked(self) -> None:
        # Make the clicked button exclusive — only one filter at a time.
        clicked = self.sender()
        for btn in self._filter_buttons:
            if btn is clicked:
                btn.setChecked(True)
            else:
                btn.setChecked(False)
        self._rebuild()

    def _rebuild(self) -> None:
        kind = self._active_kind_filter()
        text = self.search.text().strip().lower()

        self.list_widget.clear()
        shown = 0
        for it in self._all_items:
            if kind is not None and it.get("kind") != kind:
                continue
            if text:
                hay_name = it.get("name", "").lower()
                hay_id = str(it.get("id", ""))
                if text not in hay_name and text not in hay_id:
                    continue
            self._add_row(it)
            shown += 1
        self.count_label.setText(f"{shown} item{'s' if shown != 1 else ''}")

    def _add_row(self, item: dict[str, Any]) -> None:
        rarity = item.get("rarity", "COMMON").title()
        kind = item.get("kind", "other").title()
        family = item.get("family", "").title()
        # Single-line entry: rarity · kind · family · id · name.
        # Rarity-colored text so users can scan rarity at a glance.
        # Background tint matches rarity for high-rarity items only
        # (>=Legendary) so the eye lands on the good drops first.
        tags = [rarity, kind]
        if family:
            tags.append(family)
        tags_part = "  ·  ".join(t for t in tags if t)
        line = f"#{item['id']}  ·  {item['name']}  [{tags_part}]"

        list_item = QListWidgetItem(line)
        list_item.setData(Qt.ItemDataRole.UserRole, item)
        list_item.setToolTip(self._format_tooltip(item))

        rarity_color = RARITY.get(item.get("rarity", "COMMON"), RARITY["COMMON"])
        list_item.setForeground(QBrush(QColor(rarity_color)))
        # Background tint only for high-rarity rows — keeps the list
        # calm for the common case.
        rarity_rank = {
            "COMMON": 0, "UNCOMMON": 1, "RARE": 2, "EPIC": 3, "MYTHIC": 4,
            "LEGENDARY": 5, "IMMORTAL": 6, "ARCANA": 7, "BEYOND": 8,
            "CELESTIAL": 9, "DIVINE": 10, "COSMIC": 11,
        }
        if rarity_rank.get(item.get("rarity", "COMMON"), 0) >= 5:
            list_item.setBackground(QBrush(QColor(rarity_color)))
            list_item.setForeground(QBrush(QColor(MOCHA["crust"])))
        self.list_widget.addItem(list_item)

    def _format_tooltip(self, item: dict[str, Any]) -> str:
        lines = [f"<b>{item.get('name', '?')}</b> · id {item.get('id')}"]
        if item.get("rarity"):
            lines.append(f"Rarity: <b>{item['rarity'].title()}</b>")
        if item.get("kind"):
            lines.append(f"Kind: {item['kind'].title()}")
        if item.get("family"):
            lines.append(f"Family: {item['family']}")
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

    Replaces the previous 6-tab ItemBrowser + QDockWidget design.
    The popup hosts a CatalogContent widget (search + 4 filter chips
    + flat result list) inside a QWidgetAction — the proper Qt way
    to embed a widget in a menu.

    Picking a row emits ``item_picked`` (single click) or
    ``items_picked`` (for multi-selection if added later). MainWindow
    routes those into the active-target store the same way the
    previous dock version did.
    """

    item_picked = Signal(int)
    items_picked = Signal(list)

    def __init__(
        self,
        gear_cache_dir: Any,
        drops_index_path: Any,
        box_slug_cache_path: Any,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("catalog_popup")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        # Single-page catalog — single screen worth of content. Big
        # enough to read item names + filter chips without scrolling
        # the popup; small enough not to cover the editor.
        self.setMinimumSize(540, 420)
        self.setMaximumSize(780, 580)

        self.content = CatalogContent(
            gear_cache_dir=gear_cache_dir,
            drops_index_path=drops_index_path,
            box_slug_cache_path=box_slug_cache_path,
            parent=self,
        )
        self._action = QWidgetAction(self)
        self._action.setDefaultWidget(self.content)
        self.addAction(self._action)

        # Re-emit so MainWindow wires exactly as before.
        self.content.item_picked.connect(self.item_picked)
        self.content.items_picked.connect(self.items_picked)

    def sizeHint(self) -> QSize:  # noqa: ANN001
        return QSize(560, 460)

    def popup_at(self, global_pos: QPoint | None = None) -> None:
        if global_pos is None:
            global_pos = QCursor.pos()
        self.content.show()
        super().popup(global_pos)
