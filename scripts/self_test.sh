#!/usr/bin/env bash
# Run TBH reward hook self-test (Linux/macOS).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON_CMD="python3"
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    PYTHON_CMD="python"
fi

"$PYTHON_CMD" "$REPO_ROOT/src/tbh_reward_hook.py" --self-test
