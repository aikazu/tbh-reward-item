"""Load/save src/config.json as raw dict; validate via ProxyConfig."""
from __future__ import annotations

import json
import logging
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from tbh_desktop.paths import SRC_DIR

# Import ProxyConfig from the dedicated data module. This module has no
# addon side effects (no mitmproxy import, no top-level TBHRewardHook()).
# Previously we imported from tbh_reward_hook which constructed the addon
# at import time — that's why the desktop app printed "loaded: N rules"
# at launch even though the proxy hadn't been started.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
from tbh_proxy_config import ProxyConfig  # type: ignore[import-not-found]
from config_setup import DEFAULT_CONFIG_PATH  # type: ignore[import-not-found]  # noqa: E402

log = logging.getLogger(__name__)

T = TypeVar("T")


def read_json(path: Path, default: T) -> T:
    """Read JSON from *path*, return *default* if missing or unparseable.

    Centralized so call sites don't repeat the same try/except dance.
    """
    if not path.exists():
        return default
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("read_json(%s) failed: %s", path, exc)
        return default
    # If caller asked for a specific type and JSON returned a different one,
    # return default — avoids surprising callers with wrong-shaped data.
    if default is not None and not isinstance(result, type(default)):
        log.warning("read_json(%s) returned %s, expected %s", path, type(result).__name__, type(default).__name__)
        return default
    return result  # type: ignore[no-any-return]


def ensure_config(path: Path) -> bool:
    """Create config.json from config.default.json if it doesn't exist.

    Validates the copied file round-trips before keeping it.
    Returns True if the file was created, False otherwise.
    """
    if path.exists():
        return False
    if not DEFAULT_CONFIG_PATH.exists():
        log.warning("default config not found: %s", DEFAULT_CONFIG_PATH)
        return False
    if not _copy_and_validate(DEFAULT_CONFIG_PATH, path):
        log.warning("default config failed validation; not creating %s", path)
        return False
    log.info("generated %s from default", path)
    return True


def reset_config(path: Path) -> bool:
    """Reset config.json back to the default template (config.default.json).

    Overwrites the existing config.json with the default. Returns True on
    success, False if the default template is missing or invalid.
    """
    if not DEFAULT_CONFIG_PATH.exists():
        log.warning("cannot reset — default config not found: %s", DEFAULT_CONFIG_PATH)
        return False
    # Back up the existing file so we can restore on validation failure.
    backup: Path | None = None
    if path.exists():
        backup = path.with_suffix(".json.bak")
        shutil.copy2(path, backup)
    if not _copy_and_validate(DEFAULT_CONFIG_PATH, path):
        # Restore from backup so user doesn't lose their config to a bad default.
        if backup is not None:
            try:
                shutil.copy2(backup, path)
                log.warning("restored %s from backup after failed validation", path)
            except OSError as exc:
                log.warning("restore-after-failed-validation failed: %s", exc)
        log.warning("default config failed validation; %s untouched", path)
        return False
    log.info("reset %s to default", path)
    return True


def _copy_and_validate(src: Path, dst: Path) -> bool:
    """Copy src to dst, then verify dst is a valid ProxyConfig."""
    shutil.copy2(src, dst)
    try:
        ProxyConfig.load(dst)
        return True
    except Exception as exc:
        log.warning("copied config at %s failed validation: %s", dst, exc)
        try:
            dst.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def load_config(path: Path) -> dict[str, Any]:
    """Load config JSON as raw dict. Return {} if missing or invalid."""
    return read_json(path, {})


@dataclass
class SaveResult:
    ok: bool
    error: str | None = None


def validate_config(data: dict[str, Any]) -> bool:
    """Return True if data parses as a valid ProxyConfig."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tf.write(json.dumps(data).encode("utf-8"))
            tmp_path = Path(tf.name)
        try:
            ProxyConfig.load(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        return True
    except Exception as exc:
        log.warning("validate_config failed: %s", exc)
        return False


def save_config(path: Path, data: dict[str, Any]) -> SaveResult:
    """Validate, backup, atomic-write config. Restore from backup if validation fails post-write."""
    if not validate_config(data):
        return SaveResult(ok=False, error="config failed ProxyConfig validation")

    # Backup existing file before overwrite.
    if path.exists():
        backup = path.with_suffix(".json.bak")
        shutil.copy2(path, backup)

    # Atomic write: temp file + rename.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

    # Validate the written file round-trips.
    reloaded = load_config(path)
    if not validate_config(reloaded):
        # Restore from backup if it exists, otherwise delete the invalid write.
        backup = path.with_suffix(".json.bak")
        if backup.exists():
            try:
                shutil.copy2(backup, path)
            except OSError as exc:
                log.warning("restore-from-backup failed: %s", exc)
                return SaveResult(ok=False, error=f"re-validation failed; restore failed: {exc}")
        else:
            try:
                path.unlink()
            except OSError as exc:
                log.warning("delete-invalid-write failed: %s", exc)
                return SaveResult(ok=False, error=f"re-validation failed; delete failed: {exc}")
        return SaveResult(ok=False, error="written config failed re-validation; restored backup")
    return SaveResult(ok=True)
