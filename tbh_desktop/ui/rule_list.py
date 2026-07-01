"""QListView + custom delegate that renders RuleCard per row.

Owns three rule lists (Normal / Boss / Act) plus the pool-range form.
Exposes a flat list view across all three pools — sections are visually
separated in the UI by ``reward_kind`` but stored as one row stream.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QPersistentModelIndex,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.active_target import ActiveTarget, RangeTarget, RuleTarget
from tbh_desktop.ui.rule_card import REWARD_KINDS, RuleCard
from tbh_desktop.ui.theme import MOCHA


# Maps a flat row index back to (reward_kind, rule_index).
class _RuleCardModel(QAbstractItemModel):
    """Minimal model with N rows. `index()` returns an invalid QModelIndex so
    `QListView.setIndexWidget` is the sole paint path for each row."""

    def __init__(self, n: int = 0, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._n = n

    def set_row_count(self, n: int) -> None:
        self.beginResetModel()
        self._n = n
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else self._n

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else 1

    def index(  # noqa: ANN001
        self,
        row: int,
        column: int,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index: QModelIndex | QPersistentModelIndex) -> QModelIndex:  # type: ignore[reportIncompatibleMethodOverride]  # noqa: ANN001
        # PySide6 stubs incorrectly declare QAbstractItemModel.parent as
        # taking no args and returning QObject. The real Qt signature is
        # `(self, QModelIndex) -> QModelIndex`.
        return QModelIndex()

    def data(  # noqa: ANN001
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        # setIndexWidget is the sole paint path; Qt still queries data() for
        # hit-testing, accessibility tree, and selection bookkeeping. Return
        # None (invalid QVariant) so Qt uses defaults instead of crashing on
        # the pure virtual.
        if not index.isValid():
            return None
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:  # noqa: ANN001
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class _RuleCardDelegate(QStyledItemDelegate):
    """Paints one `RuleCard` per row at a fixed height."""

    CARD_HEIGHT = 158  # RuleCard preferred height — keeps all 3 default rules
    # visible at typical 1400x850 window size without scrolling.
    # See commit history: 220 was too tall — only 1 card visible at default
    # window size. 158 leaves room for header + 3 cards in the left pane.

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: ANN001
        return QSize(option.rect.width() or 600, self.CARD_HEIGHT)

    def paint(self, painter, option, index) -> None:  # noqa: ANN001
        # Embedded RuleCard paints itself via setIndexWidget; delegate only clears the row bg.
        painter.fillRect(option.rect, option.palette.base())


class _RangeCard(QFrame):
    """Compact summary card for the range-replacement rule.

    Rendered as the last row in the rule list (after Act rules) so
    the user can enable / disable + click to edit the range rule
    in one place. The enabled checkbox toggles directly on the
    card — the user no longer has to open the detail panel just
    to flip the on/off switch. RangeState is updated immediately
    via the ``toggled`` signal.

    Jul 2026: previously this card only showed a status badge
    ("OFF" / "ON" with no click action), which made it look like a
    broken label instead of an interactive rule. The badge is
    gone; the checkbox is now the on/off control.
    """

    toggled = Signal(bool)  # emits new enabled state

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("range_card")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(4)

        # Title row — checkbox replaces the old "OFF / ON" status
        # badge so the user can toggle the rule from the card.
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.chk_enabled = QCheckBox()
        self.chk_enabled.setObjectName("range_card_enabled")
        self.chk_enabled.setToolTip(
            "Enable pool range replacement. When on, every itemId "
            "between min and max gets the replacement ids below."
        )
        self.chk_enabled.toggled.connect(self.toggled.emit)
        title_row.addWidget(self.chk_enabled)
        title = QLabel("Pool range")
        title.setObjectName("range_card_title")
        title.setStyleSheet(
            f"color: {MOCHA['text']}; font-size: 14px; font-weight: 700;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        outer.addLayout(title_row)

        # Detail row — min/max range + chip count.
        self.detail_label = QLabel("(not configured)")
        self.detail_label.setObjectName("range_card_detail")
        self.detail_label.setStyleSheet(
            f"color: {MOCHA['subtext']}; font-size: 11px;"
        )
        outer.addWidget(self.detail_label)

    def set_data(self, data: dict) -> None:
        enabled = bool(data.get("enabled", False))
        lo = int(data.get("min_pool_id") or 0)
        hi = int(data.get("max_pool_id") or 0)
        n = len(data.get("replacement_reward_item_ids") or [])
        # Block signals while setting so the toggled signal doesn't
        # fire from inside set_data — only fires on user clicks.
        self.chk_enabled.blockSignals(True)
        self.chk_enabled.setChecked(enabled)
        self.chk_enabled.blockSignals(False)
        if lo and hi:
            range_str = f"itemId {lo:,} → {hi:,}"
        elif lo or hi:
            range_str = f"itemId {lo or hi:,} (one side)"
        else:
            range_str = "no range"
        self.detail_label.setText(
            f"{range_str} · {n} replacement id{'s' if n != 1 else ''}"
        )

    def is_enabled(self) -> bool:
        return self.chk_enabled.isChecked()


class RuleListView(QListView):
    rule_selected = Signal(object)  # emits RuleTarget
    range_toggled = Signal(bool)  # emits new enabled state for range rule
    card_pool_ids_changed = Signal(list)  # user edited pool_ids in a card

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rule_list")
        self.setItemDelegate(_RuleCardDelegate(self))
        self.setUniformItemSizes(True)
        self.setSelectionMode(self.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(self.ScrollMode.ScrollPerPixel)

        # Three rule lists (Normal / Boss / Act) keyed by reward_kind.
        self._rules: dict[str, list[dict[str, Any]]] = {k: [] for _, k in REWARD_KINDS}
        self._range: dict[str, Any] = {}
        self._active_target: ActiveTarget | None = None
        self._cards: list[RuleCard] = []
        self._range_card: _RangeCard | None = None
        # Map visual row -> (reward_kind, rule_index). The range card
        # lives at a special row index ``RANGE_ROW`` so callers can
        # detect a range selection by row position.
        self._row_map: list[tuple[str, int]] = []
        self._range_row: int = -1  # -1 until _rebuild_cards runs

        # Set up a model up front so selectionModel() is non-None and we can
        # wire currentRowChanged. _rebuild_cards() replaces it as needed.
        self._model = _RuleCardModel(0, self)
        self.setModel(self._model)
        self.selectionModel().currentRowChanged.connect(self._on_row_changed)

    # ---- public API --------------------------------------------------
    def load(self, data: dict[str, Any]) -> None:
        for kind in {k for _, k in REWARD_KINDS}:
            self._rules[kind] = [dict(r) for r in (data.get(f"{kind}_rules") or [])]
        self._range = dict(data.get("range_replacement") or {
            "enabled": False,
            "name": "Pool range",
            "min_pool_id": 0,
            "max_pool_id": 0,
            "replacement_reward_item_ids": [],
        })
        self._rebuild_cards()

    def dump(self) -> dict[str, Any]:
        """Serialize back to the config schema.

        For each kind bucket: start from ``self._rules[kind]`` (the canonical
        list, including any locked defaults) and overlay any updates made
        via the live cards. Cards are matched to their underlying rule by
        ``name`` (the persistent identity across edits). If a card's name
        matches an existing rule, the rule is updated in place; otherwise
        the card is appended (newly added via the + kind button).
        """
        out: dict[str, Any] = {}
        for kind in {k for _, k in REWARD_KINDS}:
            bucket = [dict(r) for r in self._rules.get(kind, [])]
            # Lookup by name → index. Names are the user's stable identity;
            # pool_id can change freely (that's the whole point of the picker).
            lookup = {r.get("name"): i for i, r in enumerate(bucket)}
            for card in self._cards:
                if card.reward_kind() != kind:
                    continue
                key = card.name()
                if key in lookup:
                    bucket[lookup[key]] = card.to_dict()
                else:
                    bucket.append(card.to_dict())
            out[f"{kind}_rules"] = bucket
        out["range_replacement"] = dict(self._range)
        return out

    def row_count(self) -> int:
        return len(self._cards)

    def select_row(self, row: int) -> None:
        if 0 <= row < len(self._cards):
            self.setCurrentIndex(self.model().index(row, 0))

    def selected_rule_pool_id(self) -> int | None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            return None
        if 0 <= target.row < len(self._cards):
            return self._cards[target.row].pool_id()
        return None

    def set_selected_rule_pool_id(self, pool_id: int) -> None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            return
        if 0 <= target.row < len(self._cards):
            self._cards[target.row].edit_pool_id.setText(str(pool_id))

    def set_active_target(self, target: ActiveTarget | None) -> None:
        self._active_target = target
        for i, card in enumerate(self._cards):
            card.set_active(
                isinstance(target, RuleTarget) and target.row == i
            )

    def active_target(self) -> ActiveTarget | None:
        return self._active_target

    def add_ids_to_selected_rule(self, ids: list[int]) -> None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            raise ValueError("No active rule target")
        if 0 <= target.row < len(self._cards):
            self._cards[target.row].add_ids(ids)

    def add_ids_to_range(self, ids: list[int]) -> None:
        existing = list(self._range.get("replacement_reward_item_ids") or [])
        for i in ids:
            if i not in existing:
                existing.append(int(i))
        self._range["replacement_reward_item_ids"] = existing

    def add_ids_to_active_target(self, ids: list[int]) -> None:
        target = self._active_target
        if target is None:
            raise ValueError("No active target (select a rule or the range form first)")
        if isinstance(target, RuleTarget):
            self.add_ids_to_selected_rule(ids)
        elif isinstance(target, RangeTarget):
            self.add_ids_to_range(ids)

    def add_rule(self, reward_kind: str, rule: dict[str, Any] | None = None) -> int:
        """Append a new (unlocked) rule to the given kind list and rebuild.
        Returns the visual row of the new card.
        """
        if reward_kind not in {k for _, k in REWARD_KINDS}:
            raise ValueError(f"unknown reward_kind {reward_kind!r}")
        if rule is None:
            rule = {
                "enabled": True,
                "name": f"{reward_kind.title()} rule",
                "reward_kind": reward_kind,
                "pool_id": None,
                "replacement_reward_item_ids": [],
            }
        self._rules[reward_kind].append(rule)
        self._rebuild_cards()
        return len(self._cards) - 1

    def remove_rule(self, row: int) -> None:
        if not (0 <= row < len(self._cards)):
            return
        card = self._cards[row]
        if card._locked:
            return  # don't remove locked defaults
        kind = card.reward_kind()
        # Find the rule in _rules[kind] by name.
        for i, r in enumerate(self._rules[kind]):
            if r.get("name") == card.name():
                del self._rules[kind][i]
                break
        self._rebuild_cards()

    # ---- internals ---------------------------------------------------
    def _rebuild_cards(self) -> None:
        # Drop existing widgets.
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()
        if self._range_card is not None:
            self._range_card.setParent(None)
            self._range_card.deleteLater()
            self._range_card = None
        self._row_map.clear()

        # Flatten the 3 rule lists into a single visual row stream.
        flat: list[tuple[str, dict[str, Any], bool]] = []  # (kind, rule, locked)
        for _, kind in REWARD_KINDS:
            for r in self._rules.get(kind, []):
                # Default rules (loaded from config) and user-added rules
                # are both editable. The locked flag is unused (no
                # rules are read-only) but kept for API parity.
                flat.append((kind, r, False))

        # Append the range card at the end so the user can click it to
        # switch the detail panel to the range form. Selecting this
        # row emits RangeTarget via rule_selected.
        self._model.set_row_count(len(flat) + 1)
        for i, (kind, rule, _locked) in enumerate(flat):
            card = RuleCard(self)
            card.set_data(rule, locked=False)
            idx = self._model.index(i, 0)
            self.setIndexWidget(idx, card)
            self._cards.append(card)
            self._row_map.append((kind, i))
            # Forward pool_ids edits to main_window so the detail
            # panel re-pulls the active rule's data (and disables
            # Pick gear/item if the user just emptied the pool list).
            card.pool_ids_changed.connect(self._on_card_pool_ids_changed)

        # Render the range card at row N.
        self._range_row = len(flat)
        range_idx = self._model.index(self._range_row, 0)
        self._range_card = _RangeCard(self)
        self._range_card.set_data(self._range)
        # Forward the toggle to main_window so the enabled state
        # lands in RangeState (and is included in the next save).
        self._range_card.toggled.connect(self.range_toggled.emit)
        self.setIndexWidget(range_idx, self._range_card)

        self.set_active_target(self._active_target)

    def _on_card_pool_ids_changed(self, new_pool_ids: list) -> None:
        """Forward a pool_ids edit from a rule card to main_window.

        Triggered when the user types in the pool_id field on a
        rule card. main_window listens on this signal (via the
        card_pool_ids_changed combiner) and re-pulls the active
        rule's data so the detail panel disables Pick gear/item
        when the pool list goes empty.
        """
        self.card_pool_ids_changed.emit(new_pool_ids)

    def _on_row_changed(self, current, _previous) -> None:  # noqa: ANN001
        if not current.isValid():
            self.set_active_target(None)
            return
        row = current.row()
        if row == self._range_row and self._range_card is not None:
            target = RangeTarget()
            self.set_active_target(target)
            self.rule_selected.emit(target)
            return
        if 0 <= row < len(self._cards):
            card = self._cards[row]
            kind, rule_index = self._row_map[row]
            target = RuleTarget(
                row=row,
                rule_index=rule_index,
                reward_kind=kind,
                pool_id=card.pool_id(),
            )
            self.set_active_target(target)
            self.rule_selected.emit(target)
