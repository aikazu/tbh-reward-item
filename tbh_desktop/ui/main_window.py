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
)

from tbh_desktop import config_io, scraper
from tbh_desktop.paths import BOX_LOOT_CACHE_DIR, CONFIG_PATH, GEAR_CACHE_DIR
from tbh_desktop.proxy_runner import ProxyRunner
from tbh_desktop.ui.box_loot_picker import BoxLootPicker
from tbh_desktop.ui.config_editor import ConfigEditor
from tbh_desktop.ui.gear_picker import GearPicker
from tbh_desktop.ui.log_panel import LogPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TBH Reward Proxy")
        self.resize(1000, 700)

        self.runner = ProxyRunner()
        self.runner.log_line.connect(self._on_log)
        self.runner.running.connect(self._on_running)

        self.editor = ConfigEditor()
        self.log_panel = LogPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.log_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
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

    def _build_toolbar(self) -> None:
        bar = self.addToolBar("main")
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_refresh_gear = QPushButton("Scrape gear")
        self.btn_save = QPushButton("Save config")
        self.port_edit = QLineEdit()
        self.port_edit.setFixedWidth(70)
        self.port_edit.setPlaceholderText("port")
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: red;")

        for w in (
            self.btn_start,
            self.btn_stop,
            self.btn_refresh_gear,
            self.btn_save,
            self.port_edit,
            self.status_dot,
        ):
            bar.addWidget(w)

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

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About TBH Reward Proxy",
            "TBH Reward Proxy desktop GUI.\nEdit config, pick reward IDs, run/stop proxy.",
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
        self.status_dot.setStyleSheet(
            "color: green;" if running else "color: red;"
        )

    def _refresh_gear(self) -> None:
        try:
            results = scraper.refresh_gear_full(GEAR_CACHE_DIR)
            total = sum(len(v) for v in results.values())
            self._on_log(
                f"Gear scraped: {total} items across {len(results)} category-grade files."
            )
        except Exception as exc:
            self._on_log(f"Gear scrape FAILED: {exc}")

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
