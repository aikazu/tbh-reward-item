"""Right-side Item browser: 6 tabs of in-game item data with a filter context."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.box_picker import BoxView
from tbh_desktop.ui.box_loot_picker import BoxLootView
from tbh_desktop.ui.gear_picker import GearView
from tbh_desktop.ui.theme import MOCHA


class FilterScope(str, Enum):
    BOX_LOOT = "box_loot"
    GEAR_FOR_BOX = "gear_for_box"
    GEAR_ALL = "gear_all"
    DROPS_INDEX = "drops_index"
    BROWSE_ALL = "browse_all"
    BOXES = "boxes"


@dataclass(frozen=True)
class FilterContext:
    box_id: int | None
    box_name: str | None
    level: int | None
    scope: FilterScope


_TAB_LABELS: list[tuple[str, FilterScope]] = [
    ("Browse all",    FilterScope.BROWSE_ALL),
    ("Box loot",      FilterScope.BOX_LOOT),
    ("Gear (scoped)", FilterScope.GEAR_FOR_BOX),
    ("Gear (all)",    FilterScope.GEAR_ALL),
    ("Drops index",   FilterScope.DROPS_INDEX),
    ("Boxes",         FilterScope.BOXES),
]


class ItemBrowser(QWidget):
    item_picked = Signal(int)        # single click
    items_picked = Signal(list)      # multi-select (Ctrl+click range)

    def __init__(
        self,
        gear_cache_dir: Path,
        drops_index_path: Path,
        box_slug_cache_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("item_browser")
        self._gear_cache_dir = Path(gear_cache_dir)
        self._drops_index_path = Path(drops_index_path)
        self._box_slug_cache_path = Path(box_slug_cache_path)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Tab widget
        self._tabs = QTabWidget()
        outer.addWidget(self._tabs, stretch=1)

        # Embedded views
        self._view_gear_all = GearView(self._gear_cache_dir)
        self._view_gear_scoped = GearView(self._gear_cache_dir)
        self._view_box_loot = BoxLootView(items=[])
        self._view_drops = BoxLootView(items=self._read_drops_index(), mode="drops_index")
        self._view_boxes = BoxView(self._box_slug_cache_path)
        self._view_browse = QFrame()  # placeholder; combines gear + drops in one grid

        for label, scope in _TAB_LABELS:
            page = self._build_page_for_scope(scope)
            self._tabs.addTab(page, label)

        # Banner
        self._banner = QLabel("Select a rule or the Range form to pick rewards")
        self._banner.setStyleSheet(
            f"color: {MOCHA['yellow']}; padding: 6px 8px; background: {MOCHA['mantle']};"
            f" border: 1px solid {MOCHA['surface0']}; border-radius: 4px;"
        )
        self._banner.setVisible(False)
        self._banner_visible: bool = False
        outer.addWidget(self._banner)

        # Status row
        status_row = QHBoxLayout()
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 11px;")
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        outer.addLayout(status_row)

    # ---- public API --------------------------------------------------
    def tab_count(self) -> int:
        return self._tabs.count()

    def active_tab(self) -> str:
        return self._tabs.tabText(self._tabs.currentIndex())

    def filter_for_context(self, context: FilterContext | None) -> None:
        if context is None:
            self._banner_visible = True
            self._banner.setVisible(True)
            self._tabs.setEnabled(False)
            self._status_label.setText("No active target")
            return
        self._banner_visible = False
        self._banner.setVisible(False)
        self._tabs.setEnabled(True)
        # Pick the tab that matches the scope.
        for i, (_label, scope) in enumerate(_TAB_LABELS):
            if scope == context.scope:
                self._tabs.setCurrentIndex(i)
                break
        # Apply scope-specific filters.
        if context.scope == FilterScope.GEAR_FOR_BOX and context.box_id is not None:
            box_loot_items = self._read_box_loot_for(context.box_id)
            self._view_gear_scoped.set_box_loot(
                box_loot_items,
                level_hint=context.level,
            )
        # Update status.
        self._refresh_status()

    def banner_visible(self) -> bool:
        return self._banner_visible

    def grid_enabled(self) -> bool:
        return self._tabs.isEnabled()

    # ---- helpers (used by MainWindow) --------------------------------
    def _read_drops_index(self) -> list[dict[str, Any]]:
        import json
        if not self._drops_index_path.exists():
            return []
        try:
            data = json.loads(self._drops_index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        # Cache file may be either a flat list of items or a {"items": [...]} dict.
        if isinstance(data, dict):
            return list(data.get("items") or [])
        if isinstance(data, list):
            return data
        return []

    def _read_box_loot_for(self, box_id: int) -> list[dict[str, Any]]:
        # Reuse the existing scraper helper that knows the cache layout.
        from tbh_desktop.paths import BOX_LOOT_CACHE_DIR
        from tbh_desktop.scraper import read_box_cache
        return read_box_cache(BOX_LOOT_CACHE_DIR, box_id) or []

    def set_box_loot(self, box_id: int) -> None:
        """Load the loot list for ``box_id`` into the Box loot tab.

        Called automatically by MainWindow when the user selects a rule
        whose ``item_id`` identifies a box (Normal Box / Stage Boss Box
        rules). Replaces the old "click Pick loot button" flow — the tab
        now reacts to selection like the gear tabs already did.

        No-op if no cache file exists for this box (caller should treat
        that as "box has no scraped loot yet" and either fall back to the
        drops index or prompt the user to scrape).
        """
        items = self._read_box_loot_for(box_id)
        self._view_box_loot.set_items(items)

    def _refresh_status(self) -> None:
        # Counts per tab — naive, but enough for v1.
        self._status_label.setText("Ready")

    def _build_page_for_scope(self, scope: FilterScope) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        view = {
            FilterScope.BROWSE_ALL:    self._view_browse,
            FilterScope.BOX_LOOT:      self._view_box_loot,
            FilterScope.GEAR_FOR_BOX:  self._view_gear_scoped,
            FilterScope.GEAR_ALL:      self._view_gear_all,
            FilterScope.DROPS_INDEX:   self._view_drops,
            FilterScope.BOXES:         self._view_boxes,
        }[scope]
        layout.addWidget(view)
        return page

    # ---- test-only hooks --------------------------------------------
    def _emit_pick_for_test(self, item_id: int) -> None:
        self.item_picked.emit(item_id)