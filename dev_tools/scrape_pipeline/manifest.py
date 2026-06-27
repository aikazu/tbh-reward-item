"""manifest.json IO for the scrape pipeline."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_manifest(stats: dict, path: Path) -> None:
    """Atomically write manifest JSON. Adds schema_version + scrape_completed_at."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "scrape_completed_at": _now_iso(),
        **stats,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def read_manifest(path: Path) -> dict:
    """Read manifest. Returns {} if missing or malformed. Raises on schema mismatch."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    found_version = data.get("schema_version")
    if found_version != SCHEMA_VERSION:
        raise ValueError(
            f"manifest schema_version mismatch: found {found_version}, expected {SCHEMA_VERSION}"
        )
    return data
