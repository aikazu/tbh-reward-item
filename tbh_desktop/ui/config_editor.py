"""Container: rule list (top) + range replacement form (bottom)
+ proxy mode form (controls mitmproxy --mode regular|local).

Public API kept compatible with the previous table-based editor so callers in
``main_window.py`` and the test suite do not change.
"""
from __future__ import annotations

import sys
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


class RangeState:
    """Headless holder for the range-replacement rule.

    Jul 2026: the range form USED to be a separate widget in the
    left-hand ConfigEditor splitter, which made the UI feel like
    two parallel forms. Now the right-hand RuleDetailPanel renders
    both pool rules AND range rules in the same form. RangeState is
    just the data layer (load / dump / add_ids / remove_id); the
    panel reads from and writes to it directly.
    """

    def __init__(self) -> None:
        self.enabled: bool = False
        self.name: str = "Pool range"
        self.min_pool_id: int = 0
        self.max_pool_id: int = 0
        self.replacement_reward_item_ids: list[int] = []

    def load(self, data: dict) -> None:
        self.enabled = bool(data.get("enabled", False))
        self.name = str(data.get("name", "Pool range"))
        self.min_pool_id = int(data.get("min_pool_id") or 0)
        self.max_pool_id = int(data.get("max_pool_id") or 0)
        self.replacement_reward_item_ids = [
            int(i) for i in (data.get("replacement_reward_item_ids") or [])
        ]

    def dump(self) -> dict:
        return {
            "enabled": self.enabled,
            "name": self.name,
            "min_pool_id": int(self.min_pool_id),
            "max_pool_id": int(self.max_pool_id),
            "replacement_reward_item_ids": list(self.replacement_reward_item_ids),
        }

    def add_ids(self, ids: list[int]) -> None:
        before = set(self.replacement_reward_item_ids)
        for i in ids:
            i = int(i)
            if i not in before:
                self.replacement_reward_item_ids.append(i)
                before.add(i)

    def remove_id(self, item_id: int) -> None:
        item_id = int(item_id)
        if item_id in self.replacement_reward_item_ids:
            self.replacement_reward_item_ids.remove(item_id)


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

        # ---- Strategy B: pendingTx rewrite toggle --------------------
        self.chk_rewrite_pending = QCheckBox("rewrite pendingTx (Strategy B)")
        self.chk_rewrite_pending.setToolTip(
            "Also rewrite pendingTx.gid + .tid in SteamItemInfo/mine to match "
            "the rewritten rewardItemId. Eliminates TamperedItemIdDetected for "
            "cross-suffix swaps. OFF by default — verify safe across sessions "
            "before enabling. See docs/analysis/strategy-b-tid-rewrite.md."
        )
        outer.addWidget(self.chk_rewrite_pending)

        # Enable/disable the name field based on mode (cosmetic — value
        # is still saved if user fills it before switching).
        self.radio_local.toggled.connect(self.edit_name.setEnabled)
        self.radio_regular.toggled.connect(self.edit_name.setDisabled)

    # ---- public API --------------------------------------------------
    def load(self, data: dict[str, Any]) -> None:
        # Mode resolution mirrors ``run_proxy._default_mode``: explicit
        # config wins, missing/unknown falls back to a platform-aware
        # default. Windows picks "local" (process injection via Win32
        # APIs is the recommended path per CLAUDE.md — no Steam Launch
        # Options needed); POSIX picks "regular" because local mode
        # requires root there, which we want to be an explicit choice.
        mode_obj = data.get("mode")
        if isinstance(mode_obj, str) and mode_obj.strip().lower() == "local":
            self.radio_local.setChecked(True)
        elif isinstance(mode_obj, str) and mode_obj.strip().lower() == "regular":
            self.radio_regular.setChecked(True)
        else:
            # No / unknown mode in config → platform-aware default.
            if sys.platform == "win32":
                self.radio_local.setChecked(True)
            else:
                self.radio_regular.setChecked(True)
        name = str(data.get("local_process_name", "") or "")
        if not name.strip():
            name = "TaskBarHero.exe"
        self.edit_name.setText(name)
        self.edit_name.setEnabled(self.radio_local.isChecked())
        # Strategy B default matches the addon side
        # (tbh_proxy_config._default_rewrite_pending_tx): ON on Windows,
        # OFF elsewhere. Mirrored here so the checkbox reflects what the
        # addon will actually do when ``rewrite_pending_tx`` is absent
        # from config.json — otherwise the user sees an unchecked
        # checkbox but the addon still rewrites.
        if "rewrite_pending_tx" in data:
            self.chk_rewrite_pending.setChecked(bool(data["rewrite_pending_tx"]))
        else:
            self.chk_rewrite_pending.setChecked(sys.platform == "win32")

    def dump(self) -> dict[str, Any]:
        return {
            "mode": "local" if self.radio_local.isChecked() else "regular",
            "local_process_name": self.edit_name.text().strip(),
            "rewrite_pending_tx": self.chk_rewrite_pending.isChecked(),
        }

    def mode(self) -> str:
        return "local" if self.radio_local.isChecked() else "regular"

    def local_process_name(self) -> str:
        return self.edit_name.text().strip()


class ConfigEditor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Stash the last-loaded raw data so dump() can preserve fields
        # the GUI doesn't edit (only_post, require_boxes_marker,
        # url_contains). Without this, saving from the GUI silently
        # wipes those fields from config.json.
        self._loaded_passthrough: dict[str, Any] = {}
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
        self._range_state = RangeState()
        self._mode_form = _ProxyModeForm()

        # Jul 2026: range replacement is edited in the right-side
        # ``RuleDetailPanel`` via ``set_range_data`` (focus on the
        # range row → ``RuleTarget(RangeTarget())`` → detail panel
        # switches to the min/max form). No duplicate form on the
        # left.

        self._splitter.addWidget(self._rule_list)
        self._splitter.addWidget(self._mode_form)
        # Rules get the dominant share (stretch 4) — mode form gets 1.
        # setStretchFactor controls resize proportionality; setSizes is
        # the initial pixel split but only takes effect if it fits in
        # the available height — the actual split gets computed on
        # first resize/show. We defer the setSizes call to after show
        # via _apply_initial_sizes below.
        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([600, 140])
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

        # ---- Add-rule buttons (one per reward kind) ---------------------
        # Default rules (Normal / Boss / Act Reward) are pre-loaded in
        # config.default.json — no "+ Add rule" buttons needed (the
        # user just enables the existing cards). The X button on each
        # rule card removes a rule if the user no longer needs it.

        # The detail panel handles range editing via set_range_data.
        # MainWindow calls editor.range_state() to read/write the
        # headless state holder. The detail panel + rule list stay
        # in sync because main_window routes set_range_data and
        # range_state mutation through the same RangeState instance.
        self._active_target_kind: str = "none"

    # ---- public API (back-compat) -----------------------------------
    def load(self, data: dict[str, Any]) -> None:
        self._rule_list.load(data)
        self._range_state.load(data.get("range_replacement") or {})
        self._mode_form.load(data)
        # Preserve fields the GUI doesn't edit so dump() roundtrips them.
        # These are set-once in config.default.json and rarely changed;
        # if the user hand-edited them, a GUI save shouldn't wipe them.
        self._loaded_passthrough = {
            k: data[k]
            for k in ("only_post", "require_boxes_marker", "url_contains")
            if k in data
        }

    def dump(self) -> dict[str, Any]:
        out = self._rule_list.dump()
        out["range_replacement"] = self._range_state.dump()
        # Merge mode + local_process_name into the dump. These live at the
        # top level of config.json (parallel to normal_rules / boss_rules /
        # act_rules / range_replacement), so we update out directly rather
        # than tucking them under a sub-key.
        out.update(self._mode_form.dump())
        # Preserve passthrough fields so GUI save doesn't wipe them.
        out.update(self._loaded_passthrough)
        return out

    def mode_form(self) -> _ProxyModeForm:
        return self._mode_form

    def rule_list(self) -> RuleListView:
        return self._rule_list

    def range_state(self) -> RangeState:
        return self._range_state

    def selected_rule_pool_id(self) -> int | None:
        return self._rule_list.selected_rule_pool_id()

    def set_selected_rule_pool_id(self, pool_id: int) -> None:
        self._rule_list.set_selected_rule_pool_id(pool_id)

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
        self._range_state.add_ids(ids)
        # Mirror into the rule_list's own range cache so dump()
        # picks up the change.
        self._rule_list._range["replacement_reward_item_ids"] = list(
            self._range_state.replacement_reward_item_ids
        )

    def add_rule(self, reward_kind: str) -> int:
        """Public passthrough to RuleListView.add_rule for the kind buttons."""
        row = self._rule_list.add_rule(reward_kind)
        # Auto-select the newly-added row so the picker can target it.
        self._rule_list.select_row(row)
        return row

    def remove_rule(self, row: int) -> None:
        self._rule_list.remove_rule(row)

    # ---- internals ---------------------------------------------------
    def _on_add_rule(self, reward_kind: str) -> None:
        self.add_rule(reward_kind)

    # ---- event filter (rule list focus) ------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        from PySide6.QtCore import QEvent
        # Range form is gone (range now lives in the detail panel).
        # The rule list focuses here on clicks; emit a rule_selected
        # so the detail panel populates.
        if event.type() == QEvent.Type.FocusIn and obj is self._rule_list:
            return False  # let Qt do its default; rule_selected already wired
        return super().eventFilter(obj, event)
