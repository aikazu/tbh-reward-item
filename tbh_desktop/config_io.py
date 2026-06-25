"""Load/save src/config.json as raw dict; validate via ProxyConfig."""
from __future__ import annotations

import json
import logging
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tbh_desktop.paths import SRC_DIR

# Import ProxyConfig from src for validation only.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
from tbh_reward_hook import ProxyConfig  # type: ignore[import-not-found]

log = logging.getLogger(__name__)


def load_config(path: Path) -> dict[str, Any]:
    """Load config JSON as raw dict. Return {} if missing or invalid."""
    if not path.exists():
        log.warning("config not found: %s", path)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("config invalid (%s): %s", path, exc)
        return {}


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
