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
    QDialog,
    QDialogButtonBox,
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
    ) -> None:
        """Either pass ``items`` directly (for tests) or ``cache_path`` to
        load from the drops index on disk. If neither, returns an empty
        picker with a "no items available" notice.
        """
        super().__init__(parent)
        self.setWindowTitle("Pick reward IDs from drops index")
        self.resize(560, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Resolve items: explicit > cache > empty.
        if items is None and cache_path is not None:
            from tbh_desktop.scraper import read_drops_index
            items = read_drops_index(cache_path)
        items = items or []
        # Filter out gear — that's the GearPicker's territory.
        non_gear = [it for it in items if str(it.get("kind", "")).lower() != "gear"]

        # Sort: by family (FAMILY_ORDER), then rarity (RARITY_ORDER), then id.
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

        non_gear.sort(key=_sort_key)

        # Header summary.
        families = sorted({it.get("family", "") for it in non_gear if it.get("family")})
        rarities = sorted({it.get("rarity", "") for it in non_gear if it.get("rarity")})
        if non_gear:
            summary = (
                f"Drops index — {len(non_gear)} non-gear items · "
                f"{len(families)} families · {len(rarities)} rarities"
            )
        else:
            summary = (
                "Drops index is empty — fetch it first "
                "(Run proxy once or call fetch_drops_index)."
            )
        layout.addWidget(QLabel(summary))

        # Search box.
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name, id, family, or rarity…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        # List widget.
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.list_widget.setIconSize(QSize(48, 48))
        # Smaller item height than gear (no extra icons strip).
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

        self._build_all(non_gear)

    def _build_all(self, items: list[dict[str, Any]]) -> None:
        """Populate the list widget with grouped headers + item rows."""
        self.list_widget.clear()
        from tbh_desktop.scraper import FAMILY_ORDER, RARITY_ORDER

        # Group by (family, rarity) preserving sort order.
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for it in items:
            key = (str(it.get("family", "")), str(it.get("rarity", "COMMON")))
            grouped.setdefault(key, []).append(it)

        # Walk in FAMILY_ORDER × RARITY_ORDER; skip empty groups.
        family_rank = {f: i for i, f in enumerate(FAMILY_ORDER)}
        rarity_rank = {r: i for i, r in enumerate(RARITY_ORDER)}

        ordered_keys = sorted(
            grouped.keys(),
            key=lambda k: (family_rank.get(k[0], 99), rarity_rank.get(k[1], 99)),
        )

        for fam, rar in ordered_keys:
            self._add_header(f"{rar.title()} {fam.title()}" if fam else rar.title())
            for it in grouped[(fam, rar)]:
                self._add_item_row(it)
        self._update_count()

    def _add_header(self, text: str) -> None:
        """Insert a non-selectable header row to break the list into sections."""
        header = QListWidgetItem(f"── {text} ──")
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
            item_match[i] = match
            li.setHidden(bool(text) and not match)
        # Second pass: hide headers whose group has no matches.
        # Walk contiguous runs of items between headers.
        i = 0
        while i < self.list_widget.count():
            li = self.list_widget.item(i)
            if li.data(Qt.ItemDataRole.UserRole) is not None:
                i += 1
                continue
            # header — find next header or end
            j = i + 1
            while j < self.list_widget.count() and self.list_widget.item(j).data(Qt.ItemDataRole.UserRole) is not None:
                j += 1
            any_visible = any(
                self.list_widget.item(k).data(Qt.ItemDataRole.UserRole) is not None
                and not self.list_widget.item(k).isHidden()
                for k in range(i + 1, j)
            )
            li.setHidden(bool(text) and not any_visible)
            i = j
        self._update_count()

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
