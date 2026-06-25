#!/usr/bin/env bash
# Install mitmproxy CA cert into system trust store (Arch/CachyOS).
# Idempotent. Requires sudo.
set -euo pipefail

CERT="${MITMPROXY_CA_CERT:-$HOME/.mitmproxy/mitmproxy-ca-cert.pem}"
ANCHOR_DIR="/etc/ca-certificates/trust-source/anchors"
INSTALLED_NAME="mitmproxy-ca-cert.pem"

if [[ ! -f "$CERT" ]]; then
    echo "ERR: cert not found: $CERT" >&2
    echo "Run mitmdump once first to generate CA at ~/.mitmproxy/" >&2
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "Re-exec with sudo..."
    exec sudo -E bash "$0" "$@"
fi

echo "Installing: $CERT"

# Method 1: p11-kit trust anchor (preferred)
if command -v trust >/dev/null 2>&1; then
    trust anchor --store "$CERT"
    echo "[OK] trust anchor stored"
    # Also drop a copy in anchors dir for update-ca-trust consistency + easy remove
    install -m 0644 "$CERT" "$ANCHOR_DIR/$INSTALLED_NAME"
    update-ca-trust extract
    echo "[OK] update-ca-trust extract"
else
    # Method 2: fallback manual copy
    mkdir -p "$ANCHOR_DIR"
    install -m 0644 "$CERT" "$ANCHOR_DIR/$INSTALLED_NAME"
    update-ca-trust extract
    echo "[OK] copied to $ANCHOR_DIR + update-ca-trust"
fi

echo
echo "Verify:"
echo "  trust list | grep -i mitmproxy"
echo
echo "NOTE: Firefox uses its own store. Import via about:preferences#privacy manually."
echo "Remove later: ./remove_cert.sh"
