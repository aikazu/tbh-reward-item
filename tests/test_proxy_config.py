# tests/test_proxy_config.py
"""Tests for src/tbh_proxy_config.ProxyConfig defaults.

Focused on the platform-aware defaults — the rest of the dataclass
behaviour is exercised by the rewriter tests (test_reward_rewriter.py)
via _make_config(). Keeping this file small and targeted so the
defaults policy is easy to read and audit.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _import_proxy_config():
    spec = importlib.util.spec_from_file_location(
        "tbh_proxy_config_under_test", _SRC / "tbh_proxy_config.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tbh_proxy_config_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_default_rewrite_pending_tx_on_windows(monkeypatch) -> None:
    mod = _import_proxy_config()
    monkeypatch.setattr(mod.sys, "platform", "win32")
    assert mod._default_rewrite_pending_tx() is True


def test_default_rewrite_pending_tx_off_on_linux(monkeypatch) -> None:
    mod = _import_proxy_config()
    monkeypatch.setattr(mod.sys, "platform", "linux")
    assert mod._default_rewrite_pending_tx() is False


def test_default_rewrite_pending_tx_off_on_darwin(monkeypatch) -> None:
    mod = _import_proxy_config()
    monkeypatch.setattr(mod.sys, "platform", "darwin")
    assert mod._default_rewrite_pending_tx() is False


def test_load_uses_platform_default_when_field_missing(monkeypatch, tmp_path) -> None:
    """``rewrite_pending_tx`` absent from config → platform-aware default.
    On Windows the addon should rewrite pendingTx even though the user
    didn't explicitly enable it."""
    import json
    mod = _import_proxy_config()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"listen_port": 8877}), encoding="utf-8")
    monkeypatch.setattr(mod.sys, "platform", "win32")
    cfg = mod.ProxyConfig.load(cfg_path)
    assert cfg.rewrite_pending_tx is True


def test_load_uses_platform_default_off_on_linux(monkeypatch, tmp_path) -> None:
    import json
    mod = _import_proxy_config()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"listen_port": 8877}), encoding="utf-8")
    monkeypatch.setattr(mod.sys, "platform", "linux")
    cfg = mod.ProxyConfig.load(cfg_path)
    assert cfg.rewrite_pending_tx is False


def test_load_explicit_false_always_respected(monkeypatch, tmp_path) -> None:
    """No surprise upgrades: explicit ``false`` is honored on Windows too.
    Linux users who migrated their config from another platform keep
    their setting; Windows users who explicitly opted out keep it."""
    import json
    mod = _import_proxy_config()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"rewrite_pending_tx": False}), encoding="utf-8")
    monkeypatch.setattr(mod.sys, "platform", "win32")
    cfg = mod.ProxyConfig.load(cfg_path)
    assert cfg.rewrite_pending_tx is False


def test_load_explicit_true_always_respected(monkeypatch, tmp_path) -> None:
    """Linux users who explicitly opted in keep their setting."""
    import json
    mod = _import_proxy_config()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"rewrite_pending_tx": True}), encoding="utf-8")
    monkeypatch.setattr(mod.sys, "platform", "linux")
    cfg = mod.ProxyConfig.load(cfg_path)
    assert cfg.rewrite_pending_tx is True