"""Tests for dev_tools.scrape_pipeline.scrape_stage."""
from __future__ import annotations

import time
from pathlib import Path

from dev_tools.scrape_pipeline.scrape_stage import cache_fresh


def test_cache_fresh_missing_file_returns_false(tmp_path):
    """No file on disk = not fresh."""
    assert cache_fresh(tmp_path / "nope.json", max_age_days=7) is False


def test_cache_fresh_brand_new_file_returns_true(tmp_path):
    """A file written now is fresh."""
    p = tmp_path / "fresh.json"
    p.write_text("{}")
    assert cache_fresh(p, max_age_days=7) is True


def test_cache_fresh_old_file_returns_false(tmp_path):
    """A file written 30 days ago is stale against a 7-day window."""
    p = tmp_path / "old.json"
    p.write_text("{}")
    # Backdate mtime by 30 days
    old_time = time.time() - (30 * 86400)
    import os
    os.utime(p, (old_time, old_time))
    assert cache_fresh(p, max_age_days=7) is False


def test_cache_fresh_at_boundary_is_fresh(tmp_path):
    """A file 6 days old against 7-day window = still fresh."""
    p = tmp_path / "boundary.json"
    p.write_text("{}")
    six_days_ago = time.time() - (6 * 86400)
    import os
    os.utime(p, (six_days_ago, six_days_ago))
    assert cache_fresh(p, max_age_days=7) is True
