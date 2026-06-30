"""About dialog — app identity, version, links, credits, license.

Replaces the bare ``QMessageBox.about`` previously wired to Help → About.
Themed (Catppuccin Mocha) to match the rest of the desktop shell.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from tbh_desktop import __app_name__, __version__
from tbh_desktop.paths import APP_ICON
from tbh_desktop.ui.theme import MOCHA

REPO_URL = "https://github.com/aikazu/tbh-reward-item"
SUPPORT_URL = "https://qrisly.net/kcmon"


def _open(url: str) -> None:
    """Open ``url`` in the user's default browser."""
    QDesktopServices.openUrl(QUrl(url))


class AboutDialog(QDialog):
    """Polished, themed About box — launched from Help → About."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("about_dialog")
        self.setWindowTitle(f"About {__app_name__}")
        self.setModal(True)
        if APP_ICON.exists():
            self.setWindowIcon(QIcon(str(APP_ICON)))

        bg = MOCHA["base"]
        card = MOCHA["surface0"]
        text = MOCHA["text"]
        subtext = MOCHA["subtext"]
        accent = MOCHA["mauve"]

        self.setStyleSheet(
            f"QDialog {{ background-color: {bg}; }}"
            f"QLabel {{ color: {text}; }}"
            f"QPushButton {{ background-color: {accent}; color: {MOCHA['crust']};"
            f" border: none; border-radius: 8px; padding: 8px 16px;"
            f" font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {MOCHA['lavender']}; }}"
            f"QPushButton:pressed {{ background-color: {MOCHA['surface1']}; }}"
            f"QPushButton[variant='secondary'] {{ background-color: {card};"
            f" color: {subtext}; }}"
            f"QPushButton[variant='secondary']:hover {{"
            f" background-color: {MOCHA['surface1']}; color: {text}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(34, 24, 34, 20)
        root.setSpacing(9)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ---- App icon ---------------------------------------------------
        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if APP_ICON.exists():
            pix = QPixmap(str(APP_ICON))
            if not pix.isNull():
                icon_lbl.setPixmap(
                    pix.scaledToWidth(
                        88, Qt.TransformationMode.SmoothTransformation
                    )
                )
        root.addWidget(icon_lbl)

        # ---- Name + version --------------------------------------------
        name = QLabel(__app_name__)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(
            f"color: {text}; font-family: 'Cinzel', serif; font-size: 18px;"
            f" font-weight: 700; letter-spacing: 2px;"
        )
        root.addWidget(name)

        ver = QLabel(f"v{__version__}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(
            f"color: {accent}; font-size: 11px; font-weight: 600;"
            f" letter-spacing: 1px;"
        )
        root.addWidget(ver)

        # ---- Description ------------------------------------------------
        desc = QLabel(
            "A man-in-the-middle proxy that rewrites <code>rewardItemId</code>"
            " in TaskBarHero backend responses, with an optional PySide6 GUI."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setTextFormat(Qt.TextFormat.RichText)
        desc.setStyleSheet(f"color: {subtext}; font-size: 11px;")
        root.addWidget(desc)

        # ---- DWYOR warning ---------------------------------------------
        warn = QLabel(
            "⚠ DWYOR — may violate the game's Terms of Service and risk"
            " account bans."
        )
        warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color: {MOCHA['peach']}; font-size: 10px;")
        root.addWidget(warn)

        # ---- Link buttons ----------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        repo = QPushButton("🔗  GitHub")
        repo.setProperty("variant", "secondary")
        repo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        repo.clicked.connect(lambda: _open(REPO_URL))
        btn_row.addWidget(repo)

        support = QPushButton("💝  Support")
        support.setProperty("variant", "secondary")
        support.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        support.clicked.connect(lambda: _open(SUPPORT_URL))
        btn_row.addWidget(support)

        btn_row.addStretch()
        root.addLayout(btn_row)

        # ---- Credits + license -----------------------------------------
        credit = QLabel(
            "Built on the <b>Persistent Reward Item Generator</b> technique"
            " researched by the UnknownCheats community."
        )
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setWordWrap(True)
        credit.setTextFormat(Qt.TextFormat.RichText)
        credit.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 10px;")
        root.addWidget(credit)

        lic = QLabel("MIT License · © 2026 aikazu")
        lic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lic.setStyleSheet(f"color: {MOCHA['overlay0']}; font-size: 10px;")
        root.addWidget(lic)

        # ---- Close ------------------------------------------------------
        close_row = QHBoxLayout()
        close_row.addStretch()
        close = QPushButton("Close")
        close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        close_row.addStretch()
        root.addLayout(close_row)
