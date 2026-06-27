"""Single in-game item card with rarity-bordered frame."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from tbh_desktop.ui.theme import MOCHA, RARITY, rarity_tint


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
            self.setFixedSize(self.SIZE_COMPACT * 2, self.SIZE_COMPACT)
            self._name_label.setVisible(False)
        else:
            self.setFixedSize(self.SIZE_FULL, self.SIZE_FULL)
            self._name_label.setVisible(True)

    def sizeHint(self) -> QSize:
        if self._compact:
            return QSize(self.SIZE_COMPACT * 2, self.SIZE_COMPACT)
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
        border_color = MOCHA["blue"] if self._selected else self.rarity_color()
        border_width = 2 if self._selected else 1
        bg = MOCHA["surface0"] if self._selected else rarity_tint(self.rarity_color())
        self.setStyleSheet(
            f"#item_card {{"
            f"  background-color: {bg};"
            f"  border: {border_width}px solid {border_color};"
            f"  border-radius: 8px;"
            f"}}"
        )

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        return text if len(text) <= max_len else text[: max_len - 1] + "…"
