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
    """A specific rule row in one of the three pool-rule lists
    (``config.normal_rules`` / ``boss_rules`` / ``act_rules``)."""
    row: int           # visual row in RuleListView
    rule_index: int    # index into the chosen list (per reward_kind)
    reward_kind: str   # "normal" | "boss" | "act"
    pool_id: int | None


@dataclass(frozen=True)
class RangeTarget:
    """The single range_replacement form (always at most one per config)."""
    pass


ActiveTarget = Union[RuleTarget, RangeTarget]


def is_rule(target: ActiveTarget | None) -> bool:
    return isinstance(target, RuleTarget)


def is_range(target: ActiveTarget | None) -> bool:
    return isinstance(target, RangeTarget)
