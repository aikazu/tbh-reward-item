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


from unittest.mock import patch


def test_run_scrape_skips_fresh_caches(tmp_path):
    """With --resume, fresh cache files are skipped."""
    from dev_tools.scrape_pipeline.scrape_stage import ENDGAME_GEAR_GRADES
    out_dir = tmp_path / "out"
    # Create fresh cache for ALL gear combos (all categories x all endgame grades)
    from tbh_desktop.scraper import GEAR_CATEGORIES
    for cat in GEAR_CATEGORIES:
        for grade in ENDGAME_GEAR_GRADES:
            cache_dir = out_dir / "gear" / cat
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{grade}.json").write_text("[]")
    with patch("tbh_desktop.scraper.refresh_gear_full") as scraper_fn, \
         patch("tbh_desktop.scraper.fetch_drops_index") as drops_fn, \
         patch("tbh_desktop.scraper.refresh_material_details") as mat_fn:
        drops_fn.return_value = []
        mat_fn.return_value = 0
        from dev_tools.scrape_pipeline.scrape_stage import run_scrape
        stats = run_scrape(out_dir, resume=True, max_cache_age_days=7)
    scraper_fn.assert_not_called()
    assert stats["combos_cached"] >= 1


def test_run_scrape_calls_scraper_for_stale_cache(tmp_path):
    """Stale cache triggers re-scrape."""
    import os, time, json
    out_dir = tmp_path / "out"
    gear_dir = out_dir / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    # Use IMMORTAL which IS in ENDGAME_GEAR_GRADES
    cache = gear_dir / "IMMORTAL.json"
    cache.write_text("[]")
    # Backdate mtime 30 days
    old = time.time() - (30 * 86400)
    os.utime(cache, (old, old))
    with patch("tbh_desktop.scraper.refresh_gear_full") as scraper_fn, \
         patch("tbh_desktop.scraper.fetch_drops_index") as drops_fn, \
         patch("tbh_desktop.scraper.refresh_material_details") as mat_fn:
        drops_fn.return_value = []
        mat_fn.return_value = 0
        scraper_fn.return_value = {"sword_IMMORTAL": []}
        from dev_tools.scrape_pipeline.scrape_stage import run_scrape
        run_scrape(out_dir, resume=True, max_cache_age_days=7)
    assert scraper_fn.called


def test_run_scrape_falls_back_to_cache_on_error(tmp_path):
    """If scraper raises, existing cache is preserved + combo counted as failed."""
    import json
    from dev_tools.scrape_pipeline.errors import NetworkError
    out_dir = tmp_path / "out"
    gear_dir = out_dir / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    cache = gear_dir / "IMMORTAL.json"
    cache.write_text(json.dumps([{"id": 300001}]))
    with patch("tbh_desktop.scraper.refresh_gear_full") as scraper_fn, \
         patch("tbh_desktop.scraper.fetch_drops_index") as drops_fn, \
         patch("tbh_desktop.scraper.refresh_material_details") as mat_fn:
        drops_fn.return_value = []
        mat_fn.return_value = 0
        scraper_fn.side_effect = NetworkError("flake")
        from dev_tools.scrape_pipeline.scrape_stage import run_scrape
        stats = run_scrape(out_dir, resume=False, max_cache_age_days=7)
    assert stats["combos_failed"] >= 1
    # Cache preserved
    assert json.loads(cache.read_text()) == [{"id": 300001}]
