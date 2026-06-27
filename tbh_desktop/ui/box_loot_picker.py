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

T7: BoxLootView (QWidget) extracted from BoxLootPicker (QDialog). The
dialog is now a thin shim around the view + OK/Cancel buttons. UI state
(filters, search, list) lives on the view so it can be embedded in a
larger panel (T9) without the dialog chrome.
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
    QWidget,
)

from tbh_desktop.ui.image_cache import ImageCache


# Short labels for inline stat-name display. Mirrors the gear picker
# helper so the two pickers render stat names consistently.
_STAT_SHORT: dict[str, str] = {
    "Attack Damage": "ATK",
    "Attack Speed": "ASPD",
    "Critical Rate": "CRIT",
    "Critical Damage": "CD",
    "Cooldown Reduction": "CDR",
    "Max HP": "HP",
    "Defense": "DEF",
    "Fire Damage Percent": "Fire Dmg",
    "Fire Resistance": "Fire Res",
    "Water Damage Percent": "Water Dmg",
    "Water Resistance": "Water Res",
    "Earth Damage Percent": "Earth Dmg",
    "Earth Resistance": "Earth Res",
    "Lightning Damage Percent": "Lightning Dmg",
    "Lightning Resistance": "Lightning Res",
    "Light Damage Percent": "Light Dmg",
    "Light Resistance": "Light Res",
    "Dark Damage Percent": "Dark Dmg",
    "Dark Resistance": "Dark Res",
}


def _short_stat_name(name: str) -> str:
    if name in _STAT_SHORT:
        return _STAT_SHORT[name]
    parts = name.split()
    return " ".join(parts[:2]) if len(parts) > 2 else name


def _format_info_inline(info: dict[str, Any] | None) -> str:
    """Format a material's wiki info dict as a single inline row.

    Example: ``Fire Dmg +20~30% (W) · Fire Res +5~10% (A) · ATK +1~2 (X)``.

    Slot suffix is single-letter for compactness: W=Weapon, A=Armor,
    X=Accessory, H=Helmet. Returns '' if info is empty/absent.
    """
    if not info:
        return ""
    stats = info.get("stats") or []
    if not stats:
        return ""
    slot_short = {"Weapon": "W", "Armor": "A", "Accessory": "X", "Helmet": "H"}
    parts: list[str] = []
    for s in stats:
        stat = s.get("stat", "").strip()
        value = s.get("value", "").strip()
        slot = s.get("slot", "").strip()
        if not stat or not value:
            continue
        suffix = f" ({slot_short.get(slot, slot[0] if slot else '?')})" if slot else ""
        parts.append(f"{_short_stat_name(stat)} {value}{suffix}")
    return " · ".join(parts)


class BoxLootView(QWidget):
    """Embeddable material picker (non-dialog). Filter + list + search UI.

    Two modes (see ``__init__``):
    - ``"materials"`` (default): range-replacement picker. Materials only,
      SOULSTONE excluded.
    - ``"box_loot"``: per-rule loot picker scoped to a specific box.
      Materials only; gear has its own GearPicker.

    Public API:
    - ``visible_items() -> list[dict]`` — items currently rendered (raw
      dicts after all filters, in display order). Header rows excluded.
    - ``selected_ids() -> list[int]`` — ids of currently selected rows.
    - ``set_family_filter(name)`` — set the family filter (None / "" =
      clear). Triggers a rebuild.
    - ``set_selected_ids_for_test(ids)`` — test hook to mark rows as
      selected without simulating user interaction.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        items: list[dict[str, Any]] | None = None,
        cache_path: Any | None = None,
        scope_box_name: str | None = None,
        mode: str = "materials",
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._scope_box_name = scope_box_name

        # Resolve items: explicit > cache > empty.
        if items is None and cache_path is not None:
            from tbh_desktop.scraper import read_drops_index
            items = read_drops_index(cache_path)
        items = items or []
        # Merge per-item info (effect + stat rolls + crafting) from the
        # per-(family,rarity) cache files. The drops index itself doesn't
        # carry this — it's added by refresh_material_details during the
        # Scrape Data flow. The picker reads it from disk here so the
        # effect + stats show up without hovering or opening the wiki.
        from tbh_desktop.paths import ITEM_DIR
        from tbh_desktop.scraper import load_material_info_by_id
        info_by_id = load_material_info_by_id(ITEM_DIR)
        for it in items:
            iid = it.get("id")
            if isinstance(iid, int) and iid in info_by_id:
                it["info"] = info_by_id[iid]
        # Filter by mode.
        if mode == "materials":
            # Range replacement picker: materials from the wiki drops index,
            # excludes SOULSTONE (bind-on-pickup crafting; unsafe as range
            # replacement target).
            from tbh_desktop.scraper import FAMILY_ORDER as _FAMILY_ORDER
            safe_families = {f for f in _FAMILY_ORDER if f != "SOULSTONE"}
            filtered = [
                it for it in items
                if str(it.get("kind", "")).lower() == "material"
                and str(it.get("family", "")).upper() in safe_families
            ]
        else:  # "box_loot"
            # Per-rule loot picker: the caller already passed the box's ACTUAL
            # loot list (see main_window._pick_box_loot_for_rule). Just filter
            # out gear — it has its own GearPicker dialog. We trust the input
            # list as ground truth; do NOT widen to the drops index (that
            # showed items like anniversary coins + soulstones for boxes that
            # never drop them — see issue "box 40 ada offering paling rare").
            filtered = [
                it for it in items
                if str(it.get("kind", "")).lower() == "material"
            ]

        # NOTE: scope_box_name substring matching is intentionally REMOVED. It was a
        # leftover from when the picker was fed the full drops index and tried
        # to filter by box name in item names — but item names like "Bronze
        # Ingot" never contain the box name, so the filter just truncated the
        # list silently. The caller now passes the box's ACTUAL loot list,
        # which is already scoped. scope_box_name is still accepted as a
        # constructor arg only for window-title purposes (the dialog shim
        # uses it).

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

        self._all_items = filtered
        self._build_ui()

        # Stash the filtered+scoped items; _apply_filters rebuilds the list
        # with rarity filter + search applied on top.
        self._apply_filters()

    # ---------------------------------------------------------- UI construction
    def _build_ui(self) -> None:
        """Construct the widget layout and child widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        filtered = self._all_items

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
        # Family dropdown in canonical FAMILY_ORDER, then any extra families
        # present in the items that aren't in the canonical set (e.g. a test
        # fixture or a future family added by the wiki).
        from tbh_desktop.scraper import FAMILY_ORDER as _FAMILY_ORDER_FOR_PICKER
        ordered_families: list[str] = []
        for f in _FAMILY_ORDER_FOR_PICKER:
            if f in family_counts and f not in ordered_families:
                ordered_families.append(f)
        for f in sorted(family_counts.keys()):
            if f not in ordered_families:
                ordered_families.append(f)
        for f in ordered_families:
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
        # Two-line rows (name + info) need word-wrap so the info line
        # doesn't get clipped at the dialog width.
        self.list_widget.setWordWrap(True)
        layout.addWidget(self.list_widget)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #7f849c; font-size: 11px;")
        layout.addWidget(self.count_label)

        # Async image cache.
        self._image_cache = ImageCache(self)
        self._image_cache.icon_ready.connect(self._apply_icon)

    # ---------------------------------------------------------- public API
    def visible_items(self) -> list[dict]:
        """Return the raw item dicts currently rendered in the list, in
        display order. Hidden rows (filtered by search) are excluded.
        Header rows (no ``id``) are excluded.
        """
        items: list[dict] = []
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            if li.isHidden():
                continue
            item_id = li.data(Qt.ItemDataRole.UserRole)
            if item_id is None:
                continue  # header row
            # Match by id against the source items.
            for src in self._all_items:
                if src.get("id") == item_id:
                    items.append(src)
                    break
        return items

    def selected_ids(self) -> list[int]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole) is not None
        ]

    def set_family_filter(self, name: str | None) -> None:
        """Set the family ("Type") filter by family slug (case-insensitive).

        Pass ``None`` or empty string to clear (matches "All"). Triggers a
        rebuild of the list.
        """
        target = (name or "").strip().upper()
        if not target:
            # Reset to "All" entry (index 0, userData=None).
            if self.family_filter.currentIndex() != 0:
                self.family_filter.setCurrentIndex(0)
            return
        idx = self.family_filter.findData(target)
        if idx < 0:
            # Try case-insensitive lookup against item text.
            for i in range(self.family_filter.count()):
                if self.family_filter.itemText(i).strip().upper().startswith(target):
                    idx = i
                    break
        if idx >= 0 and idx != self.family_filter.currentIndex():
            self.family_filter.setCurrentIndex(idx)
        # setCurrentIndex already fires currentIndexChanged -> _apply_filters.

    def set_selected_ids_for_test(self, ids: list[int]) -> None:
        """Test hook: mark the rows whose ``id`` matches *ids* as selected.

        No-op in production usage; lets headless tests assert selection
        state without simulating user clicks.
        """
        id_set = {int(i) for i in ids}
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            iid = li.data(Qt.ItemDataRole.UserRole)
            if iid is not None and int(iid) in id_set:
                li.setSelected(True)
            else:
                li.setSelected(False)

    # ------------------------------------------------------------------ filters
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
        line1 = f"  {item_id} · {name}{rate_part}"
        # Inline info: effect + stat rolls (one per slot type). If the
        # item has no info yet (never re-scraped), just show the name line.
        info_line = _format_info_inline(item.get("info"))
        text = f"{line1}\n{info_line}" if info_line else line1
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
        # Surface the wiki-derived info in the tooltip too, so the user
        # can see the FULL text (the inline line is truncated to keep the
        # row short).
        info = item.get("info") or {}
        if info.get("effect"):
            tooltip_lines.append(f"<br><i>{info['effect']}</i>")
        for st in info.get("stats", []):
            slot = st.get("slot", "")
            stat = st.get("stat", "")
            value = st.get("value", "")
            tier = st.get("tier", "")
            slot_prefix = f"[{slot}] " if slot else ""
            tier_suffix = f" (T{tier})" if tier else ""
            tooltip_lines.append(
                f"{slot_prefix}<b>{stat}</b> {value}{tier_suffix}"
            )
        if info.get("crafting"):
            tooltip_lines.append(f"<br>Crafting: {info['crafting']}")
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
        """Filter rows by text match (name, id). Headers stay visible as
        long as any item in their group still matches; hide otherwise.
        """
        text = text.strip().lower()
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            item_id = li.data(Qt.ItemDataRole.UserRole)
            if item_id is None:
                continue  # header row — keep visible (header hide handled below)
            if not text:
                li.setHidden(False)
                continue
            label = li.text().lower()
            tip = (li.toolTip() or "").lower()
            li.setHidden(
                text not in label
                and text not in str(item_id)
                and text not in tip
            )
        # Hide family headers whose group has no visible items.
        visible_after_header: set[int] = set()
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            if li.data(Qt.ItemDataRole.UserRole) is not None and not li.isHidden():
                visible_after_header.add(i)
        # Walk: hide header if no following item rows are visible before next header.
        next_header_idx: int | None = None
        for i in range(self.list_widget.count() - 1, -1, -1):
            li = self.list_widget.item(i)
            if li.data(Qt.ItemDataRole.UserRole) is None:
                next_header_idx = i
                li.setHidden(True)
                continue
            if next_header_idx is not None and not li.isHidden():
                self.list_widget.item(next_header_idx).setHidden(False)
                next_header_idx = None
        self._update_count()

    def _update_count(self) -> None:
        selectable = sum(
            1
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) is not None
            and not self.list_widget.item(i).isHidden()
        )
        self.count_label.setText(f"{selectable} items")


class BoxLootPicker(QDialog):
    """Thin dialog shim around :class:`BoxLootView`. Kept so legacy callers
    (main_window + the existing test suite) continue to compile unchanged.

    UI attributes (``list_widget``, ``rarity_filter``, ``family_filter``)
    are exposed via property forwarding to the embedded ``BoxLootView``,
    so existing tests that poke them directly still pass.
    """

    def __init__(
        self,
        parent=None,
        *,
        items: list[dict[str, Any]] | None = None,
        cache_path: Any | None = None,
        scope_box_name: str | None = None,
        mode: str = "materials",
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        if mode == "box_loot":
            self.setWindowTitle(
                f"Pick from box loot ({scope_box_name})"
                if scope_box_name
                else "Pick from box loot"
            )
        else:
            self.setWindowTitle(
                f"Pick reward IDs from {scope_box_name}" if scope_box_name
                else "Pick reward IDs from drops index"
            )
        # box_loot mode shows everything (no header); materials mode needs
        # more vertical space for grouped headers.
        self.resize(640, 720)

        self._view = BoxLootView(
            self,
            items=items,
            cache_path=cache_path,
            scope_box_name=scope_box_name,
            mode=mode,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self._view)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---------------------------------------------------------- forwarded API
    # Each attribute is forwarded to the embedded BoxLootView so legacy callers
    # (including the existing test suite) can interact with the picker the
    # same way they did before the extraction.
    @property
    def list_widget(self) -> QListWidget:
        return self._view.list_widget

    @property
    def rarity_filter(self) -> QComboBox:
        return self._view.rarity_filter

    @property
    def family_filter(self) -> QComboBox:
        return self._view.family_filter

    def selected_ids(self) -> list[int]:
        return self._view.selected_ids()