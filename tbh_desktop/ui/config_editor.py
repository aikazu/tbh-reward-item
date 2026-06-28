"""Container: rule list (top) + range replacement form (bottom)
+ proxy mode form (controls mitmproxy --mode regular|local).

Public API kept compatible with the previous table-based editor so callers in
``main_window.py`` and the test suite do not change.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSplitter,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.paths import DROPS_INDEX_CACHE
from tbh_desktop.ui.active_target import RangeTarget
from tbh_desktop.ui.item_card import ItemCard
from tbh_desktop.ui.rule_card import resolve_item_label
from tbh_desktop.ui.rule_list import RuleListView
from tbh_desktop.ui.theme import MOCHA, chip_style, section_heading_style

# Re-exported so tests can monkeypatch the cache path used by the range form.
_DROPS_INDEX_PATH = DROPS_INDEX_CACHE

_MONO_FONT = QFont("JetBrains Mono", 11)
_MONO_FONT.setStyleHint(QFont.StyleHint.Monospace)
_MONO_FONT.setFamily("JetBrains Mono")


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("section_heading")
    label.setStyleSheet(section_heading_style())
    return label


def _mono_input(*, placeholder: str = "") -> QLineEdit:
    edit = QLineEdit()
    edit.setFont(_MONO_FONT)
    if placeholder:
        edit.setPlaceholderText(placeholder)
    edit.setMinimumWidth(120)
    return edit


def _ghost_button(text: str, *, tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("toolbar_zone", "ghost")
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


class _RangeForm(QWidget):
    """Inline range replacement form. Emits pick_gear / pick_item when the
    respective ghost button is clicked; MainWindow wires those to its
    picker dialogs (same pattern as RuleDetailPanel)."""

    pick_gear = Signal()
    pick_item = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("range_form")
        self._chips: list[ItemCard] = []
        self._replacement_ids: list[int] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(10)

        # ---- Header: title + enabled toggle ----------------------------
        header = QHBoxLayout()
        header.setSpacing(8)
        self.section_heading = _section_label("RANGE REPLACEMENT")
        header.addWidget(self.section_heading)
        header.addStretch()
        self.chk_enabled = QCheckBox("enabled")
        self.chk_enabled.setToolTip("Enable range replacement (matches by item id range)")
        header.addWidget(self.chk_enabled)
        outer.addLayout(header)

        # ---- MATCH ITEM ID section -------------------------------------
        outer.addWidget(_section_label("MATCH ITEM ID"))
        id_row = QHBoxLayout()
        id_row.setSpacing(12)
        from_col = QVBoxLayout()
        self.lbl_min = QLabel("from")
        self.lbl_min.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 10px;")
        self.edit_min = _mono_input(placeholder="500000")
        from_col.addWidget(self.lbl_min)
        from_col.addWidget(self.edit_min)
        to_col = QVBoxLayout()
        self.lbl_max = QLabel("to")
        self.lbl_max.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 10px;")
        self.edit_max = _mono_input(placeholder="950000")
        to_col.addWidget(self.lbl_max)
        to_col.addWidget(self.edit_max)
        id_row.addLayout(from_col)
        id_row.addLayout(to_col)
        id_row.addStretch()
        outer.addLayout(id_row)

        # ---- REPLACES WITH section -------------------------------------
        outer.addWidget(_section_label("REPLACES WITH"))
        self.edit_ids = _mono_input(placeholder="605041, 605051, 605061")
        self.edit_ids.setMinimumWidth(0)
        self.edit_ids.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer.addWidget(self.edit_ids)

        # ---- chip row (visual mirror of the IDs above) -----------------
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(6)
        self._chip_row.addStretch()
        outer.addLayout(self._chip_row)

        # ---- pick buttons ----------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_pick_gear = _ghost_button("Pick gear", tooltip="Pick a gear item from cache")
        self.btn_pick_gear.setObjectName("btn_pick_gear_range")
        self.btn_pick_gear.clicked.connect(self.pick_gear)
        self.btn_pick_item = _ghost_button("Pick item", tooltip="Pick a non-gear item from the drops index")
        self.btn_pick_item.setObjectName("btn_pick_item_range")
        self.btn_pick_item.clicked.connect(self.pick_item)
        btn_row.addWidget(self.btn_pick_gear)
        btn_row.addWidget(self.btn_pick_item)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        # ---- bottom rule line ------------------------------------------
        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setFrameShadow(QFrame.Shadow.Plain)
        rule.setStyleSheet(f"color: {MOCHA['surface0']}; background: {MOCHA['surface0']};")
        rule.setFixedHeight(1)

    # ---- public API --------------------------------------------------
    def load(self, data: dict) -> None:
        self.chk_enabled.setChecked(bool(data.get("enabled", False)))
        self.edit_min.setText(str(data.get("match_min_item_id") or ""))
        self.edit_max.setText(str(data.get("match_max_item_id") or ""))
        ids = data.get("replacement_reward_item_ids") or []
        self.edit_ids.setText(", ".join(str(i) for i in ids))
        self._replacement_ids = [int(i) for i in ids]
        self._rebuild_chips()

    def dump(self) -> dict:
        def _i(s: str) -> int:
            try:
                return int((s or "").strip())
            except ValueError:
                return 0
        return {
            "enabled": self.chk_enabled.isChecked(),
            "name": "Range replacement",
            "match_min_item_id": _i(self.edit_min.text()),
            "match_max_item_id": _i(self.edit_max.text()),
            "replacement_reward_item_ids": list(self._replacement_ids),
        }

    def add_ids(self, ids: list[int]) -> None:
        before = set(self._replacement_ids)
        for i in ids:
            if i not in before:
                self._replacement_ids.append(int(i))
                before.add(int(i))
        self.edit_ids.setText(", ".join(str(i) for i in self._replacement_ids))
        self._rebuild_chips()

    def _rebuild_chips(self) -> None:
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        for i, item_id in enumerate(self._replacement_ids):
            label, rarity = resolve_item_label(item_id)
            chip = ItemCard(self)
            chip.set_compact(True)
            chip.setObjectName(f"range_chip_{item_id}")
            chip.set_data({"id": item_id, "name": label, "rarity": rarity})
            chip.setStyleSheet(chip_style(rarity, compact=True))
            chip.setToolTip(f"{label} (#{item_id}) — click to remove")
            chip.mousePressEvent = lambda _e, _id=item_id: self._remove_id(_id)  # type: ignore[method-assign]
            self._chip_row.insertWidget(i, chip)
            self._chips.append(chip)

    def _remove_id(self, item_id: int) -> None:
        if item_id in self._replacement_ids:
            self._replacement_ids.remove(item_id)
            self.edit_ids.setText(", ".join(str(i) for i in self._replacement_ids))
            self._rebuild_chips()


class _ProxyModeForm(QWidget):
    """Controls mitmproxy's ``--mode regular|local`` and process name.

    Regular: bind listen_port on 0.0.0.0, client must set HTTP_PROXY.
    Local:   spawn the named process with proxy auto-injected (no system
             proxy, no Steam Launch Options). On Linux this needs root;
             ``tbh_desktop.linux_elevation`` re-execs the GUI under pkexec
             before we get here.

    Why a UI for this: the field used to live in config.json only, with
    no GUI hookup. Users had to hand-edit JSON to switch modes. Worse,
    ``ConfigEditor.dump()`` didn't roundtrip ``mode`` / ``local_process_name``,
    so saving the rules wiped them out. This widget fixes both.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("proxy_mode_form")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        # ---- Header ---------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(_section_label("PROXY MODE"))
        header.addStretch()
        outer.addLayout(header)

        # ---- Radio buttons: regular / local --------------------------
        mode_row = QHBoxLayout()
        mode_row.setSpacing(16)
        self.radio_regular = QRadioButton("regular")
        self.radio_regular.setToolTip(
            "Bind listen_port on 0.0.0.0. Configure HTTP_PROXY on the client "
            "(e.g. Steam Launch Options on Linux)."
        )
        self.radio_local = QRadioButton("local")
        self.radio_local.setToolTip(
            "Spawn the named process with proxy env + CA cert auto-injected. "
            "No Steam Launch Options needed. On Linux, this needs root — "
            "the GUI prompts for polkit password on launch."
        )
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.radio_regular, 0)
        self._mode_group.addButton(self.radio_local, 1)
        mode_row.addWidget(self.radio_regular)
        mode_row.addWidget(self.radio_local)
        mode_row.addStretch()
        outer.addLayout(mode_row)

        # ---- Process name (only meaningful for local mode) -----------
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        lbl = QLabel("process name")
        lbl.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 10px;")
        self.edit_name = _mono_input(placeholder="TaskBarHero.exe")
        self.edit_name.setToolTip(
            "Executable name to spawn under the local redirector. "
            "On Linux/Proton the top-level process is usually the "
            "Windows binary name (TaskBarHero.exe). Verify with "
            "`pgrep -af <name>` while the game is running."
        )
        name_row.addWidget(lbl)
        name_row.addWidget(self.edit_name, 1)
        outer.addLayout(name_row)

        # Enable/disable the name field based on mode (cosmetic — value
        # is still saved if user fills it before switching).
        self.radio_local.toggled.connect(self.edit_name.setEnabled)
        self.radio_regular.toggled.connect(self.edit_name.setDisabled)

    # ---- public API --------------------------------------------------
    def load(self, data: dict[str, Any]) -> None:
        # Default to local + TaskBarHero.exe when the user has no
        # explicit mode yet. The whole point of this tool is to scope
        # interception to the game process so the user doesn't have to
        # wire Steam Launch Options or system proxy settings — if we
        # default to "regular" we silently force them into that.
        mode = data.get("mode")
        if isinstance(mode, str) and mode.strip().lower() == "local":
            self.radio_local.setChecked(True)
        elif isinstance(mode, str) and mode.strip().lower() == "regular":
            self.radio_regular.setChecked(True)
        else:
            # No / unknown mode in config → default to local.
            self.radio_local.setChecked(True)
        name = str(data.get("local_process_name", "") or "")
        if not name.strip():
            name = "TaskBarHero.exe"
        self.edit_name.setText(name)
        self.edit_name.setEnabled(self.radio_local.isChecked())

    def dump(self) -> dict[str, Any]:
        return {
            "mode": "local" if self.radio_local.isChecked() else "regular",
            "local_process_name": self.edit_name.text().strip(),
        }

    def mode(self) -> str:
        return "local" if self.radio_local.isChecked() else "regular"

    def local_process_name(self) -> str:
        return self.edit_name.text().strip()


class ConfigEditor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Vertical splitter between rules list (top, larger) and range
        # form (bottom, smaller). The splitter handle is draggable so
        # users can resize either pane; default sizes give rules the
        # dominant share but range form is ALWAYS visible — no toggle
        # to click through (toggles are annoying "2x checklist to
        # enable" friction).
        from PySide6.QtWidgets import QSplitter
        from tbh_desktop.ui.theme import MOCHA

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._splitter.setObjectName("rules_range_splitter")
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)

        self._rule_list = RuleListView()
        self._range_form = _RangeForm()
        self._mode_form = _ProxyModeForm()

        # Wrap range form in a labelled container so users see what it is.
        self._range_wrap = QWidget()
        range_layout = QVBoxLayout(self._range_wrap)
        range_layout.setContentsMargins(0, 4, 0, 0)
        range_layout.setSpacing(4)
        range_heading = QLabel("RANGE REPLACEMENT")
        range_heading.setObjectName("panel_heading")
        range_heading.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 2px; padding: 0 4px;"
        )
        range_layout.addWidget(range_heading)
        range_layout.addWidget(self._range_form)

        self._splitter.addWidget(self._rule_list)
        self._splitter.addWidget(self._range_wrap)
        self._splitter.addWidget(self._mode_form)
        # Rules get the dominant share (stretch 4) — range form + mode
        # form each get 1. setStretchFactor controls resize
        # proportionality; setSizes is the initial pixel split but only
        # takes effect if it fits in the available height — the actual
        # split gets computed on first resize/show. We defer the setSizes
        # call to after show via _apply_initial_sizes below.
        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 1)
        self._splitter.setSizes([520, 160, 140])
        outer.addWidget(self._splitter)
        # Apply the requested sizes once the widget is visible — without
        # this the initial paint uses Qt's default 50/50 split and the
        # user sees range form eating half the panel even though our
        # intent was 75/25. Guard with try/except — Qt's C++ splitter
        # can be deleted before the singleShot fires during teardown
        # (test teardown, window close), raising RuntimeError.
        from PySide6.QtCore import QTimer
        def _apply_split_sizes():
            try:
                self._splitter.setSizes([520, 160, 140])
            except RuntimeError:
                pass  # splitter already destroyed
        QTimer.singleShot(0, _apply_split_sizes)

        # Make the range form focus set the active target to RangeTarget.
        for w in (
            self._range_form.chk_enabled,
            self._range_form.edit_min,
            self._range_form.edit_max,
            self._range_form.edit_ids,
        ):
            w.installEventFilter(self)
        self._active_target_kind: str = "none"

    # ---- public API (back-compat) -----------------------------------
    def load(self, data: dict[str, Any]) -> None:
        self._rule_list.load(data)
        self._range_form.load(data.get("range_replacement") or {})
        self._mode_form.load(data)

    def dump(self) -> dict[str, Any]:
        out = self._rule_list.dump()
        out["range_replacement"].update(self._range_form.dump())
        # Merge mode + local_process_name into the dump. These live at the
        # top level of config.json (parallel to specific_queue_rules /
        # range_replacement), so we update out directly rather than
        # tucking them under a sub-key.
        out.update(self._mode_form.dump())
        return out

    def mode_form(self) -> _ProxyModeForm:
        return self._mode_form

    def rule_list(self) -> RuleListView:
        return self._rule_list

    def range_form(self) -> _RangeForm:
        return self._range_form

    def selected_rule_item_id(self) -> int | None:
        return self._rule_list.selected_rule_item_id()

    def selected_rule_level(self) -> int | None:
        return self._rule_list.selected_rule_level()

    def set_selected_rule_item_id(self, box_id: int, level: int | None) -> None:
        self._rule_list.set_selected_rule_item_id(box_id, level)

    def add_ids_to_selected_rule(self, ids: list[int]) -> None:
        self._rule_list.add_ids_to_selected_rule(ids)

    def add_ids_to_active_target(self, ids: list[int]) -> None:
        """Route ids to whichever target is currently active (rule or range)."""
        target = self._rule_list.active_target()
        if isinstance(target, RangeTarget):
            self.add_ids_to_range(ids)
        else:
            self.add_ids_to_selected_rule(ids)

    def add_ids_to_range(self, ids: list[int]) -> None:
        # Route through the active-target system for symmetry.
        self._rule_list.set_active_target(RangeTarget())
        self._range_form.add_ids(ids)
        self._rule_list._range["replacement_reward_item_ids"] = list(
            self._range_form._replacement_ids
        )

    # ---- event filter (range form focus) ----------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.FocusIn and obj in (
            self._range_form.chk_enabled,
            self._range_form.edit_min,
            self._range_form.edit_max,
            self._range_form.edit_ids,
        ):
            self._rule_list.set_active_target(RangeTarget())
        return super().eventFilter(obj, event)
