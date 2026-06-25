#!/usr/bin/env bash
# Install Python dependencies for TBH reward proxy (Linux/macOS).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON_CMD="python3"
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    PYTHON_CMD="python"
fi

# Prefer system mitmdump if present; otherwise install via pip.
if ! command -v mitmdump >/dev/null 2>&1; then
    "$PYTHON_CMD" -m pip install --upgrade pip
    "$PYTHON_CMD" -m pip install -r "$REPO_ROOT/requirements.txt"
fi

echo
echo "Done. You can run self_test.sh now."
