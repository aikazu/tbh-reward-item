"""Exponential backoff with jitter for retry loops."""
from __future__ import annotations

import random
from typing import cast


def backoff(
    attempt: int,
    base: float = 0.4,
    cap: float = 30.0,
    rng: random.Random | None = None,
) -> float:
    """Return delay in seconds for the given attempt (0-indexed).

    Formula: ``min(cap, base * 2 ** attempt) + uniform(0, 0.25 * that_delay)``.
    Pass ``rng`` to make output deterministic in tests.
    """
    rng = rng if rng is not None else cast(random.Random, random)
    raw = min(cap, base * (2 ** attempt))
    jitter = rng.uniform(0, raw * 0.25)
    return raw + jitter
