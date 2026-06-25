#!/usr/bin/env bash
# Launch TBH reward mitmproxy (Linux/macOS).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON_CMD="python3"
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    PYTHON_CMD="python"
fi

"$PYTHON_CMD" "$REPO_ROOT/src/run_proxy.py"
