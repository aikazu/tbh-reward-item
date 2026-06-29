"""Dialog to pick a box ID from the box slug cache.

T8: ``BoxView(QWidget)`` is the embeddable widget holding the list, search
field, level dropdown, and slot wiring. ``BoxPicker(QDialog)`` is now a
thin shim around it (kept so legacy callers — and the existing test suite
— continue to compile unchanged).

Cache format (read by ``BoxView``):
    {"boxes": [{"id": <int>, "name": <str>, "level": <int?>}, ...]}

The legacy ``box_slug_cache.json`` writers (G1-G6) wrote a flat dict
``{box_id_str: slug}``; the T8 widget consumes the boxes-with-name shape
because that is what the spec/test fixtures use and what the wider
ItemBrowser (T9) will share.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PySide6.QtCore import Qt
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

from tbh_desktop.scraper import derive_item_image_url
from tbh_desktop.ui.image_cache import ImageCache

# Matches the trailing level segment of a box slug.
#   "normal-monster-box-lv80"  -> 80  (explicit Lv prefix)
#   "normal-monster-box-1"     -> 1   (bare tier number)
_SLUG_LEVEL_RE = re.compile(r"(?:-lv|-)(\d+)$", re.IGNORECASE)


def _slug_to_display(slug: str) -> str:
    """'normal-monster-box-lv80' -> 'Normal Monster Box Lv80'."""
    # Replace hyphens with spaces, then title-case.  "lv" -> "Lv" naturally.
    return slug.replace("-", " ").title()


def parse_box_level(slug: str) -> int | None:
    """Extract the level number encoded in a box slug, or ``None``.

    >>> parse_box_level("normal-monster-box-lv80")
    80
    >>> parse_box_level("normal-monster-box-1")
    1
    >>> parse_box_level("stage-boss-box")
    None
    """
    m = _SLUG_LEVEL_RE.search(slug)
    return int(m.group(1)) if m else None


def box_level_from_cache(cache_path: Path, box_id: int) -> int | None:
    """Look up ``box_id`` in the slug cache and return its parsed level.

    Returns ``None`` if the cache is missing, the id is not found, or the
    slug does not encode a level.
    """
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None
    slug = data.get(str(box_id))
    if slug is None:
        return None
    return parse_box_level(slug)


def load_box_cache(cache_path: Path) -> dict[str, str]:
    """Load the slug cache as ``{box_id_str: slug}`` (empty on error)."""
    if not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------- cache reader (T8)
def _read_boxes_list(cache_path: Path) -> list[dict]:
    """Read the T8 boxes cache format.

    Accepts either:
      - {"boxes": [{"id": int, "name": str, "level": int?}, ...]}
      - legacy {box_id_str: slug} (reconstructed into boxes entries)

    Returns an empty list on missing/unreadable file.
    """
    if not cache_path.exists():
        return []
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []

    if isinstance(data, dict) and isinstance(data.get("boxes"), list):
        boxes: list[dict] = []
        for entry in data["boxes"]:
            if not isinstance(entry, dict):
                continue
            try:
                box_id = int(entry.get("id"))
            except (TypeError, ValueError):
                continue
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            level_raw = entry.get("level")
            level: int | None = None
            if level_raw is not None:
                try:
                    level = int(level_raw)
                except (TypeError, ValueError):
                    level = None
            boxes.append({"id": box_id, "name": name, "level": level})
        return boxes

    # Legacy {box_id_str: slug} fallback — synthesise display names.
    if isinstance(data, dict):
        legacy: list[dict] = []
        for key, slug in data.items():
            try:
                box_id = int(key)
            except (TypeError, ValueError):
                continue
            if not isinstance(slug, str):
                continue
            legacy.append(
                {
                    "id": box_id,
                    "name": _slug_to_display(slug),
                    "level": parse_box_level(slug),
                }
            )
        return legacy

    return []


# =============================================================================
# BoxView — embeddable widget (T8)
# =============================================================================
class BoxView(QWidget):
    """Embeddable box list with search and level filter.

    Mirrors the layout ``BoxPicker`` exposed as a modal:
    - Search field (case-insensitive substring on name OR id)
    - Level dropdown ("All" + each distinct level found in the cache)
    - Selectable list, single selection

    Public API:
    - ``set_name_filter(text: str)`` — apply a name/id substring filter
    - ``visible_boxes() -> list[dict]`` — boxes currently shown (after all
      filters). Each entry is ``{"id": int, "name": str, "level": int | None}``.
    - ``selected_box_id() -> int | None`` — id of the currently selected row
    - ``selected_box_level() -> int | None`` — level of the selected row
    - ``set_selected_box_id_for_test(box_id: int)`` — test fixture hook
    """

    def __init__(self, cache_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level_by_id: dict[int, int | None] = {}

        # Read cache once into the in-memory list — filter operations never
        # touch disk. _build_ui wires widgets; _populate rebuilds from this.
        self._boxes: list[dict] = _read_boxes_list(Path(cache_path))
        for b in self._boxes:
            self._level_by_id[int(b["id"])] = b.get("level")

        # Background-thread image fetcher. box images are derived from id
        # (the wiki always serves these paths for obtainable boxes) so we
        # don't need a separate image field in the slug cache.
        self._image_cache = ImageCache(self)
        self._image_cache.icon_ready.connect(self._apply_icon)

        self._build_ui()
        self._populate()

    # ---------------------------------------------------------- UI construction
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Select a box:"))

        # Search row
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name or id…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search)
        layout.addLayout(search_row)

        # Level dropdown — "All" + each distinct level present in the cache.
        # Avoids the user picking a level that no box has.
        level_row = QHBoxLayout()
        level_row.addWidget(QLabel("Level:"))
        self.level = QComboBox()
        self.level.currentIndexChanged.connect(self._apply_filter)
        level_row.addWidget(self.level)
        level_row.addStretch()
        layout.addLayout(level_row)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        layout.addWidget(self.list_widget)

        # Count
        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #7f849c; font-size: 11px;")
        layout.addWidget(self.count_label)

    # ---------------------------------------------------------- public API
    def set_name_filter(self, text: str) -> None:
        """Set the search field; list visibility updates accordingly."""
        # Block signals so programmatic change doesn't echo into _apply_filter
        # recursively — same pattern as GearView._populate_level_options.
        self.search.blockSignals(True)
        self.search.setText(text)
        self.search.blockSignals(False)
        self._apply_filter(text)

    def visible_boxes(self) -> list[dict]:
        """Return the boxes currently rendered (visible after filters).

        Each entry has at least ``id`` and ``name``; ``level`` is present
        when the cache encoded one.
        """
        out: list[dict] = []
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            if li.isHidden():
                continue
            out.append(
                {
                    "id": li.data(Qt.ItemDataRole.UserRole),
                    "name": self._display_name_for_id(li.data(Qt.ItemDataRole.UserRole)),
                    "level": self._level_by_id.get(li.data(Qt.ItemDataRole.UserRole)),
                }
            )
        return out

    def selected_box_id(self) -> int | None:
        items = self.list_widget.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def selected_box_level(self) -> int | None:
        box_id = self.selected_box_id()
        if box_id is None:
            return None
        return self._level_by_id.get(box_id)

    def set_selected_box_id_for_test(self, box_id: int) -> None:
        """Test fixture: select the row whose id == ``box_id``.

        Selects + scrolls to + focuses the matching row. Raises AssertionError
        if no row matches (the test fixture is misconfigured).
        """
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            if li.data(Qt.ItemDataRole.UserRole) == box_id:
                self.list_widget.setCurrentRow(i)
                return
        raise AssertionError(f"box_id {box_id} not present in view")

    # ------------------------------------------------------------------ build
    def _populate(self) -> None:
        """Populate the level dropdown and the list from self._boxes."""
        # Level dropdown — "All" + sorted distinct levels
        self.level.blockSignals(True)
        self.level.clear()
        self.level.addItem("All", None)
        seen_levels: set[int] = set()
        for b in self._boxes:
            lv = b.get("level")
            if isinstance(lv, int):
                seen_levels.add(lv)
        for lv in sorted(seen_levels):
            self.level.addItem(f"Lv{lv}", lv)
        self.level.blockSignals(False)

        self._rebuild_list()
        self._update_count()

    def _rebuild_list(self) -> None:
        self.list_widget.clear()
        # Stable order: by id ascending.
        for b in sorted(self._boxes, key=lambda b: int(b["id"])):
            box_id = int(b["id"])
            text = f"{box_id} · {b['name']}"
            lv = b.get("level")
            if isinstance(lv, int):
                text += f" (Lv{lv})"
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, box_id)
            self.list_widget.addItem(list_item)
            # Kick off an async image fetch — derived from id, no extra
            # image field required in the slug cache.
            image_url = (
                str(b.get("image", "")).strip()
                or derive_item_image_url(box_id)
            )
            if image_url:
                self._image_cache.request(image_url, box_id)
        # Re-apply current filters after repopulating.
        self._apply_filter(self.search.text())

    def _apply_icon(self, item_id: int, icon) -> None:
        """Apply an icon to the matching row when the async fetch lands.

        Linear scan — list is small (a few hundred box variants max) and
        icons arrive one at a time on the GUI thread, so this is cheap.
        """
        target = int(item_id)
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            if li.data(Qt.ItemDataRole.UserRole) == target:
                li.setIcon(icon)
                break

    def _display_name_for_id(self, box_id: int) -> str:
        for b in self._boxes:
            if int(b["id"]) == box_id:
                return str(b["name"])
        return ""

    # ------------------------------------------------------------------ filter
    def _apply_filter(self, _text: str | None = None) -> None:
        """Update row visibility from the current search + level selection."""
        needle = self.search.text().strip().lower()
        level_filter = self.level.currentData()
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            box_id = li.data(Qt.ItemDataRole.UserRole)
            label = li.text()
            name_part = label.split(" · ", 1)[1] if " · " in label else ""
            name_part = name_part.split(" (Lv", 1)[0]
            text_match = (not needle) or (
                needle in name_part.lower() or needle in str(box_id)
            )
            level = self._level_by_id.get(box_id)
            level_match = level_filter is None or level == level_filter
            li.setHidden(not (text_match and level_match))
        self._update_count()

    def _update_count(self) -> None:
        visible = sum(
            1
            for i in range(self.list_widget.count())
            if not self.list_widget.item(i).isHidden()
        )
        total = self.list_widget.count()
        if visible == total:
            self.count_label.setText(f"{total} boxes")
        else:
            self.count_label.setText(f"{visible} of {total} boxes")


# =============================================================================
# BoxPicker — thin dialog shim (T8)
# =============================================================================
class BoxPicker(QDialog):
    """Thin dialog shim around :class:`BoxView`.

    Kept so legacy callers (and the existing test suite) continue to compile
    unchanged. All UI attributes (``search``, ``list_widget``, ``count_label``)
    are exposed via property forwarding to the embedded ``BoxView``.
    """

    def __init__(self, slug_cache_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pick a box")
        self.resize(420, 560)

        self._view = BoxView(Path(slug_cache_path), self)

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
    @property
    def search(self) -> QLineEdit:
        return self._view.search

    @property
    def list_widget(self) -> QListWidget:
        return self._view.list_widget

    @property
    def count_label(self) -> QLabel:
        return self._view.count_label

    def selected_box_id(self) -> int | None:
        return self._view.selected_box_id()

    def selected_box_level(self) -> int | None:
        return self._view.selected_box_level()
