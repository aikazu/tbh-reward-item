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
from tbh_desktop.ui.box_loot_picker import BoxLootPicker
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

        # Wire editor pick buttons
        self.editor.btn_pick_box.clicked.connect(self._pick_box_loot)
        self.editor.btn_pick_gear_rule.clicked.connect(
            lambda: self._pick_gear(self.editor.add_ids_to_selected_rule)
        )
        self.editor.btn_pick_gear_range.clicked.connect(
            lambda: self._pick_gear(self.editor.add_ids_to_range)
        )

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

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Save config", self._save)
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
            reply = QMessageBox.question(
                self,
                "Unsaved port",
                "Port changed. Save config first?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
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

    def _parse_port(self) -> int:
        try:
            return int(self.port_edit.text().strip() or 8877)
        except ValueError:
            return 8877

    def _pick_gear(self, add_callback) -> None:
        if not GEAR_CACHE_DIR.exists() or not any(GEAR_CACHE_DIR.glob("gear_*.json")):
            self._on_log("No gear cache. Click 'Scrape gear' first.")
            return
        dlg = GearPicker(GEAR_CACHE_DIR, self)
        if dlg.exec():
            add_callback(dlg.selected_ids())

    def _pick_box_loot(self) -> None:
        box_id = self.editor.selected_rule_item_id()
        if box_id is None:
            self._on_log("Select a rule row with a valid item_id first.")
            return
        loot = scraper.refresh_box_loot(BOX_LOOT_CACHE_DIR, box_id)
        if not loot:
            self._on_log(f"No loot for box {box_id}. Check box_id / wiki items page.")
            return
        dlg = BoxLootPicker(box_id, loot, self)
        if dlg.exec():
            self.editor.add_ids_to_selected_rule(dlg.selected_ids())

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.gear_scraper.is_running():
            reply = QMessageBox.question(
                self,
                "Scrape in progress?",
                "Gear scrape is running. Exit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.runner.is_running():
            reply = QMessageBox.question(
                self,
                "Stop proxy?",
                "Proxy is running. Stop and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.runner.stop()
        super().closeEvent(event)
