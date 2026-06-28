# tests/test_run_proxy.py
"""Tests for src/run_proxy.py (non-GUI, pure config + CLI parsing)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _import_run_proxy():
    spec = importlib.util.spec_from_file_location("run_proxy_under_test", SRC / "run_proxy.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_proxy_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _patch_config(monkeypatch, tmp_path: Path, payload: dict | None) -> None:
    cfg = tmp_path / "config.json"
    if payload is None:
        cfg.unlink(missing_ok=True)
    else:
        cfg.write_text(json.dumps(payload), encoding="utf-8")
    mod = _import_run_proxy()
    monkeypatch.setattr(mod, "CONFIG_PATH", cfg)


def test_load_mode_defaults_to_regular(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path, {"listen_port": 8877})
    mod = sys.modules["run_proxy_under_test"]
    assert mod.load_mode() == ("regular", None)


def test_load_mode_local_with_name(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path, {
        "mode": "local",
        "local_process_name": "TaskBarHero.exe",
        "listen_port": 8877,
    })
    mod = sys.modules["run_proxy_under_test"]
    assert mod.load_mode() == ("local", "TaskBarHero.exe")


def test_load_mode_local_without_name_falls_back(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path, {"mode": "local", "listen_port": 8877})
    mod = sys.modules["run_proxy_under_test"]
    assert mod.load_mode() == ("regular", None)


def test_load_mode_unknown_value_falls_back(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path, {"mode": "bogus", "listen_port": 8877})
    mod = sys.modules["run_proxy_under_test"]
    assert mod.load_mode() == ("regular", None)


def test_cli_overrides_config(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path, {"mode": "regular", "listen_port": 8877})
    mod = sys.modules["run_proxy_under_test"]
    assert mod.load_mode("local", "game.exe") == ("local", "game.exe")


def test_cli_local_without_name_falls_back(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path, {"listen_port": 8877})
    mod = sys.modules["run_proxy_under_test"]
    assert mod.load_mode("local", None) == ("regular", None)
    assert mod.load_mode("local", "") == ("regular", None)
    assert mod.load_mode("local", "   ") == ("regular", None)