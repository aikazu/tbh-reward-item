"""Tests for ConfigEditor: load/dump round-trip + range state.

Jul 2026: the range form is gone — it lives as a card in the rule
list (RangeCard) and is edited via the right-hand RuleDetailPanel.
RangeState is the headless data layer that backs both.
"""
from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.active_target import RangeTarget
from tbh_desktop.ui.config_editor import ConfigEditor, RangeState


SAMPLE = {
    "normal_rules": [
        {"enabled": True, "name": "Normal Reward", "reward_kind": "normal",
         "pool_ids": [9100111], "replacement_reward_item_ids": [1, 2]},
    ],
    "boss_rules": [
        {"enabled": False, "name": "Boss Reward", "reward_kind": "boss",
         "pool_ids": [], "replacement_reward_item_ids": []},
    ],
    "act_rules": [
        {"enabled": False, "name": "Act Reward", "reward_kind": "act",
         "pool_ids": [], "replacement_reward_item_ids": []},
    ],
    "range_replacement": {
        "enabled": False, "name": "Pool range",
        "min_pool_id": 0, "max_pool_id": 0,
        "replacement_reward_item_ids": [7],
    },
}


def test_config_editor_load_dump_round_trip(qapp: QApplication) -> None:
    editor = ConfigEditor()
    editor.load(SAMPLE)
    out = editor.dump()
    assert "normal_rules" in out
    assert "boss_rules" in out
    assert "act_rules" in out
    assert out["range_replacement"]["replacement_reward_item_ids"] == [7]


def test_config_editor_exposes_rule_list(qapp: QApplication) -> None:
    editor = ConfigEditor()
    editor.load(SAMPLE)
    assert editor.rule_list().row_count() == 3


def test_range_state_load_dump_round_trip() -> None:
    """Headless RangeState reads config schema and round-trips it."""
    rs = RangeState()
    rs.load({
        "enabled": True,
        "name": "Pool range",
        "min_pool_id": 100,
        "max_pool_id": 200,
        "replacement_reward_item_ids": [605041],
    })
    assert rs.enabled is True
    assert rs.min_pool_id == 100
    assert rs.max_pool_id == 200
    assert rs.replacement_reward_item_ids == [605041]
    out = rs.dump()
    assert out == {
        "enabled": True,
        "name": "Pool range",
        "min_pool_id": 100,
        "max_pool_id": 200,
        "replacement_reward_item_ids": [605041],
    }


def test_range_state_add_ids_dedups(qapp: QApplication) -> None:
    editor = ConfigEditor()
    rs = editor.range_state()
    rs.add_ids([100, 200, 100])  # 100 dup'd
    assert rs.replacement_reward_item_ids == [100, 200]
    rs.remove_id(100)
    assert rs.replacement_reward_item_ids == [200]


def test_config_editor_no_separate_range_form_widget(qapp: QApplication) -> None:
    """The range form widget is gone from the splitter; range is
    edited in the right-hand RuleDetailPanel via set_range_data."""
    editor = ConfigEditor()
    assert not hasattr(editor, "_range_form")
    assert hasattr(editor, "_range_state")
    assert hasattr(editor, "range_state")


def test_rule_list_has_range_card(qapp: QApplication) -> None:
    """The rule list renders a RangeCard as the last row (after Act
    rules) so the user can click it to switch the detail panel to
    range form."""
    editor = ConfigEditor()
    editor.load(SAMPLE)
    view = editor.rule_list()
    # 3 default rule cards + 1 range card = 4 rows total
    assert view.model().rowCount() == 4
    range_idx = view.model().index(3, 0)
    assert view.indexWidget(range_idx) is view._range_card


def test_range_rule_selected_emits_range_target(qapp: QApplication) -> None:
    """Selecting the range row emits a RangeTarget."""
    editor = ConfigEditor()
    editor.load(SAMPLE)
    view = editor.rule_list()
    captured: list[RangeTarget] = []
    view.rule_selected.connect(lambda t: captured.append(t))
    idx = view.model().index(3, 0)
    view.selectionModel().setCurrentIndex(
        idx, QItemSelectionModel.SelectionFlag.SelectCurrent
    )
    assert len(captured) == 1
    assert isinstance(captured[0], RangeTarget)


def test_range_card_enabled_checkbox_toggles(qapp: QApplication) -> None:
    """The range card has a real QCheckBox (not a status badge).
    Toggling it emits range_toggled so main_window can persist."""
    editor = ConfigEditor()
    editor.load(SAMPLE)
    view = editor.rule_list()
    captured: list[bool] = []
    view.range_toggled.connect(lambda v: captured.append(v))
    # SAMPLE has enabled=False for range rule.
    assert view._range_card.is_enabled() is False
    view._range_card.chk_enabled.setChecked(True)
    assert captured == [True]
    view._range_card.chk_enabled.setChecked(False)
    assert captured == [True, False]


def test_range_card_block_signals_during_set_data(qapp: QApplication) -> None:
    """set_data must not fire toggled — only user clicks should."""
    editor = ConfigEditor()
    editor.load({**SAMPLE,
                 "range_replacement": {
                     "enabled": True, "name": "Pool range",
                     "min_pool_id": 100, "max_pool_id": 200,
                     "replacement_reward_item_ids": [],
                 }})
    view = editor.rule_list()
    captured: list[bool] = []
    view.range_toggled.connect(lambda v: captured.append(v))
    # Reload — set_data fires on each rule including the range card,
    # so the captured list should stay empty if blockSignals works.
    editor.load({**SAMPLE,
                 "range_replacement": {
                     "enabled": False, "name": "Pool range",
                     "min_pool_id": 0, "max_pool_id": 0,
                     "replacement_reward_item_ids": [],
                 }})
    assert captured == []
    assert view._range_card.is_enabled() is False


def test_config_editor_add_ids_to_range(qapp: QApplication) -> None:
    """add_ids_to_range writes to RangeState + mirror in rule_list."""
    editor = ConfigEditor()
    editor.load(SAMPLE)
    editor.add_ids_to_range([605041])
    out = editor.dump()
    assert 605041 in out["range_replacement"]["replacement_reward_item_ids"]
    # SAMPLE pre-loads id 7, so expect 2 total.
    assert len(out["range_replacement"]["replacement_reward_item_ids"]) == 2


def test_config_editor_loads_three_default_rules(qapp: QApplication) -> None:
    """Default rules (Normal / Boss / Act Reward) are loaded from
    config — they're not added via a button. The X on each card
    removes one if the user doesn't need it."""
    editor = ConfigEditor()
    editor.load(SAMPLE)
    assert editor.rule_list().row_count() == 3
    out_before = editor.dump()
    editor.rule_list().add_rule("act", {
        "enabled": True, "name": "Custom Act", "reward_kind": "act",
        "pool_ids": [9301011], "replacement_reward_item_ids": [],
    })
    out_after = editor.dump()
    assert len(out_after["act_rules"]) == len(out_before["act_rules"]) + 1


def test_proxy_form_strategy_b_default_on_windows(qapp: QApplication, monkeypatch) -> None:
    """Strategy B checkbox defaults to checked on Windows when the
    config doesn't specify ``rewrite_pending_tx``."""
    import tbh_desktop.ui.config_editor as ce_mod
    monkeypatch.setattr(ce_mod.sys, "platform", "win32")
    editor = ConfigEditor()
    editor.load(SAMPLE)
    assert editor._mode_form.chk_rewrite_pending.isChecked() is True


def test_proxy_form_strategy_b_default_off_on_linux(qapp: QApplication, monkeypatch) -> None:
    import tbh_desktop.ui.config_editor as ce_mod
    monkeypatch.setattr(ce_mod.sys, "platform", "linux")
    editor = ConfigEditor()
    editor.load(SAMPLE)
    assert editor._mode_form.chk_rewrite_pending.isChecked() is False


def test_proxy_form_strategy_b_explicit_value_respected(qapp: QApplication, monkeypatch) -> None:
    """Explicit ``False`` in config overrides the Windows default."""
    import tbh_desktop.ui.config_editor as ce_mod
    monkeypatch.setattr(ce_mod.sys, "platform", "win32")
    editor = ConfigEditor()
    editor.load({**SAMPLE, "rewrite_pending_tx": False})
    assert editor._mode_form.chk_rewrite_pending.isChecked() is False