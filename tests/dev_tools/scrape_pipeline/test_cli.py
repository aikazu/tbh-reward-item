"""Tests for dev_tools.scrape_pipeline.cli."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from dev_tools.scrape_pipeline.cli import main, parse_args


def test_parse_args_defaults():
    """No args = stage=all, no resume."""
    args = parse_args([])
    assert args.stage == "all"
    assert args.resume is False
    assert args.max_cache_age == 7
    assert args.workers == 4
    assert args.dry_run is False


def test_parse_args_explicit_stage():
    args = parse_args(["scrape", "--resume"])
    assert args.stage == "scrape"
    assert args.resume is True


def test_main_dry_run_does_not_write(tmp_path: Path, capsys):
    """--dry-run prints intent but doesn't call stage fns or write files."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape") as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle") as bundle_fn:
        rc = main(["all", "--dry-run", "--out-dir", str(tmp_path)])
    assert rc == 0
    scrape_fn.assert_not_called()
    bundle_fn.assert_not_called()
    captured = capsys.readouterr()
    assert "dry-run" in captured.out.lower()


def test_main_runs_both_stages_for_all(tmp_path: Path):
    """--stage all runs both scrape and bundle."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape", return_value={"combos_done": 5, "combos_cached": 0, "items_total": 10}) as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle", return_value={"downloaded": 100}) as bundle_fn, \
         patch("dev_tools.scrape_pipeline.cli.write_manifest") as write_fn:
        rc = main(["all", "--out-dir", str(tmp_path)])
    assert rc == 0
    scrape_fn.assert_called_once()
    bundle_fn.assert_called_once()
    write_fn.assert_called_once()
    # Manifest payload combines both
    payload = write_fn.call_args[0][0]
    assert payload["scrape"]["combos_done"] == 5
    assert payload["images"]["downloaded"] == 100


def test_main_runs_only_scrape_when_stage_scrape(tmp_path: Path):
    """--stage scrape skips bundle."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape", return_value={}) as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle") as bundle_fn, \
         patch("dev_tools.scrape_pipeline.cli.write_manifest") as write_fn:
        main(["scrape", "--out-dir", str(tmp_path)])
    scrape_fn.assert_called_once()
    bundle_fn.assert_not_called()
    write_fn.assert_called_once()


def test_main_runs_only_bundle_when_stage_bundle(tmp_path: Path):
    """--stage bundle skips scrape."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape") as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle", return_value={}) as bundle_fn, \
         patch("dev_tools.scrape_pipeline.cli.write_manifest") as write_fn:
        main(["bundle", "--out-dir", str(tmp_path)])
    scrape_fn.assert_not_called()
    bundle_fn.assert_called_once()
    write_fn.assert_called_once()


def test_main_returns_1_when_scrape_produces_zero_with_no_cache(tmp_path: Path):
    """Hard fail: scrape returned 0 items AND nothing cached."""
    with patch("dev_tools.scrape_pipeline.cli.run_scrape", return_value={"combos_done": 0, "combos_cached": 0, "items_total": 0}) as scrape_fn, \
         patch("dev_tools.scrape_pipeline.cli.run_bundle", return_value={}) as bundle_fn, \
         patch("dev_tools.scrape_pipeline.cli.write_manifest") as write_fn:
        rc = main(["all", "--out-dir", str(tmp_path)])
    assert rc == 1
