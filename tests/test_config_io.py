"""Tests for config_io."""
from __future__ import annotations

from pathlib import Path

import pytest

from tbh_desktop import config_io


def test_load_config_returns_raw_dict(config_file: Path) -> None:
    data = config_io.load_config(config_file)
    assert isinstance(data, dict)
    assert data["listen_port"] == 8877
    assert data["only_post"] is True
    # advanced field preserved
    assert data["url_contains"] == ["/backend-function/base/v1"]


def test_load_config_missing_file_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    data = config_io.load_config(missing)
    assert data == {}


def test_load_config_invalid_json_returns_empty(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    data = config_io.load_config(bad)
    assert data == {}