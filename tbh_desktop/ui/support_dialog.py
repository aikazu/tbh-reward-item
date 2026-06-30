"""Support dialog — QRIS donation popup shown on each app launch.

Modal ``QDialog`` with the QRIS image + a link to ``qrisly.net/kcmon``.
``main.py`` pops it up once per launch, right after the main window
appears. Closing it (or clicking the link button) lets the app continue.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from tbh_desktop.paths import REPO_ROOT
from tbh_desktop.ui.theme import MOCHA

QRIS_IMAGE = REPO_ROOT / "qris.webp"
SUPPORT_URL = "https://qrisly.net/kcmon"


def _open_link() -> None:
    """Open the support URL in the user's default browser."""
    QDesktopServices.openUrl(QUrl(SUPPORT_URL))


class _ClickableQRLabel(QLabel):
    """QLabel that opens the support URL when its pixmap is clicked."""

    def mousePressEvent(self, event) -> None:  # noqa: D401, ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            _open_link()
        super().mousePressEvent(event)


class SupportDialog(QDialog):
    """Themed QRIS support popup — one per launch."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("support_dialog")
        self.setWindowTitle("Support the Project")
        self.setModal(True)

        bg = MOCHA["base"]
        card = MOCHA["surface0"]
        text = MOCHA["text"]
        subtext = MOCHA["subtext"]
        accent = MOCHA["mauve"]

        # NOTE: ``flat`` is a reserved QPushButton property, so use a custom
        # ``variant`` property for the secondary (Close) button styling.
        self.setStyleSheet(
            f"QDialog {{ background-color: {bg}; }}"
            f"QLabel {{ color: {text}; }}"
            f"QPushButton {{ background-color: {accent}; color: {MOCHA['crust']};"
            f" border: none; border-radius: 8px; padding: 8px 18px;"
            f" font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {MOCHA['lavender']}; }}"
            f"QPushButton:pressed {{ background-color: {MOCHA['surface1']}; }}"
            f"QPushButton[variant='secondary'] {{ background-color: {card};"
            f" color: {subtext}; }}"
            f"QPushButton[variant='secondary']:hover {{"
            f" background-color: {MOCHA['surface1']}; color: {text}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 22)
        root.setSpacing(10)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ---- Heading ----------------------------------------------------
        emoji = QLabel("💝")
        emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emoji.setStyleSheet("font-size: 34px;")
        root.addWidget(emoji)

        title = QLabel("Support the Project")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {text}; font-family: 'Cinzel', serif; font-size: 16px;"
            f" font-weight: 700; letter-spacing: 2px;"
        )
        root.addWidget(title)

        subtitle = QLabel(
            "If this tool saved you time, consider supporting its development."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {subtext}; font-size: 11px;")
        root.addWidget(subtitle)

        # ---- QRIS image (clickable) ------------------------------------
        self._qr = _ClickableQRLabel()
        self._qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._qr.setToolTip(f"Click to open {SUPPORT_URL}")
        if QRIS_IMAGE.exists():
            pix = QPixmap(str(QRIS_IMAGE))
            if not pix.isNull():
                self._qr.setPixmap(
                    pix.scaledToWidth(
                        260, Qt.TransformationMode.SmoothTransformation
                    )
                )
            else:
                self._qr.setText("[QRIS image unavailable]")
                self._qr.setStyleSheet(f"color: {subtext}; font-size: 11px;")
        else:
            self._qr.setText(f"[qris.webp missing — visit {SUPPORT_URL}]")
            self._qr.setStyleSheet(f"color: {subtext}; font-size: 11px;")
        root.addWidget(self._qr)

        caption = QLabel("Scan the QRIS above, or click the button below.")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setStyleSheet(f"color: {subtext}; font-size: 10px;")
        root.addWidget(caption)

        # ---- Buttons ----------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        visit = QPushButton("🔗  Visit qrisly.net/kcmon")
        visit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        visit.clicked.connect(_open_link)
        btn_row.addWidget(visit)

        close = QPushButton("Close")
        close.setProperty("variant", "secondary")
        close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        btn_row.addWidget(close)

        btn_row.addStretch()
        root.addLayout(btn_row)
