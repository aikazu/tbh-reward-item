"""One rule: enabled, name, reward_kind, pool_id, three Pick buttons, replacement chip row.

Arsenal-console layout — sharp corners, monospace IDs, rarity-bordered chips.

Pool-based rule model (Jul 2026 — tbh.city migration)
-------------------------------------------------------

Each rule targets a specific reward pool (Normal / Boss / Act) and
substitutes that pool's rewardItemId with the user-configured replacement
IDs. The rule carries:

* ``reward_kind`` — one of ``"normal"`` (monster_pool, pool 91xxxxxx),
  ``"boss"`` (boss_pool at BOSS-typed stages, pool 92xxxxxx), or
  ``"act"`` (boss_pool at ACTBOSS-typed stages, pool 93xxxxxx).
  Selectable via the rule card dropdown.
* ``pool_id`` — the tbh.city drop_key that identifies the drop pool
  (e.g. ``9100111`` = Act 1 / stage 1 normal pool). The proxy matches
  the body's ``itemId`` field directly against this integer — they're
  the same namespace on the wire.
* ``replacement_reward_item_ids`` — the cycling list of replacement
  item ids (must be obtainable; range replacement accepts any range).
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

# Reward kinds — display label + machine name.
# These correspond to tbh.city's drop pool naming:
#   "normal" → monster_pool (Normal Reward — pool 91xxxxxx)
#   "boss"   → boss_pool at BOSS-typed stages (Boss Reward — pool 92xxxxxx)
#   "act"    → boss_pool at ACTBOSS-typed stages (Act Reward — pool 93xxxxxx)
REWARD_KINDS: list[tuple[str, str]] = [
    ("Normal Reward", "normal"),
    ("Boss Reward",   "boss"),
    ("Act Reward",    "act"),
]
REWARD_KIND_LABELS: dict[str, str] = {
    "normal": "Normal Reward",
    "boss": "Boss Reward",
    "act": "Act Reward",
}

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
    pick_pool_id = Signal()  # opens CatalogPopup to pick a pool (Normal/Boss/Act)
    pick_replacement = Signal()  # opens CatalogPopup to pick replacement item ids
    remove = Signal()
    edited = Signal()
    pool_ids_changed = Signal(list)  # pool_ids edited; main_window re-pulls data

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rule_card")
        self.setProperty("active", False)
        self._locked: bool = False
        self._active: bool = False
        self._name: str = ""
        self._reward_kind: str = "normal"
        self._pool_ids: tuple[int, ...] = ()
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
        self.btn_remove.setFixedWidth(28)
        self.btn_remove.setProperty("toolbar_zone", "ghost")
        self.btn_remove.clicked.connect(self.remove)
        row1.addWidget(self.btn_remove)

        outer.addLayout(row1)

        # ---- Row 2: reward_kind + pool_id ----------------------------
        # The rule's "where" — which drop pool it targets. Reward kinds
        # are mutually exclusive: normal/boss/act. Each carries its own
        # pool_id (= tbh.city drop_key, e.g. 9100111 = Act 1 normal pool).
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        kind_label = QLabel("Reward")
        kind_label.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 11px;")
        row2.addWidget(kind_label)

        self.reward_kind_combo = QComboBox()
        self.reward_kind_combo.setToolTip(
            "Which reward pool this rule targets:\n"
            "  • Normal Reward: monster drops (pool 91xxxxxx)\n"
            "  • Boss Reward:   boss-stage drops (pool 92xxxxxx)\n"
            "  • Act Reward:    act-boss drops (pool 93xxxxxx)"
        )
        for label, machine in REWARD_KINDS:
            self.reward_kind_combo.addItem(label, userData=machine)
        self.reward_kind_combo.currentIndexChanged.connect(self._on_reward_kind_changed)
        row2.addWidget(self.reward_kind_combo)

        self.edit_pool_id = QLineEdit()
        self.edit_pool_id.setPlaceholderText("pool ids (comma-separated)")
        self.edit_pool_id.setFixedWidth(160)
        self.edit_pool_id.setFont(_MONO_FONT)
        self.edit_pool_id.setToolTip(
            "tbh.city drop_key (pool id). e.g. 9100111 = Act 1 normal pool,\n"
            "9301011 = Act 1 act-boss pool. See Catalog popup for the list."
        )
        self.edit_pool_id.textChanged.connect(self._on_pool_id_changed)
        row2.addWidget(self.edit_pool_id)

        self.pool_id_display = _make_mono_label("—", object_name="pool_id_display")
        self.pool_id_display.setMinimumWidth(110)
        self.pool_id_display.setStyleSheet(
            f"color: {MOCHA['text']}; background: {MOCHA['crust']};"
            f" border: 1px solid {MOCHA['surface1']}; border-radius: 2px;"
            f" padding: 4px 8px;"
        )
        row2.addWidget(self.pool_id_display)
        row2.addStretch()
        outer.addLayout(row2)

        # Pick buttons live ONLY in the DETAIL panel (no duplication).
        # The signals stay so MainWindow can trigger them programmatically
        # when needed, but no buttons are rendered on the rule card itself.
        self.btn_pick_pool_id = None
        self.btn_pick_replacement = None
        self.btn_pick_gear = None

        # Backwards-compat aliases — older code paths and tests still
        # reference these attribute names. The pool_id field plays the
        # same role (a single user-editable integer that identifies the
        # rule's target drop pool).
        self.edit_item_id = self.edit_pool_id
        self.item_id_display = self.pool_id_display

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
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(4)
        self._chip_row.addStretch()
        outer.addLayout(self._chip_row)

        self.section_heading.setStyleSheet(section_heading_style())
        self._refresh_style()

    # ---- data --------------------------------------------------------
    def set_data(self, rule: dict, locked: bool = False) -> None:
        self._locked = locked
        self._name = str(rule.get("name") or "")
        # Reward kind (Jul 2026 — tbh.city migration). 3 values only:
        # normal / boss / act.
        rk = rule.get("reward_kind")
        if isinstance(rk, str) and rk in {m for _, m in REWARD_KINDS}:
            self._reward_kind = rk
        else:
            self._reward_kind = "normal"
        pid = rule.get("pool_ids") or rule.get("pool_id")
        if isinstance(pid, list):
            self._pool_ids: tuple[int, ...] = tuple(int(p) for p in pid)
        elif isinstance(pid, int):
            self._pool_ids = (pid,)
        else:
            self._pool_ids = ()
        self._replacement_ids = [int(i) for i in (rule.get("replacement_reward_item_ids") or [])]

        for w in (self.chk_enabled, self.edit_name, self.edit_pool_id, self.reward_kind_combo):
            w.blockSignals(True)
        try:
            self.chk_enabled.setChecked(bool(rule.get("enabled", False)))
            self.edit_name.setText(self._name)
            # Set the combo by user data.
            for i in range(self.reward_kind_combo.count()):
                if self.reward_kind_combo.itemData(i) == self._reward_kind:
                    self.reward_kind_combo.setCurrentIndex(i)
                    break
            self.edit_pool_id.setText(self._format_pool_ids_text())
            self._refresh_pool_id_display()
        finally:
            for w in (self.chk_enabled, self.edit_name, self.edit_pool_id, self.reward_kind_combo):
                w.blockSignals(False)

        self.btn_remove.setEnabled(not locked)
        self._rebuild_chips()
        self._refresh_style()

    def to_dict(self) -> dict:
        return {
            "enabled": self.chk_enabled.isChecked(),
            "name": self.edit_name.text(),
            "reward_kind": self._reward_kind,
            "pool_ids": list(self._pool_ids),
            "replacement_reward_item_ids": list(self._replacement_ids),
        }

    def name(self) -> str:
        return self.edit_name.text()

    def reward_kind(self) -> str:
        return self._reward_kind

    def pool_ids(self) -> tuple[int, ...]:
        return self._pool_ids

    # Backwards-compat alias — old code calls ``pool_id()`` expecting a
    # single int. Returns the first pool_id if any, else None.
    def pool_id(self) -> int | None:
        return self._pool_ids[0] if self._pool_ids else None

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

    def set_item_id(self, pool_id: int | None) -> None:
            """Backwards-compat setter (older callers pass a single integer).
            Writes to ``pool_ids`` as a single-element tuple.
            """
            self._pool_ids = (int(pool_id),) if pool_id is not None else ()
            for w in (self.edit_item_id, self.edit_pool_id):
                w.blockSignals(True)
            try:
                self.edit_pool_id.setText(self._format_pool_ids_text())
            finally:
                for w in (self.edit_item_id, self.edit_pool_id):
                    w.blockSignals(False)
            self._refresh_pool_id_display()

    def remove_id(self, item_id: int) -> None:
        if item_id in self._replacement_ids:
            self._replacement_ids.remove(item_id)
            self._rebuild_chips()
        self.edited.emit()

    def _rebuild_chips(self) -> None:
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        peek_ids = self._replacement_ids[:6]
        n_total = len(self._replacement_ids)
        n_more = n_total - len(peek_ids)
        for i, item_id in enumerate(peek_ids):
            label, rarity = resolve_item_label(item_id)
            chip = ItemCard(self)
            chip.set_compact(True)
            chip.setObjectName(f"chip_{item_id}")
            chip.set_data({"id": item_id, "name": label, "rarity": rarity})
            chip.setToolTip(f"{label} (#{item_id}) — click to remove")
            chip.mousePressEvent = (
                lambda _e, _id=item_id: self.remove_id(_id)
            )
            self._chip_row.insertWidget(i, chip)
            self._chips.append(chip)
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

    def _on_reward_kind_changed(self, _idx: int) -> None:
        data = self.reward_kind_combo.currentData()
        self._reward_kind = str(data) if isinstance(data, str) else "normal"
        self._refresh_style()
        self.edited.emit()

    def _format_pool_ids_text(self) -> str:
        """Comma-separated string for the pool_id input field."""
        return ", ".join(str(p) for p in self._pool_ids)

    def _on_pool_id_changed(self, text: str) -> None:
        # Accept comma-separated ids. Empty / invalid → clear.
        ids: list[int] = []
        for raw in text.split(","):
            tok = raw.strip()
            if not tok:
                continue
            try:
                ids.append(int(tok))
            except ValueError:
                continue
        self._pool_ids = tuple(ids)
        self._refresh_pool_id_display()
        self.edited.emit()
        # Notify main_window so the detail panel can re-pull +
        # disable Pick gear/item when the pool list goes empty.
        self.pool_ids_changed.emit(list(self._pool_ids))

    def _refresh_pool_id_display(self) -> None:
        if not self._pool_ids:
            self.pool_id_display.setText("—")
        elif len(self._pool_ids) == 1:
            self.pool_id_display.setText(str(self._pool_ids[0]))
        else:
            self.pool_id_display.setText(f"{len(self._pool_ids)} pools")

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
        self.style().unpolish(self)
        self.style().polish(self)
