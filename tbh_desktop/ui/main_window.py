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

from tbh_desktop import config_io, linux_elevation, scraper
from tbh_desktop.paths import CONFIG_PATH, DROPS_INDEX_CACHE, GEAR_CACHE_DIR, STAGE_DROP_MAP_CACHE, STAGES_INDEX_CACHE
from tbh_desktop.proxy_runner import ProxyRunner
from tbh_desktop.scrape_runner import ScrapeRunner
from tbh_desktop.ui.catalog_popup import CatalogPopup
from tbh_desktop.ui.config_editor import ConfigEditor
from tbh_desktop.ui.gear_picker import GearPicker
from tbh_desktop.ui.log_panel import LogPanel
from tbh_desktop.ui.rule_detail_panel import RuleDetailPanel
from tbh_desktop.ui.status_badge import StatusBadge
from tbh_desktop.ui.theme import (
    MOCHA,
    panel_heading_style,
    status_dot_style,
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TBH Reward Proxy")
        self.resize(1400, 850)

        # ---- Background runners ------------------------------------------
        self.runner = ProxyRunner()
        self.runner.log_line.connect(self._on_log)
        self.runner.running.connect(self._on_running)
        self.runner.startup_failed.connect(self._on_runner_startup_failed)

        self.gear_scraper = ScrapeRunner()
        self.gear_scraper.log_line.connect(self._on_log)
        self.gear_scraper.finished.connect(self._on_gear_scraped)
        self.gear_scraper.error.connect(self._on_gear_error)
        self.gear_scraper.scraping.connect(self._on_gear_scraping)

        # ---- Core widgets -----------------------------------------------
        self.editor = ConfigEditor()
        self.detail_panel = RuleDetailPanel()
        # Catalog: popup instead of dock. The ItemBrowser is owned by the
        # popup (so it has a parent for paint events); MainWindow keeps
        # a reference and forwards item_picked / items_picked to the
        # active-target router identically to the old dock version.
        # Jul 2026: stage-first catalog — passes stage_drop_map.json and
        # stages_index.json instead of box_slug_cache (boxes no longer
        # drive the picker flow).
        from tbh_desktop.ui.catalog_popup import CatalogPopup
        self.catalog_popup = CatalogPopup(
            gear_cache_dir=GEAR_CACHE_DIR,
            drops_index_path=DROPS_INDEX_CACHE,
            stage_drop_map_path=STAGE_DROP_MAP_CACHE,
            stages_index_path=STAGES_INDEX_CACHE,
            parent=self,
        )
        self.item_browser = self.catalog_popup.content
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
        # 30 / 70 split — DETAIL (right, edit form for the selected
        # rule) gets the dominant share because it's where the actual
        # editing happens. RULES stays visible as a navigation rail.
        self._splitter.setStretchFactor(0, 30)
        self._splitter.setStretchFactor(1, 70)
        self._splitter.setSizes([420, 980])
        self.setCentralWidget(self._splitter)        # ---- Log dock (bottom, collapsible) -----------------------------
        # Log dock starts COLLAPSED — the panel only opens when the user
        # explicitly clicks the View → Log panel menu item. Default-open
        # log panels eat ~50% of the window at launch (Qt's default
        # dock height), forcing the user to drag the dock border back
        # up to recover the main workspace. Collapsed-by-default means
        # the app launches with the full main area visible and the log
        # appears as a one-line dock header that can be expanded when
        # the user actually wants to see traffic.
        self.log_dock = QDockWidget("Log", self)
        self.log_dock.setObjectName("log_dock")
        self.log_dock.setWidget(self.log_panel)
        self.log_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        # Pin the dock to a small fixed size — Qt's title-bar floor
        # (~85px) limits how small we can go, so 80px max stays the
        # dock at the absolute minimum regardless of content.
        self.log_dock.setMinimumHeight(80)
        self.log_dock.setMaximumHeight(80)
        # Collapse the dock by default. Use show()/hide() (rather than
        # setVisible) so Qt's toggleViewAction state stays consistent
        # with the menu action's checkable state. setVisible() on a
        # freshly-added dock sometimes leaves the dock in a half-shown
        # Log dock stays visible by default so the user can see scrape
        # progress, proxy events, and any pool-not-found warnings
        # without having to dig through a View menu. Jul 2026: the
        # 80px max height keeps it compact enough not to steal screen
        # real-estate from the rule editor.

        # ---- Catalog popup (triggered from toolbar Catalog button) ------
        # Catalog is no longer a docked panel — it's a QMenu popup that
        # appears anchored at the toolbar button when the user clicks.
        # Auto-dismisses on outside click so it never takes screen space
        # the user isn't actively using.

        # ---- Toolbar (4 zones) + menu + status bar ----------------------
        self._build_toolbar()
        self._build_menu()
        self.setStatusBar(QStatusBar())
        self._tamper_count: int = 0
        self._update_tamper_status()

        # Initialize button/dot state to "not running".
        self._on_running(False)

        # ---- Wire signals -----------------------------------------------
        # RuleListView selection → populate the detail panel + the catalog dock.
        self.editor.rule_list().rule_selected.connect(self._on_rule_selected)
        # RuleDetailPanel pick buttons → existing picker dialogs.
        self.detail_panel.pick_pool_id.connect(self._pick_pool_id_for_detail)
        self.detail_panel.pick_gear.connect(
            lambda: self._pick_replacement_for_detail("gear")
        )
        self.detail_panel.pick_item.connect(
            lambda: self._pick_replacement_for_detail("item")
        )
        self.detail_panel.remove_id_requested.connect(self._on_detail_chip_removed)
        self.detail_panel.pool_id_changed.connect(self._on_detail_pool_ids_changed)
        self.detail_panel.range_edited.connect(self._on_detail_range_edited)
        # Range card enabled checkbox (in the rule list) toggles
        # RangeState directly — same effect as flipping the switch
        # in the detail panel's range form.
        self.editor.rule_list().range_toggled.connect(self._on_detail_range_edited)
        # Catalog dock picks still route to the active target.
        self.item_browser.item_picked.connect(self._on_item_browser_pick)
        self.item_browser.items_picked.connect(self._on_item_browser_picks)
        # ConfigEditor focus event also routes to detail panel.
        self.editor.installEventFilter(self)
        # When the user selects a range target on the rule list, the
        # detail panel's "Pick item" button picks for the range form.
        self.detail_panel.pick_item.connect(
            lambda: self._pick_replacement_for_detail("item")
        )

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

        # ---- DATA zone: Scrape ------------------------------------------
        bar.addSeparator()
        self.btn_refresh_gear = QPushButton("Scrape data")
        self.btn_refresh_gear.setObjectName("btn_refresh_gear")
        self.btn_refresh_gear.setProperty("toolbar_zone", "secondary")
        self.btn_refresh_gear.setToolTip(
            "Refresh item + stage caches from tbh.city (items / stages / "
            "drop tables). Picks up new pool data so the rule editor's "
            "Pick replacement sees fresh drop candidates."
        )
        bar.addWidget(self.btn_refresh_gear)

        # ---- CONFIG zone: Save / Reset ----------------------------------
        bar.addSeparator()
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

        # ---- STEAM zone: Copy + Catalog popup -------------------------
        bar.addSeparator()
        self.btn_copy_steam = QPushButton("Copy Steam")
        self.btn_copy_steam.setObjectName("btn_copy_steam")
        self.btn_copy_steam.setProperty("toolbar_zone", "secondary")
        self.btn_copy_steam.setToolTip(
            "Copy the Steam launch option string for the current proxy "
            "port to the clipboard.\n"
            "Paste into Steam → TaskBarHero → Properties → Launch Options."
        )
        bar.addWidget(self.btn_copy_steam)

        # Catalog popup is now triggered from the View menu
        # (action_toggle_items) — no toolbar button. The user opens the
        # catalog via the menu OR via "Pick replacement" in the rule
        # detail panel (the detail-panel flow is the primary one).

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
        # Click handler flips the dock's current visibility. The menu
        # action's checked state is set BEFORE setVisible so Qt renders
        # the checkmark from the action's own state — no
        # dock.visibilityChanged → action.setChecked round-trip needed
        # (avoids a teardown GC crash where the action's C++ object
        # is already deleted when the dock emits its final signal).
        view_menu = menubar.addMenu("View")
        self.action_toggle_log = view_menu.addAction("Log panel")
        self.action_toggle_log.setCheckable(True)
        # Log dock is visible by default (Jul 2026) so the user sees
        # scrape progress + pool warnings without opening the View menu.
        self.action_toggle_log.setChecked(self.log_dock.isVisible())
        self.action_toggle_log.triggered.connect(self._toggle_log_dock)
        # Catalog dock starts VISIBLE — force menu checked to match
        # (build_menu runs before the dock's show() takes effect).
        self.action_toggle_items = view_menu.addAction("Item browser")
        self.action_toggle_items.setCheckable(True)
        self.action_toggle_items.setChecked(False)
        self.action_toggle_items.triggered.connect(self._show_catalog_popup)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._about)

    # ------------------------------------------------------------------ misc
    # ------------------------------------------------------------------ dock toggles
    def _toggle_log_dock(self) -> None:
        # Flip log dock visibility. The View menu action is the
        # authoritative source for the log dock state (toolbar has
        # no log button), so update it to match. Done as a method (not
        # a lambda) so the QAction ref isn't captured in a closure
        # that survives past QAction destruction during teardown.
        new_vis = not self.log_dock.isVisible()
        self.log_dock.setVisible(new_vis)
        self.action_toggle_log.setChecked(new_vis)

    def _show_catalog_popup(self) -> None:
        # Anchor the catalog popup at the current cursor position.
        # The View menu action invokes this — no specific toolbar
        # button to anchor against anymore (the toolbar Catalog button
        # was removed in Jul 2026 — the rule detail panel's "Pick
        # replacement" button is the primary path).
        self.catalog_popup.popup_at()

    def _about(self) -> None:
        from tbh_desktop.ui.about_dialog import AboutDialog

        AboutDialog(self).exec()

    def _confirm(self, title: str, message: str, *, default_yes: bool = False) -> bool:
        """Show a Yes/No dialog. Returns True if user clicked Yes."""
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        default = (
            QMessageBox.StandardButton.Yes if default_yes else QMessageBox.StandardButton.No
        )
        reply = QMessageBox.question(self, title, message, buttons, default)
        return reply == QMessageBox.StandardButton.Yes

    def _config_has_unsaved_changes(self) -> bool:
        """Compare the editor's in-memory state to the on-disk config.

        Returning True here triggers the Save / Discard / Cancel
        dialog when the user clicks START, so they don't accidentally
        launch mitmproxy with rules they've only been viewing in the
        editor (not yet written to disk).
        """
        try:
            on_disk = config_io.load_config(CONFIG_PATH)
        except (OSError, ValueError):
            return True  # can't read disk → assume user must save
        in_memory = self.editor.dump()
        # Strip the comment fields the editor injects (they're the same
        # in both dicts; checking equality on them is noise).
        def _strip(d: dict) -> dict:
            return {k: v for k, v in d.items() if not k.startswith("_")}
        return _strip(on_disk) != _strip(in_memory)

    def _confirm_unsaved_changes(self) -> str:
        """Three-button dialog: Save / Discard / Cancel.

        Defaults to Cancel so an accidental Enter doesn't nuke edits.
        Returns one of ``"save"``, ``"discard"``, ``"cancel"``.
        """
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Unsaved changes")
        msg.setText(
            "The rule editor has changes that aren't saved to disk yet.\n\n"
            "Starting mitmproxy now will run with the OLD config on disk. "
            "Save first?"
        )
        btn_save = msg.addButton("Save first", QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg.addButton("Discard & start", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_cancel)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is btn_save:
            return "save"
        if clicked is btn_discard:
            return "discard"
        return "cancel"

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
        # Detect tamper warnings from the addon (passive TamperDetector
        # emits "TAMPER WARNING: N mismatch(es)... Session total: M").
        # Parse the session total so the status bar shows a live count.
        if "TAMPER WARNING" in line and "Session total:" in line:
            try:
                after = line.split("Session total:")[1].strip()
                num = int(after.split(".")[0].strip())
                if num > self._tamper_count:
                    self._tamper_count = num
                    self._update_tamper_status()
            except (ValueError, IndexError):
                pass

    def _update_tamper_status(self) -> None:
        """Show the current tamper count in the status bar."""
        if self._tamper_count > 0:
            self.statusBar().showMessage(
                f"⚠ Tamper reports this session: {self._tamper_count}"
            )
        else:
            self.statusBar().clearMessage()

    def _on_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.status_dot.setStyleSheet(status_dot_style(running))
        self.status_dot.setToolTip(
            "Proxy status: running" if running else "Proxy status: stopped"
        )
        self.status_badge.set_state(running)
        # Reset tamper counter when a new proxy session starts so the
        # status bar reflects only the current session's reports.
        if running:
            self._tamper_count = 0
            self._update_tamper_status()

    # ------------------------------------------------------------------ scraper
    def _refresh_gear(self) -> None:
        """Single 'Scrape data' button — refresh tbh.city items + stages
        + reverse drop map. ``run_scrape`` already writes the items
        index, gear cache split, materials split, stages index, stage
        details, and stage_drop_map.json — no parallel fetch needed.
        """
        if self.gear_scraper.is_running():
            self._on_log("Scrape already running…")
            return
        self._on_gear_scraping(True)
        # resume=True with 7-day window: subsequent clicks are near-instant
        # because per-stage detail cache stays fresh.
        self.gear_scraper.start(resume=True, max_cache_age_days=7)

    def _on_gear_scraping(self, scraping: bool) -> None:
        self.btn_refresh_gear.setEnabled(not scraping)
        if scraping:
            self._on_log("Scraping… (items + stages, may take a minute)")
            self.btn_refresh_gear.setText("Scraping…")
        else:
            self.btn_refresh_gear.setText("Scrape data")

    def _on_gear_scraped(self, total: int, num_files: int) -> None:
        self._on_log(
            f"Scrape done: {total} items, {num_files} stages cached."
        )

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
        # Detect any unsaved rule / mode / range changes and prompt the
        # user before starting. Starting mitmproxy with a stale config
        # would silently ignore the user's edits — they'd be confused
        # when their rules don't fire. Three-button dialog: Save / Discard
        # / Cancel (default = Cancel, focused on Escape so an accidental
        # Enter doesn't nuke in-flight edits).
        if self._config_has_unsaved_changes():
            choice = self._confirm_unsaved_changes()
            if choice == "cancel":
                self._on_log("Start cancelled — unsaved changes preserved.")
                return
            if choice == "save":
                self._save()
            # 'discard' falls through — start with the on-disk config.
        # Pull current mode/name from the editor and persist to disk so
        # the config reflects what we're about to start. This matters
        # because run_proxy.py also re-reads config.json for any keys we
        # don't forward as CLI args (filter rules, etc.) — those need to
        # be on disk too, not just in the in-memory editor dump.
        mode = self.editor.mode_form().mode()
        name = self.editor.mode_form().local_process_name()
        self._save()  # save current editor state (incl. mode + name)
        # Pre-check: if port is held by something else, don't bother
        # spawning mitmdump just to watch it fail. mitmdump binds to
        # 0.0.0.0:<port>; we test the same target so the result matches.
        # Skip precheck in local mode — mitmdump binds differently
        # (LOCAL redirector, not a listen port), and the user's port
        # choice still needs to be reserved for the SPAWN'd process's
        # outbound traffic.
        if mode != "local":
            port = self._parse_port()
            if not self.runner.port_available(port):
                self._show_port_in_use_dialog(port)
                return
        # Linux + local + not root → mitmdump's setuid helper needs root
        # and there's no TTY in the GUI subprocess, so a bare start()
        # will fail with "sudo: a terminal is required". Ask the user
        # to elevate via pkexec (polkit) before spawning, so the prompt
        # shows up in their face instead of dying silently.
        if linux_elevation.runtime_needs_elevation(mode, name):
            if not self._confirm(
                "Local mode needs root",
                "mitmproxy's local redirector needs root to inject the proxy "
                f"into '{name}'. A polkit password prompt will appear.\n\n"
                "Continue?",
            ):
                return
            self.runner.start_elevated(mode=mode, name=name)
            return
        self.runner.start(mode=mode, name=name)

    def _show_port_in_use_dialog(self, port: int) -> None:
        """Modal hint when the listen port is held by something else.

        mitmdump can't bind it, so we surface the exact actionable
        command (`fuser -k 8877/tcp` or `lsof -ti:8877 | xargs kill`).
        This is the same dialog the user would see if mitmdump crashed
        on startup, but earlier — no need to wait for the subprocess
        to exit and emit startup_failed.
        """
        hint = (
            f"mitmdump needs port {port} but it's already in use.\n\n"
            "Most common cause: a previous mitmdump (or a stray "
            "run_proxy.py) didn't get cleaned up. Use one of:\n\n"
            f"  • Linux:  fuser -k {port}/tcp\n"
            f"           ss -ltnp 'sport = :{port}'   # find who holds it\n"
            f"  • macOS:  lsof -ti:{port} | xargs kill\n"
            f"  • Win:    netstat -ano | findstr :{port}\n"
            f"           taskkill /PID <pid> /F\n\n"
            "If another tool (e.g. Shadowsocks, clash) is using this "
            "port, change 'listen_port' in the toolbar to something free."
        )
        QMessageBox.critical(self, f"Port {port} in use", hint)

    def _on_runner_startup_failed(self, title: str, body: str) -> None:
        """Modal when mitmdump exits within 3s of starting.

        The runner has already mirrored every line to the log panel,
        so we don't duplicate the noise — just give the user a modal
        they can't miss with the captured tail and a hint list.
        """
        QMessageBox.critical(self, title, body)

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
    def _pick_pool_id_for_detail(self) -> None:
        """Open StagePickerDialog, set the selected rule's pool_ids.

        The user picks a stage (act / stage_no / difficulty); the
        dialog fetches the matching drop_key from the cached stage
        detail for the active rule's kind (Normal / Boss / Act) and
        sets it on the rule.
        """
        from tbh_desktop.ui.active_target import RuleTarget
        from tbh_desktop.ui.stage_picker import StagePickerDialog
        target = self.editor.rule_list().active_target()
        if not isinstance(target, RuleTarget):
            QMessageBox.information(self, "No rule", "Select a rule row first.")
            return
        dlg = StagePickerDialog(target.reward_kind, self)
        dlg.pool_key_selected.connect(
            lambda drop_key: self._on_pool_key_picked(target, drop_key)
        )
        dlg.exec()

    def _on_pool_key_picked(self, target, drop_key: int) -> None:
        """Callback: user picked a stage, append its drop_key to the
        rule's pool_ids list (multi-pool support — user can pick
        several stages to cover multiple acts / difficulties in one rule).
        """
        rule_list = self.editor.rule_list()
        row = target.row
        if not (0 <= row < len(rule_list._cards)):
            return
        card = rule_list._cards[row]
        existing = list(card.pool_ids())
        if drop_key not in existing:
            existing.append(int(drop_key))
        new_text = ", ".join(str(p) for p in existing)
        card.edit_pool_id.blockSignals(True)
        card.edit_pool_id.setText(new_text)
        card.edit_pool_id.blockSignals(False)
        card._on_pool_id_changed(new_text)
        self._on_log(
            f"Pool {drop_key} added to {target.reward_kind} rule "
            f"(now {len(existing)} pool(s))."
        )
        refreshed = rule_list.active_target()
        if refreshed is not None:
            self._on_rule_selected(refreshed)

    def _pick_replacement_for_detail(self, axis: str = "gear") -> None:
        """Open CatalogPopup to pick replacement item ids for the active rule.

        ``axis`` is either ``"gear"`` (slot categories: Weapon /
        Off-hand / Armor / Accessory) or ``"item"`` (family categories:
        Crafting / Decoration / Engraving / Inscription / Offering /
        Soulstone). The picker is pre-scoped to that chip row.

        Pool-scoped rule: replacement candidates are restricted to
        the union of the rule's pool drop tables (per user feedback —
        replacement must be drawn from one of the pools the rule
        targets).

        Range rule: replacement candidates are restricted to the
        item-id range [match_min, match_max] — same scoping logic as
        the proxy addon (the range match runs at proxy time on the
        item id; the picker shouldn't offer ids that can't match).

        Fallback (no target / no scope): full catalog.
        """
        from tbh_desktop.ui.active_target import RangeTarget, RuleTarget
        target = self.editor.rule_list().active_target()

        # --- Pool rule scope ---
        if isinstance(target, RuleTarget):
            card_pool_ids = self._card_pool_ids(target)
            if card_pool_ids:
                allowed = self._pool_drop_item_ids(card_pool_ids)
                if not allowed:
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self,
                        "No drop data for these pools",
                        f"This rule's {len(card_pool_ids)} pool(s) "
                        f"({', '.join(str(p) for p in card_pool_ids[:5])}{'…' if len(card_pool_ids) > 5 else ''}) "
                        f"have no cached drop entries.\n\n"
                        f"Coba Pick pool lagi dan pilih stage yang sudah di-scrape "
                        f"(klik Scrape data dulu kalau stages_index.json masih kosong).",
                    )
                    return
                self._open_picker_with_scope(allowed, axis)
                return

        # --- Range rule: full catalog (NOT scoped) ---
        # Range replacement hits every pool whose drop_key falls in
        # [min_pool_id, max_pool_id] — that crosses many pools, so any
        # item in the catalog is a valid replacement. Don't filter by
        # item-id range; the user picks freely from the whole list.
        if isinstance(target, RangeTarget):
            self._open_picker_with_scope([], axis)
            return

        # --- Fallback: full catalog ---
        self._open_picker_with_scope([], axis)

    def _open_picker_with_scope(
        self, allowed_item_ids: list[int], axis: str
    ) -> None:
        """Open the CatalogPopup with the given scope. Empty list
        means no scope restriction (full catalog)."""
        if allowed_item_ids:
            self.catalog_popup.exec_for_replacement_scoped(
                allowed_item_ids, axis=axis
            )
        else:
            self.catalog_popup.exec_for_replacement(axis=axis)
        ids = self.catalog_popup.last_picked_ids
        if not ids:
            return
        # Defensive: re-filter against the allowed set in case the
        # user somehow picked an id the dialog didn't block.
        if allowed_item_ids:
            safe = [i for i in ids if int(i) in allowed_item_ids]
            dropped = len(ids) - len(safe)
            if dropped:
                self._on_log(
                    f"Warning: {dropped} picked id(s) were outside "
                    "the rule's scope and were discarded."
                )
            ids = safe
        if not ids:
            return
        # Route to the right place (pool rule vs range rule).
        target = self.editor.rule_list().active_target()
        from tbh_desktop.ui.active_target import RangeTarget, RuleTarget
        if isinstance(target, RangeTarget):
            rs = self.editor.range_state()
            for i in ids:
                rs.add_ids([int(i)])
            # Mirror into rule_list range cache so dump() picks up.
            self.editor.rule_list()._range["replacement_reward_item_ids"] = list(
                rs.replacement_reward_item_ids
            )
            self._on_log(
                f"Added {len(ids)} replacement id(s) to range rule. "
                f"Total: {len(rs.replacement_reward_item_ids)}"
            )
        elif isinstance(target, RuleTarget):
            self.editor.add_ids_to_selected_rule(ids)
            self._on_log(
                f"Added {len(ids)} replacement id(s) to "
                f"{target.reward_kind} rule."
            )
        # Refresh detail panel chips.
        from tbh_desktop.ui.active_target import RangeTarget as _RT
        if isinstance(target, _RT):
            self._on_rule_selected(target)

    def _items_in_range(self, lo: int, hi: int) -> list[int]:
        """Return the subset of catalog item ids that fall in
        [lo, hi] (inclusive). Used to scope the range-rule
        replacement picker — without this the user would be
        offered 5875 items when they only want ids in their
        configured range.
        """
        out: list[int] = []
        for it in self.catalog_popup.content._all_items:
            iid = int(it.get("id", 0))
            if lo <= iid <= hi:
                out.append(iid)
        return out

    def _card_pool_ids(self, target) -> list[int]:
        """Return the pool_ids tuple stored on the active rule's card.

        Falls back to [target.pool_id] (the RuleTarget single id) when
        the rule has only one pool — keeps the legacy single-pool code
        path working.
        """
        rule_list = self.editor.rule_list()
        row = target.row
        if not (0 <= row < len(rule_list._cards)):
            return [target.pool_id] if target.pool_id else []
        card = rule_list._cards[row]
        pids = card.pool_ids()
        return list(pids) if pids else ([target.pool_id] if target.pool_id else [])

    def _pool_drop_item_ids(self, pool_ids: list[int]) -> list[int]:
        """Resolve a list of tbh.city pool_ids to the union of their
        drop table item_ids.

        Reads from ``pool_drops.json`` (the v2 drop_key → [item_id]
        index generated by scrape_stage). Each pool_id (drop_key) maps
        directly to the items that pool can yield across the entire
        game (e.g. 9100111 = Act 1 stages 1-9 Normal monster pool →
        union of all items in that pool). Returns the deduplicated
        union across all requested pool_ids.
        """
        if not pool_ids:
            return []
        import json
        from tbh_desktop.paths import POOL_DROPS_CACHE
        if not POOL_DROPS_CACHE.exists():
            return []
        try:
            payload = json.loads(POOL_DROPS_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(payload, dict):
            return []
        raw = payload.get("pool_drops") or {}
        if not isinstance(raw, dict):
            return []
        out: list[int] = []
        seen: set[int] = set()
        for pool_id in pool_ids:
            entries = raw.get(str(pool_id)) or raw.get(pool_id) or []
            if not isinstance(entries, list):
                continue
            for iid in entries:
                try:
                    iid_int = int(iid)
                except (TypeError, ValueError):
                    continue
                if iid_int not in seen:
                    seen.add(iid_int)
                    out.append(iid_int)
        return out

    def _pick_replacement_for_range(self) -> None:
        """Open CatalogPopup to pick replacement item ids for the pool-range form."""
        self.catalog_popup.exec_for_replacement()
        ids = self.catalog_popup.last_picked_ids
        if ids:
            self.editor.add_ids_to_range(ids)
            self._on_log(f"Added {len(ids)} replacement id(s) to pool range.")

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
        """Route selection events to the detail panel.

        RuleTarget → populate the rule form (name / kind / pool chips
        / replacement chips).
        RangeTarget → populate the range form (enabled / min / max /
        replacement chips) in the same detail panel.
        None → empty state.
        """
        from tbh_desktop.ui.active_target import RangeTarget, RuleTarget

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
            self.detail_panel.set_rule_data(
                name=card.name(),
                reward_kind=card.reward_kind(),
                pool_ids=list(card.pool_ids()),
                replacement_ids=card.replacement_ids(),
            )
            return

        # RangeTarget — same detail panel, just the min/max form.
        if isinstance(target, RangeTarget):
            range_rule = self.editor.dump().get("range_replacement") or {}
            self.detail_panel.set_range_data(
                enabled=bool(range_rule.get("enabled", False)),
                match_min=int(range_rule.get("min_pool_id", 0)),
                match_max=int(range_rule.get("max_pool_id", 0)),
                replacement_ids=list(range_rule.get("replacement_reward_item_ids") or []),
            )
            return

        # Unknown target type.
        self.detail_panel.show_empty()

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

    def _on_detail_pool_ids_changed(self, new_pool_ids: list) -> None:
        """Persist a multi-pool edit from the detail panel back into
        the source rule_card."""
        target = self.editor.rule_list().active_target()
        from tbh_desktop.ui.active_target import RuleTarget
        if not isinstance(target, RuleTarget):
            return
        rule_list = self.editor.rule_list()
        row = target.row
        if 0 <= row < len(rule_list._cards):
            card = rule_list._cards[row]
            new_text = ", ".join(str(p) for p in new_pool_ids)
            card.edit_pool_id.blockSignals(True)
            card.edit_pool_id.setText(new_text)
            card.edit_pool_id.blockSignals(False)
            card._on_pool_id_changed(new_text)
            self._on_log(
                f"Rule {card.name()} now binds {len(new_pool_ids)} "
                "pool(s)."
            )

    def _on_detail_range_edited(self) -> None:
        """Persist a range-form edit (min / max) from the detail panel
        back into ConfigEditor's RangeState. The enabled toggle is
        on the rule-list card (RangeCard) — single source of truth —
        so this handler doesn't touch it."""
        rs = self.editor.range_state()
        rs.min_pool_id = int(self.detail_panel.range_min_value.value())
        rs.max_pool_id = int(self.detail_panel.range_max_value.value())
        # Mirror into the rule_list's own range cache so dump()
        # picks up the change.
        self.editor.rule_list()._range["min_pool_id"] = rs.min_pool_id
        self.editor.rule_list()._range["max_pool_id"] = rs.max_pool_id
        self._on_log(
            f"Range rule: itemId {rs.min_pool_id:,} "
            f"→ {rs.max_pool_id:,}"
        )

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
        """Switch the detail panel to the range form when the rule
        list emits a range selection (or focus moves into the editor).
        The right pane shows the same chip row / pick-item / min-max
        UI whether a per-kind rule or the range rule is active.
        """
        from PySide6.QtCore import QEvent
        from tbh_desktop.ui.active_target import RangeTarget

        if event.type() != QEvent.Type.FocusIn:
            return super().eventFilter(obj, event)
        if obj is self.editor:
            return super().eventFilter(obj, event)
        return super().eventFilter(obj, event)
