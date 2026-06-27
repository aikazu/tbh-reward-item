# scripts/activate.fish — fish wrapper to source venv activate.
#
# Usage: source scripts/activate.fish
#
# Auto-detects repo root from script location. Works from any cwd
# because fish's `status dirname` returns the script's real path
# even when sourced via relative path or symlink.

set -l script_dir (status dirname)
set -l repo_root (realpath "$script_dir/..")
set -l venv_dir "$repo_root/.venv"

if not test -d "$venv_dir"
    echo "scripts/activate.fish: venv not found at $venv_dir" >&2
    echo "  Fix: python -m venv .venv && .venv/bin/pip install -r requirements-desktop.txt" >&2
    return 1
end

source "$venv_dir/bin/activate.fish"