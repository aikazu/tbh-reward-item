"""Dialog to pick reward IDs from the wiki drop-finder index.

G7:
- Populated from the /en/tools/drops/ index (materials + stage boxes +
  consumables — every kind except ``gear``). No need to pick a box first;
  the user just browses the full catalog and selects IDs.
- Gear is shown via the dedicated GearPicker dialog (separate per-category
  filtering). BoxLootPicker focuses on the "what other stuff drops" use case
  for range replacement IDs.
- Rich display: image (async), name, kind + rarity + family tags, drop rate
  (only meaningful for items sourced from a specific box; for stage-boxes
  the rate is from the box loot table).
- Sort order: rarity (COMMON→COSMIC) within family; families group as
  CRAFTING → DECORATION → ENGRAVING → INSCRIPTION → OFFERING → SOULSTONE.
- Group headers (e.g. "── Legendary Crafting ──") break up the list visually.
- Tooltip shows box_id + kind + family when applicable.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from tbh_desktop.ui.image_cache import ImageCache


class BoxLootPicker(QDialog):
    """Pick reward IDs from the wiki drops index (everything non-gear)."""

    def __init__(
        self,
        parent=None,
        *,
        items: list[dict[str, Any]] | None = None,
        cache_path: Any | None = None,
        scope_box_name: str | None = None,
        mode: str = "materials",  # "materials" | "box_loot"
    ) -> None:
        """Pick reward IDs from the wiki drops index.

        Two modes:
        - "materials" (default): range replacement picker. Lists only
          materials, excludes SOULSTONE family (those are bind-on-pickup
          crafting materials; using them as range replacement targets can
          silently break addon logic). No stage-box, no gear.
        - "box_loot": per-rule loot picker. Scoped to a specific box, lists
          ALL items in that box (materials + stage boxes + everything else).
          User picks a single rule's replacement IDs.

        Gear and stage-boxes are excluded from the "materials" mode — gear
        has its own GearPicker, and stage-boxes are containers, not reward
        items.
        """
        super().__init__(parent)
        self._mode = mode
        self.setWindowTitle(
            f"Pick reward IDs from {scope_box_name}" if scope_box_name
            else "Pick reward IDs from drops index"
        )
        # box_loot mode shows everything (no header); materials mode needs
        # more vertical space for grouped headers.
        self.resize(640, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Resolve items: explicit > cache > empty.
        if items is None and cache_path is not None:
            from tbh_desktop.scraper import read_drops_index
            items = read_drops_index(cache_path)
        items = items or []
        # Filter by mode.
        if mode == "materials":
            # Range replacement picker: materials only, exclude SOULSTONE.
            from tbh_desktop.scraper import FAMILY_ORDER as _FAMILY_ORDER
            safe_families = {f for f in _FAMILY_ORDER if f != "SOULSTONE"}
            filtered = [
                it for it in items
                if str(it.get("kind", "")).lower() == "material"
                and str(it.get("family", "")).upper() in safe_families
            ]
        else:  # "box_loot"
            # Per-rule loot picker: everything non-gear from the box.
            filtered = [
                it for it in items
                if str(it.get("kind", "")).lower() != "gear"
            ]

        # If scope_box_name given, pre-filter to items whose name contains it.
        if scope_box_name:
            needle = scope_box_name.lower()
            scoped = [it for it in filtered if needle in it.get("name", "").lower()]
            if scoped:
                filtered = scoped

        # Sort by family rank, then rarity rank, then id. SOULSTONE never
        # appears in materials mode (filtered above).
        from tbh_desktop.scraper import FAMILY_ORDER, RARITY_ORDER
        family_rank = {f: i for i, f in enumerate(FAMILY_ORDER)}
        rarity_rank = {r: i for i, r in enumerate(RARITY_ORDER)}

        def _sort_key(it: dict[str, Any]) -> tuple[int, int, int]:
            fam = str(it.get("family", ""))
            rar = str(it.get("rarity", "COMMON"))
            return (
                family_rank.get(fam, 99),
                rarity_rank.get(rar, 99),
                int(it.get("id", 0)),
            )

        filtered.sort(key=_sort_key)

        # ── Filter row ───────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.addWidget(QLabel("Rarity:"))
        self.rarity_filter = QComboBox()
        self.rarity_filter.setToolTip("Filter by material rarity")
        rarity_counts: dict[str, int] = {}
        for it in filtered:
            r = str(it.get("rarity", "COMMON")).upper()
            rarity_counts[r] = rarity_counts.get(r, 0) + 1
        self.rarity_filter.addItem(f"All ({len(filtered)})", None)
        # Rarity dropdown shows COMMON → COSMIC in canonical order.
        from tbh_desktop.scraper import RARITY_ORDER
        for r in RARITY_ORDER:
            if r in rarity_counts:
                self.rarity_filter.addItem(
                    f"{r.title()} ({rarity_counts[r]})", r
                )
        self.rarity_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.rarity_filter)

        # Family ("Type") filter — second dropdown, narrows to a specific
        # crafting category: CRAFTING / DECORATION / ENGRAVING / INSCRIPTION /
        # OFFERING. SOULSTONE excluded entirely in materials mode.
        filter_row.addWidget(QLabel("Type:"))
        self.family_filter = QComboBox()
        self.family_filter.setToolTip(
            "Filter by material type — Crafting / Decoration / Engraving / "
            "Inscription / Offering"
        )
        family_counts: dict[str, int] = {}
        for it in filtered:
            f = str(it.get("family", "")).upper()
            family_counts[f] = family_counts.get(f, 0) + 1
        self.family_filter.addItem(f"All ({len(filtered)})", None)
        # Family dropdown in canonical FAMILY_ORDER.
        from tbh_desktop.scraper import FAMILY_ORDER as _FAMILY_ORDER_FOR_PICKER
        for f in _FAMILY_ORDER_FOR_PICKER:
            if f in family_counts:
                self.family_filter.addItem(
                    f"{f.title()} ({family_counts[f]})", f
                )
        self.family_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.family_filter)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Search box.
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name or id…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filters)
        layout.addWidget(self.search)

        # List widget.
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.list_widget.setIconSize(QSize(48, 48))
        layout.addWidget(self.list_widget)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #7f849c; font-size: 11px;")
        layout.addWidget(self.count_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Async image cache.
        self._image_cache = ImageCache(self)
        self._image_cache.icon_ready.connect(self._apply_icon)

        # Stash the filtered+scoped items; _apply_filters rebuilds the list
        # with rarity filter + search applied on top.
        self._all_items = filtered
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Rebuild list with rarity + family + search filters applied."""
        rarity = self.rarity_filter.currentData()  # None = all
        family = self.family_filter.currentData()  # None = all
        text = self.search.text().strip().lower()
        self.list_widget.clear()
        # Track family boundaries so we can insert header rows.
        last_family: str | None = None
        for it in self._all_items:
            if rarity is not None and str(it.get("rarity", "")).upper() != rarity:
                continue
            if family is not None and str(it.get("family", "")).upper() != family:
                continue
            if text:
                name = str(it.get("name", "")).lower()
                if text not in name and text not in str(it.get("id", "")):
                    continue
            fam = str(it.get("family", ""))
            if fam != last_family:
                self._add_family_header(fam)
                last_family = fam
            self._add_item_row(it)
        self._update_count()

    def _add_family_header(self, family: str) -> None:
        """Insert a non-selectable header row to demarcate a family group.

        Items are pre-sorted by FAMILY_ORDER, so consecutive items share a
        family. The header row is visually distinct (grey, bold, dimmed)
        and not selectable.
        """
        label = family.replace("_", " ").title() if family else "Other"
        header = QListWidgetItem(f"── {label} ──")
        header.setFlags(Qt.ItemFlag.NoItemFlags)  # not selectable
        header.setForeground(QColor("#8a92a6"))
        font = QFont()
        font.setBold(True)
        header.setFont(font)
        self.list_widget.addItem(header)

    def _add_item_row(self, item: dict[str, Any]) -> None:
        """Add a single item row."""
        item_id = item.get("id")
        name = item.get("name", "")
        if item_id is None or not name:
            return
        rate = item.get("rate", "")
        kind = str(item.get("kind", "other")).lower()
        rarity = str(item.get("rarity", "")).title()
        family = str(item.get("family", "")).title()
        rate_part = f" ({rate})" if rate else ""
        text = f"  {item_id} · {name}{rate_part}"
        list_item = QListWidgetItem(text)
        list_item.setData(Qt.ItemDataRole.UserRole, item_id)
        # Tooltip with structured info.
        tooltip_lines = [f"<b>{name}</b> · id {item_id}"]
        if rarity:
            tooltip_lines.append(f"Rarity: <b>{rarity}</b>")
        if family:
            tooltip_lines.append(f"Family: {family}")
        if kind:
            tooltip_lines.append(f"Kind: {kind}")
        if rate:
            tooltip_lines.append(f"Drop rate: <b>{rate}</b>")
        list_item.setToolTip("<br>".join(tooltip_lines))
        # Background tint per rarity (subtle differentiation).
        tint = self._rarity_tint(rarity)
        if tint is not None:
            list_item.setBackground(tint)
        # Image (async). Common kind = material/Item_X.png pattern; stage-box
        # usually has no icon — that's fine, no icon set.
        image_url = str(item.get("image", "")).strip()
        if image_url:
            self._image_cache.request(image_url, item_id)
        self.list_widget.addItem(list_item)

    @staticmethod
    def _rarity_tint(rarity: str):
        """Background tint by rarity tier (dark-theme friendly)."""
        tints = {
            "Common": QColor(80, 80, 90, 60),
            "Uncommon": QColor(60, 110, 70, 70),
            "Rare": QColor(60, 90, 150, 80),
            "Legendary": QColor(160, 120, 50, 90),
            "Immortal": QColor(170, 70, 130, 90),
            "Arcana": QColor(110, 60, 160, 90),
            "Beyond": QColor(180, 80, 60, 90),
            "Celestial": QColor(70, 150, 170, 90),
            "Divine": QColor(200, 170, 60, 100),
            "Cosmic": QColor(190, 90, 200, 100),
        }
        return tints.get(rarity)

    def _apply_icon(self, item_id: int, icon) -> None:
        """Apply an icon to the matching list item when the async fetch lands."""
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            if li.data(Qt.ItemDataRole.UserRole) == item_id:
                li.setIcon(icon)
                break

    def _filter(self, text: str) -> None:
        """Filter rows by text match (name, id, family, rarity). Headers stay
        visible if any item in their group still matches; hide otherwise.
        """
        text = text.strip().lower()
        # First pass: mark item rows as hidden/matched.
        item_match: dict[int, bool] = {}
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            item_id = li.data(Qt.ItemDataRole.UserRole)
            if item_id is None:
                continue  # header row
            label = li.text()
            name = label.split(" · ", 1)[-1].rsplit(" (", 1)[0].strip() if " · " in label else ""
            match = bool(text) and (
                text in name.lower()
                or text in str(item_id)
                or text in (li.toolTip() or "").lower()
            )
    def _update_count(self) -> None:
        selectable = sum(
            1
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) is not None
            and not self.list_widget.item(i).isHidden()
        )
        self.count_label.setText(f"{selectable} items")

    def selected_ids(self) -> list[int]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole) is not None
        ]
