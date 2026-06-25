"""Dialog to pick a box ID from the box slug cache.

Presents all known box IDs (from ``box_slug_cache.json``) as a searchable
list.  Each entry shows ``id · Display Name (LvN)`` when the slug encodes a
level.  Returns the selected ``box_id`` (and its parsed level) via
:meth:`selected_box_id` / :meth:`selected_box_level`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

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


class BoxPicker(QDialog):
    """Searchable list of known boxes; user picks one to use as item_id."""

    def __init__(self, slug_cache_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pick a box")
        self.resize(420, 560)
        self._level_by_id: dict[int, int | None] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Select a box:"))

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name or id…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        layout.addWidget(self.list_widget)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #7f849c; font-size: 11px;")
        layout.addWidget(self.count_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._build(slug_cache_path)

    # ------------------------------------------------------------------ build
    def _build(self, cache_path: Path) -> None:
        data = load_box_cache(cache_path)
        for box_id_str, slug in sorted(data.items(), key=lambda kv: int(kv[0])):
            try:
                box_id = int(box_id_str)
            except ValueError:
                continue
            display = _slug_to_display(slug)
            level = parse_box_level(slug)
            self._level_by_id[box_id] = level
            text = f"{box_id} · {display}"
            if level is not None:
                text += f" (Lv{level})"
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, box_id)
            self.list_widget.addItem(list_item)
        self._update_count()

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            li.setHidden(bool(text) and text not in li.text().lower())
        self._update_count()

    def _update_count(self) -> None:
        visible = sum(
            1
            for i in range(self.list_widget.count())
            if not self.list_widget.item(i).isHidden()
        )
        total = self.list_widget.count()
        self.count_label.setText(
            f"{total} boxes" if visible == total else f"{visible} of {total} boxes"
        )

    # ------------------------------------------------------------------ result
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
