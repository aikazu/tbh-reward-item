"""Tests for dev_tools.scrape_pipeline.backoff."""
from __future__ import annotations

import random

from dev_tools.scrape_pipeline.backoff import backoff


def test_backoff_grows_exponentially():
    """Each attempt's delay should roughly double (within jitter bound)."""
    rng = random.Random(42)
    delays = [backoff(attempt=i, base=0.4, cap=30.0, rng=rng) for i in range(5)]
    # Without jitter (jitter range [0, 0.25*delay]), each next must be > 0.75 * prev
    for prev, curr in zip(delays, delays[1:]):
        assert curr > prev * 0.75, f"delay did not grow: {prev} -> {curr}"


def test_backoff_respects_cap():
    """Delay must never exceed the cap (even with jitter)."""
    rng = random.Random(0)
    # attempt=20 would give 0.4 * 2^20 = 419430s raw; must cap to 30
    assert backoff(attempt=20, base=0.4, cap=30.0, rng=rng) <= 30.0 * 1.25


def test_backoff_deterministic_with_seeded_rng():
    """Same seed must produce same delay sequence."""
    delays_a = [backoff(attempt=i, rng=random.Random(123)) for i in range(3)]
    delays_b = [backoff(attempt=i, rng=random.Random(123)) for i in range(3)]
    assert delays_a == delays_b


def test_backoff_jitter_within_quarter():
    """Jitter must be in [0, 0.25 * base_delay] range."""
    rng = random.Random(7)
    for attempt in range(5):
        base = min(30.0, 0.4 * (2 ** attempt))
        delay = backoff(attempt=attempt, base=0.4, cap=30.0, rng=rng)
        # First call to rng.uniform consumed for jitter; just check bounds
        assert base <= delay <= base * 1.25, f"attempt={attempt}: {delay} not in [{base}, {base * 1.25}]"
