"""Right-pane detail editor for the currently selected rule.

When the user picks a rule from the left list, this panel takes over and
shows everything they need to edit that one rule:

  - Header: rule name + status dot (active/inactive)
  - Item ID field (with mono font) + Level field
  - REPLACES WITH chip row + 3 Pick buttons
  - Empty state hint when no rule is selected

Why this exists: the previous right pane was an ItemBrowser (a 6-tab
catalog of every item in the game). That catalog is useful as a *picker*
(it opens inside modal dialogs), but it shouldn't be the primary surface
the user stares at — the primary surface should be the rule they're
editing. This widget fills that gap.

Public API mirrors the parts of ``RuleCard`` MainWindow already needed
so the wiring stays compatible with the existing rule_list signals:

  - ``set_target(target)`` — pass a ``RuleTarget`` (rule on left) or
    ``RangeTarget`` (range form); None clears + shows empty state.
  - ``pick_box_id``, ``pick_box_loot``, ``pick_gear`` — re-emit the
    underlying ``RuleCard`` signals so MainWindow's slot handlers
    continue to work unchanged.

The widget owns its own ``RuleCard`` instance for the selected rule
plus a chip strip that mirrors ``RuleCard._replacement_ids``. When the
selection changes, it copies the data out of the source card and
re-binds the chip strip + buttons to the new rule.

Range-target rendering shows a stripped-down summary pointing the user
to the range form (which already lives at the bottom of the left panel
via ``ConfigEditor._range_form`` — we don't duplicate it here, we just
explain that the range form is where range replacements are edited).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.active_target import RangeTarget, RuleTarget
from tbh_desktop.ui.item_card import ItemCard
from tbh_desktop.ui.rule_card import resolve_item_label
from tbh_desktop.ui.theme import MOCHA, chip_style, panel_heading_style


def _mono_font(size: int = 11) -> QFont:
    font = QFont("JetBrains Mono", size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFamily("JetBrains Mono")
    return font


def _panel_heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("panel_heading")
    label.setStyleSheet(panel_heading_style())
    return label


def _panel_subheading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("panel_subheading")
    label.setStyleSheet(panel_heading_style())
    label.setWordWrap(True)
    return label


class _ChipRow(QWidget):
    """Replacement-id chip strip with click-to-remove.

    Mirrors ``RuleCard._chip_row`` behavior but standalone, so the detail
    panel can manage its own chip strip without poking into RuleCard's
    private state.
    """

    remove_requested = Signal(int)  # emits item_id to remove

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chips: list[ItemCard] = []
        self._ids: list[int] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addStretch()
        self._layout = layout

    def set_ids(self, ids: list[int]) -> None:
        self._ids = [int(i) for i in ids]
        self._rebuild()

    def _rebuild(self) -> None:
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        # Stretch is index 0; insert chips before it.
        for i, item_id in enumerate(self._ids):
            label, rarity = resolve_item_label(item_id)
            chip = ItemCard(self)
            chip.set_compact(True)
            chip.setObjectName(f"detail_chip_{item_id}")
            chip.set_data({"id": item_id, "name": label, "rarity": rarity})
            chip.setStyleSheet(chip_style(rarity, compact=True))
            chip.setToolTip(f"{label} (#{item_id}) — click to remove")
            # Click → request removal. Wrap in default-arg capture so the
            # bound id doesn't change if more chips are added later.
            chip.mousePressEvent = (
                lambda _e, _id=item_id: self.remove_requested.emit(_id)
            )
            self._layout.insertWidget(i, chip)
            self._chips.append(chip)


class RuleDetailPanel(QWidget):
    """Right-pane editor for the currently selected rule.

    Emits the same signals as a ``RuleCard`` (``pick_box_id``,
    ``pick_box_loot``, ``pick_gear``) so the existing MainWindow slot
    handlers keep working without rewiring.
    """

    pick_box_id = Signal()
    pick_box_loot = Signal()
    pick_gear = Signal()
    remove_id_requested = Signal(int)  # item_id
    selection_cleared = Signal()  # user cleared the active target

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rule_detail_panel")
        self._target: RuleTarget | RangeTarget | None = None
        self._rule_name: str = ""
        self._item_id: int | None = None
        self._replacement_ids: list[int] = []
        self._level: int | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Header: panel title + active-rule banner --------------------
        header = QWidget()
        header.setObjectName("detail_header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        self.title_label = _panel_heading("RULE DETAIL")
        header_layout.addWidget(self.title_label)

        self.subtitle_label = _panel_subheading(
            "Select a rule on the left to edit its item ID, level, and reward picks."
        )
        header_layout.addWidget(self.subtitle_label)

        # Active-rule banner: shows the selected rule name + status dot.
        self.banner = QFrame()
        self.banner.setObjectName("active_rule_banner")
        self.banner.setStyleSheet(
            f"#active_rule_banner {{"
            f"  background-color: {MOCHA['mantle']};"
            f"  border: 1px solid {MOCHA['surface0']};"
            f"  border-radius: 4px;"
            f"  margin: 8px 12px 4px 12px;"
            f"  padding: 10px 12px;"
            f"}}"
        )
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        banner_layout.setSpacing(10)

        self.banner_dot = QLabel("●")
        self.banner_dot.setObjectName("banner_dot")
        self.banner_dot.setFixedWidth(12)
        self.banner_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner_layout.addWidget(self.banner_dot)

        self.banner_name = QLabel("(no rule selected)")
        self.banner_name.setObjectName("banner_name")
        self.banner_name.setStyleSheet(
            f"color: {MOCHA['text']}; font-size: 14px; font-weight: 600;"
        )
        banner_layout.addWidget(self.banner_name, stretch=1)

        self.banner_id = QLabel("")
        self.banner_id.setObjectName("banner_id")
        self.banner_id.setFont(_mono_font(12))
        self.banner_id.setStyleSheet(
            f"color: {MOCHA['blue']}; background: {MOCHA['crust']};"
            f" border: 1px solid {MOCHA['surface1']}; border-radius: 3px;"
            f" padding: 3px 8px;"
        )
        banner_layout.addWidget(self.banner_id)

        header_layout.addWidget(self.banner)
        outer.addWidget(header)

        # ---- Body: empty state + edit form -------------------------------
        self.body_stack = QWidget()
        body_layout = QVBoxLayout(self.body_stack)
        body_layout.setContentsMargins(12, 8, 12, 12)
        body_layout.setSpacing(10)
        outer.addWidget(self.body_stack, stretch=1)

        # Empty state — shown when no rule is selected.
        self.empty_label = QLabel(
            "No rule selected.\n\n"
            "Click a rule on the left, or the range form at the bottom of "
            "the rules panel, to edit its rewards."
        )
        self.empty_label.setObjectName("empty_state")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        body_layout.addWidget(self.empty_label, stretch=1)

        # Edit form — only visible when a rule is selected. Hidden initially.
        self.form = QWidget()
        self.form.setObjectName("rule_detail_form")
        form_layout = QVBoxLayout(self.form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)

        # Item ID + Level row.
        id_row = QHBoxLayout()
        id_row.setSpacing(10)
        id_col = QVBoxLayout()
        id_label = QLabel("ITEM ID")
        id_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 1px;"
        )
        self.item_id_value = QLabel("—")
        self.item_id_value.setObjectName("item_id_value")
        self.item_id_value.setFont(_mono_font(14))
        self.item_id_value.setStyleSheet(
            f"color: {MOCHA['text']}; background: {MOCHA['crust']};"
            f" border: 1px solid {MOCHA['surface1']}; border-radius: 3px;"
            f" padding: 6px 10px;"
        )
        self.item_id_value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        id_col.addWidget(id_label)
        id_col.addWidget(self.item_id_value)
        id_row.addLayout(id_col, stretch=2)

        level_col = QVBoxLayout()
        level_label = QLabel("LEVEL")
        level_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 1px;"
        )
        self.level_value = QLabel("—")
        self.level_value.setObjectName("level_value")
        self.level_value.setFont(_mono_font(14))
        self.level_value.setStyleSheet(
            f"color: {MOCHA['text']}; background: {MOCHA['crust']};"
            f" border: 1px solid {MOCHA['surface1']}; border-radius: 3px;"
            f" padding: 6px 10px;"
        )
        self.level_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.level_value.setFixedWidth(80)
        level_col.addWidget(level_label)
        level_col.addWidget(self.level_value)
        id_row.addLayout(level_col)
        form_layout.addLayout(id_row)

        # Pick buttons row.
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_pick_box_id = QPushButton("Pick box")
        self.btn_pick_box_id.setObjectName("btn_pick_box_id_detail")
        self.btn_pick_box_id.setProperty("toolbar_zone", "secondary")
        self.btn_pick_box_id.clicked.connect(self.pick_box_id)
        btn_row.addWidget(self.btn_pick_box_id)

        self.btn_pick_box_loot = QPushButton("Pick loot")
        self.btn_pick_box_loot.setObjectName("btn_pick_box_loot_detail")
        self.btn_pick_box_loot.setProperty("toolbar_zone", "secondary")
        self.btn_pick_box_loot.clicked.connect(self.pick_box_loot)
        btn_row.addWidget(self.btn_pick_box_loot)

        self.btn_pick_gear = QPushButton("Pick gear")
        self.btn_pick_gear.setObjectName("btn_pick_gear_detail")
        self.btn_pick_gear.setProperty("toolbar_zone", "secondary")
        self.btn_pick_gear.clicked.connect(self.pick_gear)
        btn_row.addWidget(self.btn_pick_gear)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        # REPLACES WITH section.
        replaces_label = QLabel("REPLACES WITH")
        replaces_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 1px; padding-top: 4px;"
        )
        form_layout.addWidget(replaces_label)

        # Count badge + chip row in a vertical layout so the chips wrap.
        chips_container = QWidget()
        chips_layout = QVBoxLayout(chips_container)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(6)

        self.chip_count_label = QLabel("0 IDs (click chip to remove)")
        self.chip_count_label.setObjectName("chip_count_label")
        self.chip_count_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px;"
        )
        chips_layout.addWidget(self.chip_count_label)

        self.chip_row = _ChipRow()
        self.chip_row.remove_requested.connect(self.remove_id_requested)
        chips_layout.addWidget(self.chip_row)

        # Wrap-friendly container so chips overflow gracefully on narrow
        # windows instead of pushing the panel width to infinity.
        # Use a custom FlowLayout (PySide6 doesn't ship QFlowLayout).
        self._chip_wrap = _FlowWrap(self.chip_row)
        chips_layout.addWidget(self._chip_wrap)

        form_layout.addWidget(chips_container)

        # Initially hidden — empty state shows first.
        self.form.setVisible(False)
        body_layout.addWidget(self.form, stretch=1)

        # Hint footer.
        hint = QLabel(
            "Tips:\n"
            "  • Use Pick box to set the box/item ID for this rule.\n"
            "  • Use Pick loot to add rewards from that box's drop table.\n"
            "  • Use Pick gear to add rewards from the gear cache (any category).\n"
            "  • Click a chip to remove that ID from the replacement list."
        )
        hint.setObjectName("detail_hint")
        hint.setStyleSheet(
            f"color: {MOCHA['overlay0']}; font-size: 11px;"
            f" padding: 10px 14px; background: {MOCHA['mantle']};"
            f" border: 1px solid {MOCHA['surface0']}; border-radius: 4px;"
            f" margin-top: 8px;"
        )
        hint.setWordWrap(True)
        form_layout.addWidget(hint)

    # ---- public API --------------------------------------------------
    def show_empty(self) -> None:
        """Show the empty state (no rule selected)."""
        self._target = None
        self._show_empty_state()

    def show_range_summary(self) -> None:
        """Show the range-form summary (range target active)."""
        self._target = RangeTarget()
        self._show_range_summary()

    def set_rule_data(
        self,
        *,
        name: str,
        item_id: int | None,
        level: int | None,
        replacement_ids: list[int],
    ) -> None:
        """Populate the detail panel from a single rule's data.

        MainWindow looks up the active rule card on selection change and
        calls this. Keeping the data source outside the panel avoids a
        circular import (the panel needs MainWindow to know what the
        rule list has — but MainWindow imports the panel).
        """
        self._target = RuleTarget(row=-1, rule_index=-1, box_id=item_id, level=level)
        self._rule_name = name
        self._item_id = item_id
        self._replacement_ids = list(replacement_ids)
        self._level = level
        self._show_rule_form()

    # ---- state helpers -----------------------------------------------
    def _show_empty_state(self) -> None:
        self.empty_label.setVisible(True)
        self.form.setVisible(False)
        self.banner_name.setText("(no rule selected)")
        self.banner_dot.setStyleSheet(f"color: {MOCHA['overlay0']}; font-size: 14px;")
        self.banner_id.setVisible(False)
        self.subtitle_label.setText(
            "Select a rule on the left to edit its item ID, level, and reward picks."
        )

    def _show_range_summary(self) -> None:
        self.empty_label.setVisible(False)
        self.form.setVisible(False)
        self.banner_name.setText("Range replacement")
        self.banner_dot.setStyleSheet(f"color: {MOCHA['blue']}; font-size: 14px;")
        self.banner_id.setVisible(False)
        self.subtitle_label.setText(
            "Edit range replacement settings in the RANGE REPLACEMENT form "
            "at the bottom of the rules panel on the left."
        )

    def _show_rule_form(self) -> None:
        self.empty_label.setVisible(False)
        self.form.setVisible(True)
        # Banner: rule name + dot + item id.
        self.banner_name.setText(self._rule_name or "(unnamed rule)")
        self.banner_dot.setStyleSheet(f"color: {MOCHA['green']}; font-size: 14px;")
        self.banner_id.setVisible(True)
        self.banner_id.setText(
            f"#{self._item_id}" if self._item_id is not None else "no item ID"
        )
        self.subtitle_label.setText(
            "Edit this rule's item ID, level, and the rewards it cycles through."
        )
        # Form fields.
        self.item_id_value.setText(
            str(self._item_id) if self._item_id is not None else "—"
        )
        self.level_value.setText(
            str(self._level) if self._level is not None else "—"
        )
        # Chip row.
        self.chip_row.set_ids(self._replacement_ids)
        n = len(self._replacement_ids)
        self.chip_count_label.setText(
            f"{n} ID{'s' if n != 1 else ''} (cycled in order · click to remove)"
        )


class _FlowWrap(QWidget):
    """Minimal flow layout that wraps children to the next row on overflow.

    PySide6 doesn't ship ``QFlowLayout`` (Qt 6.10+ only, not in the
    stable releases we target). This widget manually relayouts its
    children to wrap when the row width exceeds the available width.
    Sized to its tallest single row so it doesn't grow vertically
    beyond what the chips need.
    """

    def __init__(self, child: QWidget | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._children: list[QWidget] = []
        self._spacing = 6
        if child is not None:
            child.setParent(self)
            self._children.append(child)

    def addWidget(self, w: QWidget) -> None:
        w.setParent(self)
        self._children.append(w)
        self._relayout()

    def setSpacing(self, spacing: int) -> None:
        self._spacing = spacing
        self._relayout()

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        if not self._children:
            self.setMinimumHeight(0)
            return
        x, y = 0, 0
        row_height = 0
        avail = max(self.width(), 100)
        for w in self._children:
            hint = w.sizeHint()
            if x + hint.width() > avail and x > 0:
                # Wrap to next row.
                x = 0
                y += row_height + self._spacing
                row_height = 0
            w.move(x, y)
            w.resize(hint.width(), hint.height())
            x += hint.width() + self._spacing
            row_height = max(row_height, hint.height())
        self.setMinimumHeight(y + row_height)
