"""Dialog to pick reward IDs from a box's loot table."""
from __future__ import annotations

from typing import Any

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


class BoxLootPicker(QDialog):
    def __init__(
        self, box_id: int, loot_items: list[dict[str, Any]], parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Pick from box {box_id} loot")
        self.resize(400, 500)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Box {box_id} — loot table:"))
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

        # Build the list once; _filter toggles item visibility (preserves selection).
        self._build_all(loot_items)

    def _build_all(self, items: list[dict[str, Any]]) -> None:
        """Populate the list widget once. Skip items lacking id or name keys."""
        self.list_widget.clear()
        for item in items:
            item_id = item.get("id")
            name = item.get("name")
            if item_id is None or name is None:
                continue  # malformed cache entry — skip defensively
            text = f"{item_id} · {name} ({item.get('rate', '')})"
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item_id)
            self.list_widget.addItem(list_item)

    def _filter(self, text: str) -> None:
        """Toggle item visibility by name/id substring. Empty text shows all."""
        text = text.strip().lower()
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            item_id = list_item.data(Qt.ItemDataRole.UserRole)
            # item text is "id · name (rate)"; match against name and id.
            label = list_item.text()
            name = label.split(" · ", 1)[1] if " · " in label else ""
            match = text in name.lower() or text in str(item_id)
            list_item.setHidden(not match if text else False)

    def selected_ids(self) -> list[int]:
        return [
            item.data(Qt.ItemDataRole.UserRole) for item in self.list_widget.selectedItems()
        ]