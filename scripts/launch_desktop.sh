#!/usr/bin/env bash
# launch_desktop.sh — check readiness then launch TBH desktop app.
#
# Checks (stops at first failure):
#   1. Python venv exists (.venv/)
#   2. Desktop deps installed (PySide6, requests, bs4, playwright, cloakbrowser)
#   3. mitmproxy installed (system or venv — needed for Start/Stop)
#   4. src/config.json exists and is valid JSON
#   5. CloakBrowser binary downloaded (optional — auto-downloads on first scrape)
#
# If any required check fails, it prints what's missing and how to fix it,
# then exits 1. If all pass, launches the desktop app.
#
# Usage:
#   ./scripts/launch_desktop.sh          # checks + launch
#   ./scripts/launch_desktop.sh --check   # checks only, no launch

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

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

# ── 1. Python venv ─────────────────────────────────────────────────────────
if [[ ! -x ".venv/bin/python" ]]; then
    fail "Python venv not found at .venv/"
    echo "  Fix: python -m venv .venv && .venv/bin/pip install -r requirements-desktop.txt"
    errors=$((errors + 1))
else
    ok "Python venv: $(.venv/bin/python --version 2>&1)"
fi

# ── 2. Desktop deps ─────────────────────────────────────────────────────────
check_dep() {
    local mod="$1" label="$2"
    if .venv/bin/python -c "import $mod" 2>/dev/null; then
        ok "$label"
    else
        fail "$label not installed"
        echo "  Fix: .venv/bin/pip install -r requirements-desktop.txt"
        errors=$((errors + 1))
    fi
}

if [[ -x ".venv/bin/python" ]]; then
    check_dep "PySide6"        "PySide6 (GUI framework)"
    check_dep "requests"       "requests (wiki scraping)"
    check_dep "bs4"            "beautifulsoup4 (HTML parsing)"
    check_dep "playwright"     "playwright (browser automation)"
    check_dep "cloakbrowser"   "cloakbrowser (stealth browser)"
fi

# ── 3. mitmproxy ─────────────────────────────────────────────────────────────
if command -v mitmdump &>/dev/null; then
    ok "mitmproxy: $(mitmdump --version 2>&1 | head -1)"
elif .venv/bin/python -c "import mitmproxy" 2>/dev/null; then
    ok "mitmproxy: (via venv)"
else
    warn "mitmproxy not found — Start/Stop proxy won't work"
    echo "  Fix (Arch): sudo pacman -S mitmproxy"
    echo "  Fix (pip):  .venv/bin/pip install mitmproxy"
    # Not fatal — app can still launch, just can't run proxy
fi

# ── 4. config.json ──────────────────────────────────────────────────────────
if [[ ! -f "src/config.json" ]]; then
    fail "src/config.json not found"
    echo "  The proxy addon needs this file. Create one with the example format from README."
    errors=$((errors + 1))
elif ! .venv/bin/python -c "import json; json.loads(open('src/config.json').read())" 2>/dev/null; then
    fail "src/config.json is invalid JSON"
    echo "  Fix the file — the addon keeps last good config on invalid reload, but the app needs valid JSON to start."
    errors=$((errors + 1))
else
    ok "src/config.json: valid"
fi

# ── 5. CloakBrowser binary (optional) ────────────────────────────────────────
if .venv/bin/python -c "import cloakbrowser" 2>/dev/null; then
    CB_BIN=$(.venv/bin/python -c "
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
# Suppress Wayland noise: "This plugin supports grabbing the mouse only for
# popup windows" is informational (Qt can't grab mouse for non-popup windows
# on Wayland by design — does not affect functionality).
export QT_LOGGING_RULES="${QT_LOGGING_RULES:-};qt.qpa.wayland.warning=false"
exec .venv/bin/python -m tbh_desktop.main
