# TBH Reward Proxy

**DWYOR** — modifies TBH game traffic; account ban risk.

Man-in-the-middle proxy that rewrites `rewardItemId` in **TaskBarHero** (Steam AppId 3678970, Windows Unity idle RPG) backend responses. mitmproxy addon + optional PySide6 desktop GUI.

## Stack

- Python 3.10+
- `mitmproxy` — proxy addon (in `requirements.txt`)
- `PySide6 >= 6.6`, `requests >= 2.31`, `beautifulsoup4 >= 4.12`, `lxml >= 5.0`, `pytest-qt >= 4.3`, `playwright >= 1.40`, `cloakbrowser >= 0.4`, `Pillow >= 10.0` (in `requirements-desktop.txt`)
- No `pyproject.toml` — pure `requirements*.txt` + venv
- Type-check via `pyright` (`pyrightconfig.json`)

## Commands

```bash
# Proxy addon (no GUI)
sudo pacman -S mitmproxy                       # Arch / CachyOS preferred (PEP 668)
./scripts/install_requirements.sh              # pip fallback
./scripts/run_proxy.sh                         # Linux launcher
mitmdump -s src/tbh_reward_hook.py --listen-port 8877 --set block_global=false -q
python3 src/tbh_reward_hook.py --self-test     # offline regex + rule test

# Desktop GUI
python -m venv .venv
.venv/bin/pip install -r requirements-desktop.txt
./scripts/launch_desktop.sh                    # readiness check + launch
.venv/bin/python -m tbh_desktop.main           # manual

# Tests
pytest                                         # skips @pytest.mark.gui + integration
pytest -m gui                                  # opt-in GUI tests (real Qt event loop)

# CA cert (mitmproxy intercepts HTTPS — client must trust its CA)
./scripts/install_cert.sh                      # Linux: system trust store
./scripts/remove_cert.sh
windows\install_cert.bat                       # Windows: auto-elevate UAC
```

## Architecture

```
TBH/
├── src/                                # mitmproxy addon
│   ├── tbh_reward_hook.py              # TBHRewardHook + RewardRewriter (regex engine)
│   ├── tbh_proxy_config.py             # ProxyConfig / QueueRule / RangeRule data classes
│   ├── run_proxy.py                    # launcher (finds mitmdump or python -m mitmproxy.tools.main)
│   ├── config_setup.py                 # ensure_config() — copies config.default.json → config.json
│   ├── config.default.json             # seed template
│   └── config.json                     # generated on first run, hot-reloaded
├── tbh_desktop/                        # optional PySide6 GUI
│   ├── main.py                         # entry: QApplication + theme + MainWindow + SIGINT handler
│   ├── paths.py                        # re-exports from src/config_setup.py (single source of truth)
│   ├── config_io.py                    # load/save (validate → atomic temp+rename → re-validate → restore .bak)
│   ├── gear_filters.py                 # rarity/tier/slot filter predicates for gear views
│   ├── linux_elevation.py              # pkexec/sudo helper for --mode local setuid redirector
│   ├── proxy_runner.py                 # subprocess + group SIGTERM/SIGKILL + stdout→Qt signal stream
│   ├── scraper.py                      # gear + box loot scrape (requests/bs4, CloakBrowser for gear)
│   ├── gear_scraper_runner.py          # QObject thread wrapper around scraper.refresh_gear_full
│   └── ui/
│       ├── main_window.py              # QMainWindow: QSplitter(RuleDetailPanel+catalog) + CatalogPopup + StatusBadge toolbar + Log dock + _ThreadLogBridge
│       ├── rule_detail_panel.py        # right-side rule editor form
│       ├── catalog_popup.py            # unified gear/box/loot picker popup
│       ├── status_badge.py             # toolbar RUNNING/STOPPED indicator
│       ├── config_editor.py            # wraps RuleListView + _RangeForm (post-T11)
│       ├── rule_list.py / rule_card.py # card-based rule list
│       ├── item_browser.py             # 6-tab right panel + FilterContext (post-T9)
│       ├── item_card.py                # rarity-bordered card
│       ├── gear_picker.py              # GearView (GearPicker dialog = shim)
│       ├── box_picker.py               # BoxView
│       ├── box_loot_picker.py          # BoxLootView
│       ├── active_target.py            # RuleTarget | RangeTarget union
│       ├── log_panel.py                # bottom dock, monospace
│       └── theme.py                    # Catppuccin Mocha + rarity palette + ornament + image_cache.py
├── scripts/                            # run_proxy, install_requirements, self_test, install_cert, remove_cert, launch_desktop (+ activate.{,fish})
├── windows/                            # Windows equivalents + install_cert.bat
├── tests/                              # top-level: config_io, scraper, proxy_runner, run_proxy, reward_rewriter, gear_picker, main_window
│                                       # + tests/ui/ (gui-marked widget + smoke tests), tests/dev_tools/scrape_pipeline/, tests/fixtures/ (HTML)
├── docs/                               # ARCHITECTURE.md + analysis/ + desktop-gaps-fix-spec.md + superpowers specs/plans
├── requirements.txt                    # mitmproxy
├── requirements-desktop.txt            # PySide6, requests, bs4, lxml, pytest-qt, playwright, cloakbrowser, Pillow
├── pytest.ini                          # -m "not integration and not gui" -p no:pytestqt
├── conftest.py                         # sys.path + _NoopQtBot stub + gui marker
└── pyrightconfig.json
```

## Rewrite pipeline (`src/tbh_reward_hook.py:response`)

1. `only_post` → method must be POST
2. `url_contains` → URL must contain any marker (default `/backend-function/base/v1`)
3. `require_boxes_marker` → body must contain literal `"boxes"`
4. Regex: find `"itemId":<n>` then `"rewardItemId":<m>` after it. Replace `rewardItemId` with cycled value from `replacement_reward_item_ids` (modulo list length).
5. Priority: **specific rules first, then range**. Specific rules match `itemId` exactly; range matches `[match_min, match_max]`.
6. **Strategy B (optional, `rewrite_pending_tx`)**: after a `rewardItemId` rewrite, `PendingTxRewriter` rewrites matching `pendingTx.gid` + `.tid` in DynamoDB-format `SteamItemInfo`/`mine` responses so pending-tx item ids stay consistent with the new rewardItemId. Without it, the mismatch trips `TamperedItemIdDetected`. Off by default.

Filter + rule shape defined in `ProxyConfig` / `QueueRule` / `RangeRule` (`src/tbh_proxy_config.py`).

## Hot reload & safety

- **mtime-based**: addon checks `config.json` mtime on every response. Save from GUI → mtime bump → next request picks up new rules. No restart needed.
- **Corrupt config**: keeps last valid config, logs `kept previous config (config.json invalid)`. Bad edit never breaks interception.
- **Atomic save (desktop)**: `validate → backup .json.bak → write .tmp → rename → re-validate → restore from .bak if invalid`.
- **`listen_port` requires restart**: mitmproxy binds at startup. Start button guards desync: if toolbar port ≠ saved port, prompts "Save config first?" before starting.
- **Manual reload**: `pkill -HUP -f mitmdump` (handler `_on_sighup` sets mtime=0 to force re-check).
- **Self-test**: `python3 src/tbh_reward_hook.py --self-test` uses **built-in fixture** (white/blue box), does NOT read live `config.json`. Update `run_self_test()` if changing rule logic.

## Steam client setup (Linux — critical)

TaskBarHero runs on Linux via Proton + SteamLinuxRuntime_4 + pressure-vessel. The sandbox isolates the network namespace and does **not** forward host proxy env by default.

**Working method: Steam Launch Options** (Steam → TaskBarHero → Properties → Launch Options):

```
HTTP_PROXY=http://127.0.0.1:8877 HTTPS_PROXY=http://127.0.0.1:8877 %command%
```

Proton forwards these into the Wine process; Unity's `HttpClient` reads them. **Native Unity sockets may ignore proxy env regardless.**

**CA trust inside Proton prefix** (Wine/Proton uses its own cert store, NOT Linux system trust):

```bash
WINEPREFIX=~/.local/share/Steam/steamapps/compatdata/3678970/pfx \
  wine certmgr -add -c -root ~/.mitmproxy/mitmproxy-ca-cert.cer
```

Fallback if `certmgr` unavailable: copy `.cer` into `~/.local/share/Steam/steamapps/compatdata/3678970/pfx/drive_c/windows/system32/cert/CA/`.

## `--mode local` (spawn-and-inject) alternative

Bypass the Steam Launch Options dance entirely. mitmproxy's `--mode local:NAME` spawns the named executable with `HTTP_PROXY` / `HTTPS_PROXY` env + mitmproxy CA auto-injected as `SSL_CERT_FILE`, then only intercepts that process's traffic. **Scoped, no system proxy, no Steam Launch Options.**

Enable via `src/config.json`:

```json
{
    "mode": "local",
    "local_process_name": "TaskBarHero.exe",
    "listen_port": 8877,
    ...
}
```

…or via CLI (overrides config.json):

```bash
./scripts/run_proxy.sh --mode local --name TaskBarHero.exe
windows\run_proxy.bat --mode local --name TaskBarHero.exe
```

**Windows**: works out of the box (process injection via Win32 APIs, no elevation needed). **Recommended** over Steam Launch Options on Windows — survives game updates that touch `boot.unity3d`.

**Linux caveats**: mitmproxy's local redirector uses a setuid helper (`mitmproxy-linux-redirector`), so mitmdump will prompt for `sudo` at startup. Run as root, or pre-elevate with `sudo -E ./scripts/run_proxy.sh --mode local --name <proc>`. Proton-launched games live inside a `pressure-vessel` container whose top-level process name is usually `TaskBarHero.exe` (Windows binary name) — verify with `pgrep -af TaskBarHero` while the game is running before relying on the match.

## Gotchas

### pytest-qt teardown hangs on Plasma Wayland
- Symptom: kills DE under `QT_QPA_PLATFORM=offscreen`.
- Default in `pytest.ini`: `-p no:pytestqt`, `addopts = -m "not integration and not gui"`.
- GUI tests marked `@pytest.mark.gui`. Stub `qtbot` fixture (`_NoopQtBot` in `conftest.py`) lets collection succeed without spinning up `QApplication`.
- Always export `QT_QPA_PLATFORM=offscreen` on CachyOS (Xe GPU driver bug — applies even outside pytest).

### HarfBuzz SIGSEGV from non-Qt threads
- Symptom: `QPlainTextEdit.appendPlainText` called from `threading.Thread` → crash in `QTextEngine::shapeTextWithHarfbuzzNG` (PySide6 6.11 / Qt 6.11, ellipsis glyph).
- Fix: `_ThreadLogBridge` QObject lives on GUI thread; worker threads call `bridge.log_line.emit(...)`. Qt's `AutoConnection` queues the signal across threads → slot runs on GUI thread.
- `ProxyRunner` and `GearScraperRunner` already follow this pattern. New background threads MUST go through a bridge, never call GUI methods directly.

### Process group signaling (proxy kill)
- `ProxyRunner.start()` uses `start_new_session=True` so child forms its own process group.
- `stop()` calls `os.killpg(pgid, SIGTERM)` then escalates to `SIGKILL` after 3s. Without the group kill, `mitmdump` grandchild is orphaned holding the listen port.
- `run_proxy.py` installs SIGTERM/SIGINT handlers that call `_terminate(proc)` (whole group) before re-raising — otherwise default SIGTERM aborts immediately and skips the `finally` block.

### CloakBrowser fallback
- Gear scrape uses CloakBrowser (stealth Chromium, 58 C++ patches, ~200 MB binary auto-downloaded, Ed25519-verified).
- If `cloakbrowser` not installed → falls back to stock Playwright (`playwright install chromium` required).
- Gear scrape covers Legendary+ only (Legendary / Immortal / Arcana / Beyond / Celestial / Divine / Cosmic × Weapon / Off-hand / Armor / Accessory). Lower grades not scraped.

### Pickers are dialog shims
`GearPicker` / `BoxPicker` / `BoxLootPicker` are thin `QDialog`s wrapping extracted `*View` classes. Edit the `*View` for behavior; dialog is just a modal shell.

### CA private key
Never commit `~/.mitmproxy/mitmproxy-ca*.pem` or `.p12` files. Anyone with the key can sign any HTTPS cert for any client that trusts the CA.

## Acknowledgements

Built on the **Persistent Reward Item Generator** technique researched and shared by the UnknownCheats community: [original thread](https://www.unknowncheats.me/forum/other-games/758547-tbh-persistent-reward-item-generator.html).