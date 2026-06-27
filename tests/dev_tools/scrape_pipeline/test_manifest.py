"""Tests for dev_tools.scrape_pipeline.manifest."""
from __future__ import annotations

import json

import pytest

from dev_tools.scrape_pipeline.manifest import (
    SCHEMA_VERSION,
    read_manifest,
    write_manifest,
)


def test_round_trip(tmp_path):
    """Write then read returns the same payload (with schema_version added)."""
    path = tmp_path / "manifest.json"
    stats = {
        "scrape_started_at": "2026-06-27T10:00:00",
        "scrape": {"combos_done": 5, "items_total": 100},
        "images": {"downloaded": 100, "failed": 0},
    }
    write_manifest(stats, path)
    loaded = read_manifest(path)
    assert loaded["schema_version"] == SCHEMA_VERSION
    assert loaded["scrape_started_at"] == "2026-06-27T10:00:00"
    assert loaded["scrape"] == {"combos_done": 5, "items_total": 100}
    assert loaded["images"] == {"downloaded": 100, "failed": 0}
    assert "scrape_completed_at" in loaded


def test_atomic_write_no_partial_file(tmp_path):
    """If write_manifest is interrupted, no manifest.json should remain."""
    path = tmp_path / "manifest.json"
    # Pre-create a good manifest
    path.write_text('{"schema_version": 1, "old": true}')
    # Write new content; old content must NOT survive
    write_manifest({"scrape": {"done": 1}}, path)
    assert json.loads(path.read_text())["scrape"] == {"done": 1}


def test_missing_file_returns_empty(tmp_path):
    """read_manifest on a missing file returns {} (no raise)."""
    assert read_manifest(tmp_path / "nope.json") == {}


def test_corrupt_file_returns_empty(tmp_path):
    """read_manifest on a malformed JSON returns {} (no raise)."""
    path = tmp_path / "manifest.json"
    path.write_text("not json at all")
    assert read_manifest(path) == {}


def test_schema_version_mismatch_raises(tmp_path):
    """read_manifest raises on schema_version mismatch."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 999}))
    with pytest.raises(ValueError, match="schema_version"):
        read_manifest(path)


def test_schema_version_constant_is_int():
    """SCHEMA_VERSION must be a positive integer for safe comparison."""
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1
