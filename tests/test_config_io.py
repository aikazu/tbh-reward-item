"""Tests for config_io."""
from __future__ import annotations

import json
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


def test_save_config_writes_valid_json(tmp_path: Path, sample_config_dict: dict) -> None:
    target = tmp_path / "config.json"
    config_io.save_config(target, sample_config_dict)
    reloaded = config_io.load_config(target)
    assert reloaded == sample_config_dict


def test_save_config_creates_backup(tmp_path: Path, sample_config_dict: dict) -> None:
    target = tmp_path / "config.json"
    target.write_text('{"old": true}', encoding="utf-8")
    config_io.save_config(target, sample_config_dict)
    backup = target.with_suffix(".json.bak")
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8")) == {"old": True}


def test_save_config_rejects_invalid_does_not_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    original = {"listen_port": 1234, "range_replacement": {"match_min_item_id": "not-an-int"}}
    target.write_text(json.dumps(original), encoding="utf-8")
    # invalid: range_replacement.match_min_item_id must be int-coercible.
    result = config_io.save_config(target, {"listen_port": 9999, "range_replacement": {"match_min_item_id": "not-an-int"}})
    assert result.ok is False
    # original preserved
    assert json.loads(target.read_text(encoding="utf-8"))["listen_port"] == 1234


def test_validate_config_returns_true_for_valid(sample_config_dict: dict) -> None:
    assert config_io.validate_config(sample_config_dict) is True


def test_validate_config_returns_false_for_invalid() -> None:
    # ProxyConfig.load rejects non-int listen_port.
    assert config_io.validate_config({"listen_port": "not-an-int"}) is False