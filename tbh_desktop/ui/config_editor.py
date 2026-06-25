# tbh_desktop/ui/config_editor.py
"""Editor for specific_queue_rules + range_replacement, operating on raw dict."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


COL_ENABLED = 0
COL_NAME = 1
COL_ITEM_ID = 2
COL_REPLACEMENT = 3

# ItemDataRole used to mark a row as a locked default rule (cannot be removed).
LOCK_ROLE = Qt.ItemDataRole.UserRole + 1

# Indonesian hint shown when the pick-box button is disabled.
TOOLTIP_PICK_BOX_DISABLED = "Pilih rule dulu untuk memilih loot box"
# Indonesian hint shown when the remove button is disabled on a locked rule.
TOOLTIP_REMOVE_LOCKED = "Default rule tidak bisa dihapus"


class ConfigEditor(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: dict[str, Any] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # ── Specific Queue Rules ──────────────────────────────────────────
        rules_group = QGroupBox("Specific Queue Rules")
        rules_layout = QVBoxLayout(rules_group)
        rules_layout.setSpacing(8)

        self.rules_table = QTableWidget(0, 4)
        self.rules_table.setHorizontalHeaderLabels(
            ["Enabled", "Name", "Item ID", "Replacement IDs"]
        )
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.verticalHeader().setVisible(False)
        header = self.rules_table.horizontalHeader()
        header.setSectionResizeMode(COL_ENABLED, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_ITEM_ID, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_REPLACEMENT, QHeaderView.ResizeMode.Stretch)
        rules_layout.addWidget(self.rules_table)

        rules_buttons = QHBoxLayout()
        rules_buttons.setSpacing(6)
        btn_add = QPushButton("＋  Add rule")
        self.btn_remove = QPushButton("－  Remove rule")
        self.btn_pick_box = QPushButton("Pick from box loot")
        self.btn_pick_gear_rule = QPushButton("Pick gear")
        for b in (btn_add, self.btn_remove, self.btn_pick_box, self.btn_pick_gear_rule):
            rules_buttons.addWidget(b)
        rules_buttons.addStretch()
        rules_layout.addLayout(rules_buttons)
        btn_add.clicked.connect(self._add_rule)
        self.btn_remove.clicked.connect(self._remove_rule)

        # Action buttons start disabled until a valid row is selected.
        self._loading = False
        self.btn_remove.setEnabled(False)
        self.btn_remove.setToolTip(TOOLTIP_REMOVE_LOCKED)
        self.btn_pick_box.setEnabled(False)
        self.btn_pick_box.setToolTip(TOOLTIP_PICK_BOX_DISABLED)
        self.rules_table.itemSelectionChanged.connect(self._update_action_button_states)

        layout.addWidget(rules_group)

        # ── Range Replacement ─────────────────────────────────────────────
        range_group = QGroupBox("Range Replacement")
        range_form = QFormLayout(range_group)
        range_form.setSpacing(8)
        range_form.setContentsMargins(14, 18, 14, 14)
        self.range_enabled = QCheckBox("enabled")
        self.range_min = QLineEdit()
        self.range_min.setPlaceholderText("e.g. 500000")
        self.range_max = QLineEdit()
        self.range_max.setPlaceholderText("e.g. 950000")
        self.range_ids = QLineEdit()
        self.range_ids.setPlaceholderText("529191, 419191, 409191")
        self.btn_pick_gear_range = QPushButton("Pick gear")
        range_form.addRow("Enabled", self.range_enabled)
        range_form.addRow("match_min_item_id", self.range_min)
        range_form.addRow("match_max_item_id", self.range_max)
        range_form.addRow("replacement IDs", self.range_ids)
        range_form.addRow("", self.btn_pick_gear_range)
        layout.addWidget(range_group)

        layout.addStretch()

    def load(self, data: dict[str, Any]) -> None:
        self._data = data
        rules = data.get("specific_queue_rules", []) or []
        # Guard selection signal firing mid-population.
        self._loading = True
        self.rules_table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            self._set_rule_row(row, rule, locked=True)
        self._loading = False
        rng = data.get("range_replacement", {}) or {}
        self.range_enabled.setChecked(bool(rng.get("enabled", False)))
        self.range_min.setText(str(rng.get("match_min_item_id") or ""))
        self.range_max.setText(str(rng.get("match_max_item_id") or ""))
        self.range_ids.setText(self._ids_to_text(rng.get("replacement_reward_item_ids") or []))
        self._update_action_button_states()

    def _set_rule_row(self, row: int, rule: dict[str, Any], locked: bool = True) -> None:
        enabled_item = QTableWidgetItem()
        enabled_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        enabled_item.setCheckState(
            Qt.CheckState.Checked if rule.get("enabled") else Qt.CheckState.Unchecked
        )
        # Mark default (loaded) rules as locked so they cannot be removed.
        enabled_item.setData(LOCK_ROLE, locked)
        self.rules_table.setItem(row, COL_ENABLED, enabled_item)
        self.rules_table.setItem(row, COL_NAME, QTableWidgetItem(str(rule.get("name") or "")))
        self.rules_table.setItem(row, COL_ITEM_ID, QTableWidgetItem(str(rule.get("item_id") or "")))
        self.rules_table.setItem(
            row, COL_REPLACEMENT,
            QTableWidgetItem(self._ids_to_text(rule.get("replacement_reward_item_ids") or [])),
        )

    def _add_rule(self) -> None:
        row = self.rules_table.rowCount()
        self.rules_table.insertRow(row)
        # User-added rules are never locked.
        self._set_rule_row(
            row,
            {"enabled": False, "name": "", "item_id": "", "replacement_reward_item_ids": []},
            locked=False,
        )

    def _remove_rule(self) -> None:
        row = self.rules_table.currentRow()
        if row < 0:
            return
        enabled_item = self.rules_table.item(row, COL_ENABLED)
        if enabled_item is not None and enabled_item.data(LOCK_ROLE) is True:
            QMessageBox.warning(
                self,
                "Cannot remove",
                "Default rules cannot be removed. Add your own rule to edit.",
            )
            return
        self.rules_table.removeRow(row)

    def _update_action_button_states(self) -> None:
        """Sync remove/pick-box button enabled state + tooltips to the selection.

        Called on itemSelectionChanged. No-op while loading to avoid spurious
        updates during table population.
        """
        if self._loading:
            return
        row = self.rules_table.currentRow()
        if row < 0:
            self.btn_remove.setEnabled(False)
            self.btn_remove.setToolTip(TOOLTIP_REMOVE_LOCKED)
            self.btn_pick_box.setEnabled(False)
            self.btn_pick_box.setToolTip(TOOLTIP_PICK_BOX_DISABLED)
            return
        enabled_item = self.rules_table.item(row, COL_ENABLED)
        locked = bool(enabled_item.data(LOCK_ROLE)) if enabled_item is not None else False
        self.btn_remove.setEnabled(not locked)
        self.btn_remove.setToolTip(TOOLTIP_REMOVE_LOCKED if locked else "")
        valid = self.selected_rule_item_id() is not None
        self.btn_pick_box.setEnabled(valid)
        self.btn_pick_box.setToolTip("" if valid else TOOLTIP_PICK_BOX_DISABLED)

    def selected_rule_item_id(self) -> int | None:
        row = self.rules_table.currentRow()
        if row < 0:
            return None
        item = self.rules_table.item(row, COL_ITEM_ID)
        if item is None:
            return None
        text = item.text().strip()
        try:
            return int(text)
        except ValueError:
            return None

    def add_ids_to_selected_rule(self, ids: list[int]) -> None:
        row = self.rules_table.currentRow()
        if row < 0:
            return
        cell = self.rules_table.item(row, COL_REPLACEMENT)
        if cell is None:
            return
        existing = self._text_to_ids(cell.text())
        merged = existing + [i for i in ids if i not in existing]
        cell.setText(self._ids_to_text(merged))

    def add_ids_to_range(self, ids: list[int]) -> None:
        existing = self._text_to_ids(self.range_ids.text())
        merged = existing + [i for i in ids if i not in existing]
        self.range_ids.setText(self._ids_to_text(merged))

    def dump(self) -> dict[str, Any]:
        """Return updated raw dict preserving advanced fields."""
        data = dict(self._data)
        rules = []
        original_rules = self._data.get("specific_queue_rules") or []
        for row in range(self.rules_table.rowCount()):
            base = dict(original_rules[row]) if row < len(original_rules) else {}
            base["enabled"] = self.rules_table.item(row, COL_ENABLED).checkState() == Qt.CheckState.Checked
            base["name"] = self.rules_table.item(row, COL_NAME).text()
            base["item_id"] = self._parse_int(self.rules_table.item(row, COL_ITEM_ID).text())
            base["replacement_reward_item_ids"] = self._text_to_ids(
                self.rules_table.item(row, COL_REPLACEMENT).text()
            )
            rules.append(base)
        data["specific_queue_rules"] = rules
        prev_range = data.get("range_replacement") or {}
        data["range_replacement"] = {
            "enabled": self.range_enabled.isChecked(),
            "name": prev_range.get("name", "Range replacement"),
            "match_min_item_id": self._parse_int(self.range_min.text()),
            "match_max_item_id": self._parse_int(self.range_max.text()),
            "replacement_reward_item_ids": self._text_to_ids(self.range_ids.text()),
        }
        return data

    @staticmethod
    def _parse_int(text: str) -> int:
        try:
            return int((text or "").strip())
        except ValueError:
            return 0

    @staticmethod
    def _ids_to_text(ids: list[Any]) -> str:
        return ", ".join(str(i) for i in (ids or []))

    @staticmethod
    def _text_to_ids(text: str) -> list[int]:
        out: list[int] = []
        for part in (text or "").replace(",", " ").split():
            try:
                out.append(int(part))
            except ValueError:
                continue
        return out
