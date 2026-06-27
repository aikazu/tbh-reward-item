"""One rule: enabled, name, item_id, three Pick buttons, replacement chip row."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.item_card import ItemCard
from tbh_desktop.ui.theme import MOCHA


class RuleCard(QFrame):
    pick_box_id = Signal()
    pick_box_loot = Signal()
    pick_gear = Signal()
    remove = Signal()
    edited = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rule_card")
        self._locked: bool = False
        self._active: bool = False
        self._name: str = ""
        self._item_id: int | None = None
        self._replacement_ids: list[int] = []
        self._chips: list[ItemCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # Row 1: enabled + name
        row1 = QHBoxLayout()
        self.chk_enabled = QCheckBox()
        self.chk_enabled.toggled.connect(self.edited)
        row1.addWidget(self.chk_enabled)
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Rule name")
        self.edit_name.textChanged.connect(self._on_name_changed)
        row1.addWidget(self.edit_name, stretch=1)
        outer.addLayout(row1)

        # Row 2: item_id + pick buttons
        row2 = QHBoxLayout()
        self.edit_item_id = QLineEdit()
        self.edit_item_id.setPlaceholderText("box / item id")
        self.edit_item_id.setFixedWidth(110)
        self.edit_item_id.textChanged.connect(self._on_item_id_changed)
        row2.addWidget(self.edit_item_id)
        self.btn_pick_box_id = QPushButton("Pick box")
        self.btn_pick_box_id.clicked.connect(self.pick_box_id)
        row2.addWidget(self.btn_pick_box_id)
        self.btn_pick_box_loot = QPushButton("Pick loot")
        self.btn_pick_box_loot.clicked.connect(self.pick_box_loot)
        row2.addWidget(self.btn_pick_box_loot)
        self.btn_pick_gear = QPushButton("Pick gear")
        self.btn_pick_gear.clicked.connect(self.pick_gear)
        row2.addWidget(self.btn_pick_gear)
        row2.addStretch()
        outer.addLayout(row2)

        # Row 3: chip wrap
        self._chip_row = QHBoxLayout()
        self._chip_row.setSpacing(4)
        self._chip_row.addStretch()
        outer.addLayout(self._chip_row)

        # Row 4: remove
        row4 = QHBoxLayout()
        row4.addStretch()
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.clicked.connect(self.remove)
        row4.addWidget(self.btn_remove)
        outer.addLayout(row4)

        self._refresh_style()

    # ---- data --------------------------------------------------------
    def set_data(self, rule: dict, locked: bool = False) -> None:
        self._locked = locked
        self._name = str(rule.get("name") or "")
        raw_id = rule.get("item_id")
        self._item_id = int(raw_id) if isinstance(raw_id, int) else None
        self._replacement_ids = [int(i) for i in (rule.get("replacement_reward_item_ids") or [])]
        self.chk_enabled.setChecked(bool(rule.get("enabled", False)))
        self.edit_name.setText(self._name)
        self.edit_item_id.setText("" if self._item_id is None else str(self._item_id))
        self.btn_remove.setEnabled(not locked)
        self._rebuild_chips()
        self._refresh_style()

    def to_dict(self) -> dict:
        return {
            "enabled": self.chk_enabled.isChecked(),
            "name": self.edit_name.text(),
            "item_id": self._item_id,
            "replacement_reward_item_ids": list(self._replacement_ids),
        }

    def name(self) -> str:
        return self.edit_name.text()

    def item_id(self) -> int | None:
        return self._item_id

    def replacement_ids(self) -> list[int]:
        return list(self._replacement_ids)

    # ---- chips -------------------------------------------------------
    def add_ids(self, ids: list[int]) -> None:
        before = set(self._replacement_ids)
        for i in ids:
            if i not in before:
                self._replacement_ids.append(int(i))
                before.add(int(i))
        self._rebuild_chips()
        self.edited.emit()

    def remove_id(self, item_id: int) -> None:
        if item_id in self._replacement_ids:
            self._replacement_ids.remove(item_id)
            self._rebuild_chips()
            self.edited.emit()

    def _rebuild_chips(self) -> None:
        # remove old chips
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        # add new
        for i, item_id in enumerate(self._replacement_ids):
            chip = ItemCard(self)
            chip.set_compact(True)
            chip.set_data({"id": item_id, "name": str(item_id), "rarity": "COMMON"})
            chip.setToolTip(f"item_id {item_id} — click to remove")
            chip.mousePressEvent = lambda _e, _id=item_id: self.remove_id(_id)  # type: ignore[method-assign]
            self._chip_row.insertWidget(i, chip)
            self._chips.append(chip)

    # ---- active state ------------------------------------------------
    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._refresh_style()

    def is_active(self) -> bool:
        return self._active

    # ---- internals ---------------------------------------------------
    def _on_name_changed(self, text: str) -> None:
        self._name = text
        self.edited.emit()

    def _on_item_id_changed(self, text: str) -> None:
        try:
            self._item_id = int(text.strip()) if text.strip() else None
        except ValueError:
            self._item_id = None
        self.edited.emit()

    def _refresh_style(self) -> None:
        left_border = MOCHA["blue"] if self._active else MOCHA["surface0"]
        self.setStyleSheet(
            f"#rule_card {{"
            f"  background-color: {MOCHA['mantle']};"
            f"  border: 1px solid {MOCHA['surface0']};"
            f"  border-left: 4px solid {left_border};"
            f"  border-radius: 8px;"
            f"}}"
        )
