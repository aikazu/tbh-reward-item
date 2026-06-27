"""Main window: 4-zone composition (rail + editor + item browser + log dock)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolBar,
    QWidget,
)

from tbh_desktop import config_io, scraper
from tbh_desktop.gear_scraper_runner import GearScraperRunner
from tbh_desktop.paths import BOX_LOOT_CACHE_DIR, CONFIG_PATH, DROPS_INDEX_CACHE, GEAR_CACHE_DIR
from tbh_desktop.proxy_runner import ProxyRunner
from tbh_desktop.scraper import BOX_SLUG_CACHE, read_box_cache
from tbh_desktop.ui.box_loot_picker import BoxLootPicker
from tbh_desktop.ui.box_picker import BoxPicker
from tbh_desktop.ui.config_editor import ConfigEditor
from tbh_desktop.ui.gear_picker import GearPicker
from tbh_desktop.ui.item_browser import ItemBrowser
from tbh_desktop.ui.left_rail import Action, LeftRail
from tbh_desktop.ui.log_panel import LogPanel
from tbh_desktop.ui.theme import status_dot_style


class _ThreadLogBridge(QObject):
    """Tiny QObject that lets non-Qt threads push log lines into the GUI
    log panel via a Qt signal.

    Why this exists: ``ProxyRunner`` and ``GearScraperRunner`` already
    emit ``log_line`` from their worker threads. ``Qt.AutoConnection``
    routes those across threads correctly (the receiver lives on the GUI
    thread, so the slot runs there).

    But the inline ``threading.Thread`` spawned by
    ``MainWindow._refresh_gear`` for the drops index fetch was calling
    ``self._on_log(...)`` *directly* — that bypasses the queue and
    invokes ``QPlainTextEdit.appendPlainText`` from a non-GUI thread.
    Layout operations on a widget from a foreign thread are undefined
    behavior; on PySide6 6.11 / Qt 6.11 with a font containing the
    ellipsis glyph, that crashed inside HarfBuzz
    (``QTextEngine::shapeTextWithHarfbuzzNG``) with a SIGSEGV.

    Fix: spawn a ``_ThreadLogBridge`` (lives on the GUI thread) and have
    the worker thread call ``bridge.log_line.emit(...)``. Qt queues the
    signal across threads so the slot runs on the GUI thread safely.
    """

    log_line = Signal(str)

    def __init__(self) -> None:
        super().__init__()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TBH Reward Proxy")
        self.resize(1100, 750)

        self.runner = ProxyRunner()
        self.runner.log_line.connect(self._on_log)
        self.runner.running.connect(self._on_running)

        self.gear_scraper = GearScraperRunner()
        self.gear_scraper.log_line.connect(self._on_log)
        self.gear_scraper.finished.connect(self._on_gear_scraped)
        self.gear_scraper.error.connect(self._on_gear_error)
        self.gear_scraper.scraping.connect(self._on_gear_scraping)

        self.editor = ConfigEditor()
        self.left_rail = LeftRail()
        self.item_browser = ItemBrowser(
            gear_cache_dir=GEAR_CACHE_DIR,
            drops_index_path=DROPS_INDEX_CACHE,
            box_slug_cache_path=BOX_SLUG_CACHE,
        )
        self.log_panel = LogPanel()

        # 4-zone composition: rail | editor | item browser, with log dock below.
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self.left_rail)
        h.addWidget(self.editor, stretch=3)
        h.addWidget(self.item_browser, stretch=2)
        self.setCentralWidget(central)

        self.log_dock = QDockWidget("Log", self)
        self.log_dock.setWidget(self.log_panel)
        self.log_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        self._build_toolbar()
        self._build_menu()
        self.setStatusBar(QStatusBar())

        # Initialize button/dot state to "not running".
        self._on_running(False)

        self._reload_config()

        # Wire editor pick buttons — Range Replacement
        # (Specific-rule pick buttons live on each RuleCard inside the
        # RuleListView; route them through _on_rule_card_pick.)

        # Wire LeftRail actions to existing slots.
        self.left_rail.action.connect(self._on_rail_action)

        # Wire ItemBrowser picks to route by active target.
        self.item_browser.item_picked.connect(self._on_item_browser_pick)
        self.item_browser.items_picked.connect(self._on_item_browser_picks)
        # Route rule selection from editor to ItemBrowser filter context.
        self.editor.rule_list().rule_selected.connect(self._on_rule_selected)

    # ------------------------------------------------------------------ build
    def _build_toolbar(self) -> None:
        bar = self.addToolBar("main")
        bar.setObjectName("main_toolbar")
        bar.setMovable(False)
        bar.setFloatable(False)

        # ---- Primary zone: Start / Stop --------------------------------
        self.btn_start = QPushButton("▶  START")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setProperty("toolbar_zone", "primary")
        self.btn_start.setToolTip("Start the mitmproxy subprocess (Ctrl+S to save first)")

        self.btn_stop = QPushButton("■  STOP")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setProperty("toolbar_zone", "primary")
        self.btn_stop.setToolTip("Terminate the running proxy subprocess")

        # ---- Secondary zone: Scrape / Check / Save / Reset --------------
        self.btn_refresh_gear = QPushButton("SCRAPE")
        self.btn_refresh_gear.setProperty("toolbar_zone", "secondary")
        self.btn_refresh_gear.setToolTip(
            "Refresh gear cache (28 category-grade files via headless browser) "
            "AND drops index (~190 items: materials, stage boxes). "
            "Slow — first launch starts the browser. Subsequent scrapes are "
            "fast since cached files are reused."
        )
        self.btn_check_data = QPushButton("CHECK")
        self.btn_check_data.setProperty("toolbar_zone", "secondary")
        self.btn_check_data.setToolTip(
            "Show counts and freshness for gear cache + drops index. "
            "Lets you see if a re-scrape is needed."
        )

        self.btn_save = QPushButton("SAVE")
        self.btn_save.setProperty("toolbar_zone", "secondary")
        self.btn_save.setToolTip("Validate and atomically write config.json")

        self.btn_reset = QPushButton("RESET")
        self.btn_reset.setProperty("toolbar_zone", "secondary")
        self.btn_reset.setToolTip(
            "Reset config.json back to the default template (config.default.json). "
            "Your current rules will be lost."
        )

        # ---- Ghost zone: Copy Steam -------------------------------------
        self.btn_copy_steam = QPushButton("COPY STEAM")
        self.btn_copy_steam.setObjectName("btn_copy_steam")
        self.btn_copy_steam.setProperty("toolbar_zone", "ghost")
        self.btn_copy_steam.setToolTip(
            "Copy the Steam launch option string for the current proxy port "
            "(HTTP_PROXY + HTTPS_PROXY + %command%) to the clipboard.\n"
            "Paste into Steam → TaskBarHero → Properties → Launch Options."
        )

        # ---- Status: mono port field + pulsing dot ----------------------
        mono = QFont("JetBrains Mono", 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setFamily("JetBrains Mono")

        port_label = QLabel("PORT")
        port_label.setStyleSheet("color: #a6adc8; font-size: 10px; letter-spacing: 1px;")

        self.port_edit = QLineEdit()
        self.port_edit.setObjectName("port_edit_toolbar")
        self.port_edit.setFixedWidth(80)
        self.port_edit.setFont(mono)
        self.port_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.port_edit.setPlaceholderText("8877")
        self.port_edit.setToolTip("Proxy listen port (requires restart after change)")

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("status_dot_pulse")
        self.status_dot.setToolTip("Proxy status: stopped")
        self.status_dot.setStyleSheet(status_dot_style(False))

        # ---- Compose zones with separators -----------------------------
        bar.addWidget(self.btn_start)
        bar.addWidget(self.btn_stop)
        bar.addSeparator()
        bar.addWidget(self.btn_refresh_gear)
        bar.addWidget(self.btn_check_data)
        bar.addWidget(self.btn_save)
        bar.addWidget(self.btn_reset)
        bar.addSeparator()
        bar.addWidget(self.btn_copy_steam)
        bar.addSeparator()
        bar.addWidget(port_label)
        bar.addWidget(self.port_edit)
        bar.addSeparator()
        bar.addWidget(self.status_dot)

        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self.runner.stop)
        self.btn_refresh_gear.clicked.connect(self._refresh_gear)
        self.btn_check_data.clicked.connect(self._check_data)
        self.btn_save.clicked.connect(self._save)
        self.btn_reset.clicked.connect(self._reset_config)
        self.btn_copy_steam.clicked.connect(self._copy_steam_launch_option)
        # Tooltip preview stays in sync with port edits (so user sees the
        # exact string that will be copied before clicking).
        self.port_edit.textChanged.connect(self._refresh_steam_copy_tooltip)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Save config", self._save)
        file_menu.addAction("Reset config to default", self._reset_config)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._about)

    # ------------------------------------------------------------------ misc
    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About TBH Reward Proxy",
            "TBH Reward Proxy desktop GUI.\n"
            "Edit config, pick reward IDs, run/stop proxy.\n\n"
            "Scraping powered by CloakBrowser (stealth Chromium).",
        )

    def _confirm(self, title: str, message: str, *, default_yes: bool = False) -> bool:
        """Show a Yes/No dialog. Returns True if user clicked Yes."""
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        default = (
            QMessageBox.StandardButton.Yes if default_yes else QMessageBox.StandardButton.No
        )
        reply = QMessageBox.question(self, title, message, buttons, default)
        return reply == QMessageBox.StandardButton.Yes

    def _reload_config(self) -> None:
        data = config_io.load_config(CONFIG_PATH)
        self.editor.load(data)
        self.port_edit.setText(str(data.get("listen_port", 8877)))
        if not data and CONFIG_PATH.exists():
            QMessageBox.warning(
                self,
                "Config invalid",
                f"Could not load {CONFIG_PATH.name}. Using empty defaults. "
                "Fix the file and Save to reload.",
            )

    def _on_log(self, line: str) -> None:
        self.log_panel.append_log(line)

    def _on_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.status_dot.setStyleSheet(status_dot_style(running))
        self.status_dot.setToolTip(
            "Proxy status: running" if running else "Proxy status: stopped"
        )

    def _refresh_gear(self) -> None:
        """Single 'Scrape Data' button — runs gear scrape, then drops index.

        Drops index fetch is fast (~1 request) so we run it inline after
        kicking off the gear scrape. The gear scraper runs in its own
        thread; the drops fetch happens in a separate thread to keep the UI
        responsive.
        """
        if self.gear_scraper.is_running():
            self._on_log("Scrape already running…")
            return
        # Mark UI as scraping.
        self._on_gear_scraping(True)
        # Kick off gear scrape in its own thread.
        self.gear_scraper.start()
        # Run drops index fetch in parallel — it doesn't depend on gear data.
        # The drops thread must NOT call self._on_log directly (would touch
        # the log widget from a non-GUI thread → SIGSEGV in HarfBuzz text
        # shaping). Use a small QObject bridge that lives on the GUI thread
        # and emits across-thread so the slot runs safely on the GUI thread.
        import threading
        bridge = _ThreadLogBridge()
        bridge.log_line.connect(self._on_log)
        # Keep a ref so it isn't GC'd mid-scrape.
        self._drops_log_bridge = bridge
        def _fetch_drops_async() -> None:
            try:
                from tbh_desktop.paths import DROPS_INDEX_CACHE, ITEM_DIR
                from tbh_desktop.scraper import fetch_drops_index, refresh_material_details
                items = fetch_drops_index(DROPS_INDEX_CACHE)
                bridge.log_line.emit(
                    f"Drops index: {len(items)} items cached (materials + stage boxes)"
                )
                # After the drops index is up to date, fetch each
                # material's wiki detail (effect + stat rolls + crafting)
                # and inline the info into the per-(family,rarity) files
                # under ITEM_DIR. Best-effort — partial enrichment is fine
                # (e.g. wiki may 429 us), and any failure is logged.
                try:
                    enriched = refresh_material_details(ITEM_DIR, items)
                    bridge.log_line.emit(
                        f"Material details: enriched {enriched} items (effect + stats)"
                    )
                except Exception as exc:
                    bridge.log_line.emit(f"Material details enrichment failed: {exc}")
            except Exception as exc:
                bridge.log_line.emit(f"Drops index fetch failed: {exc}")
        threading.Thread(target=_fetch_drops_async, daemon=True).start()

    def _on_gear_scraping(self, scraping: bool) -> None:
        self.btn_refresh_gear.setEnabled(not scraping)
        if scraping:
            self._on_log("Scraping gear… (this may take a minute)")
            self.btn_refresh_gear.setText("Scraping…")
        else:
            self.btn_refresh_gear.setText("Scrape Data")

    def _on_gear_scraped(self, total: int, num_files: int) -> None:
        self._on_log(f"Gear scraped: {total} items across {num_files} category-grade files.")

    def _on_gear_error(self, msg: str) -> None:
        self._on_log(f"Gear scrape FAILED: {msg}")

    def _check_data(self) -> None:
        """Show what data is cached: counts + last fetched + disk usage."""
        import datetime as _dt
        import json

        from tbh_desktop.paths import (
            BOX_DROP_MAP_CACHE,
            DROPS_INDEX_CACHE,
            GEAR_CACHE_DIR,
        )
        from tbh_desktop.scraper import read_drops_index

        # Drops index.
        drops = read_drops_index(DROPS_INDEX_CACHE)
        drops_count = len(drops)
        drops_size = DROPS_INDEX_CACHE.stat().st_size if DROPS_INDEX_CACHE.exists() else 0
        drops_mtime = (
            DROPS_INDEX_CACHE.stat().st_mtime if DROPS_INDEX_CACHE.exists() else 0
        )

        # Gear cache: 28 files, one per (category, grade), at gear/{cat}/{rarity}.json.
        gear_files = (
            sorted(GEAR_CACHE_DIR.glob("*/*.json"))
            if GEAR_CACHE_DIR.exists() else []
        )
        gear_total = 0
        gear_latest_mtime = 0.0
        for p in gear_files:
            try:
                items = json.loads(p.read_text(encoding="utf-8"))
                gear_total += len(items) if isinstance(items, list) else 0
                if p.stat().st_mtime > gear_latest_mtime:
                    gear_latest_mtime = p.stat().st_mtime
            except (OSError, json.JSONDecodeError):
                pass
        gear_total_size = sum(p.stat().st_size for p in gear_files)

        # Box drop map.
        box_drops_count = 0
        if BOX_DROP_MAP_CACHE.exists():
            try:
                box_drops = json.loads(BOX_DROP_MAP_CACHE.read_text(encoding="utf-8"))
                box_drops_count = len(box_drops) if isinstance(box_drops, dict) else 0
            except (OSError, json.JSONDecodeError):
                pass

        def _fmt(ts: float) -> str:
            if not ts:
                return "(never)"
            return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

        def _fmt_size(n: int) -> str:
            if n < 1024:
                return f"{n} B"
            if n < 1024 * 1024:
                return f"{n / 1024:.1f} KB"
            return f"{n / (1024 * 1024):.1f} MB"

        msg_lines = [
            "Data cache status:",
            "",
            "Drops index",
            f"  · items: {drops_count}",
            f"  · last fetched: {_fmt(drops_mtime)}",
            f"  · size: {_fmt_size(drops_size)}",
            f"  · file: {DROPS_INDEX_CACHE.name}",
            "",
            "Gear cache",
            f"  · files: {len(gear_files)}",
            f"  · total items: {gear_total}",
            f"  · last updated: {_fmt(gear_latest_mtime)}",
            f"  · total size: {_fmt_size(gear_total_size)}",
            "",
            "Box drop map",
            f"  · items tracked: {box_drops_count}",
            "",
        ]
        if drops_count == 0 or not gear_files:
            msg_lines.append("⚠  No cached data. Click 'Scrape Data' to populate.")
        else:
            msg_lines.append("✓ Data is present. Re-scrape to refresh.")
        QMessageBox.information(self, "Data Status", "\n".join(msg_lines))

    def _start(self) -> None:
        saved_port = config_io.load_config(CONFIG_PATH).get("listen_port", 8877)
        if self._parse_port() != saved_port:
            if not self._confirm("Unsaved port", "Port changed. Save config first?"):
                return
            self._save()
        self.runner.start()

    def _save(self) -> None:
        data = self.editor.dump()
        data["listen_port"] = self._parse_port()
        result = config_io.save_config(CONFIG_PATH, data)
        if result.ok:
            self._on_log("Config saved.")
        else:
            self._on_log(f"Config save FAILED: {result.error}")

    def _reset_config(self) -> None:
        """Reset config.json to default template, reload editor + port field."""
        if self.runner.is_running():
            if not self._confirm(
                "Reset config?",
                "Proxy is running. Stop it and reset config to default?",
            ):
                return
            self.runner.stop()
        elif not self._confirm(
            "Reset config?",
            "Reset config.json back to the default template?\n"
            "Your current rules will be lost.",
        ):
            return
        if config_io.reset_config(CONFIG_PATH):
            self._reload_config()
            self._on_log("Config reset to default.")
        else:
            self._on_log("Config reset FAILED: default template not found.")

    def _parse_port(self) -> int:
        try:
            return int(self.port_edit.text().strip() or 8877)
        except ValueError:
            return 8877

    # ------------------------------------------------------------------ steam
    def _steam_launch_option(self, port: int | None = None) -> str:
        """Build the Steam launch option string for the given (or current) port.

        Mirrors the README recipe: Proton forwards these env vars into the
        Wine process, where Unity's ``HttpClient`` picks them up.
        """
        if port is None:
            port = self._parse_port()
        return (
            f"HTTP_PROXY=http://127.0.0.1:{port} "
            f"HTTPS_PROXY=http://127.0.0.1:{port} %command%"
        )

    def _refresh_steam_copy_tooltip(self) -> None:
        """Keep the Copy button tooltip in sync with the current port field.

        Lets the user hover the button to preview exactly what would be copied
        before clicking. Plain string concat, no Qt-specific concerns.
        """
        self.btn_copy_steam.setToolTip(
            "Copy this Steam launch option to the clipboard:\n\n"
            f"    {self._steam_launch_option()}\n\n"
            "Paste into Steam → TaskBarHero → Properties → Launch Options."
        )

    def _copy_steam_launch_option(self) -> None:
        """Copy the Steam launch option for the current port to clipboard.

        Falls back to port 8877 if the field is empty/invalid (matches
        ``_parse_port`` semantics). Surfaces success in both the status bar
        (auto-clears) and the log panel (durable) — clipboard writes are
        silent in Qt, so we must tell the user explicitly.
        """
        text = self._steam_launch_option()
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            QMessageBox.warning(
                self,
                "Clipboard unavailable",
                "Could not access the system clipboard. Copy the string "
                "manually from the README.",
            )
            return
        clipboard.setText(text)
        self._on_log(f"Steam launch option copied: {text}")
        self.statusBar().showMessage(
            "Steam launch option copied to clipboard", 3000
        )

    # ------------------------------------------------------------------ pickers
    def _pick_box_id_for_rule(self) -> None:
        """Open BoxPicker, set the selected rule's Item ID + store its level."""
        dlg = BoxPicker(BOX_SLUG_CACHE, self)
        if not dlg.exec():
            return
        box_id = dlg.selected_box_id()
        if box_id is None:
            return
        level = dlg.selected_box_level()
        self.editor.set_selected_rule_item_id(box_id, level)
        if level is not None:
            self._on_log(f"Box {box_id} (Lv{level}) set as item_id.")
        else:
            self._on_log(f"Box {box_id} set as item_id.")

    def _get_box_loot(self, box_id: int) -> list[dict]:
        """Fetch box loot (network or cache) and log if empty."""
        loot = scraper.refresh_box_loot(BOX_LOOT_CACHE_DIR, box_id)
        if not loot:
            self._on_log(f"No loot for box {box_id}. Check box_id / wiki items page.")
        return loot

    def _pick_box_loot_for_rule(self) -> None:
        """Pick reward IDs from THIS BOX's loot (not the full wiki drops index).

        Source of truth is the box's cached loot table (``read_box_cache``) —
        whatever the box actually drops. Each entry is enriched with
        ``family`` + ``rarity`` from the drops index (by id match) so the
        picker can group rows by family + sort by rarity. Items not present
        in the drops index (no family/rarity metadata available) still pass
        through but show as "Other".

        Gear is excluded from the loot picker — gear has its own GearPicker
        dialog.
        """
        from tbh_desktop.paths import DROPS_INDEX_CACHE
        from tbh_desktop.scraper import (
            fetch_drops_index,
            read_box_cache,
        )
        from tbh_desktop.ui.box_loot_picker import BoxLootPicker

        box_id = self.editor.selected_rule_item_id()
        box_loot: list[dict] = []
        box_name: str | None = None
        if box_id is not None:
            box_loot = self._get_box_loot(box_id)
            if box_loot:
                box_name = box_loot[0].get("box_name") or None
        if not box_loot:
            QMessageBox.warning(
                self,
                "Box loot empty",
                f"No loot data for box {box_id}. Pick a box first (Pick box "
                f"ID) and make sure the box page was scraped.",
            )
            return
        # Enrich each loot entry with family + rarity from drops index.
        # Lookup by item id; cache the index once.
        idx_items = fetch_drops_index(DROPS_INDEX_CACHE)
        idx_by_id = {
            it["id"]: it
            for it in idx_items
            if isinstance(it.get("id"), int)
        }
        for entry in box_loot:
            iid = entry.get("id")
            meta = idx_by_id.get(iid) if isinstance(iid, int) else None
            if meta is not None:
                entry.setdefault("family", meta.get("family", ""))
                entry.setdefault("rarity", meta.get("rarity", "COMMON"))
            else:
                entry.setdefault("family", "")
                entry.setdefault("rarity", "COMMON")
        dlg = BoxLootPicker(
            self,
            items=box_loot,
            scope_box_name=box_name,
            mode="box_loot",
        )
        if dlg.exec():
            self.editor.add_ids_to_selected_rule(dlg.selected_ids())

    def _pick_gear_for_rule(self) -> None:
        """Pick gear scoped to the selected rule's box (name + level filter)."""
        if not GEAR_CACHE_DIR.exists() or not any(GEAR_CACHE_DIR.glob("*/*.json")):
            self._on_log("No gear cache. Click 'Scrape gear' first.")
            return
        box_id = self.editor.selected_rule_item_id()
        level_hint = self.editor.selected_rule_level()
        box_loot: list[dict] = []
        if box_id is not None:
            # Use cached loot if available to avoid network on every gear pick.
            box_loot = read_box_cache(BOX_LOOT_CACHE_DIR, box_id)
            if not box_loot:
                # Try fetching once; if still empty, proceed without box filter.
                box_loot = self._get_box_loot(box_id)
        dlg = GearPicker(
            GEAR_CACHE_DIR,
            self,
            box_loot=box_loot or None,
            level_hint=level_hint,
        )
        if dlg.exec():
            self.editor.add_ids_to_selected_rule(dlg.selected_ids())

    def _pick_gear_for_range(self) -> None:
        """Pick gear for range replacement (no box scope — shows all gear)."""
        if not GEAR_CACHE_DIR.exists() or not any(GEAR_CACHE_DIR.glob("*/*.json")):
            self._on_log("No gear cache. Click 'Scrape gear' first.")
            return
        dlg = GearPicker(GEAR_CACHE_DIR, self)
        if dlg.exec():
            self.editor.add_ids_to_range(dlg.selected_ids())

    def _pick_box_loot_for_range(self) -> None:
        """Pick reward IDs from the wiki drops index (materials, stage boxes,
        consumables — everything except gear). Populates directly from the
        cached drops index; no need to pick a box first.
        """
        from tbh_desktop.paths import DROPS_INDEX_CACHE
        from tbh_desktop.scraper import fetch_drops_index
        from tbh_desktop.ui.box_loot_picker import BoxLootPicker

        items = fetch_drops_index(DROPS_INDEX_CACHE)
        if not items:
            QMessageBox.warning(
                self,
                "Drops index empty",
                "Could not load the drops index. Connect to the internet and "
                "run the proxy once, or run the script: "
                "`python -m tbh_desktop.scraper fetch_drops_index`.",
            )
            return
        dlg = BoxLootPicker(self, items=items)
        if dlg.exec():
            self.editor.add_ids_to_range(dlg.selected_ids())

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.gear_scraper.is_running():
            if not self._confirm(
                "Scrape in progress?",
                "Gear scrape is running. Exit anyway?",
            ):
                event.ignore()
                return
            # Stop the scrape immediately so it doesn't keep running after the
            # window closes. _cleanup() also calls stop() defensively in case
            # this path is bypassed (e.g. SIGINT → app.quit()).
            self.gear_scraper.stop()
        if self.runner.is_running():
            if not self._confirm(
                "Stop proxy?",
                "Proxy is running. Stop and exit?",
            ):
                event.ignore()
                return
            self.runner.stop()
        super().closeEvent(event)

    def _cleanup(self) -> None:
        """Force-stop all background activities without prompts.

        Called from ``aboutToQuit`` (SIGINT / app.quit()) — must be fast and
        non-interactive so the process exits cleanly.
        """
        self.gear_scraper.stop()
        self.runner.stop()

    # ------------------------------------------------------------------ rail / target routing
    def _on_rail_action(self, action: Action) -> None:
        """Dispatch a LeftRail button click to the existing slot."""
        if action is Action.START:
            self._start()
        elif action is Action.STOP:
            self.runner.stop()
        elif action is Action.SAVE:
            self._save()
        elif action is Action.RESET:
            self._reset_config()
        elif action is Action.SCRAPE:
            self._refresh_gear()
        elif action is Action.CHECK_DATA:
            self._check_data()
        elif action is Action.COPY_STEAM:
            self._copy_steam_launch_option()
        elif action is Action.TOGGLE_LOG:
            self.log_dock.toggleViewAction().trigger()
        elif action is Action.TOGGLE_ITEMS:
            self.item_browser.setVisible(not self.item_browser.isVisible())

    def _on_rule_selected(self, target) -> None:
        """Switch the ItemBrowser filter context based on the active rule row."""
        from tbh_desktop.ui.active_target import RuleTarget
        from tbh_desktop.ui.item_browser import FilterContext, FilterScope
        if isinstance(target, RuleTarget):
            scope = FilterScope.GEAR_FOR_BOX if target.box_id else FilterScope.GEAR_ALL
            self.item_browser.filter_for_context(
                FilterContext(
                    box_id=target.box_id,
                    box_name=None,
                    level=target.level,
                    scope=scope,
                )
            )
        else:
            self.item_browser.filter_for_context(None)

    def _on_item_browser_pick(self, item_id: int) -> None:
        """Route a single-item pick to the active target's store."""
        try:
            self.editor.add_ids_to_active_target([int(item_id)])
        except ValueError:
            # No active target — ignore.
            pass

    def _on_item_browser_picks(self, item_ids: list) -> None:
        """Route a multi-item pick."""
        ids = [int(i) for i in item_ids]
        try:
            self.editor.add_ids_to_active_target(ids)
        except ValueError:
            pass
