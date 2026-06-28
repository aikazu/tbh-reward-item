#!/usr/bin/env bash
# launch_desktop.sh — check readiness then launch TBH desktop app.
#
# Checks (stops at first failure):
#   1. Python interpreter available (system python3 / py, OR .venv/ if present)
#   2. Desktop deps installed (PySide6, requests, bs4, playwright, cloakbrowser)
#   3. mitmproxy installed (system or venv — needed for Start/Stop)
#   4. src/config.json exists and is valid JSON
#   5. CloakBrowser binary downloaded (optional — auto-downloads on first scrape)
#
# Does NOT force .venv/. Use whatever interpreter has the deps:
#   - If .venv/ exists, it's used (honor user's choice)
#   - Otherwise system python3/python is used
#   - If deps missing, prints what's missing and how to fix it, then exits 1.
#
# Usage:
#   ./scripts/launch_desktop.sh          # checks + launch
#   ./scripts/launch_desktop.sh --check   # checks only, no launch

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=scripts/_py.sh
source "$REPO_ROOT/scripts/_py.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }

CHECK_ONLY=false
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=true

errors=0

# Resolve interpreter once (venv-preferred, falls back to system).
if ! _PY_INTERP="$(_py_resolve)"; then
    fail "no Python interpreter found"
    echo "  Fix (Arch):  sudo pacman -S python"
    echo "  Fix (pip):   python3 -m venv .venv && .venv/bin/pip install -r requirements-desktop.txt"
    exit 1
fi

PY_LABEL="$_PY_INTERP"
ok "Python: $("$PY_LABEL" --version 2>&1) [$PY_LABEL]"

# ── 2. Desktop deps ─────────────────────────────────────────────────────────
check_dep() {
    local mod="$1" label="$2" fix="$3"
    if "$_PY_INTERP" -c "import $mod" 2>/dev/null; then
        ok "$label"
    else
        fail "$label not installed"
        echo "  Fix: $fix"
        errors=$((errors + 1))
    fi
}

check_dep "PySide6"      "PySide6 (GUI framework)" \
    "$PY_LABEL -m pip install -r requirements-desktop.txt"
check_dep "requests"     "requests (wiki scraping)" \
    "$PY_LABEL -m pip install requests"
check_dep "bs4"          "beautifulsoup4 (HTML parsing)" \
    "$PY_LABEL -m pip install beautifulsoup4"
check_dep "playwright"   "playwright (browser automation)" \
    "$PY_LABEL -m pip install playwright && $PY_LABEL -m playwright install chromium"
check_dep "cloakbrowser" "cloakbrowser (stealth browser)" \
    "$PY_LABEL -m pip install cloakbrowser"

# ── 3. mitmproxy ─────────────────────────────────────────────────────────────
if command -v mitmdump &>/dev/null; then
    ok "mitmproxy: $(mitmdump --version 2>&1 | head -1)"
elif "$_PY_INTERP" -c "import mitmproxy" 2>/dev/null; then
    ok "mitmproxy: (via $PY_LABEL)"
else
    warn "mitmproxy not found — Start/Stop proxy won't work"
    echo "  Fix (Arch): sudo pacman -S mitmproxy"
    echo "  Fix (pip):  $PY_LABEL -m pip install mitmproxy"
    # Not fatal — app can still launch, just can't run proxy
fi

# ── 4. config.json ──────────────────────────────────────────────────────────
# If config.json is missing but config.default.json is present, auto-generate
# it before the existence check. This mirrors the desktop app / addon
# auto-generate logic in src/config_setup.py.
if [[ ! -f "src/config.json" && -f "src/config.default.json" ]]; then
    if "$_PY_INTERP" -c "
import shutil, sys
sys.path.insert(0, 'src')
from config_setup import ensure_config, CONFIG_PATH
ensure_config(CONFIG_PATH)
" 2>/dev/null; then
        if [[ -f "src/config.json" ]]; then
            ok "src/config.json (auto-generated from config.default.json)"
        fi
    fi
fi

if [[ ! -f "src/config.json" ]]; then
    fail "src/config.json not found"
    echo "  The proxy addon needs this file. Create one with the example format from README."
    errors=$((errors + 1))
elif ! "$_PY_INTERP" -c "import json; json.loads(open('src/config.json').read())" 2>/dev/null; then
    fail "src/config.json is invalid JSON"
    echo "  Fix the file — the addon keeps last good config on invalid reload, but the app needs valid JSON to start."
    errors=$((errors + 1))
else
    ok "src/config.json: valid"
fi

# ── 5. CloakBrowser binary (optional) ────────────────────────────────────────
if "$_PY_INTERP" -c "import cloakbrowser" 2>/dev/null; then
    CB_BIN=$("$_PY_INTERP" -c "
import cloakbrowser, os
try:
    p = cloakbrowser.ensure_binary()
    print(p if (p and os.path.exists(p)) else '')
except:
    print('')
" 2>/dev/null || echo "")
    if [[ -n "$CB_BIN" ]]; then
        ok "CloakBrowser binary: $(basename "$CB_BIN")"
    else
        warn "CloakBrowser binary not downloaded yet — will auto-download (~200MB) on first scrape"
    fi
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
if [[ $errors -gt 0 ]]; then
    fail "$errors check(s) failed. Fix the issues above before launching."
    exit 1
fi

ok "All checks passed. Ready to launch."
echo ""

if [[ "$CHECK_ONLY" == true ]]; then
    exit 0
fi

echo "Launching TBH desktop app…"
# Warn if the user launched us via sudo. The GUI itself does NOT need
# root — only mitmdump's local-redirector setuid helper does, and
# that's handled at Start-button time via pkexec (which prompts the
# user for their polkit password). Running the GUI as root actually
# breaks things: the elevated process can't attach to the user's
# X11/Wayland session, so the window never appears.
if [[ $EUID -eq 0 ]]; then
    warn "Running as root (EUID=0). The GUI cannot attach to your"
    warn "  X11/Wayland session from a root context — the window will"
    warn "  not appear. Launch as your regular desktop user instead:"
    warn "    $REPO_ROOT/scripts/launch_desktop.sh"
    warn "  (the Start button will prompt for your polkit password"
    warn "  only when actually needed for mode='local')."
    echo ""
fi
# Suppress Wayland noise: "This plugin supports grabbing the mouse only for
# popup windows" is informational (Qt can't grab mouse for non-popup windows
# on Wayland by design — does not affect functionality).
export QT_LOGGING_RULES="${QT_LOGGING_RULES:-};qt.qpa.wayland.warning=false"
exec "$_PY_INTERP" -m tbh_desktop.main