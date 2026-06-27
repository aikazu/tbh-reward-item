"""Ensure project-root dev_tools is on sys.path before test package imports resolve."""
from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))
