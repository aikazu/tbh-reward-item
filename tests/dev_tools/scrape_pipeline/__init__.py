"""Load backoff directly from the project-root source file, bypassing sys.modules shadow."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Backoff lives at the project root; load it directly from the filesystem
# so it bypasses the sys.modules shadow from tests/dev_tools/ namespace.
# __file__ = .../tests/dev_tools/scrape_pipeline/__init__.py
# .parent = .../tests/dev_tools/scrape_pipeline
# .parent.parent = .../tests/dev_tools
# .parent.parent.parent = .../tests  → parent.parent.parent.parent = project root
_root = Path(__file__).parent.parent.parent.parent / "dev_tools" / "scrape_pipeline"
_spec = importlib.util.spec_from_file_location(
    "dev_tools.scrape_pipeline.backoff",
    _root / "backoff.py",
)
if _spec and _spec.loader:
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["dev_tools.scrape_pipeline.backoff"] = _module
    _spec.loader.exec_module(_module)

# Re-export for consumers of this package
from dev_tools.scrape_pipeline.backoff import backoff

__all__ = ["backoff"]
