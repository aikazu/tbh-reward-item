"""Single in-game item card with rarity-bordered frame.

Self-painted: the chip's background color is drawn directly in
``paintEvent`` rather than relying on QSS or QPalette, both of which
proved unreliable for chips that get reparented (rule cards rename
each chip to ``chip_<id>`` so multiple chips don't collide in QSS
lookups — but that also breaks ``#item_card`` selectors, and QPalette
backgrounds get clobbered by inherited parent palettes).

What you get:
- rarity-tinted background (low-alpha tint of the rarity color)
- rarity-colored left-border accent + neutral 1px border on the
  other three sides
- selected state: blue border + surface0 background (no tint)
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from tbh_desktop.scraper import derive_item_image_url
from tbh_desktop.ui.theme import MOCHA, RARITY, rarity_tint


def _hex(c: str) -> QColor:
    return QColor(c)


class ItemCard(QFrame):
    SIZE_FULL = 96
    SIZE_COMPACT = 48

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item_id: int = 0
        self._name: str = ""
        self._rarity: str = "COMMON"
        self._selected: bool = False
        self._compact: bool = False

        self.setObjectName("item_card")
        self.setFixedSize(self.SIZE_FULL, self.SIZE_FULL)
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setText("")  # populated later when ImageCache resolves
        layout.addWidget(self._icon_label, stretch=1)

        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setWordWrap(False)
        self._name_label.setStyleSheet("font-size: 11px; color: #cdd6f4;")
        layout.addWidget(self._name_label)

        self._refresh_style()

    # ---- public API --------------------------------------------------
    def set_data(self, item: dict) -> None:
        self._item_id = int(item.get("id", 0))
        self._name = str(item.get("name", ""))
        raw_rarity = str(item.get("rarity", "COMMON")).upper()
        new_rarity = raw_rarity if raw_rarity in RARITY else "COMMON"
        new_truncated = self._truncate(self._name, 14)
        if new_rarity == self._rarity and new_truncated == self._name_label.text():
            return  # no visible change
        self._rarity = new_rarity
        self._name_label.setText(new_truncated)
        self._refresh_style()
        # If the caller provided an explicit URL, use it; otherwise derive
        # from item id (the wiki always serves these paths for obtainable
        # items). Wire the global image cache to deliver the pixmap once
        # the background fetch resolves. Self-contained — callers don't
        # need their own ImageCache.
        explicit_url = str(item.get("image", "")).strip()
        image_url = explicit_url or derive_item_image_url(self._item_id)
        if image_url:
            self._request_icon(image_url)

    def _request_icon(self, image_url: str) -> None:
        """Kick off an icon fetch via the shared global ImageCache.

        The cache is process-wide so the same URL is fetched exactly once
        even if the chip appears in multiple places (rule card, detail
        panel, range form). Falls back silently if PySide6 isn't initialized.
        """
        try:
            from tbh_desktop.ui.image_cache import get_global_image_cache
            cache = get_global_image_cache()
        except Exception:
            return
        try:
            cache.icon_ready.connect(self._on_global_icon, Qt.ConnectionType.UniqueConnection)
        except Exception:
            # connect() may fail if cache was destroyed; fine.
            return
        cache.request(image_url, self._item_id)

    def _on_global_icon(self, item_id: int, icon) -> None:
        if item_id == self._item_id and icon is not None:
            # icon is a QIcon; extract a square QPixmap (QIcon.pixmap doesn't
            # accept AspectRatioMode — we let the label scale via
            # KeepAspectRatio on setPixmap with a QSize).
            size = self.SIZE_COMPACT - 8 if self._compact else 56
            self._icon_label.setPixmap(
                icon.pixmap(QSize(size, size))
            )


    def item_id(self) -> int:
        return self._item_id

    def name(self) -> str:
        return self._name

    def rarity(self) -> str:
        return self._rarity

    def rarity_color(self) -> str:
        return RARITY[self._rarity]

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self._refresh_style()

    def is_selected(self) -> bool:
        return self._selected

    def set_compact(self, compact: bool) -> None:
        if self._compact == compact:
            return
        self._compact = compact
        if compact:
            self.setFixedSize(self.SIZE_COMPACT * 2 + 24, self.SIZE_COMPACT)
            # Keep the name label visible in compact mode but render
            # it as a small inline label so the chip is identifiable
            # without needing to hover for the tooltip.
            self._name_label.setVisible(True)
            self._name_label.setStyleSheet(
                "font-size: 10px; color: #cdd6f4; padding-left: 4px;"
            )
        else:
            self.setFixedSize(self.SIZE_FULL, self.SIZE_FULL)
            self._name_label.setVisible(True)
            self._name_label.setStyleSheet(
                "font-size: 11px; color: #cdd6f4;"
            )

    def sizeHint(self) -> QSize:
        if self._compact:
            return QSize(self.SIZE_COMPACT * 2 + 24, self.SIZE_COMPACT)
        return QSize(self.SIZE_FULL, self.SIZE_FULL)

    def set_icon_pixmap(self, pixmap) -> None:
        """Optional: assign a QPixmap once ImageCache resolves the URL."""
        if pixmap is not None and not pixmap.isNull():
            size = self.SIZE_COMPACT - 8 if self._compact else 56
            self._icon_label.setPixmap(pixmap.scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    # ---- internals ---------------------------------------------------
    def _refresh_style(self) -> None:
        # No-op: styling is now applied in paintEvent so the chip renders
        # correctly regardless of where it's been reparented. Kept as a
        # method so callers that called ``set_data`` don't need to change.
        self.update()  # schedule a repaint with the new rarity/selection

    def paintEvent(self, event) -> None:  # noqa: ANN001
        """Draw background + border + contents manually.

        This bypasses QSS/QPalette entirely so the chip looks the same
        wherever it ends up in the tree (including after ``setParent``
        renames the objectName).
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRect(0, 0, self.width(), self.height())

        # Background — rarity tint or surface0 if selected.
        bg = (
            _hex(MOCHA["surface0"])
            if self._selected
            else _hex(rarity_tint(self.rarity_color()))
        )
        painter.fillRect(rect, QBrush(bg))

        # Left border accent (rarity color, 2px wide).
        accent_color = _hex(MOCHA["blue"] if self._selected else self.rarity_color())
        painter.fillRect(QRect(0, 0, 2, self.height()), QBrush(accent_color))

        # Outer border (1px neutral surface1, or 2px blue if selected).
        border_color = accent_color if self._selected else _hex(MOCHA["surface1"])
        border_width = 2 if self._selected else 1
        pen = QPen(border_color)
        pen.setWidth(border_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        # Let QFrame paint the child widgets (icon + name) on top.
        super().paintEvent(event)
        painter.end()

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        return text if len(text) <= max_len else text[: max_len - 1] + "…"
