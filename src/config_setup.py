"""Shared config-path resolution and first-run auto-generate.

Lives in ``src/`` (not ``tbh_desktop/``) so the mitmproxy addon can import
it without dragging in PySide6. The desktop side re-exports these constants
via ``tbh_desktop.paths``.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.default.json")

log = logging.getLogger(__name__)


def ensure_config(path: Path = CONFIG_PATH) -> bool:
    """Create *path* from ``config.default.json`` if it doesn't exist.

    Returns True if the file was created, False if it already existed.
    Logs but does not raise on copy failure.
    """
    if path.exists():
        return False
    if not DEFAULT_CONFIG_PATH.exists():
        log.warning("default config not found: %s", DEFAULT_CONFIG_PATH)
        return False
    try:
        shutil.copy2(DEFAULT_CONFIG_PATH, path)
        log.info("generated %s from default", path)
        return True
    except OSError as exc:
        log.warning("could not generate %s: %s", path, exc)
        return False
