"""Global dark theme (Catppuccin Mocha) + shared style constants.

Apply once at app startup via :func:`apply_theme`. All widgets inherit the
palette; individual panels add their own accent rules where needed.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# --- Catppuccin Mocha palette ---
MOCHA = {
    "base":      "#1e1e2e",
    "mantle":    "#181825",
    "crust":     "#11111b",
    "surface0":  "#313244",
    "surface1":  "#45475a",
    "surface2":  "#585b70",
    "text":      "#cdd6f4",
    "subtext":   "#a6adc8",
    "overlay0":  "#6c7086",
    "overlay1":  "#7f849c",
    "overlay2":  "#9399b2",
    "blue":      "#89b4fa",
    "lavender":  "#b4befe",
    "sapphire":  "#74c7ec",
    "mauve":     "#cba6f7",
    "red":       "#f38ba8",
    "maroon":    "#eba0ac",
    "peach":     "#fab387",
    "yellow":    "#f9e2af",
    "green":     "#a6e3a1",
    "teal":      "#94e2d5",
}

# Rarity → accent color. Covers the 10 tier names that
# actually appear in tbh.city's items_normalized.json (Jul 2026
# scrape): Common / Uncommon / Rare / Legendary / Immortal /
# Arcana / Beyond / Celestial / Divine / Cosmic. Anything
# missing falls back to COMMON gray, so we MUST keep the
# dict aligned with what the scraper produces.
#
# Palette rule: each tier gets a distinct, bright-enough-on-dark
# color. Legendary is the "warm gold" baseline; surrounding tiers
# diverge in hue (warm → cool as you climb the ladder) so the
# user can sort by visual rarity at a glance.
RARITY: dict[str, str] = {
    # Lower tiers — muted, low contrast.
    "COMMON":    "#7f849c",  # neutral gray
    "UNCOMMON":  "#a6e3a1",  # green
    "RARE":      "#89b4fa",  # blue
    # tbh.city LEG+ gear tiers (in scrape order, low → high).
    "LEGENDARY": "#f9e2af",  # warm gold
    "IMMORTAL":  "#fab387",  # orange
    "ARCANA":    "#b4befe",  # periwinkle
    "BEYOND":    "#94e2d5",  # teal
    "CELESTIAL": "#89dceb",  # sky blue
    "DIVINE":    "#f5c2e7",  # pink
    "COSMIC":    "#ffffff",  # pure white (final-tier signature)
}

# Display order: lowest to highest. Used for sorting the catalog
# list (cosmic-first) and any rarity-rank comparisons. Matches
# tbh.city's 10 tier names in items_normalized.json.
RARITY_ORDER: tuple[str, ...] = (
    "COMMON", "UNCOMMON", "RARE",
    "LEGENDARY", "IMMORTAL", "ARCANA", "BEYOND",
    "CELESTIAL", "DIVINE", "COSMIC",
)

# Numeric rank — used to decide when a row's foreground should
# use the rarity color (high tiers) vs. plain text (low tiers,
# which would be near-invisible on the dark base).
RARITY_RANK: dict[str, int] = {name: i for i, name in enumerate(RARITY_ORDER)}


def rarity_color(rarity: str) -> str:
    """Return the accent color for a rarity, falling back to COMMON
    gray for unknown tiers. Single helper so the table above is
    the only place that needs updating when tbh.city adds tiers."""
    return RARITY.get(str(rarity or "").upper(), RARITY["COMMON"])


def rarity_tint(hex_color: str, alpha: int = 0x33) -> str:
    """Return ``hex_color`` with the given alpha byte appended as ``#rrggbbaa``."""
    if not (hex_color.startswith("#") and len(hex_color) == 7):
        raise ValueError(f"Expected #rrggbb, got {hex_color!r}")
    return f"{hex_color}{alpha:02x}"


_FONTS_DIR = Path(__file__).resolve().parent / "fonts"


def register_fonts() -> None:
    """Load bundled Cinzel + JetBrains Mono into the QFontDatabase.

    Idempotent — safe to call more than once. Silently no-ops if a font file
    is missing so the app still starts on a broken install.
    """
    from PySide6.QtGui import QFontDatabase  # local import keeps test boot fast

    for name in (
        "Cinzel-Regular.ttf",
        "Cinzel-Bold.ttf",
        "JetBrainsMono-Regular.ttf",
        "JetBrainsMono-Bold.ttf",
    ):
        path = _FONTS_DIR / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


# Unified QSS applied app-wide.  Prefix every rule with the app's widget
# types so the stylesheet does not leak into embedded web views if any.
_QSS = f"""
QMainWindow, QWidget {{
    background-color: {MOCHA['base']};
    color: {MOCHA['text']};
    font-size: 13px;
}}

/* ---- Toolbar ---- */
QToolBar {{
    background-color: {MOCHA['mantle']};
    border: none;
    border-bottom: 1px solid {MOCHA['surface0']};
    padding: 6px 8px;
    spacing: 6px;
}}
QToolBar QToolButton {{
    padding: 4px 8px;
}}

/* ---- Push buttons ---- */
QPushButton {{
    background-color: {MOCHA['surface0']};
    border: 1px solid {MOCHA['surface1']};
    border-radius: 6px;
    padding: 7px 16px;
    color: {MOCHA['text']};
    font-weight: 500;
    min-width: 80px;
}}
QPushButton:hover {{
    background-color: {MOCHA['surface1']};
    border-color: {MOCHA['blue']};
}}
QPushButton:pressed {{
    background-color: {MOCHA['surface2']};
}}
QPushButton:disabled {{
    background-color: {MOCHA['crust']};
    color: {MOCHA['overlay0']};
    border-color: {MOCHA['surface0']};
}}
QPushButton#btn_start {{
    background-color: {MOCHA['green']};
    color: {MOCHA['crust']};
    font-weight: 600;
    border: none;
}}
QPushButton#btn_start:hover {{
    background-color: #b5eea9;
}}
QPushButton#btn_start:disabled {{
    background-color: {MOCHA['surface0']};
    color: {MOCHA['overlay0']};
}}
QPushButton#btn_stop {{
    background-color: {MOCHA['red']};
    color: {MOCHA['crust']};
    font-weight: 600;
    border: none;
}}
QPushButton#btn_stop:hover {{
    background-color: #f5a3c1;
}}
QPushButton#btn_stop:disabled {{
    background-color: {MOCHA['surface0']};
    color: {MOCHA['overlay0']};
}}

/* ---- Line edits + spin boxes ---- */
QLineEdit, QSpinBox, QComboBox {{
    background-color: {MOCHA['mantle']};
    border: 1px solid {MOCHA['surface1']};
    border-radius: 5px;
    padding: 6px 10px;
    color: {MOCHA['text']};
    selection-background-color: {MOCHA['blue']};
    selection-color: {MOCHA['crust']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {MOCHA['blue']};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {MOCHA['mantle']};
    border: 1px solid {MOCHA['surface1']};
    selection-background-color: {MOCHA['surface0']};
    selection-color: {MOCHA['blue']};
    outline: none;
}}

/* ---- Table ---- */
QTableWidget {{
    background-color: {MOCHA['mantle']};
    alternate-background-color: {MOCHA['base']};
    gridline-color: {MOCHA['surface0']};
    border: 1px solid {MOCHA['surface0']};
    border-radius: 6px;
    selection-background-color: {MOCHA['surface0']};
    selection-color: {MOCHA['text']};
    outline: none;
}}
QTableWidget::item {{
    padding: 4px 6px;
}}
QHeaderView::section {{
    background-color: {MOCHA['surface0']};
    color: {MOCHA['subtext']};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {MOCHA['surface1']};
    border-bottom: 1px solid {MOCHA['surface1']};
    font-weight: 600;
}}

/* ---- Checkboxes ---- */
QCheckBox {{
    spacing: 8px;
    color: {MOCHA['text']};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {MOCHA['surface2']};
    border-radius: 4px;
    background-color: {MOCHA['mantle']};
}}
QCheckBox::indicator:checked {{
    background-color: {MOCHA['green']};
    border-color: {MOCHA['green']};
}}

/* ---- Group box ---- */
QGroupBox {{
    background-color: {MOCHA['base']};
    border: 1px solid {MOCHA['surface0']};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 600;
    color: {MOCHA['subtext']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {MOCHA['blue']};
}}

/* ---- List widget ---- */
QListWidget {{
    background-color: {MOCHA['mantle']};
    alternate-background-color: {MOCHA['base']};
    border: 1px solid {MOCHA['surface0']};
    border-radius: 6px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 5px 8px;
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background-color: {MOCHA['surface0']};
    color: {MOCHA['blue']};
}}

/* ---- Status / labels ---- */
QStatusBar {{
    background-color: {MOCHA['mantle']};
    color: {MOCHA['subtext']};
    border-top: 1px solid {MOCHA['surface0']};
}}
QLabel {{
    color: {MOCHA['text']};
    background: transparent;
}}

/* ---- Menubar ---- */
QMenuBar {{
    background-color: {MOCHA['mantle']};
    color: {MOCHA['text']};
    border-bottom: 1px solid {MOCHA['surface0']};
}}
QMenuBar::item:selected {{
    background-color: {MOCHA['surface0']};
}}
QMenu {{
    background-color: {MOCHA['mantle']};
    border: 1px solid {MOCHA['surface1']};
    color: {MOCHA['text']};
}}
QMenu::item:selected {{
    background-color: {MOCHA['surface0']};
}}

/* ---- Scroll bars ---- */
QScrollBar:vertical {{
    background: {MOCHA['mantle']};
    width: 10px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {MOCHA['surface1']};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {MOCHA['surface2']};
}}
QScrollBar:horizontal {{
    background: {MOCHA['mantle']};
    height: 10px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {MOCHA['surface1']};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {MOCHA['surface2']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px; width: 0px; border: none;
}}

/* ---- Splitter ---- */
QSplitter::handle {{
    background-color: {MOCHA['surface0']};
    width: 2px;
}}

/* ---- Dialog buttons ---- */
QDialogButtonBox QPushButton {{
    min-width: 90px;
    padding: 8px 20px;
}}

/* ---- Tooltips ---- */
QToolTip {{
    background-color: {MOCHA['crust']};
    color: {MOCHA['text']};
    border: 1px solid {MOCHA['surface1']};
    border-radius: 4px;
    padding: 4px 8px;
}}
"""


def apply_theme(app: QApplication) -> None:
    """Apply Catppuccin Mocha dark palette + global stylesheet to *app*."""
    # Palette
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(MOCHA["base"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(MOCHA["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(MOCHA["mantle"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(MOCHA["base"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(MOCHA["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(MOCHA["surface0"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(MOCHA["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(MOCHA["surface0"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(MOCHA["blue"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(MOCHA["crust"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(MOCHA["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(MOCHA["overlay0"]))
    app.setPalette(pal)
    app.setFont(QFont("Sans Serif", 10))
    app.setStyleSheet(
        _QSS + "\n"
        + arsenal_stylesheet() + "\n"
        + section_heading_style() + "\n"
        + status_badge_style(False) + "\n"
        + zone_label_style() + "\n"
        + panel_heading_style() + "\n"
        + empty_state_style() + "\n"
        + shell_splitter_style()
    )


def log_panel_style() -> str:
    """Return the QSS snippet for the log panel (terminal-like monospace).

    Includes an empty-state hint via ``QPlainTextEdit[empty='true']`` —
    shown when no log lines have been emitted yet, so the panel doesn't
    render as a featureless black rectangle on first launch.
    """
    return (
        f"QPlainTextEdit {{"
        f"  background: {MOCHA['crust']};"
        f"  color: {MOCHA['text']};"
        f"  font-family: 'FiraCode Nerd Font Mono', 'JetBrainsMono Nerd Font Mono',"
        f"    'Noto Sans Mono', monospace;"
        f"  font-size: 12px;"
        f"  border: 1px solid {MOCHA['surface0']};"
        f"  border-radius: 4px;"
        f"  padding: 4px;"
        f"}}"
        # Empty state — grey italic centered hint.
        f"QPlainTextEdit[empty='true'] {{"
        f"  color: {MOCHA['overlay0']};"
        f"  font-style: italic;"
        f"}}"
    )


def status_dot_style(running: bool) -> str:
    """Return QSS for the status dot label, green when running, red otherwise."""
    color = MOCHA["green"] if running else MOCHA["red"]
    return f"color: {color}; font-size: 18px;"


def status_badge_style(running: bool) -> str:
    """QSS for the labeled proxy-status badge (dot + text label).

    Replaces the bare floating dot. The dot + label pair is rendered as
    a single pill so the meaning is obvious — bare dots look like
    decoration, labeled badges look like status.
    """
    if running:
        bg, fg, dot = MOCHA["green"], MOCHA["crust"], MOCHA["green"]
    else:
        bg, fg, dot = MOCHA["surface1"], MOCHA["subtext"], MOCHA["red"]
    return (
        f"#status_badge {{"
        f"  background-color: {bg};"
        f"  color: {fg};"
        f"  border: none;"
        f"  border-radius: 10px;"
        f"  padding: 4px 12px 4px 10px;"
        f"  font-weight: 700;"
        f"  font-size: 11px;"
        f"  letter-spacing: 1px;"
        f"}}"
        f"#status_badge QLabel#status_badge_dot {{"
        f"  color: {dot};"
        f"  font-size: 12px;"
        f"}}"
        f"#status_badge QLabel#status_badge_label {{"
        f"  color: {fg};"
        f"  font-size: 11px;"
        f"  font-weight: 700;"
        f"  letter-spacing: 1px;"
        f"}}"
    )


def zone_label_style() -> str:
    """QSS for toolbar zone divider labels (PROXY · DATA · CONFIG · STEAM).

    Tiny uppercase labels that group toolbar buttons into intent zones,
    so the user can scan the toolbar in one glance instead of parsing
    nine flat buttons in a row.
    """
    return (
        f"QLabel#zone_label {{"
        f"  color: {MOCHA['overlay1']};"
        f"  font-family: 'Cinzel', serif;"
        f"  font-size: 10px;"
        f"  font-weight: 700;"
        f"  letter-spacing: 2px;"
        f"  padding: 0 6px;"
        f"  background: transparent;"
        f"}}"
        f"QLabel#zone_label[zone='accent'] {{"
        f"  color: {MOCHA['blue']};"
        f"}}"
    )


def panel_heading_style() -> str:
    """QSS for panel-level headings (LEFT panel, RIGHT panel, LOG).

    Distinct from ``section_heading`` (Cinzel decorative label) — these
    are functional headings that label major UI zones.
    """
    return (
        f"QLabel#panel_heading {{"
        f"  color: {MOCHA['subtext']};"
        f"  font-family: 'Cinzel', 'Cinzel-Regular', serif;"
        f"  font-size: 11px;"
        f"  font-weight: 700;"
        f"  letter-spacing: 3px;"
        f"  text-transform: uppercase;"
        f"  padding: 8px 12px 4px 12px;"
        f"  background: transparent;"
        f"}}"
        f"QLabel#panel_subheading {{"
        f"  color: {MOCHA['overlay1']};"
        f"  font-size: 11px;"
        f"  padding: 0 12px 6px 12px;"
        f"  background: transparent;"
        f"}}"
    )


def empty_state_style() -> str:
    """QSS for the empty-state hint inside the log panel + status panels.

    Renders as a centered italic muted message — used both by the log
    panel ("No log entries yet") and by the rule-detail panel when no
    rule is selected ("Select a rule on the left to edit it").
    """
    return (
        f"QLabel#empty_state {{"
        f"  color: {MOCHA['overlay0']};"
        f"  font-style: italic;"
        f"  font-size: 12px;"
        f"  padding: 24px;"
        f"  background: transparent;"
        f"}}"
    )


def shell_splitter_style() -> str:
    """QSS for the main horizontal splitter handle between Rules and Detail.

    Width is set programmatically via ``setHandleWidth(6)`` — do NOT
    override it in QSS or the programmatic value is silently lost.
    The handle gets a visible ``surface1`` background + a thin grip
    dot column so users can spot it as draggable.

    Why a grip dot column instead of ``background-image: radial-gradient``:
    PySide6 6.11's QSS engine silently drops ``background-image``
    declarations on ``::handle`` sub-controls (only the base splitter
    accepts them), so the gradient never paints. The fallback column
    of grip dots is drawn via a dotted border which Qt DOES render
    on handle sub-controls.
    """
    grip_color = MOCHA["overlay1"]
    return (
        f"QSplitter#main_splitter::handle {{"
        f"  background-color: {MOCHA['surface0']};"
        f"  border-left: 1px solid {MOCHA['mantle']};"
        f"  border-right: 1px solid {MOCHA['mantle']};"
        f"  border-top: 1px dotted {grip_color};"
        f"  border-bottom: 1px dotted {grip_color};"
        f"  margin: 6px 0;"
        f"}}"
        f"QSplitter#main_splitter::handle:hover {{"
        f"  background-color: {MOCHA['surface1']};"
        f"  border-left: 1px solid {MOCHA['blue']};"
        f"  border-right: 1px solid {MOCHA['blue']};"
        f"}}"
    )


def chip_style(rarity: str, *, compact: bool = False) -> str:
    """Border-only QSS for an :class:`ItemCard` instance.

    The background color is now applied via QPalette inside ItemCard
    itself (palette paints deterministically regardless of where the
    chip is reparented or what its objectName is — QSS dynamic-property
    selectors were unreliable for chips whose objectName got renamed
    by their parent layout).

    This function only returns the border (rarity-tinted left + neutral
    all-around) so callers can re-apply the QSS on rebuilds without
    overwriting the palette-managed background.
    """
    border_color = RARITY.get(rarity.upper(), RARITY["COMMON"])
    padding = "2px 6px" if compact else "4px 8px"
    note = " (compact)" if compact else ""
    return (
        f"QFrame {{"
        f"  border: 1px solid {MOCHA['surface1']};"
        f"  border-left: 2px solid {border_color};"
        f"  border-radius: 2px;"
        f"  background: transparent;"
        f"  padding: {padding};"
        f"  /* chip{note} */"
        f"}}"
    )


def section_heading_style() -> str:
    """QSS for QLabel#section_heading — Cinzel, wide letter-spacing, subtext hue."""
    return (
        f"QLabel#section_heading {{"
        f"  color: {MOCHA['subtext']};"
        f"  font-family: 'Cinzel', 'Cinzel-Regular', serif;"
        f"  font-size: 11px;"
        f"  font-weight: 600;"
        f"  letter-spacing: 2px;"
        f"  text-transform: uppercase;"
        f"  padding: 2px 0;"
        f"  background: transparent;"
        f"}}"
    )


def arsenal_stylesheet() -> str:
    """Arsenal Console QSS — toolbar zones, pulsing status dot, sharp corners.

    Returned as a single string to be appended to the global stylesheet (or
    applied with ``setStyleSheet``) without disturbing the existing palette.
    Square corners (2-3px), heavy left-border accents, monospace IDs.
    """
    return (
        # Toolbar height + bottom border.
        f"QToolBar#main_toolbar {{"
        f"  background-color: {MOCHA['mantle']};"
        f"  border-bottom: 1px solid {MOCHA['surface1']};"
        f"  padding: 6px 10px;"
        f"  spacing: 8px;"
        f"  min-height: 48px;"
        f"}}"
        # Primary zone (Start / Stop).
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='primary'] {{"
        f"  background-color: {MOCHA['surface0']};"
        f"  color: {MOCHA['text']};"
        f"  border: 1px solid {MOCHA['surface2']};"
        f"  border-radius: 2px;"
        f"  padding: 7px 16px;"
        f"  font-weight: 600;"
        f"  min-width: 92px;"
        f"}}"
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='primary']:hover {{"
        f"  border-color: {MOCHA['blue']};"
        f"  background-color: {MOCHA['surface1']};"
        f"}}"
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='primary'][name='btn_start'] {{"
        f"  background-color: {MOCHA['green']};"
        f"  color: {MOCHA['crust']};"
        f"  border-color: {MOCHA['green']};"
        f"}}"
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='primary'][name='btn_start']:hover {{"
        f"  background-color: #b5eea9;"
        f"}}"
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='primary'][name='btn_stop'] {{"
        f"  background-color: {MOCHA['red']};"
        f"  color: {MOCHA['crust']};"
        f"  border-color: {MOCHA['red']};"
        f"}}"
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='primary'][name='btn_stop']:hover {{"
        f"  background-color: #f5a3c1;"
        f"}}"
        # Secondary zone (Scrape / Check / Save / Reset) — blue outline only.
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='secondary'] {{"
        f"  background-color: transparent;"
        f"  color: {MOCHA['text']};"
        f"  border: 1px solid {MOCHA['surface1']};"
        f"  border-radius: 2px;"
        f"  padding: 6px 14px;"
        f"  min-width: 96px;"
        f"}}"
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='secondary']:hover {{"
        f"  border-color: {MOCHA['blue']};"
        f"  background-color: {MOCHA['surface0']};"
        f"}}"
        # Ghost zone (Copy Steam) — no fill.
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='ghost'] {{"
        f"  background-color: transparent;"
        f"  color: {MOCHA['subtext']};"
        f"  border: 1px dashed {MOCHA['surface1']};"
        f"  border-radius: 2px;"
        f"  padding: 6px 12px;"
        f"  min-width: 0;"
        f"}}"
        f"QToolBar#main_toolbar QPushButton[toolbar_zone='ghost']:hover {{"
        f"  color: {MOCHA['text']};"
        f"  border-color: {MOCHA['blue']};"
        f"}}"
        # Port input — monospace, fixed width.
        f"QToolBar#main_toolbar QLineEdit {{"
        f"  font-family: 'JetBrains Mono', 'JetBrainsMono Nerd Font Mono', monospace;"
        f"  font-size: 12px;"
        f"  background-color: {MOCHA['crust']};"
        f"  border: 1px solid {MOCHA['surface1']};"
        f"  border-radius: 2px;"
        f"  padding: 4px 8px;"
        f"  min-width: 80px;"
        f"  max-width: 80px;"
        f"  qproperty-alignment: 'AlignRight';"  # noqa: Q_PROPERTY
        f"}}"
        # Pulsing status dot.
        f"QLabel#status_dot_pulse {{"
        f"  color: {MOCHA['green']};"
        f"  font-size: 18px;"
        f"}}"
        # General toolbar separator tweak.
        f"QToolBar::separator {{"
        f"  background-color: {MOCHA['surface0']};"
        f"  width: 1px;"
        f"  margin: 6px 4px;"
        f"}}"
        # Square corner rule for embedded rule cards.
        f"#rule_card {{"
        f"  background-color: {MOCHA['mantle']};"
        f"  border: 1px solid {MOCHA['surface0']};"
        f"  border-left: 3px solid {MOCHA['surface0']};"
        f"  border-radius: 3px;"
        f"}}"
        f"#rule_card[active='true'] {{"
        f"  border-left: 3px solid {MOCHA['sapphire']};"
        f"  background-color: {MOCHA['base']};"
        f"}}"
    )
