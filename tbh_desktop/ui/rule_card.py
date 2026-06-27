"""One rule: enabled, name, item_id, three Pick buttons, replacement chip row.

Arsenal-console layout — sharp corners, monospace IDs, rarity-bordered chips.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
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
from tbh_desktop.ui.item_card import ItemCard
from tbh_desktop.ui.theme import MOCHA, RARITY, chip_style, section_heading_style

# Path that resolve_item_label reads on each call. Patchable in tests.
_DROPS_INDEX_PATH: Path = DROPS_INDEX_CACHE


def resolve_item_label(item_id: int) -> tuple[str, str]:
    """Return (display_label, rarity) for an item_id.

    Reads the cached drops index synchronously (the file is small — a few
    hundred items). Falls back to ``("Unknown #<id>", "COMMON")`` when the
    cache is missing or the id isn't in it.
    """
    try:
        if _DROPS_INDEX_PATH.exists():
            data = json.loads(_DROPS_INDEX_PATH.read_text(encoding="utf-8"))
            items = data.get("items") if isinstance(data, dict) else data
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and it.get("id") == item_id:
                        name = str(it.get("name") or f"#{item_id}")
                        rarity = str(it.get("rarity") or "COMMON").upper()
                        if rarity not in RARITY:
                            rarity = "COMMON"
                        return name, rarity
    except (OSError, ValueError):
        pass
    return f"Unknown #{item_id}", "COMMON"


_MONO_FONT = QFont("JetBrains Mono", 11)
_MONO_FONT.setStyleHint(QFont.StyleHint.Monospace)
_MONO_FONT.setFamily("JetBrains Mono")


def _make_mono_label(text: str = "", *, object_name: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setFont(_MONO_FONT)
    if object_name:
        label.setObjectName(object_name)
    return label


class RuleCard(QFrame):
    pick_box_id = Signal()
    pick_box_loot = Signal()
    pick_gear = Signal()
    remove = Signal()
    edited = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rule_card")
        self.setProperty("active", False)
        self._locked: bool = False
        self._active: bool = False
        self._name: str = ""
        self._item_id: int | None = None
        self._replacement_ids: list[int] = []
        self._chips: list[ItemCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        # ---- Row 1: status dot + name + actions -------------------------
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("status_dot")
        self.status_dot.setFixedWidth(14)
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row1.addWidget(self.status_dot)

        self.chk_enabled = QCheckBox()
        self.chk_enabled.setToolTip("Enable this rule")
        self.chk_enabled.toggled.connect(self.edited)
        row1.addWidget(self.chk_enabled)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Rule name")
        self.edit_name.textChanged.connect(self._on_name_changed)
        row1.addWidget(self.edit_name, stretch=1)

        self.btn_remove = QPushButton("✕")
        self.btn_remove.setObjectName("btn_remove_rule")
        self.btn_remove.setToolTip("Remove rule")
        self.btn_remove.setFixedWidth(32)
        self.btn_remove.setProperty("toolbar_zone", "ghost")
        self.btn_remove.clicked.connect(self.remove)
        row1.addWidget(self.btn_remove)

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("btn_rule_settings")
        self.btn_settings.setToolTip("Rule settings")
        self.btn_settings.setFixedWidth(32)
        self.btn_settings.setProperty("toolbar_zone", "ghost")
        self.btn_settings.setEnabled(False)  # reserved for future menu
        row1.addWidget(self.btn_settings)

        outer.addLayout(row1)

        # ---- Row 2: ID + 3 pick buttons (mono + ghost) -----------------
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        id_label = QLabel("ID")
        id_label.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 11px;")
        row2.addWidget(id_label)

        self.item_id_display = _make_mono_label("—", object_name="item_id_display")
        self.item_id_display.setMinimumWidth(96)
        self.item_id_display.setStyleSheet(
            f"color: {MOCHA['text']}; background: {MOCHA['crust']};"
            f" border: 1px solid {MOCHA['surface1']}; border-radius: 2px;"
            f" padding: 4px 8px;"
        )
        row2.addWidget(self.item_id_display)

        self.edit_item_id = QLineEdit()
        self.edit_item_id.setPlaceholderText("box / item id")
        self.edit_item_id.setFixedWidth(96)
        self.edit_item_id.setFont(_MONO_FONT)
        self.edit_item_id.textChanged.connect(self._on_item_id_changed)
        row2.addWidget(self.edit_item_id)

        row2.addSpacing(8)
        self.btn_pick_box_id = QPushButton("Pick box")
        self.btn_pick_box_id.setProperty("toolbar_zone", "ghost")
        self.btn_pick_box_id.clicked.connect(self.pick_box_id)
        row2.addWidget(self.btn_pick_box_id)
        self.btn_pick_box_loot = QPushButton("Pick loot")
        self.btn_pick_box_loot.setProperty("toolbar_zone", "ghost")
        self.btn_pick_box_loot.clicked.connect(self.pick_box_loot)
        row2.addWidget(self.btn_pick_box_loot)
        self.btn_pick_gear = QPushButton("Pick gear")
        self.btn_pick_gear.setProperty("toolbar_zone", "ghost")
        self.btn_pick_gear.clicked.connect(self.pick_gear)
        row2.addWidget(self.btn_pick_gear)
        row2.addStretch()
        outer.addLayout(row2)

        # ---- Row 3: REPLACES divider + count + peek -------------------
        divider_row = QHBoxLayout()
        divider_row.setSpacing(8)
        self.section_heading = QLabel("REPLACES")
        self.section_heading.setObjectName("section_heading")
        divider_row.addWidget(self.section_heading)
        self.replace_count = QLabel("0")
        self.replace_count.setObjectName("replace_count")
        self.replace_count.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 11px;"
            f" background: {MOCHA['surface0']};"
            f" border-radius: 8px; padding: 1px 8px;"
        )
        divider_row.addWidget(self.replace_count)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet(f"color: {MOCHA['surface1']}; background: {MOCHA['surface1']};")
        line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        divider_row.addWidget(line, stretch=1)
        outer.addLayout(divider_row)

        # ---- Row 4: chip peek (compact, wraps) -------------------------
        # The full chip strip lives in the detail panel — the rule card
        # only shows a peek so the user can tell at a glance what rewards
        # the rule cycles through. Chips are clipped if they overflow
        # rather than expanding the card height.
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(4)
        self._chip_row.addStretch()
        outer.addLayout(self._chip_row)

        # Pre-apply section heading QSS so first paint shows correct font.
        self.section_heading.setStyleSheet(section_heading_style())
        self._refresh_style()

    # ---- data --------------------------------------------------------
    def set_data(self, rule: dict, locked: bool = False) -> None:
        self._locked = locked
        self._name = str(rule.get("name") or "")
        raw_id = rule.get("item_id")
        self._item_id = int(raw_id) if isinstance(raw_id, int) else None
        self._replacement_ids = [int(i) for i in (rule.get("replacement_reward_item_ids") or [])]

        # Suppress edited signals during programmatic load.
        for w in (self.chk_enabled, self.edit_name, self.edit_item_id):
            w.blockSignals(True)
        try:
            self.chk_enabled.setChecked(bool(rule.get("enabled", False)))
            self.edit_name.setText(self._name)
            self.edit_item_id.setText("" if self._item_id is None else str(self._item_id))
            self._refresh_item_id_display()
        finally:
            for w in (self.chk_enabled, self.edit_name, self.edit_item_id):
                w.blockSignals(False)

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
        # Limit peek to first 6 chips — the full strip lives in the detail
        # panel; the rule card just gives an at-a-glance preview.
        peek_ids = self._replacement_ids[:6]
        n_total = len(self._replacement_ids)
        n_more = n_total - len(peek_ids)
        for i, item_id in enumerate(peek_ids):
            label, rarity = resolve_item_label(item_id)
            chip = ItemCard(self)
            chip.set_compact(True)
            chip.setObjectName(f"chip_{item_id}")
            # ItemCard self-styles via QPalette (background) + a single
            # setStyleSheet call in _refresh_style for the border. Don't
            # override its stylesheet here — overriding with a separate
            # chip_style() QSS turns off autoFillBackground and the chip
            # renders as an empty rectangle.
            chip.set_data({"id": item_id, "name": label, "rarity": rarity})
            chip.setToolTip(f"{label} (#{item_id}) — click to remove")
            # Click → request removal. Wrap in default-arg capture so the
            # bound id doesn't change if more chips are added later.
            chip.mousePressEvent = (
                lambda _e, _id=item_id: self.remove_id(_id)
            )
            self._chip_row.insertWidget(i, chip)
            self._chips.append(chip)
        # "+N more" badge if the peek is truncated.
        if n_more > 0:
            from PySide6.QtWidgets import QLabel as _QL
            more = _QL(f"+{n_more} more")
            more.setObjectName("chip_more")
            more.setStyleSheet(
                f"color: {MOCHA['overlay1']}; font-size: 11px;"
                f" padding: 2px 8px; background: {MOCHA['surface0']};"
                f" border-radius: 8px;"
            )
            self._chip_row.insertWidget(len(peek_ids), more)
            self._chips.append(more)  # type: ignore[arg-type]
        # Update the count badge.
        self.replace_count.setText(str(n_total))
        self.replace_count.setToolTip(
            f"{n_total} reward ID{'s' if n_total != 1 else ''} (cycled in order)"
        )

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
        self._refresh_item_id_display()
        self.edited.emit()

    def _refresh_item_id_display(self) -> None:
        self.item_id_display.setText("—" if self._item_id is None else str(self._item_id))

    def _refresh_style(self) -> None:
        enabled = self.chk_enabled.isChecked()
        if self._active:
            dot_color = MOCHA["sapphire"]
        elif enabled:
            dot_color = MOCHA["green"]
        else:
            dot_color = MOCHA["overlay0"]
        self.status_dot.setStyleSheet(f"color: {dot_color}; font-size: 14px;")
        self.setProperty("active", self._active)
        # Re-apply inline stylesheet so QSS dynamic property [active='true']
        # can resolve. Qt only reads the stylesheet on setStyleSheet, not on
        # setProperty, so we re-set it.
        self.style().unpolish(self)
        self.style().polish(self)
