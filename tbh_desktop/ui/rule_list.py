"""QListView + custom delegate that renders RuleCard per row.

Owns the rule model and the range-replacement form values. Exposes the same
public API the old `ConfigEditor` had, plus an `add_ids_to_active_target`
method that routes by `ActiveTarget` type.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QSize, Signal
from PySide6.QtWidgets import (
    QListView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from tbh_desktop.ui.active_target import ActiveTarget, RangeTarget, RuleTarget
from tbh_desktop.ui.rule_card import RuleCard


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

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else self._n

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else 1

    def index(self, row, column, parent: QModelIndex = QModelIndex()):  # noqa: ANN001
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index):  # noqa: ANN001
        return QModelIndex()


class _RuleCardDelegate(QStyledItemDelegate):
    """Paints one `RuleCard` per row at a fixed height."""

    CARD_HEIGHT = 188  # RuleCard preferred height (rows 1+2+3+4 with padding)

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: ANN001
        return QSize(option.rect.width() or 600, self.CARD_HEIGHT)

    def paint(self, painter, option, index) -> None:  # noqa: ANN001
        # Embedded RuleCard paints itself via setIndexWidget; delegate only clears the row bg.
        painter.fillRect(option.rect, option.palette.base())


class RuleListView(QListView):
    rule_selected = Signal(object)  # emits RuleTarget

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rule_list")
        self.setItemDelegate(_RuleCardDelegate(self))
        self.setUniformItemSizes(True)
        self.setSelectionMode(self.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(self.ScrollMode.ScrollPerPixel)

        self._rules: list[dict[str, Any]] = []
        self._range: dict[str, Any] = {}
        self._active_target: ActiveTarget | None = None
        self._cards: list[RuleCard] = []
        self._level_for_row: dict[int, int] = {}

        # Set up a model up front so selectionModel() is non-None and we can
        # wire currentRowChanged. _rebuild_cards() replaces it as needed.
        self._model = _RuleCardModel(0, self)
        self.setModel(self._model)
        self.selectionModel().currentRowChanged.connect(self._on_row_changed)

    # ---- public API --------------------------------------------------
    def load(self, data: dict[str, Any]) -> None:
        self._rules = [dict(r) for r in (data.get("specific_queue_rules") or [])]
        self._range = dict(data.get("range_replacement") or {
            "enabled": False,
            "name": "Range replacement",
            "match_min_item_id": 0,
            "match_max_item_id": 0,
            "replacement_reward_item_ids": [],
        })
        self._rebuild_cards()

    def dump(self) -> dict[str, Any]:
        return {
            "specific_queue_rules": [c.to_dict() for c in self._cards],
            "range_replacement": dict(self._range),
        }

    def row_count(self) -> int:
        return len(self._cards)

    def select_row(self, row: int) -> None:
        if 0 <= row < len(self._cards):
            self.setCurrentIndex(self.model().index(row, 0))

    def selected_rule_item_id(self) -> int | None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            return None
        if 0 <= target.row < len(self._cards):
            return self._cards[target.row].item_id()
        return None

    def selected_rule_level(self) -> int | None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            return None
        if 0 <= target.row < len(self._cards):
            return self._level_for_row.get(target.row)
        return None

    def set_selected_rule_item_id(self, box_id: int, level: int | None) -> None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            return
        if 0 <= target.row < len(self._cards):
            self._cards[target.row].edit_item_id.setText(str(box_id))
            self._level_for_row[target.row] = level

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

    # ---- internals ---------------------------------------------------
    def _rebuild_cards(self) -> None:
        # Drop existing widgets.
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()
        # Reset the model so QListView knows about the new row count.
        self._model.set_row_count(len(self._rules))
        for i, rule in enumerate(self._rules):
            card = RuleCard(self)
            card.set_data(rule, locked=(i < self._initial_lock_count()))
            idx = self._model.index(i, 0)
            self.setIndexWidget(idx, card)
            self._cards.append(card)
        self.set_active_target(self._active_target)

    def _initial_lock_count(self) -> int:
        """Default rules are locked. Heuristic: rules with no `__user__` marker
        are treated as defaults. We use the rule dict's own `enabled` field
        plus the data we have at load time to infer — for v1 we lock the
        first row (the canonical default rule). Override later if config_io
        exposes a `user_added` flag.
        """
        return 1 if self._rules else 0

    def _on_row_changed(self, current, _previous) -> None:  # noqa: ANN001
        if not current.isValid():
            self.set_active_target(None)
            return
        row = current.row()
        if 0 <= row < len(self._cards):
            card = self._cards[row]
            target = RuleTarget(
                row=row,
                rule_index=row,
                box_id=card.item_id(),
                level=self._level_for_row.get(row),
            )
            self.set_active_target(target)
            self.rule_selected.emit(target)
