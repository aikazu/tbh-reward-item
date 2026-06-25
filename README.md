# TBH Reward Proxy

[English](README.md) · [Bahasa Indonesia](README.id.md)

A man-in-the-middle proxy that rewrites the `rewardItemId` field in TBH game backend responses. Built on top of [mitmproxy](https://mitmproxy.org/).

It intercepts responses to POST requests at specific endpoints, swaps reward items per the rules in `config.json`, and forwards the modified result to the client.

---

## Table of Contents

- [Components](#components)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
  - [Linux (Arch / CachyOS)](#linux-arch--cachyos)
  - [Windows](#windows)
- [Configuration](#configuration)
  - [Specific Rules (specific_queue_rules)](#specific-rules-specific_queue_rules)
  - [Range Rules (range_replacement)](#range-rules-range_replacement)
- [Running the Proxy](#running-the-proxy)
  - [Reloading config](#reloading-config)
- [Steam Client Setup (TaskBarHero via Proton)](#steam-client-setup-taskbarhero-via-proton)
- [CA Certificate](#ca-certificate)
  - [Linux (system trust)](#linux-system-trust)
  - [Firefox](#firefox)
  - [Chromium / Chrome](#chromium--chrome)
  - [Other Clients](#other-clients)
- [Self-Test](#self-test)
- [Troubleshooting](#troubleshooting)
- [Security Warning](#security-warning)
- [File Structure](#file-structure)

---

## Components

| File | Purpose |
|---|---|
| `tbh_reward_hook.py` | mitmproxy addon. Intercept + rewrite logic. Platform-agnostic, pure Python stdlib. |
| `config.json` | Rewrite rules: listen port, URL filters, specific rules, range rules. |
| `run_proxy.py` | Launcher: find `mitmdump`, fallback to `mitmproxy.tools.main` module. |
| `run_proxy.sh` / `run_proxy.bat` | Shell wrapper that runs `run_proxy.py`. |
| `install_requirements.sh` / `.bat` | Install dependencies (`mitmproxy`). |
| `self_test.sh` / `.bat` | Run offline rewrite tests (without proxy running). |
| `install_cert.sh` | Install mitmproxy CA into system trust store (Linux). |
| `remove_cert.sh` | Remove mitmproxy CA from system trust store (Linux). |
| `requirements.txt` | Dependency: `mitmproxy`. |

---

## How It Works

The addon hooks mitmproxy's `response` event. Filter pipeline:

1. **Method filter** — if `only_post: true`, only POST is processed.
2. **URL filter** — response URL must contain one of the markers in `url_contains`.
3. **Body marker filter** — if `require_boxes_marker: true`, body must contain literal `"boxes"`.
4. **Rewrite** — regex finds `"itemId":<n>` then `"rewardItemId":<m>` after it. If itemId matches a rule, replace `rewardItemId` with a value from `replacement_reward_item_ids` (cycled per match).
5. **Write back** — `response.set_text()` with the new body.

```
Client --POST--> [mitmproxy:8877] --forward--> TBH Backend
                      |
                      v
                 response (JSON boxes)
                      |
                 hook: rewrite rewardItemId
                      |
Client <--mod response-- [mitmproxy:8877]
```

The regex uses backslash escaping to handle JSON that may be escaped (`\"itemId\"` as well as `"itemId"`).

---

## Requirements

- Python 3.10+ (modern typing `dict[str, Any]`, `tuple[str, ...]`).
- `mitmproxy` 10+ (tested on 12.2.3).
- sudo access (Linux) for cert install + dependencies.

---

## Installation

### Linux (Arch / CachyOS)

`mitmproxy` is available in the `extra` repo:

```bash
sudo pacman -S mitmproxy
```

Or via the script (auto-checks and installs via pip if `mitmdump` is missing — on Arch pip is blocked by PEP 668, so pacman is preferred):

```bash
./scripts/install_requirements.sh
```

Verify:

```bash
mitmdump --version
python3 src/tbh_reward_hook.py --self-test
```

### Windows

```bat
windows\install_requirements.bat
```

Uses `py` if available, falls back to `python`. Installs `mitmproxy` via pip.

---

## Configuration

Edit `config.json`. Format:

```json
{
  "listen_port": 8877,
  "only_post": true,
  "require_boxes_marker": true,
  "url_contains": ["/backend-function/base/v1"],
  "specific_queue_rules": [
    {
      "enabled": true,
      "name": "White box",
      "item_id": 910801,
      "replacement_reward_item_ids": [519171, 519171, 519171]
    }
  ],
  "range_replacement": {
    "enabled": false,
    "name": "Range replacement",
    "match_min_item_id": 500000,
    "match_max_item_id": 950000,
    "replacement_reward_item_ids": [529191, 419191, 409191, 619191, 429191, 509191]
  }
}
```

### Specific Rules (specific_queue_rules)

Matches `itemId` exactly. Each match consumes one value from `replacement_reward_item_ids` cyclically (index modulo list length).

Example: White box `910801` → replace reward with `519171`. If 3 White boxes exist, all become `519171` (list has 3 identical elements).

### Range Rules (range_replacement)

`enabled: false` by default. When active, matches `itemId` within `[match_min_item_id, match_max_item_id]`. Priority: specific rules evaluated first; if no match, check range.

Cycling is identical: one value per match, modulo list length.

---

## Running the Proxy

```bash
./scripts/run_proxy.sh          # Linux
windows\run_proxy.bat           # Windows
```

Or directly:

```bash
mitmdump -s src/tbh_reward_hook.py --listen-port 8877 --set block_global=false -q
```

Output (TBH logs only):

```
[TBH] TBH Reward Proxy loaded: 2 queue rules, range mode=off.
[TBH] TBH Reward Proxy replaced White box: itemId=910801, rewardItemId=1001->519171
[TBH] TBH Reward Proxy wrote 3 replacement(s).
```

Stop: `Ctrl+C`.

Point the target client at proxy `127.0.0.1:8877` (HTTP/HTTPS proxy).

### Reloading config (hot reload)

`config.json` is **hot-reloaded** — no proxy restart needed. The addon checks the file mtime on every intercepted response and reloads automatically when it changes.

- Edit `config.json`, save → next request picks up the new rules. Log: `TBH Reward Proxy reloaded: ...`.
- Manual reload without editing: `pkill -HUP -f mitmdump` (sends SIGHUP).
- **Corrupt config safety**: if `config.json` is invalid (bad JSON, wrong types), the addon keeps the **last good config** running and logs `kept previous config (config.json invalid)`. A bad edit never breaks active interception. Fix the file and save to reload.
- If `config.json` is missing/corrupt at startup, the proxy boots with an empty fallback config (no rules) and logs `using fallback empty config`.

You only need to restart the proxy to change `listen_port` (mitmproxy binds the port at startup).

---

## Steam Client Setup (TaskBarHero via Proton)

TaskBarHero is a Windows Unity game (Steam AppId 3678970) running through Proton + SteamLinuxRuntime_4 + pressure-vessel on Linux. The sandbox isolates the network namespace and does not forward host proxy env vars by default.

### Working method: Steam Launch Options (tested, confirmed working)

Steam → right-click **TaskbarHero** → Properties → **Launch Options**, enter:

```
HTTP_PROXY=http://127.0.0.1:8877 HTTPS_PROXY=http://127.0.0.1:8877 %command%
```

Proton forwards these env vars into the Wine process, where Unity's `HttpClient` picks them up.

### CA trust inside Proton prefix

Unity/Proton uses the **Wine/Proton Windows cert store**, not the Linux system trust. Install the mitmproxy CA into the Proton prefix (AppId 3678970):

```bash
WINEPREFIX=~/.local/share/Steam/steamapps/compatdata/3678970/pfx \
  wine certmgr -add -c -root ~/.mitmproxy/mitmproxy-ca-cert.cer
```

If `certmgr` is unavailable in that prefix, copy the cert into the Wine CA dir:

```bash
PFX=~/.local/share/Steam/steamapps/compatdata/3678970/pfx
cp ~/.mitmproxy/mitmproxy-ca-cert.cer "$PFX/drive_c/windows/system32/cert/CA/"
```

### Notes

- Native Unity sockets (non-HttpClient) may ignore proxy env regardless of method.
- AppId 3678970 is a commercial Steam title — intercepting/modifying its traffic may violate Steam and/or game ToS. Use only on owned accounts in controlled environments.
- If Launch Options env is ignored, alternatives: transparent iptables redirect (host layer, requires bypassing pressure-vessel network isolation) or Wine proxy registry (`HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings`).

---

## CA Certificate

mitmproxy intercepts HTTPS using its own CA. Clients must trust this CA, otherwise certificate errors appear. The CA is generated automatically the first time `mitmdump` runs, located at `~/.mitmproxy/`.

### Linux (system trust)

Install:

```bash
./scripts/install_cert.sh
```

The script auto-re-execs as sudo, uses `trust anchor --store` + `update-ca-trust extract`. Verify:

```bash
trust list | grep -i mitmproxy
```

Remove (when no longer intercepting):

```bash
./scripts/remove_cert.sh
```

### Firefox

Firefox has its own store and does not read system trust.

1. `about:preferences#privacy`
2. Certificates → View Certificates → **Authorities** tab
3. Import → `~/.mitmproxy/mitmproxy-ca-cert.pem`
4. Check "Trust this CA to identify websites" → OK

### Chromium / Chrome

Reads system trust (Linux step above is sufficient). Or bypass via flag:

```bash
chromium --ignore-certificate-errors-spki-list=$(openssl x509 -in ~/.mitmproxy/mitmproxy-ca-cert.pem -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64)
```

### Other Clients

- **Electron/Node**: `NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem`
- **Python (requests/urllib)**: `SSL_CERT_FILE=~/.mitmproxy/mitmproxy-ca-cert.pem` or `REQUESTS_CA_BUNDLE=...`
- **Android emulator**: push cert to `/system/etc/security/cacerts/` (different process).
- **Windows client**: import `.cer` via `certmgr.msc` → Trusted Root.

---

## Self-Test

Offline rewrite test without the proxy running. Validates regex + rule logic against `config.json`.

```bash
./scripts/self_test.sh          # Linux
windows\self_test.bat           # Windows
```

Success output:

```
[TBH] TBH Reward Proxy loaded: 2 queue rules, range mode=off.
Self-test OK.
```

The self-test reads `config.json` and compares rewrite results against expected values. If you change rules in config, update the expected values in the `run_self_test()` function (`tbh_reward_hook.py`) so the test stays meaningful.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: mitmproxy` | mitmproxy not installed | `sudo pacman -S mitmproxy` / `./scripts/install_requirements.sh` |
| Proxy runs but responses unchanged | URL/body filter mismatch | Check `url_contains`, ensure body contains `"boxes"`. Look for log `[TBH] matched URL but found no replaceable` |
| Client HTTPS cert error | CA not trusted | Run `./scripts/install_cert.sh` (see [CA Certificate](#ca-certificate)) |
| `AssertionError` in self-test | Expected values don't match config | Align expected values in `run_self_test()` with `config.json` |
| Port 8877 in use | Port conflict | Change `listen_port` in `config.json` |
| Firefox still errors | Separate store | Import manually via `about:preferences#privacy` |
| `sudo: a terminal is required` | sudo non-interactive without TTY | Run via `!` prefix in prompt, or `echo PASS \| sudo -S ...` |

Verbose debug (without `-q`):

```bash
mitmdump -s src/tbh_reward_hook.py --listen-port 8877 --set block_global=false --flow-detail 2
```

---

## Security Warning

**The mitmproxy CA can sign any HTTPS certificate.** If a machine trusts this CA, anyone running a proxy on that machine can intercept all encrypted traffic.

- Only install the CA on environments you control (dev/test).
- Remove the CA after use: `./scripts/remove_cert.sh`.
- Never commit `~/.mitmproxy/mitmproxy-ca*.pem` files to any repo.
- Never share the CA private key (`mitmproxy-ca.pem`, `mitmproxy-ca.p12`).
- Use on third-party services/games may violate their ToS. User bears responsibility.

---

## File Structure

```
TBH/
├── src/
│   ├── tbh_reward_hook.py  # mitmproxy addon (rewrite logic)
│   ├── run_proxy.py        # launcher (find mitmdump / fallback module)
│   └── config.json         # rewrite rules
├── scripts/
│   ├── run_proxy.sh            # Linux wrapper
│   ├── install_requirements.sh # Linux dep installer
│   ├── self_test.sh            # Linux rewrite test
│   ├── install_cert.sh         # Linux CA system trust installer
│   └── remove_cert.sh          # Linux CA system trust remover
├── windows/
│   ├── run_proxy.bat           # Windows wrapper
│   ├── install_requirements.bat # Windows dep installer
│   └── self_test.bat           # Windows rewrite test
├── requirements.txt        # mitmproxy
├── README.md               # English docs
└── README.id.md            # Indonesian docs
```

Scripts use absolute paths (`REPO_ROOT` in shell, `%~dp0..` in bat) so they work from any cwd. Source files (`src/`) reference siblings via `Path(__file__).resolve().parent`, so keep `tbh_reward_hook.py`, `run_proxy.py`, and `config.json` together.
