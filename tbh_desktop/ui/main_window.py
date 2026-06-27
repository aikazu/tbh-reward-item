"""Main window — redesigned 2-pane shell with labeled toolbar zones.

The previous layout used a flat 3-zone composition (rules | catalog |
log) where the right pane was a permanent 6-tab in-game item browser.
That catalog is useful *inside picker dialogs* (where users select
reward IDs), but it's the wrong primary surface — the user came here
to edit a rule, not browse the whole game catalog.

The new layout elevates "edit the rule I'm working on" to the right
pane and demotes the catalog to a toggleable dock so it stays
accessible without competing for primary real estate.

Composition
-----------
::

    ┌── File Edit View Catalog Help ────────────────────────────────────┐
    │ PROXY  START STOP   DATA  SCRAPE CHECK   CONFIG  SAVE RESET       │
    │ STEAM  COPY STEAM   PORT  [8877]            ●  STOPPED              │
    ├───────────────────────────────────────────────────────────────────┤
    │ ┌── Rules (40%) ──────────┐ ┌── Detail (60%) ─────────────────┐ │
    │ │ ▣ Normal Box 910901     │ │ ▣ Normal Box    #910901         │ │
    │ │   REPLACES ×1          │ │ ITEM ID  [910901]  LEVEL [1]    │ │
    │ │ ▣ Stage Boss 920901     │ │ [Pick box][Pick loot][Pick gear] │ │
    │ │   REPLACES ×1          │ │ REPLACES WITH (3 cycled):       │ │
    │ │ ▣ Act Boss 930901       │ │  [135001 ×][605041 ×][605051 ×] │ │
    │ │   REPLACES ×1          │ │                                  │ │
    │ │ + Add rule             │ │ ─── RANGE REPLACEMENT ───        │ │
    │ │                        │ │ ☐ enabled  from [500000]→[950000]│ │
    │ │                        │ │ REPLACES WITH: [135001 ×]        │ │
    │ └────────────────────────┘ └──────────────────────────────────┘ │
    │ ┌── Log (collapsible) ───────────────────────────────────────────┐│
    │ │ 12:34:56 Config saved                                          ││
    │ │ 12:34:57 Proxy starting on :8877                               ││
    │ └────────────────────────────────────────────────────────────────┘│
    └───────────────────────────────────────────────────────────────────┘

Toolbar has 4 explicit visual zones — PROXY, DATA, CONFIG, STEAM —
each marked with a tiny uppercase Cinzel label so the user can scan
the toolbar in one glance instead of parsing 9 flat buttons.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop import config_io, scraper
from tbh_desktop.gear_scraper_runner import GearScraperRunner
from tbh_desktop.paths import BOX_LOOT_CACHE_DIR, CONFIG_PATH, DROPS_INDEX_CACHE, GEAR_CACHE_DIR
from tbh_desktop.proxy_runner import ProxyRunner
from tbh_desktop.scraper import BOX_SLUG_CACHE, read_box_cache
from tbh_desktop.ui.box_picker import BoxPicker
from tbh_desktop.ui.config_editor import ConfigEditor
from tbh_desktop.ui.gear_picker import GearPicker
from tbh_desktop.ui.item_browser import ItemBrowser
from tbh_desktop.ui.log_panel import LogPanel
from tbh_desktop.ui.rule_detail_panel import RuleDetailPanel
from tbh_desktop.ui.status_badge import StatusBadge
from tbh_desktop.ui.theme import (
    MOCHA,
    panel_heading_style,
    status_dot_style,
    zone_label_style,
)


class _ThreadLogBridge(QObject):
    """Bridge QObject so non-Qt threads can push log lines via a Qt signal.

    See commit history: a previous version called ``QPlainTextEdit.appendPlainText``
    directly from a worker thread, which crashed inside HarfBuzz text shaping
    on PySide6 6.11 / Qt 6.11 with a SIGSEGV. Routed through a Qt signal now.
    """

    log_line = Signal(str)

    def __init__(self) -> None:
        super().__init__()


def _zone_label(text: str, *, accent: bool = False) -> QLabel:
    """Tiny uppercase Cinzel label used to group toolbar buttons."""
    label = QLabel(text)
    label.setObjectName("zone_label")
    label.setProperty("zone", "accent" if accent else "default")
    label.setStyleSheet(zone_label_style())
    return label


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TBH Reward Proxy")
        self.resize(1400, 850)

        # ---- Background runners ------------------------------------------
        self.runner = ProxyRunner()
        self.runner.log_line.connect(self._on_log)
        self.runner.running.connect(self._on_running)

        self.gear_scraper = GearScraperRunner()
        self.gear_scraper.log_line.connect(self._on_log)
        self.gear_scraper.finished.connect(self._on_gear_scraped)
        self.gear_scraper.error.connect(self._on_gear_error)
        self.gear_scraper.scraping.connect(self._on_gear_scraping)

        # ---- Core widgets -----------------------------------------------
        self.editor = ConfigEditor()
        self.detail_panel = RuleDetailPanel()
        self.item_browser = ItemBrowser(
            gear_cache_dir=GEAR_CACHE_DIR,
            drops_index_path=DROPS_INDEX_CACHE,
            box_slug_cache_path=BOX_SLUG_CACHE,
        )
        self.log_panel = LogPanel()

        # ---- Shell: horizontal splitter between Rules + Detail ----------
        # The handle is 6px wide (vs Qt's default 4px) with a visible
        # surface1 background so users can actually grab and drag it.
        # Without this the splitter is invisible and users assume the
        # layout is fixed — they end up either resizing the whole
        # window or accepting cramped panels.
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setObjectName("main_splitter")
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setOpaqueResize(True)
        # Left: config editor (rules + range form).
        left_wrap = self._wrap_with_panel_heading(
            self.editor, "RULES", "Select a rule on the left to edit its rewards on the right."
        )
        # Right: rule detail editor (the new primary edit surface).
        right_wrap = self._wrap_with_panel_heading(
            self.detail_panel, "DETAIL", ""
        )
        self._splitter.addWidget(left_wrap)
        self._splitter.addWidget(right_wrap)
        # RULES (left) gets the larger share — the user came here to
        # browse/edit rules and they want to see all of them at once
        # without scrolling. DETAIL (right) is the edit form for the
        # currently selected rule; it needs enough room for the form
        # fields + chip strip but doesn't have to be the dominant pane.
        # 62 / 38 split.
        self._splitter.setStretchFactor(0, 62)
        self._splitter.setStretchFactor(1, 38)
        self._splitter.setSizes([865, 535])
        self.setCentralWidget(self._splitter)

        # ---- Log dock (bottom, collapsible) -----------------------------
        self.log_dock = QDockWidget("Log", self)
        self.log_dock.setObjectName("log_dock")
        self.log_dock.setWidget(self.log_panel)
        self.log_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        # Make the dock collapsible but not floatable / movable — keeps
        # the layout predictable across screen sizes and prevents the
        # user from accidentally dragging it out into a floating
        # top-level window.
        self.log_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        # ---- Catalog dock (right side, hidden by default) ---------------
        # Kept accessible for users who want to browse the full wiki catalog,
        # but demoted from "permanent right pane" to "toggleable dock".
        self.catalog_dock = QDockWidget("Catalog", self)
        self.catalog_dock.setObjectName("catalog_dock")
        self.catalog_dock.setWidget(self.item_browser)
        self.catalog_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.catalog_dock)
        self.catalog_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.catalog_dock.hide()  # hidden by default — user opts in

        # ---- Toolbar (4 zones) + menu + status bar ----------------------
        self._build_toolbar()
        self._build_menu()
        self.setStatusBar(QStatusBar())

        # Initialize button/dot state to "not running".
        self._on_running(False)

        # ---- Wire signals -----------------------------------------------
        # RuleListView selection → populate the detail panel + the catalog dock.
        self.editor.rule_list().rule_selected.connect(self._on_rule_selected)
        # RuleDetailPanel pick buttons → existing picker dialogs.
        self.detail_panel.pick_box_id.connect(self._pick_box_id_for_detail)
        self.detail_panel.pick_box_loot.connect(self._pick_box_loot_for_detail)
        self.detail_panel.pick_gear.connect(self._pick_gear_for_detail)
        self.detail_panel.remove_id_requested.connect(self._on_detail_chip_removed)
        # Catalog dock picks still route to the active target.
        self.item_browser.item_picked.connect(self._on_item_browser_pick)
        self.item_browser.items_picked.connect(self._on_item_browser_picks)
        # ConfigEditor focus event also routes to detail panel.
        self.editor.range_form().installEventFilter(self)

        self._reload_config()

    # ------------------------------------------------------------------ shell
    def _wrap_with_panel_heading(
        self, inner: QWidget, heading: str, subheading: str = ""
    ) -> QWidget:
        """Wrap *inner* with a small panel heading + subheading.

        Used to label the major zones (RULES, DETAIL) so the user can
        scan the shell in one glance instead of guessing what's where.
        """
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        head = QLabel(heading)
        head.setObjectName("panel_heading")
        head.setStyleSheet(panel_heading_style())
        layout.addWidget(head)

        if subheading:
            sub = QLabel(subheading)
            sub.setObjectName("panel_subheading")
            sub.setStyleSheet(panel_heading_style())
            sub.setWordWrap(True)
            layout.addWidget(sub)

        layout.addWidget(inner, stretch=1)
        return wrap

    # ------------------------------------------------------------------ toolbar
    def _build_right_cluster(self) -> QWidget:
        """Build the right-aligned cluster (Port + status badge).

        Packaged into one widget so the main toolbar's right side reads
        as a single unit: ``Port [8877]  ●  [STOPPED]``. The cluster sits
        after an expanding spacer that pushes it flush to the right
        edge of the toolbar.
        """
        cluster = QWidget()
        cluster.setObjectName("toolbar_right_cluster")
        layout = QHBoxLayout(cluster)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Expanding spacer — eats the remaining toolbar width so the
        # cluster (and only the cluster) sits at the right edge.
        spacer = QWidget()
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setMinimumWidth(1)
        layout.addWidget(spacer, stretch=1)

        # Port label + input.
        port_label = QLabel("Port")
        port_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 1px; padding-left: 4px;"
        )
        layout.addWidget(port_label)

        mono = QFont("JetBrains Mono", 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setFamily("JetBrains Mono")
        self.port_edit = QLineEdit()
        self.port_edit.setObjectName("port_edit_toolbar")
        self.port_edit.setFixedWidth(72)
        self.port_edit.setFont(mono)
        self.port_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.port_edit.setPlaceholderText("8877")
        self.port_edit.setToolTip("Proxy listen port (requires restart after change)")
        layout.addWidget(self.port_edit)

        # Vertical divider for visual separation.
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet(f"color: {MOCHA['surface0']}; background: {MOCHA['surface0']};")
        sep.setFixedWidth(1)
        layout.addWidget(sep)

        # Legacy bare status dot (back-compat with existing tests).
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("status_dot_pulse")
        self.status_dot.setToolTip("Proxy status: stopped")
        self.status_dot.setStyleSheet(status_dot_style(False))
        layout.addWidget(self.status_dot)

        # Labeled StatusBadge — the meaningful state indicator.
        self.status_badge = StatusBadge(text_off="STOPPED", text_on="RUNNING")
        self.status_badge.setObjectName("status_badge_toolbar")
        layout.addWidget(self.status_badge)

        return cluster

    def _build_toolbar(self) -> None:
        bar = self.addToolBar("main")
        bar.setObjectName("main_toolbar")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setIconSize(bar.iconSize())  # keep default; no icons

        # ---- PROXY zone: Start / Stop -----------------------------------
        bar.addWidget(_zone_label("PROXY"))
        self.btn_start = QPushButton("▶  START")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setProperty("toolbar_zone", "primary")
        self.btn_start.setToolTip("Start the mitmproxy subprocess")
        bar.addWidget(self.btn_start)

        self.btn_stop = QPushButton("■  STOP")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setProperty("toolbar_zone", "primary")
        self.btn_stop.setToolTip("Terminate the running proxy subprocess")
        bar.addWidget(self.btn_stop)

        # ---- DATA zone: Scrape / Check ----------------------------------
        bar.addSeparator()
        bar.addWidget(_zone_label("DATA"))
        self.btn_refresh_gear = QPushButton("Scrape data")
        self.btn_refresh_gear.setObjectName("btn_refresh_gear")
        self.btn_refresh_gear.setProperty("toolbar_zone", "secondary")
        self.btn_refresh_gear.setToolTip(
            "Refresh gear cache + drops index via headless browser. "
            "Slow on first launch, fast after that."
        )
        bar.addWidget(self.btn_refresh_gear)

        self.btn_check_data = QPushButton("Check data")
        self.btn_check_data.setObjectName("btn_check_data")
        self.btn_check_data.setProperty("toolbar_zone", "secondary")
        self.btn_check_data.setToolTip(
            "Show counts and freshness for gear cache + drops index."
        )
        bar.addWidget(self.btn_check_data)

        # ---- CONFIG zone: Save / Reset ----------------------------------
        bar.addSeparator()
        bar.addWidget(_zone_label("CONFIG"))
        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("btn_save")
        self.btn_save.setProperty("toolbar_zone", "secondary")
        self.btn_save.setToolTip("Validate and atomically write config.json")
        bar.addWidget(self.btn_save)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setObjectName("btn_reset")
        self.btn_reset.setProperty("toolbar_zone", "secondary")
        self.btn_reset.setToolTip(
            "Reset config.json back to the default template. "
            "Your current rules will be lost."
        )
        bar.addWidget(self.btn_reset)

        # ---- STEAM zone: Copy + Port (live in the main toolbar) --------
        bar.addSeparator()
        bar.addWidget(_zone_label("STEAM"))
        self.btn_copy_steam = QPushButton("Copy Steam")
        self.btn_copy_steam.setObjectName("btn_copy_steam")
        self.btn_copy_steam.setProperty("toolbar_zone", "secondary")
        self.btn_copy_steam.setToolTip(
            "Copy the Steam launch option string for the current proxy "
            "port to the clipboard.\n"
            "Paste into Steam → TaskBarHero → Properties → Launch Options."
        )
        bar.addWidget(self.btn_copy_steam)

        # ---- Right-side: Port field + status badge (in main toolbar) ---
        # The status indicator belongs at the far right where users expect
        # to find it. Previous designs put it in a separate QToolBar at
        # RightToolBarArea, which rendered as a sparse second toolbar row
        # under the main one — looked like a separate empty window. Now
        # they're appended to the same main toolbar with an expanding
        # spacer before them so they sit flush right.
        bar.addWidget(self._build_right_cluster())

        # ---- Wiring -----------------------------------------------------
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self.runner.stop)
        self.btn_refresh_gear.clicked.connect(self._refresh_gear)
        self.btn_check_data.clicked.connect(self._check_data)
        self.btn_save.clicked.connect(self._save)
        self.btn_reset.clicked.connect(self._reset_config)
        self.btn_copy_steam.clicked.connect(self._copy_steam_launch_option)
        # Tooltip preview stays in sync with port edits.
        self.port_edit.textChanged.connect(self._refresh_steam_copy_tooltip)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Save config", self._save)
        file_menu.addAction("Reset config to default", self._reset_config)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # View menu: visibility toggles for log dock + catalog dock.
        view_menu = menubar.addMenu("View")
        self.action_toggle_log = view_menu.addAction("Log panel")
        self.action_toggle_log.setCheckable(True)
        self.action_toggle_log.setChecked(True)
        self.action_toggle_log.toggled.connect(
            lambda checked: self.log_dock.toggleViewAction().setChecked(checked)
        )
        # Back-compat: keep ``action_toggle_items`` as the toggle for the
        # catalog dock (the old name still resolves to the catalog pane).
        self.action_toggle_items = view_menu.addAction("Item browser")
        self.action_toggle_items.setCheckable(True)
        self.action_toggle_items.setChecked(self.item_browser.isVisible())
        self.action_toggle_items.toggled.connect(
            lambda checked: self.catalog_dock.toggleViewAction().setChecked(checked)
        )

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
        # Re-emit the current selection (if any) so the detail panel
        # refreshes its banner + chip row to match the freshly loaded
        # config.
        target = self.editor.rule_list().active_target()
        if target is not None:
            self._on_rule_selected(target)

    def _on_log(self, line: str) -> None:
        self.log_panel.append_log(line)

    def _on_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.status_dot.setStyleSheet(status_dot_style(running))
        self.status_dot.setToolTip(
            "Proxy status: running" if running else "Proxy status: stopped"
        )
        self.status_badge.set_state(running)

    # ------------------------------------------------------------------ scraper
    def _refresh_gear(self) -> None:
        """Single 'Scrape Data' button — runs gear scrape, then drops index."""
        if self.gear_scraper.is_running():
            self._on_log("Scrape already running…")
            return
        self._on_gear_scraping(True)
        self.gear_scraper.start()
        # Drops index fetch in parallel via thread-safe bridge.
        import threading
        bridge = _ThreadLogBridge()
        bridge.log_line.connect(self._on_log)
        self._drops_log_bridge = bridge
        def _fetch_drops_async() -> None:
            try:
                from tbh_desktop.paths import DROPS_INDEX_CACHE, ITEM_DIR
                from tbh_desktop.scraper import fetch_drops_index, refresh_material_details
                items = fetch_drops_index(DROPS_INDEX_CACHE)
                bridge.log_line.emit(
                    f"Drops index: {len(items)} items cached (materials + stage boxes)"
                )
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
            self.btn_refresh_gear.setText("Scrape data")

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

        drops = read_drops_index(DROPS_INDEX_CACHE)
        drops_count = len(drops)
        drops_size = DROPS_INDEX_CACHE.stat().st_size if DROPS_INDEX_CACHE.exists() else 0
        drops_mtime = (
            DROPS_INDEX_CACHE.stat().st_mtime if DROPS_INDEX_CACHE.exists() else 0
        )

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
        """Build the Steam launch option string for the given (or current) port."""
        if port is None:
            port = self._parse_port()
        return (
            f"HTTP_PROXY=http://127.0.0.1:{port} "
            f"HTTPS_PROXY=http://127.0.0.1:{port} %command%"
        )

    def _refresh_steam_copy_tooltip(self) -> None:
        self.btn_copy_steam.setToolTip(
            "Copy this Steam launch option to the clipboard:\n\n"
            f"    {self._steam_launch_option()}\n\n"
            "Paste into Steam → TaskBarHero → Properties → Launch Options."
        )

    def _copy_steam_launch_option(self) -> None:
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
    def _pick_box_id_for_detail(self) -> None:
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
        # Refresh the detail panel so the new ID shows up.
        target = self.editor.rule_list().active_target()
        if target is not None:
            self._on_rule_selected(target)

    def _get_box_loot(self, box_id: int) -> list[dict]:
        """Fetch box loot (network or cache) and log if empty."""
        loot = scraper.refresh_box_loot(BOX_LOOT_CACHE_DIR, box_id)
        if not loot:
            self._on_log(f"No loot for box {box_id}. Check box_id / wiki items page.")
        return loot

    def _pick_box_loot_for_detail(self) -> None:
        """Pick reward IDs from THIS BOX's loot (not the full wiki drops index)."""
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

    def _pick_gear_for_detail(self) -> None:
        """Pick gear scoped to the selected rule's box (name + level filter)."""
        if not GEAR_CACHE_DIR.exists() or not any(GEAR_CACHE_DIR.glob("*/*.json")):
            self._on_log("No gear cache. Click 'Scrape data' first.")
            return
        box_id = self.editor.selected_rule_item_id()
        level_hint = self.editor.selected_rule_level()
        box_loot: list[dict] = []
        if box_id is not None:
            box_loot = read_box_cache(BOX_LOOT_CACHE_DIR, box_id)
            if not box_loot:
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
            self._on_log("No gear cache. Click 'Scrape data' first.")
            return
        dlg = GearPicker(GEAR_CACHE_DIR, self)
        if dlg.exec():
            self.editor.add_ids_to_range(dlg.selected_ids())

    def _pick_box_loot_for_range(self) -> None:
        """Pick reward IDs from the wiki drops index (materials + boxes)."""
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

    # ------------------------------------------------------------------ events
    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.gear_scraper.is_running():
            if not self._confirm(
                "Scrape in progress?",
                "Gear scrape is running. Exit anyway?",
            ):
                event.ignore()
                return
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
        """Force-stop all background activities without prompts."""
        self.gear_scraper.stop()
        self.runner.stop()

    # ------------------------------------------------------------------ rule/detail routing
    def _on_rule_selected(self, target) -> None:
        """Route selection events to the detail panel + the catalog dock.

        RuleTarget → populate the detail panel + swap the catalog to a
        scope that matches the box.
        RangeTarget → show the range-summary state in the detail panel.
        None → show empty state.
        """
        from tbh_desktop.ui.active_target import RangeTarget, RuleTarget
        from tbh_desktop.ui.item_browser import FilterContext, FilterScope

        if isinstance(target, RangeTarget):
            self.detail_panel.show_range_summary()
            return
        if target is None:
            self.detail_panel.show_empty()
            return
        if isinstance(target, RuleTarget):
            # Look up the active rule card and pull the live data out.
            rule_list = self.editor.rule_list()
            row = target.row
            card = rule_list._cards[row] if 0 <= row < len(rule_list._cards) else None
            if card is None:
                self.detail_panel.show_empty()
                return
            level = rule_list._level_for_row.get(row)
            self.detail_panel.set_rule_data(
                name=card.name(),
                item_id=card.item_id(),
                level=level,
                replacement_ids=card.replacement_ids(),
            )
            # Swap the catalog to the matching scope so a quick browse
            # reflects what the user is editing.
            scope = FilterScope.GEAR_FOR_BOX if target.box_id else FilterScope.GEAR_ALL
            self.item_browser.filter_for_context(
                FilterContext(
                    box_id=target.box_id,
                    box_name=None,
                    level=target.level,
                    scope=scope,
                )
            )

    def _on_detail_chip_removed(self, item_id: int) -> None:
        """Forward a chip-remove request from the detail panel to the
        underlying rule card, then re-render the detail panel."""
        target = self.editor.rule_list().active_target()
        from tbh_desktop.ui.active_target import RuleTarget
        if not isinstance(target, RuleTarget):
            return
        rule_list = self.editor.rule_list()
        row = target.row
        if 0 <= row < len(rule_list._cards):
            rule_list._cards[row].remove_id(int(item_id))
            self._on_rule_selected(target)

    def _on_item_browser_pick(self, item_id: int) -> None:
        """Route a single-item pick from the catalog dock to the active target."""
        try:
            self.editor.add_ids_to_active_target([int(item_id)])
        except ValueError:
            pass

    def _on_item_browser_picks(self, item_ids: list) -> None:
        """Route a multi-item pick from the catalog dock to the active target."""
        ids = [int(i) for i in item_ids]
        try:
            self.editor.add_ids_to_active_target(ids)
        except ValueError:
            pass

    # ------------------------------------------------------------------ eventFilter
    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        """Switch the detail panel to range-summary when the range form takes focus."""
        from PySide6.QtCore import QEvent
        from tbh_desktop.ui.active_target import RangeTarget

        if event.type() == QEvent.Type.FocusIn and obj is self.editor.range_form():
            self.editor.rule_list().set_active_target(RangeTarget())
            self.detail_panel.show_range_summary()
            return False
        return super().eventFilter(obj, event)
