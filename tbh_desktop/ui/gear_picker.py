"""Dialog to pick gear reward IDs from cached gear list."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class GearPicker(QDialog):
    def __init__(self, gear_items: list[dict[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pick gear")
        self.resize(400, 500)
        self._all = gear_items

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name or id...")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate(gear_items)

    def _populate(self, items: list[dict[str, Any]]) -> None:
        self.list_widget.clear()
        for item in items:
            text = f'{item["id"]} · {item["name"]} ({item.get("rarity", "")})'
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item["id"])
            self.list_widget.addItem(list_item)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        if not text:
            self._populate(self._all)
            return
        filtered = [
            i for i in self._all if text in i["name"].lower() or text in str(i["id"])
        ]
        self._populate(filtered)

    def selected_ids(self) -> list[int]:
        return [
            item.data(Qt.ItemDataRole.UserRole) for item in self.list_widget.selectedItems()
        ]