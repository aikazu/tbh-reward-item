"""Global dark theme (Catppuccin Mocha) + shared style constants.

Apply once at app startup via :func:`apply_theme`. All widgets inherit the
palette; individual panels add their own accent rules where needed.
"""
from __future__ import annotations

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
    app.setStyleSheet(_QSS)


def log_panel_style() -> str:
    """Return the QSS snippet for the log panel (terminal-like monospace)."""
    return (
        f"QPlainTextEdit {{"
        f"  background: {MOCHA['crust']};"
        f"  color: {MOCHA['text']};"
        f"  font-family: 'FiraCode Nerd Font Mono', 'JetBrainsMono Nerd Font Mono',"
        f"    'Noto Sans Mono', monospace;"
        f"  font-size: 12px;"
        f"  border: 1px solid {MOCHA['surface0']};"
        f"  border-radius: 6px;"
        f"}}"
    )


def status_dot_style(running: bool) -> str:
    """Return QSS for the status dot label, green when running, red otherwise."""
    color = MOCHA["green"] if running else MOCHA["red"]
    return f"color: {color}; font-size: 18px;"
