"""Dialog to pick gear reward IDs from per-category×grade cache files.

G4: rebuilds the list from ``GEAR_CACHE_DIR/gear_{cat}_{grade}.json`` files
matching the current Category/Grade/Level-range filters. Search box and
multi-select behaviour preserved from the original flat-list picker.

New in G4:
  - Optional ``box_loot`` list: when supplied, only gear whose ``name``
    matches one of the loot item names is shown (so the picker is scoped to
    the box the user is editing).  A "Show all gear" checkbox toggles this.
  - Optional ``level_hint``: pre-sets the level spinboxes to the box's level
    (±5 tolerance) so the picker opens pre-filtered.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
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
    QSpinBox,
    QVBoxLayout,
)

from tbh_desktop.gear_filters import CATEGORY_DISPLAY, GRADE_DISPLAY
from tbh_desktop.scraper import read_gear_cache

# Inject the "All" pseudo-option (None slug means no filter).
_CATEGORY_DISPLAY: dict[str, str | None] = {"All": None, **CATEGORY_DISPLAY}
_GRADE_DISPLAY: dict[str, str | None] = {"All": None, **GRADE_DISPLAY}

# Level tolerance when a level_hint is supplied (± this many levels).
_LEVEL_TOLERANCE = 5


class GearPicker(QDialog):
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
        self._cache_dir = Path(cache_dir)

        # Build a set of base gear names from the box loot table (if given).
        # Gear cache stores "Long Sword", loot stores "Dimensional Sword" etc.
        # We match on the suffix after the last space-hyphen token, but the
        # simplest robust match is: loot name == gear name exactly OR gear
        # name ends with the "core" token of the loot name.  We keep it
        # simple: exact name match (case-insensitive).
        self._loot_names: set[str] | None = None
        if box_loot:
            self._loot_names = {
                str(it.get("name", "")).strip().lower() for it in box_loot if it.get("name")
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

        # Level range row
        level_row = QHBoxLayout()
        level_row.addWidget(QLabel("Level:"))
        self.level_min = QSpinBox()
        self.level_min.setRange(0, 100)
        self.level_min.setValue(1)
        self.level_min.valueChanged.connect(self._rebuild)
        level_row.addWidget(self.level_min)
        level_row.addWidget(QLabel("–"))
        self.level_max = QSpinBox()
        self.level_max.setRange(0, 100)
        self.level_max.setValue(100)
        self.level_max.valueChanged.connect(self._rebuild)
        level_row.addWidget(self.level_max)
        level_row.addStretch()
        filters_layout.addLayout(level_row)

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

        # ── List + count ───────────────────────────────────────────────────
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.list_widget)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #7f849c; font-size: 11px;")
        layout.addWidget(self.count_label)

        # ── Buttons ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Apply level hint to spinboxes before initial population.
        if level_hint is not None and level_hint > 0:
            lo = max(1, level_hint - _LEVEL_TOLERANCE)
            hi = min(100, level_hint + _LEVEL_TOLERANCE)
            self.level_min.setValue(lo)
            self.level_max.setValue(hi)

        # Initial population.
        self._rebuild()

    # ------------------------------------------------------------------ filters
    def _load_items_for_filters(self) -> list[dict]:
        """Glob cache files matching the current category+grade and merge them,
        deduping by id. Returns the raw item dicts (before level filtering).
        """
        cat_slug = _CATEGORY_DISPLAY[self.category.currentText()]
        grade_slug = _GRADE_DISPLAY[self.grade.currentText()]

        if cat_slug is None and grade_slug is None:
            pattern = "gear_*_*.json"
        elif cat_slug is None:
            pattern = f"gear_*_{grade_slug}.json"
        elif grade_slug is None:
            pattern = f"gear_{cat_slug}_*.json"
        else:
            pattern = f"gear_{cat_slug}_{grade_slug}.json"

        seen: set[int] = set()
        merged: list[dict] = []
        if not self._cache_dir.exists():
            return merged
        for path in sorted(self._cache_dir.glob(pattern)):
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
        lo = self.level_min.value()
        hi = self.level_max.value()

        match_box = (
            self._loot_names is not None and self.match_box_check.isChecked()
        )
        loot_names: set[str] = self._loot_names or set()

        self.list_widget.clear()
        for item in self._load_items_for_filters():
            name = item.get("name")
            if name is None:
                continue
            level = self._parse_level(str(item.get("level", "")))
            if level < lo or level > hi:
                continue
            if match_box and str(name).strip().lower() not in loot_names:
                continue
            text = f"{item.get('id')} · {name} ({item.get('rarity', '')})"
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item.get("id"))
            self.list_widget.addItem(list_item)
        self._apply_search(self.search.text())
        self._update_count()

    def _update_count(self) -> None:
        visible = sum(1 for i in range(self.list_widget.count())
                      if not self.list_widget.item(i).isHidden())
        total = self.list_widget.count()
        if visible == total:
            self.count_label.setText(f"{total} items")
        else:
            self.count_label.setText(f"{visible} of {total} items")

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

    def selected_ids(self) -> list[int]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
        ]
