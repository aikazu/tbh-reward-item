#!/usr/bin/env bash
# scripts/_py.sh — resolve a Python interpreter.
#
# Priority (anchored at REPO_ROOT, not cwd, so resolution is stable):
#   1. <REPO_ROOT>/.venv/bin/python (if user created a venv there)
#   2. python3 on PATH
#   3. python on PATH
#
# Exits non-zero with a helpful message if nothing is found.
#
# REPO_ROOT is computed from this script's location, so resolution works
# correctly whether you source it, run it directly, or invoke it from
# another directory.
#
# Usage 1 — source it, then call py_run / _py_resolve:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   # shellcheck source=scripts/_py.sh
#   source "$SCRIPT_DIR/_py.sh"
#   py_run -c "import sys; print(sys.executable)"
#
# Usage 2 — invoke directly:
#   bash scripts/_py.sh -c "print('hi')"
#   bash /absolute/path/to/repo/scripts/_py.sh -m tbh_desktop.main

set -euo pipefail

# REPO_ROOT = parent of this script. Computed once at source time.
_PY_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_py_resolve() {
    # 1. Honor .venv/ at the repo root if user already created one.
    #    NOT cwd — otherwise running the script from outside the repo
    #    could pick up a stale .venv in $PWD.
    if [[ -x "$_PY_REPO_ROOT/.venv/bin/python" ]]; then
        echo "$_PY_REPO_ROOT/.venv/bin/python"
        return 0
    fi
    # 2. System python3
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return 0
    fi
    # 3. System python (Windows python.org launcher fallback, etc.)
    if command -v python >/dev/null 2>&1; then
        command -v python
        return 0
    fi
    return 1
}

py_run() {
    local interp
    if ! interp="$(_py_resolve)"; then
        echo "[ERR] no Python found. Install python3 or create $_PY_REPO_ROOT/.venv/" >&2
        return 127
    fi
    "$interp" "$@"
}

# If executed (not sourced), run python with forwarded args.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    py_run "$@"
fi