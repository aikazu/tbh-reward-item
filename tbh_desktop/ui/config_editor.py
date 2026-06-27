"""Container: rule list (top) + range replacement form (bottom).

Public API kept compatible with the previous table-based editor so callers in
``main_window.py`` and the test suite do not change.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.paths import DROPS_INDEX_CACHE
from tbh_desktop.ui.active_target import RangeTarget
from tbh_desktop.ui.item_card import ItemCard
from tbh_desktop.ui.rule_card import resolve_item_label
from tbh_desktop.ui.rule_list import RuleListView
from tbh_desktop.ui.theme import MOCHA, chip_style, section_heading_style

# Re-exported so tests can monkeypatch the cache path used by the range form.
_DROPS_INDEX_PATH = DROPS_INDEX_CACHE

_MONO_FONT = QFont("JetBrains Mono", 11)
_MONO_FONT.setStyleHint(QFont.StyleHint.Monospace)
_MONO_FONT.setFamily("JetBrains Mono")


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("section_heading")
    label.setStyleSheet(section_heading_style())
    return label


def _mono_input(*, placeholder: str = "") -> QLineEdit:
    edit = QLineEdit()
    edit.setFont(_MONO_FONT)
    if placeholder:
        edit.setPlaceholderText(placeholder)
    edit.setMinimumWidth(120)
    return edit


def _ghost_button(text: str, *, tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("toolbar_zone", "ghost")
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


class _RangeForm(QWidget):
    """Inline range replacement form. Emits focused() when any field is focused."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("range_form")
        self._chips: list[ItemCard] = []
        self._replacement_ids: list[int] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(10)

        # ---- Header: title + enabled toggle ----------------------------
        header = QHBoxLayout()
        header.setSpacing(8)
        self.section_heading = _section_label("RANGE REPLACEMENT")
        header.addWidget(self.section_heading)
        header.addStretch()
        self.chk_enabled = QCheckBox("enabled")
        self.chk_enabled.setToolTip("Enable range replacement (matches by item id range)")
        header.addWidget(self.chk_enabled)
        outer.addLayout(header)

        # ---- MATCH ITEM ID section -------------------------------------
        outer.addWidget(_section_label("MATCH ITEM ID"))
        id_row = QHBoxLayout()
        id_row.setSpacing(12)
        from_col = QVBoxLayout()
        self.lbl_min = QLabel("from")
        self.lbl_min.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 10px;")
        self.edit_min = _mono_input(placeholder="500000")
        from_col.addWidget(self.lbl_min)
        from_col.addWidget(self.edit_min)
        to_col = QVBoxLayout()
        self.lbl_max = QLabel("to")
        self.lbl_max.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 10px;")
        self.edit_max = _mono_input(placeholder="950000")
        to_col.addWidget(self.lbl_max)
        to_col.addWidget(self.edit_max)
        id_row.addLayout(from_col)
        id_row.addLayout(to_col)
        id_row.addStretch()
        outer.addLayout(id_row)

        # ---- REPLACES WITH section -------------------------------------
        outer.addWidget(_section_label("REPLACES WITH"))
        self.edit_ids = _mono_input(placeholder="605041, 605051, 605061")
        self.edit_ids.setMinimumWidth(0)
        self.edit_ids.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer.addWidget(self.edit_ids)

        # ---- chip row (visual mirror of the IDs above) -----------------
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(6)
        self._chip_row.addStretch()
        outer.addLayout(self._chip_row)

        # ---- pick buttons ----------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_pick_gear = _ghost_button("Pick gear", tooltip="Pick a gear item from cache")
        self.btn_pick_item = _ghost_button("Pick item", tooltip="Pick a non-gear item from the drops index")
        btn_row.addWidget(self.btn_pick_gear)
        btn_row.addWidget(self.btn_pick_item)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        # ---- bottom rule line ------------------------------------------
        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setFrameShadow(QFrame.Shadow.Plain)
        rule.setStyleSheet(f"color: {MOCHA['surface0']}; background: {MOCHA['surface0']};")
        rule.setFixedHeight(1)

    # ---- public API --------------------------------------------------
    def load(self, data: dict) -> None:
        self.chk_enabled.setChecked(bool(data.get("enabled", False)))
        self.edit_min.setText(str(data.get("match_min_item_id") or ""))
        self.edit_max.setText(str(data.get("match_max_item_id") or ""))
        ids = data.get("replacement_reward_item_ids") or []
        self.edit_ids.setText(", ".join(str(i) for i in ids))
        self._replacement_ids = [int(i) for i in ids]
        self._rebuild_chips()

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
            "replacement_reward_item_ids": list(self._replacement_ids),
        }

    def add_ids(self, ids: list[int]) -> None:
        before = set(self._replacement_ids)
        for i in ids:
            if i not in before:
                self._replacement_ids.append(int(i))
                before.add(int(i))
        self.edit_ids.setText(", ".join(str(i) for i in self._replacement_ids))
        self._rebuild_chips()

    def _rebuild_chips(self) -> None:
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        for i, item_id in enumerate(self._replacement_ids):
            label, rarity = resolve_item_label(item_id)
            chip = ItemCard(self)
            chip.set_compact(True)
            chip.setObjectName(f"range_chip_{item_id}")
            chip.set_data({"id": item_id, "name": label, "rarity": rarity})
            chip.setStyleSheet(chip_style(rarity, compact=True))
            chip.setToolTip(f"{label} (#{item_id}) — click to remove")
            chip.mousePressEvent = lambda _e, _id=item_id: self._remove_id(_id)  # type: ignore[method-assign]
            self._chip_row.insertWidget(i, chip)
            self._chips.append(chip)

    def _remove_id(self, item_id: int) -> None:
        if item_id in self._replacement_ids:
            self._replacement_ids.remove(item_id)
            self.edit_ids.setText(", ".join(str(i) for i in self._replacement_ids))
            self._rebuild_chips()


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
        self._range_form.add_ids(ids)
        self._rule_list._range["replacement_reward_item_ids"] = list(
            self._range_form._replacement_ids
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
