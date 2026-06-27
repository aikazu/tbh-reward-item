"""Container: rule list (top) + range replacement form (bottom).

Public API kept compatible with the previous table-based editor so callers in
``main_window.py`` and the test suite do not change.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.active_target import RangeTarget
from tbh_desktop.ui.rule_list import RuleListView


class _RangeForm(QWidget):
    """Inline range replacement form. Emits focused() when any field is focused."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        group = QGroupBox("Range Replacement")
        form = QFormLayout(group)
        self.chk_enabled = QCheckBox("enabled")
        self.edit_min = QLineEdit(); self.edit_min.setPlaceholderText("e.g. 500000")
        self.edit_max = QLineEdit(); self.edit_max.setPlaceholderText("e.g. 950000")
        self.edit_ids = QLineEdit(); self.edit_ids.setPlaceholderText("529191, 419191, 409191")
        self.btn_pick_gear = QPushButton("Pick gear")
        self.btn_pick_item = QPushButton("Pick item")
        form.addRow("Enabled", self.chk_enabled)
        form.addRow("match_min_item_id", self.edit_min)
        form.addRow("match_max_item_id", self.edit_max)
        form.addRow("replacement IDs", self.edit_ids)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_pick_gear)
        btn_row.addWidget(self.btn_pick_item)
        btn_row.addStretch()
        form.addRow("", btn_row)
        layout.addWidget(group)

    def load(self, data: dict) -> None:
        self.chk_enabled.setChecked(bool(data.get("enabled", False)))
        self.edit_min.setText(str(data.get("match_min_item_id") or ""))
        self.edit_max.setText(str(data.get("match_max_item_id") or ""))
        ids = data.get("replacement_reward_item_ids") or []
        self.edit_ids.setText(", ".join(str(i) for i in ids))

    def dump(self) -> dict:
        def _i(s: str) -> int:
            try:
                return int((s or "").strip())
            except ValueError:
                return 0
        return {
            "enabled": self.chk_enabled.isChecked(),
            "name": "Range replacement",
            "match_min_item_id": _i(self.edit_min.text()),
            "match_max_item_id": _i(self.edit_max.text()),
            "replacement_reward_item_ids": [
                int(p) for p in self.edit_ids.text().replace(",", " ").split() if p.lstrip("-").isdigit()
            ],
        }


class ConfigEditor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)
        self._rule_list = RuleListView()
        self._range_form = _RangeForm()
        outer.addWidget(self._rule_list, stretch=3)
        outer.addWidget(self._range_form, stretch=1)
        # Make the range form focus set the active target to RangeTarget.
        for w in (
            self._range_form.chk_enabled,
            self._range_form.edit_min,
            self._range_form.edit_max,
            self._range_form.edit_ids,
        ):
            w.installEventFilter(self)
        self._active_target_kind: str = "none"

    # ---- public API (back-compat) -----------------------------------
    def load(self, data: dict[str, Any]) -> None:
        self._rule_list.load(data)
        self._range_form.load(data.get("range_replacement") or {})

    def dump(self) -> dict[str, Any]:
        out = self._rule_list.dump()
        out["range_replacement"].update(self._range_form.dump())
        return out

    def rule_list(self) -> RuleListView:
        return self._rule_list

    def range_form(self) -> _RangeForm:
        return self._range_form

    def selected_rule_item_id(self) -> int | None:
        return self._rule_list.selected_rule_item_id()

    def selected_rule_level(self) -> int | None:
        return self._rule_list.selected_rule_level()

    def set_selected_rule_item_id(self, box_id: int, level: int | None) -> None:
        self._rule_list.set_selected_rule_item_id(box_id, level)

    def add_ids_to_selected_rule(self, ids: list[int]) -> None:
        self._rule_list.add_ids_to_selected_rule(ids)

    def add_ids_to_range(self, ids: list[int]) -> None:
        # Route through the active-target system for symmetry.
        self._rule_list.set_active_target(RangeTarget())
        self._rule_list.add_ids_to_range(ids)
        self._range_form.edit_ids.setText(
            ", ".join(str(i) for i in self._rule_list.dump()["range_replacement"]["replacement_reward_item_ids"])
        )

    # ---- event filter (range form focus) ----------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.FocusIn and obj in (
            self._range_form.chk_enabled,
            self._range_form.edit_min,
            self._range_form.edit_max,
            self._range_form.edit_ids,
        ):
            self._rule_list.set_active_target(RangeTarget())
        return super().eventFilter(obj, event)