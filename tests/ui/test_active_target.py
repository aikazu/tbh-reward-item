"""Tests for the ActiveTarget union and its routing helper."""
from __future__ import annotations

from tbh_desktop.ui.active_target import (
    ActiveTarget,
    RangeTarget,
    RuleTarget,
    is_range,
    is_rule,
)


def test_rule_target_holds_row_metadata() -> None:
    t = RuleTarget(row=2, rule_index=2, box_id=42, level=10)
    assert t.row == 2
    assert t.rule_index == 2
    assert t.box_id == 42
    assert t.level == 10


def test_range_target_is_singleton_like() -> None:
    assert RangeTarget() == RangeTarget()


def test_is_rule_and_is_range_discriminate() -> None:
    rule: ActiveTarget = RuleTarget(row=0, rule_index=0, box_id=None, level=None)
    rng: ActiveTarget = RangeTarget()
    assert is_rule(rule) is True
    assert is_range(rule) is False
    assert is_range(rng) is True
    assert is_rule(rng) is False


def test_rule_target_is_frozen() -> None:
    t = RuleTarget(row=0, rule_index=0, box_id=None, level=None)
    try:
        t.row = 5  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("RuleTarget must be frozen (frozen dataclass)")
