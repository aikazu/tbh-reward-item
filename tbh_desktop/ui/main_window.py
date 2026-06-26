"""Main window: toolbar, splitter (editor + log), proxy runner wiring."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
)

from tbh_desktop import config_io, scraper
from tbh_desktop.gear_scraper_runner import GearScraperRunner
from tbh_desktop.paths import BOX_LOOT_CACHE_DIR, CONFIG_PATH, GEAR_CACHE_DIR
from tbh_desktop.proxy_runner import ProxyRunner
from tbh_desktop.scraper import BOX_SLUG_CACHE, read_box_cache
from tbh_desktop.ui.box_loot_picker import BoxLootPicker
from tbh_desktop.ui.box_picker import BoxPicker
from tbh_desktop.ui.config_editor import ConfigEditor
from tbh_desktop.ui.gear_picker import GearPicker
from tbh_desktop.ui.log_panel import LogPanel
from tbh_desktop.ui.theme import status_dot_style


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
        self.log_panel = LogPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.log_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setHandleWidth(2)
        self.setCentralWidget(splitter)

        self._build_toolbar()
        self._build_menu()
        self.setStatusBar(QStatusBar())

        # Initialize button/dot state to "not running".
        self._on_running(False)

        self._reload_config()

        # Wire editor pick buttons — Specific Queue Rules
        self.editor.btn_pick_box_id.clicked.connect(self._pick_box_id_for_rule)
        self.editor.btn_pick_box.clicked.connect(self._pick_box_loot_for_rule)
        self.editor.btn_pick_gear_rule.clicked.connect(self._pick_gear_for_rule)

        # Wire editor pick buttons — Range Replacement
        self.editor.btn_pick_gear_range.clicked.connect(self._pick_gear_for_range)
        self.editor.btn_pick_loot_range.clicked.connect(self._pick_box_loot_for_range)

    # ------------------------------------------------------------------ build
    def _build_toolbar(self) -> None:
        bar = self.addToolBar("main")
        bar.setMovable(False)
        bar.setFloatable(False)

        self.btn_start = QPushButton("▶  Start")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setToolTip("Start the mitmproxy subprocess (Ctrl+S to save first)")

        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setToolTip("Terminate the running proxy subprocess")

        self.btn_refresh_gear = QPushButton("Scrape gear")
        self.btn_refresh_gear.setToolTip(
            "Scrape full Legendary+ gear from the wiki using CloakBrowser.\n"
            "Slow — launches a headless browser. Cache files are kept locally."
        )

        self.btn_save = QPushButton("Save config")
        self.btn_save.setToolTip("Validate and atomically write config.json")

        self.btn_reset = QPushButton("Reset config")
        self.btn_reset.setToolTip(
            "Reset config.json back to the default template (config.default.json). "
            "Your current rules will be lost."
        )

        self.port_edit = QLineEdit()
        self.port_edit.setFixedWidth(70)
        self.port_edit.setPlaceholderText("port")
        self.port_edit.setToolTip("Proxy listen port (requires restart after change)")

        self.status_dot = QLabel("●")
        self.status_dot.setToolTip("Proxy status: stopped")
        self.status_dot.setStyleSheet(status_dot_style(False))

        # Group: proxy controls
        bar.addWidget(self.btn_start)
        bar.addWidget(self.btn_stop)
        bar.addSeparator()
        # Group: config / scrape
        bar.addWidget(self.btn_refresh_gear)
        bar.addWidget(self.btn_save)
        bar.addWidget(self.btn_reset)
        bar.addSeparator()
        # Group: port + status
        bar.addWidget(QLabel("Port:"))
        bar.addWidget(self.port_edit)
        bar.addSeparator()
        bar.addWidget(self.status_dot)

        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self.runner.stop)
        self.btn_refresh_gear.clicked.connect(self._refresh_gear)
        self.btn_save.clicked.connect(self._save)
        self.btn_reset.clicked.connect(self._reset_config)

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
        if self.gear_scraper.is_running():
            self._on_log("Scrape already running…")
            return
        self.gear_scraper.start()

    def _on_gear_scraping(self, scraping: bool) -> None:
        self.btn_refresh_gear.setEnabled(not scraping)
        if scraping:
            self._on_log("Scraping gear… (this may take a minute)")
            self.btn_refresh_gear.setText("Scraping…")
        else:
            self.btn_refresh_gear.setText("Scrape gear")

    def _on_gear_scraped(self, total: int, num_files: int) -> None:
        self._on_log(f"Gear scraped: {total} items across {num_files} category-grade files.")

    def _on_gear_error(self, msg: str) -> None:
        self._on_log(f"Gear scrape FAILED: {msg}")

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
        """Pick loot (item/material) from the rule's box into Replacement IDs."""
        box_id = self.editor.selected_rule_item_id()
        if box_id is None:
            self._on_log("Select a rule row with a valid item_id first.")
            return
        loot = self._get_box_loot(box_id)
        if not loot:
            return
        dlg = BoxLootPicker(box_id, loot, self)
        if dlg.exec():
            self.editor.add_ids_to_selected_rule(dlg.selected_ids())

    def _pick_gear_for_rule(self) -> None:
        """Pick gear scoped to the selected rule's box (name + level filter)."""
        if not GEAR_CACHE_DIR.exists() or not any(GEAR_CACHE_DIR.glob("gear_*.json")):
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
        if not GEAR_CACHE_DIR.exists() or not any(GEAR_CACHE_DIR.glob("gear_*.json")):
            self._on_log("No gear cache. Click 'Scrape gear' first.")
            return
        dlg = GearPicker(GEAR_CACHE_DIR, self)
        if dlg.exec():
            self.editor.add_ids_to_range(dlg.selected_ids())

    def _pick_box_loot_for_range(self) -> None:
        """Pick box → loot (item/material) into range replacement IDs."""
        dlg = BoxPicker(BOX_SLUG_CACHE, self)
        if not dlg.exec():
            return
        box_id = dlg.selected_box_id()
        if box_id is None:
            return
        loot = self._get_box_loot(box_id)
        if not loot:
            return
        dlg2 = BoxLootPicker(box_id, loot, self)
        if dlg2.exec():
            self.editor.add_ids_to_range(dlg2.selected_ids())

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
