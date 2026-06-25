# TBH Reward Proxy

> **⚠️ DWYOR — Do With Your Own Risk**
>
> This tool intercepts and modifies game network traffic. Using it may violate
> the game's Terms of Service and **can result in your account being banned**.
> The authors are not responsible for any consequences. Use at your own risk.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![mitmproxy](https://img.shields.io/badge/mitmproxy-12%2B-E66733?logo=mitmproxy&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.6%2B-41CD52?logo=qt&logoColor=white)
![platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-blue)

[English](README.md) · [Bahasa Indonesia](README.id.md)

A man-in-the-middle proxy that rewrites the `rewardItemId` field in TBH game backend responses. Built on top of [mitmproxy](https://mitmproxy.org/), with an optional [PySide6](https://www.qt.io/) desktop GUI for visual config editing and reward-ID picking.

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
- [Desktop App](#desktop-app)
  - [Install](#desktop-install)
  - [Launch](#desktop-launch)
  - [Features](#desktop-features)
  - [Hot-Reload Interaction](#desktop-hot-reload)
  - [Known Limitations](#desktop-limitations)
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
- [Acknowledgements](#acknowledgements)

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
| `scripts/launch_desktop.sh` | Readiness-check launcher for the desktop app (Linux). |
| `windows/launch_desktop.bat` | Readiness-check launcher for the desktop app (Windows). |
| `requirements.txt` | Dependency: `mitmproxy`. |
| `requirements-desktop.txt` | Optional desktop deps: `PySide6`, `requests`, `beautifulsoup4`, `pytest-qt`. |
| `tbh_desktop/` | Optional PySide6 GUI: edit `config.json`, pick reward IDs, run/stop proxy, stream logs. See [Desktop App](#desktop-app). |
| `tests/` | Pytest suite for the desktop app (`config_io`, `scraper`, `proxy_runner`). |
| `docs/` | Specs + implementation plans. |

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

## Desktop App

![Desktop App](desktop-app.webp)

An optional PySide6 GUI that wraps the same `config.json` and `run_proxy.py` the CLI uses. Lets you edit rules visually, pick reward IDs from the TBH wiki/loot tables, and run the proxy without leaving the window.

It does **not** replace the proxy addon — the GUI spawns `src/run_proxy.py` as a subprocess and streams its stdout. The same hot-reload rules apply.

### Install <a id="desktop-install"></a>

Desktop deps are intentionally separate from `requirements.txt` (mitmproxy) so the proxy install stays light. The desktop app needs: PySide6 (GUI), requests + beautifulsoup4 (wiki scraping), playwright + cloakbrowser (stealth browser for gear scrape), pytest-qt (tests).

#### Linux (Arch / CachyOS / any distro with venv)

**Step 1 — Create a virtual environment:**

```bash
cd /path/to/TBH
python -m venv .venv
```

**Step 2 — Install desktop dependencies:**

```bash
.venv/bin/pip install -r requirements-desktop.txt
```

This installs PySide6, requests, bs4, pytest-qt, playwright, and cloakbrowser in one shot.

**Step 3 — (Optional) Install Playwright browser engine for fallback:**

CloakBrowser downloads its own stealth Chromium binary on first launch (~200 MB, cached locally). You only need `playwright install chromium` if you want the stock-Playwright fallback (used when CloakBrowser is not installed):

```bash
.venv/bin/playwright install chromium
```

> **Note for Arch users:** PySide6, python-requests, and python-beautifulsoup4 are also available via pacman (`sudo pacman -S pyside6 python-requests python-beautifulsoup4`), but using the venv is simpler and avoids PEP 668 issues. `playwright` and `cloakbrowser` are pip-only — no pacman package exists.

**Step 4 — Launch:**

```bash
.venv/bin/python -m tbh_desktop.main
```

#### Windows

**Step 1 — Create a virtual environment:**

```bat
cd C:\path\to\TBH
python -m venv .venv
```

> If `python` is not found, try `py -3 -m venv .venv` (uses the py launcher).

**Step 2 — Install desktop dependencies:**

```bat
.venv\Scripts\pip install -r requirements-desktop.txt
```

**Step 3 — (Optional) Install Playwright browser engine for fallback:**

```bat
.venv\Scripts\playwright install chromium
```

Same as Linux — only needed for the stock-Playwright fallback. CloakBrowser manages its own binary.

**Step 4 — Launch:**

```bat
.venv\Scripts\python -m tbh_desktop.main
```

#### CloakBrowser (stealth scraping engine)

Starting with v0.4+, the gear scraper uses [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) — a stealth Chromium build with 58 C++ source-level anti-detection patches — as the scraping engine. It is a drop-in replacement for Playwright's `chromium.launch()` and downloads its own patched binary on first use (~200 MB, cached locally, Ed25519-verified). No separate `playwright install` step is needed for CloakBrowser, but the `playwright` Python package must still be installed (CloakBrowser depends on it for its Playwright-compatible API).

CloakBrowser benefits over stock Playwright for scraping:

- Passes Cloudflare Turnstile, reCAPTCHA v3 (0.9 score), FingerprintJS, BrowserScan
- `humanize=True` — human-like Bézier mouse curves, per-character keyboard timing, realistic scroll
- `navigator.webdriver` patched to `false` at the C++ source level
- TLS fingerprint identical to real Chrome (ja3n/ja4/akamai match)

If CloakBrowser is not installed (`pip install cloakbrowser`), the scraper falls back to stock Playwright `chromium.launch()` automatically. The `playwright install chromium` step is only needed in that fallback case.

The proxy addon itself (`requirements.txt` / `mitmproxy`) is still required if you want Start/Stop to work — see [Installation](#installation) above.

### Launch <a id="desktop-launch"></a>

Instead of running `python -m tbh_desktop.main` manually, use the readiness-check launchers — they verify venv, deps, mitmproxy, config.json, and CloakBrowser binary before starting the app, and print fix instructions if anything is missing:

```bash
./scripts/launch_desktop.sh          # Linux: checks + launch
./scripts/launch_desktop.sh --check  # Linux: checks only, no launch
```

```bat
windows\launch_desktop.bat            : Windows: checks + launch
windows\launch_desktop.bat --check   : Windows: checks only, no launch
```

After launch, the main window has a toolbar (Start / Stop / Scrape gear / Save config / port / status dot) and a two-pane layout: editor on the left, live log on the right.

### Features <a id="desktop-features"></a>

- **Dark theme** — Catppuccin Mocha palette applied app-wide. Consistent colors for buttons, tables, lists, inputs, log panel, and pickers. The log panel uses a FiraCode/JetBrainsMono monospace font on a darker crust background for terminal-like readability.
- **Edit `src/config.json` visually**
  - `specific_queue_rules` table — enabled / name / item_id / replacement IDs columns. Add / Remove rows.
  - `range_replacement` — enabled, min/max item_id, replacement IDs.
  - `listen_port` — toolbar field.
  - Advanced fields (`only_post`, `require_boxes_marker`, `url_contains`) are **not** exposed in the GUI but are **preserved** on save: the editor reads the file as a raw dict and only touches the fields it owns.
- **Atomic save** — validates against `ProxyConfig.load` before and after writing. Backups the previous file as `config.json.bak`, writes via temp + rename, restores from backup on re-validation failure. A bad save never breaks active interception.
- **Pick reward IDs** — every `Replacement IDs` cell supports manual typing, plus:
  - **Pick from box loot** — resolves the box's slug by looking up the `box_id` in the wiki's items page (`https://taskbarhero.org/en/items` "Stage chests" table), fetches the per-box loot table from `https://taskbarhero.org/en/items/chests/<id>-<slug>/`, parses it, and lets you multi-select items. The id→slug map is cached at `tbh_desktop/box_slug_cache.json`; loot is cached per-box at `tbh_desktop/box_loot_cache/<box_id>.json`. Resolving the slug by id (rather than deriving it from the rule's `name`) fixes 404s when the heuristic slug didn't match the wiki's real slug.
  - **Pick gear** — reads from per-category×grade cache files under `tbh_desktop/gear_cache/` (files named `gear_{category}_{grade}.json`, e.g. `gear_weapon_legendary.json`). The picker has three filters: **Category** (Weapon / Off-hand / Armor / Accessory / All), **Grade** (Legendary / Immortal / Arcana / Beyond / Celestial / Divine / Cosmic / All — Legendary-and-above only), and **Level range** (min/max 1-100). Multi-select list and search box preserved.
- **Scrape gear** (was "Refresh gear") — triggers a full CloakBrowser-based scrape: opens the wiki headless, clicks the rarity chip for each Legendary+ grade and the type chip for each category, ticks "Obtainable only", and clicks "LOAD MORE" until exhausted, then writes one cache file per category×grade. Slow (launches a stealth browser). Logs the total count on completion. Falls back to existing cache files on per-combo or launch error. If CloakBrowser is not installed, falls back to stock Playwright.
- **Start / Stop proxy** — spawns `src/run_proxy.py` as a subprocess (cwd = repo root). Status dot turns green while running. Streamed stdout (with stderr merged) flows into the log panel via Qt signals — real-time, FIFO capped at 10k lines. Stop sends SIGTERM, escalates to SIGKILL after 3s. If the toolbar port field differs from the saved `listen_port` when Start is clicked, the app prompts "Port changed. Save config first?" — Yes saves then starts, No aborts. This prevents the silent desync where the proxy ran on the old port while the UI showed the new one.
- **Save config** — atomic, validated (see above). Same mtime-based hot-reload as a manual edit.
- **Close confirm** — if the proxy is running, closing the window asks before stopping it.
- **Menu** — File (Save config, Exit). Help (About).

### Hot-Reload Interaction <a id="desktop-hot-reload"></a>

The GUI edits the **same** `config.json` the addon reads. Saving from the GUI bumps the file's mtime, so the addon's per-response mtime check picks up the new rules on the very next intercepted request — no proxy restart needed.

Exception: `listen_port`. The toolbar field writes into `config.json` but mitmproxy binds the port at startup, so changing it requires a proxy restart (Stop → Start). The Start button now guards against the desync: if the toolbar port differs from the saved `listen_port` when Start is clicked, it prompts to save first (Yes saves then starts, No aborts) rather than starting on the stale saved port.

### Known Limitations <a id="desktop-limitations"></a>

- **Box loot requires a valid `item_id`** in the selected rule row, and the box must exist in the wiki's "Stage chests" table on `https://taskbarhero.org/en/items`. The slug is resolved by `box_id` lookup against that table (cached at `tbh_desktop/box_slug_cache.json`), so a matching `name` is no longer needed. Rare or new boxes not yet on the wiki will fail the lookup — fall back to typing IDs directly into the cell.
- **Scrape gear requires CloakBrowser + a browser engine** installed (`pip install cloakbrowser`). CloakBrowser downloads its ~200 MB patched Chromium binary on first launch (cached locally). Without it, the scraper falls back to stock Playwright (`playwright install chromium` needed).
- **Gear scrape covers Legendary-and-above grades only** (Legendary / Immortal / Arcana / Beyond / Celestial / Divine / Cosmic) across the four categories (Weapon / Off-hand / Armor / Accessory). Lower grades (Common / Uncommon / Rare) are not scraped by the GUI — type their IDs directly if needed.
- **Pickers need network** to fetch fresh data; they fall back to the cache on fetch failure (silent — see log panel for the warning).
- The GUI is read-only against the on-disk config; concurrent edits from another tool are not detected. If you edit the file outside the GUI while it is open, restart the app to re-read.

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
├── src/                    # mitmproxy addon (tbh_reward_hook.py, run_proxy.py, config.json)
├── scripts/                # Linux wrappers (run_proxy, install_reqs, self_test, launch_desktop)
├── windows/                # Windows wrappers (run_proxy, install_reqs, self_test, launch_desktop)
├── tbh_desktop/            # PySide6 desktop GUI (optional)
│   ├── main.py             # entry point
│   ├── config_io.py        # load/save config (atomic + validate)
│   ├── scraper.py          # gear wiki + box loot scrape, cache
│   ├── proxy_runner.py     # subprocess + stdout stream
│   ├── paths.py            # path resolution
│   └── ui/                 # main_window, config_editor, gear_picker, box_loot_picker, log_panel, theme
├── tests/                  # pytest (config_io, scraper, proxy_runner)
├── docs/                   # specs + plans
├── requirements.txt            # mitmproxy
├── requirements-desktop.txt    # PySide6, requests, bs4, pytest-qt, playwright, cloakbrowser
├── README.md
└── README.id.md
```

Scripts use absolute paths (`REPO_ROOT` in shell, `%~dp0..` in bat) so they work from any cwd. Source files (`src/`) reference siblings via `Path(__file__).resolve().parent`, so keep `tbh_reward_hook.py`, `run_proxy.py`, and `config.json` together.

The desktop app's `tbh_desktop/gear_cache/` (per category×grade gear JSON), `tbh_desktop/box_slug_cache.json` (box_id → slug map), and `tbh_desktop/box_loot_cache/` are generated and gitignored — delete them to force a re-fetch from the wiki. The legacy single-file `tbh_desktop/gear_cache.json` is superseded by the `gear_cache/` directory and is no longer written by the picker.

---

## Acknowledgements

This project builds on the **Persistent Reward Item Generator** technique researched and shared by the UnknownCheats community. Original thread: [TBH - Persistent Reward Item Generator](https://www.unknowncheats.me/forum/other-games/758547-tbh-persistent-reward-item-generator.html).
