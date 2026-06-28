#!/usr/bin/env bash
# Launch TBH reward mitmproxy (Linux/macOS).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_CMD="python3"
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    PYTHON_CMD="python"
fi

# Auto-generate config.json from config.default.json if missing.
if [[ ! -f "src/config.json" && -f "src/config.default.json" ]]; then
    "$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
from config_setup import ensure_config, CONFIG_PATH
ensure_config(CONFIG_PATH)
" && echo "Generated src/config.json from config.default.json"
fi

"$PYTHON_CMD" "$REPO_ROOT/src/run_proxy.py" "$@"
