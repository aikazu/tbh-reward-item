"""Typed union that routes Item browser picks to a rule row or the range form.

`MainWindow` owns the current `ActiveTarget`. `RuleListView` and the range
form switch it on selection/focus. `ItemBrowser.item_picked` is dispatched
based on the target type.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class RuleTarget:
    """A specific rule row in `config.specific_queue_rules`."""
    row: int           # visual row in RuleListView
    rule_index: int    # index into config.specific_queue_rules
    box_id: int | None
    level: int | None


@dataclass(frozen=True)
class RangeTarget:
    """The single range_replacement form (always at most one per config)."""
    pass


ActiveTarget = Union[RuleTarget, RangeTarget]


def is_rule(target: ActiveTarget | None) -> bool:
    return isinstance(target, RuleTarget)


def is_range(target: ActiveTarget | None) -> bool:
    return isinstance(target, RangeTarget)
