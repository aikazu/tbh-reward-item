"""Tests for the ActiveTarget union and its routing helper.

Jul 2026 — tbh.city migration: RuleTarget now carries ``reward_kind``
(Normal/Boss/Act) + ``pool_id`` (= tbh.city drop_key) instead of v1's
``box_id`` + ``level`` pair. The semantics are otherwise identical.
"""
from __future__ import annotations

from tbh_desktop.ui.active_target import (
    ActiveTarget,
    RangeTarget,
    RuleTarget,
    is_range,
    is_rule,
)


def test_rule_target_holds_row_metadata() -> None:
    t = RuleTarget(row=2, rule_index=2, reward_kind="normal", pool_id=9100111)
    assert t.row == 2
    assert t.rule_index == 2
    assert t.reward_kind == "normal"
    assert t.pool_id == 9100111


def test_range_target_is_singleton_like() -> None:
    assert RangeTarget() == RangeTarget()


def test_is_rule_and_is_range_discriminate() -> None:
    rule: ActiveTarget = RuleTarget(row=0, rule_index=0, reward_kind="boss", pool_id=None)
    rng: ActiveTarget = RangeTarget()
    assert is_rule(rule) is True
    assert is_range(rule) is False
    assert is_range(rng) is True
    assert is_rule(rng) is False


def test_rule_target_is_frozen() -> None:
    t = RuleTarget(row=0, rule_index=0, reward_kind="normal", pool_id=None)
    try:
        t.row = 5  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("RuleTarget must be frozen (frozen dataclass)")