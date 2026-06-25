#!/usr/bin/env bash
# Remove mitmproxy CA cert from system trust store (Arch/CachyOS).
# Idempotent. Requires sudo.
set -euo pipefail

ANCHOR_DIR="/etc/ca-certificates/trust-source/anchors"
INSTALLED_NAME="mitmproxy-ca-cert.pem"
ANCHOR_PATH="$ANCHOR_DIR/$INSTALLED_NAME"

if [[ $EUID -ne 0 ]]; then
    echo "Re-exec with sudo..."
    exec sudo -E bash "$0" "$@"
fi

echo "Removing mitmproxy CA cert..."

removed=0

# Method 1: p11-kit trust anchor remove
if command -v trust >/dev/null 2>&1; then
    if trust anchor --remove "$ANCHOR_PATH" 2>/dev/null; then
        echo "[OK] trust anchor removed"
        removed=1
    else
        # trust may have stored under different path; try by CN
        trust anchor --remove "mitmproxy" 2>/dev/null && removed=1 || true
    fi
fi

# Method 2: remove manual copy + update
if [[ -f "$ANCHOR_PATH" ]]; then
    rm -f "$ANCHOR_PATH"
    echo "[OK] removed $ANCHOR_PATH"
    removed=1
fi

update-ca-trust extract
echo "[OK] update-ca-trust extract"

if [[ $removed -eq 0 ]]; then
    echo "WARN: no mitmproxy cert found in store (already clean?)"
else
    echo
    echo "Verify (should be empty):"
    echo "  trust list | grep -i mitmproxy"
fi
