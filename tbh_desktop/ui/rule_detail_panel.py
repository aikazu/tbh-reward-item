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
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
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
            # ItemCard self-styles via QPalette + QSS. Don't override its
            # stylesheet here — that turns off autoFillBackground and the
            # chip renders as an empty rectangle.
            chip.set_data({"id": item_id, "name": label, "rarity": rarity})
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

    pick_pool_id = Signal()
    pick_gear = Signal()  # open CatalogPopup pre-scoped to the Gear chip
    pick_item = Signal()  # open CatalogPopup pre-scoped to the Items chip
    remove_id_requested = Signal(int)  # item_id
    selection_cleared = Signal()  # user cleared the active target
    pool_id_changed = Signal(list)  # multi-pool edit -> main_window
    range_edited = Signal()  # user changed min/max/enabled → persist

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rule_detail_panel")
        self._target: RuleTarget | RangeTarget | None = None
        self._rule_name: str = ""
        self._reward_kind: str = "normal"
        self._pool_id: int | None = None
        self._replacement_ids: list[int] = []

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

        # ---- Form fields (pool chips row + range min/max row) --------
        # The detail panel shows ONE of two field rows depending on
        # which target is active:
        #   * RuleTarget   → _pool_field_row (multi-pool chip strip)
        #   * RangeTarget  → _range_field_row (min / max QSpinBox)
        # Both are kept in the same form layout and toggled via
        # setVisible in _show_rule_form / _show_range_form.
        self._pool_field_row = QWidget()
        pool_field_layout = QVBoxLayout(self._pool_field_row)
        pool_field_layout.setContentsMargins(0, 0, 0, 0)
        pool_field_layout.setSpacing(6)
        pool_field_label = QLabel("POOL IDS")
        pool_field_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 1px;"
        )
        pool_field_layout.addWidget(pool_field_label)
        # Chip strip — one chip per pool id, X to remove.
        self.pool_chip_row = _ChipRow()
        self.pool_chip_row.setObjectName("pool_chip_row_detail")
        self.pool_chip_row.remove_requested.connect(self._on_pool_chip_removed)
        pool_field_layout.addWidget(self.pool_chip_row)
        form_layout.addWidget(self._pool_field_row)

        # Legacy item_id_value / level_value stay around so any stale
        # QSS / tests that look them up by name keep working. They're
        # hidden; the panel no longer renders them.
        self.item_id_value = QLabel("(unused)")
        self.item_id_value.setObjectName("item_id_value")
        self.item_id_value.setVisible(False)
        self.level_value = QLabel("(unused)")
        self.level_value.setObjectName("level_value")
        self.level_value.setVisible(False)
        self.level_label = QLabel("")
        self.level_label.setVisible(False)

        # Range field row: min/max spinboxes. The enabled toggle
        # lives on the rule-list card (RangeCard) — single source of
        # truth for on/off so the user can't get confused by two
        # toggles disagreeing. This panel only edits min/max + chips.
        self._range_field_row = QWidget()
        range_layout = QHBoxLayout(self._range_field_row)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setSpacing(8)
        range_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        range_min_label = QLabel("min")
        range_min_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 1px;"
        )
        range_layout.addWidget(range_min_label)
        self.range_min_value = QSpinBox()
        self.range_min_value.setObjectName("range_min_value")
        self.range_min_value.setRange(0, 999_999)
        self.range_min_value.setFixedWidth(110)
        self.range_min_value.setGroupSeparatorShown(True)
        range_layout.addWidget(self.range_min_value)
        range_max_label = QLabel("max")
        range_max_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 1px;"
        )
        range_layout.addWidget(range_max_label)
        self.range_max_value = QSpinBox()
        self.range_max_value.setObjectName("range_max_value")
        self.range_max_value.setRange(0, 999_999)
        self.range_max_value.setFixedWidth(110)
        self.range_max_value.setGroupSeparatorShown(True)
        range_layout.addWidget(self.range_max_value)
        range_layout.addStretch()
        form_layout.addWidget(self._range_field_row)
        self._range_field_row.setVisible(False)
        # Wire range field edits back to main_window via a single signal.
        # main_window handles persisting to ConfigEditor's RangeState.
        self.range_min_value.valueChanged.connect(
            lambda _v: self.range_edited.emit()
        )
        self.range_max_value.valueChanged.connect(
            lambda _v: self.range_edited.emit()
        )

        # Pick buttons row. 'Pick pool' is hidden when the range rule is
        # selected (the range matches by itemId, not pool — offering a
        # 'Pick pool' button for a non-pool rule is misleading). 'Pick
        # gear' / 'Pick item' stay visible for both modes.
        self._btn_row = QWidget()
        btn_row = QHBoxLayout(self._btn_row)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        self.btn_pick_pool_id = QPushButton("Pick pool")
        self.btn_pick_pool_id.setObjectName("btn_pick_pool_id_detail")
        self.btn_pick_pool_id.setProperty("toolbar_zone", "secondary")
        self.btn_pick_pool_id.clicked.connect(self.pick_pool_id)
        btn_row.addWidget(self.btn_pick_pool_id)

        # Replacement items are split into two pickers so the user
        # never has to wade through a mixed gear+materials catalog:
        #   * Pick gear   — CatalogPopup pre-scoped to the Gear chip
        #                    (slot categories: Weapon / Off-hand /
        #                    Armor / Accessory).
        #   * Pick item   — CatalogPopup pre-scoped to the Items chip
        #                    (family categories: Crafting / Decoration /
        #                    Engraving / Inscription / Offering / Soulstone).
        # Both honour the rule's pool scope (the user can't pick
        # items that don't drop in the rule's pools).
        self.btn_pick_gear = QPushButton("Pick gear")
        self.btn_pick_gear.setObjectName("btn_pick_gear_detail")
        self.btn_pick_gear.setProperty("toolbar_zone", "secondary")
        self.btn_pick_gear.clicked.connect(self.pick_gear)
        btn_row.addWidget(self.btn_pick_gear)

        self.btn_pick_item = QPushButton("Pick item")
        self.btn_pick_item.setObjectName("btn_pick_item_detail")
        self.btn_pick_item.setProperty("toolbar_zone", "secondary")
        self.btn_pick_item.clicked.connect(self.pick_item)
        btn_row.addWidget(self.btn_pick_item)

        btn_row.addStretch()
        form_layout.addWidget(self._btn_row)

        # REPLACES WITH section.
        replaces_label = QLabel("REPLACES WITH")
        replaces_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 1px; padding-top: 4px;"
        )
        form_layout.addWidget(replaces_label)

        # Count badge + chip row.
        self.chip_count_label = QLabel("0 IDs (click chip to remove)")
        self.chip_count_label.setObjectName("chip_count_label")
        self.chip_count_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px;"
        )
        form_layout.addWidget(self.chip_count_label)

        # The chip row itself is a simple QHBoxLayout — QFlowLayout isn't
        # shipped with PySide6, and the manual flow-wrap we tried before
        # didn't trigger paint on first show. A flat horizontal strip is
        # easier to reason about and works fine for typical use (1-10
        # IDs per rule). When many chips are added the row scrolls
        # horizontally inside the panel.
        chip_container = QWidget()
        chip_layout = QHBoxLayout(chip_container)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setSpacing(6)
        self.chip_row = _ChipRow()
        self.chip_row.remove_requested.connect(self.remove_id_requested)
        chip_layout.addWidget(self.chip_row)
        # Don't addStretch — the chip row should size to its content so
        # the strip stays at the top of the form instead of being
        # stretched to fill the remaining vertical space (which would
        # push chips off-screen if there are many of them).
        # Limit the chip row height to one row of chips.
        chip_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        chip_container.setMaximumHeight(60)
        form_layout.addWidget(chip_container)

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

    def set_rule_data(
        self,
        *,
        name: str,
        reward_kind: str,
        pool_ids: list[int] | tuple[int, ...] | None,
        replacement_ids: list[int],
    ) -> None:
        """Populate the detail panel from a single rule's data.

        ``pool_ids`` is the v2 multi-pool field: a single rule can
        target several stage drop pools (e.g. Act 1 stages 1-9 Torment
        monster pool = 1 rule covering many drop_keys). The panel
        shows each as a removable chip; the underlying rule_card keeps
        the canonical tuple.

        MainWindow looks up the active rule card on selection change
        and calls this. Keeping the data source outside the panel
        avoids a circular import (the panel needs MainWindow to know
        what the rule list has — but MainWindow imports the panel).
        """
        pool_ids = tuple(int(p) for p in (pool_ids or []) if p is not None)
        self._target = RuleTarget(
            row=-1,
            rule_index=-1,
            reward_kind=reward_kind,
            pool_id=pool_ids[0] if pool_ids else None,
        )
        self._rule_name = name
        self._reward_kind = reward_kind
        self._pool_ids = pool_ids
        self._replacement_ids = list(replacement_ids)
        self._show_rule_form()

    def set_range_data(
        self,
        *,
        enabled: bool,
        match_min: int,
        match_max: int,
        replacement_ids: list[int],
    ) -> None:
        """Populate the detail panel from the range-replacement rule.

        The range rule lives at the bottom of the config (after the
        3 per-kind rule buckets) and matches by itemId range rather
        than pool. The same Pick replacement / chip row / X remove
        flow is shared with the per-kind rule form so the user has
        only one mental model.
        """
        self._target = RangeTarget()
        self._range_enabled = enabled
        self._range_min = match_min
        self._range_max = match_max
        self._range_replacement_ids = list(replacement_ids)
        self._show_range_form()

    def active_target(self) -> RuleTarget | RangeTarget | None:
        return self._target

    # ---- pool chip helpers -------------------------------------------
    def _refresh_pool_chips(self) -> None:
        """Populate the pool chip strip from ``self._pool_ids``."""
        self.pool_chip_row.set_ids(list(self._pool_ids))

    def _on_pool_chip_removed(self, pool_id: int) -> None:
        """Forward a chip-remove request from the detail panel to the
        underlying rule card, then re-render the detail panel.
        """
        target = self._target
        if not isinstance(target, RuleTarget):
            return
        # Drop the pool id from our local cache so the chip strip
        # updates immediately, then ask main_window to persist the
        # change back to the rule_card.
        new_pool_ids = [p for p in self._pool_ids if p != pool_id]
        self._pool_ids = tuple(new_pool_ids)
        self._refresh_pool_chips()
        # Re-emit so main_window can call back into the rule_list to
        # write the new pool_ids into the source rule_card.
        self.pool_id_changed.emit(list(self._pool_ids))

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

    def _show_range_form(self) -> None:
        """Show the range-replacement form (uses the same widget layout
        as the per-kind rule form, just with min/max inputs instead
        of the pool button). The user edits the range rule in the
        same panel they edit pool rules — no separate 'range summary'
        half-state that pretends to be editable but isn't."""
        self.empty_label.setVisible(False)
        self.form.setVisible(True)
        self.banner_name.setText("Pool range")
        self.banner_dot.setStyleSheet(
            f"color: {MOCHA['blue']}; font-size: 14px;"
        )
        self.banner_id.setVisible(False)
        self.subtitle_label.setText(
            "Range replacement — every itemId between min and max gets "
            "the replacements below (cycled in order). Use this as a "
            "fallback for items not covered by any pool rule."
        )
        # Range replaces the 'pool id' row with min / max side-by-side.
        self._pool_field_row.setVisible(False)
        self._range_field_row.setVisible(True)
        self.range_min_value.setValue(int(self._range_min))
        self.range_max_value.setValue(int(self._range_max))
        # Range doesn't have a pool — hide 'Pick pool' so the user
        # isn't tempted to bind this non-pool rule to one.
        self.btn_pick_pool_id.setVisible(False)
        self.chip_row.set_ids(self._range_replacement_ids)
        n = len(self._range_replacement_ids)
        self.chip_count_label.setText(
            f"{n} ID{'s' if n != 1 else ''} (cycled in order · click to remove)"
        )

    def _show_rule_form(self) -> None:
        self.empty_label.setVisible(False)
        self.form.setVisible(True)
        # Banner: rule name + dot + pool count summary. Multi-pool rules
        # show "N pools" instead of one ID; single-pool rules still
        # surface the drop_key for quick scanning.
        self.banner_name.setText(self._rule_name or "(unnamed rule)")
        self.banner_dot.setStyleSheet(
            f"color: {MOCHA['green']}; font-size: 14px;"
        )
        n_pools = len(self._pool_ids)
        if n_pools == 0:
            self.banner_id.setVisible(False)
        elif n_pools == 1:
            self.banner_id.setVisible(True)
            self.banner_id.setText(str(self._pool_ids[0]))
        else:
            self.banner_id.setVisible(True)
            self.banner_id.setText(f"{n_pools} pools")
        kind = self._reward_kind or "rule"
        self.subtitle_label.setText(
            f"Edit this {kind} rule's pool ids and the rewards it "
            "cycles through. Use Pick pool to add stages; Pick gear or "
            "Pick item to add replacements from each pool's drop table."
        )
        # Pool-id row visible; range row hidden.
        self._pool_field_row.setVisible(True)
        self._range_field_row.setVisible(False)
        # Rule has a pool — show 'Pick pool' again.
        self.btn_pick_pool_id.setVisible(True)
        # Render one chip per pool id so the user can see + remove each.
        self._refresh_pool_chips()
        self.chip_row.set_ids(self._replacement_ids)
        n = len(self._replacement_ids)
        self.chip_count_label.setText(
            f"{n} ID{'s' if n != 1 else ''} (cycled in order · click to remove)"
        )
