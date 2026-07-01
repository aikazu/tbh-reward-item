"""Tests for ConfigEditor: keeps load/dump API, delegates to RuleListView.

Jul 2026 — tbh.city migration: ConfigEditor now writes three rule buckets
(normal_rules / boss_rules / act_rules) keyed by pool_id, plus the
pool-range form. The range form's pick buttons collapsed from
(pick_gear + pick_item) to a single pick_replacement.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.config_editor import ConfigEditor


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
        "match_min_item_id": 0, "match_max_item_id": 0,
        "replacement_reward_item_ids": [7],
    },
}


def test_config_editor_load_dump_round_trip(qapp: QApplication) -> None:
    editor = ConfigEditor()
    editor.load(SAMPLE)
    out = editor.dump()
    # Each kind bucket present in dump.
    assert "normal_rules" in out
    assert "boss_rules" in out
    assert "act_rules" in out
    assert out["range_replacement"]["replacement_reward_item_ids"] == [7]


def test_config_editor_exposes_rule_list(qapp: QApplication) -> None:
    editor = ConfigEditor()
    editor.load(SAMPLE)
    # 3 default cards (Normal / Boss / Act).
    assert editor.rule_list().row_count() == 3


def test_range_form_has_section_heading(qapp: QApplication) -> None:
    """Arsenal directive: the range form shows a Cinzel section heading."""
    editor = ConfigEditor()
    heading = editor.range_form().findChild(type(editor.range_form().section_heading))
    assert heading is not None
    assert heading.objectName() == "section_heading"
    assert "POOL" in heading.text().upper() or "RANGE" in heading.text().upper()


def test_range_form_mono_inputs_have_from_to_labels(qapp: QApplication) -> None:
    """match_min / match_max use mono font + have explicit 'from'/'to' sublabels."""
    editor = ConfigEditor()
    rf = editor.range_form()
    families = " ".join(rf.edit_min.font().families()).lower()
    assert "mono" in families or "jetbrains" in families
    assert rf.lbl_min.text().lower() == "from"
    assert rf.lbl_max.text().lower() == "to"


def test_range_form_pick_button_is_ghost_zone(qapp: QApplication) -> None:
    """The range form has a single 'Pick replacement' button declared as
    toolbar_zone='ghost' so it picks up the outline-only QSS from
    arsenal_stylesheet()."""
    editor = ConfigEditor()
    rf = editor.range_form()
    assert rf.btn_pick_item.property("toolbar_zone") == "ghost"


def test_range_form_chips_show_added_ids(qapp: QApplication, tmp_path, monkeypatch) -> None:
    """add_ids_to_range rebuilds the range form chip row from the live list."""
    import json
    drops = tmp_path / "drops_index.json"
    drops.write_text(json.dumps([
        {"id": 605041, "name": "Gold Amulet", "rarity": "LEGENDARY"}
    ]))
    monkeypatch.setattr("tbh_desktop.ui.config_editor._DROPS_INDEX_PATH", drops)
    editor = ConfigEditor()
    editor.load(SAMPLE)
    editor.add_ids_to_range([605041])
    out = editor.dump()
    assert 605041 in out["range_replacement"]["replacement_reward_item_ids"]
    # SAMPLE pre-loads id 7, so we expect 2 chips (7 + 605041).
    assert len(editor.range_form()._chips) == 2


def test_range_form_pick_button_emits_signal(qapp: QApplication) -> None:
    """Clicking Pick replacement on the range form must emit its signal
    so MainWindow can open the picker dialog."""
    editor = ConfigEditor()
    rf = editor.range_form()
    captured = []
    rf.pick_replacement.connect(lambda: captured.append("pick"))
    rf.btn_pick_item.click()
    assert captured == ["pick"]


def test_config_editor_loads_three_default_rules(qapp: QApplication) -> None:
    """Default rules (Normal / Boss / Act Reward) are loaded from
    config — they're not added via a button. The X on each card
    removes one if the user doesn't need it. The picker can add a
    custom rule via the rule_list.add_rule() API (used by tests
    and the desktop's "+ Add rule" flow if a future iteration wants
    it back)."""
    editor = ConfigEditor()
    editor.load(SAMPLE)
    # 3 default cards (Normal + Boss + Act).
    assert editor.rule_list().row_count() == 3
    # _rule_list.add_rule is still the API for adding custom rules.
    out_before = editor.dump()
    editor.rule_list().add_rule("act", {
        "enabled": True, "name": "Custom Act", "reward_kind": "act",
        "pool_ids": [9301011], "replacement_reward_item_ids": [],
    })
    out_after = editor.dump()
    assert len(out_after["act_rules"]) == len(out_before["act_rules"]) + 1


def test_proxy_form_strategy_b_default_on_windows(qapp: QApplication, monkeypatch) -> None:
    """Strategy B checkbox defaults to checked on Windows when the
    config doesn't specify ``rewrite_pending_tx``. Mirrors the addon
    side (tbh_proxy_config._default_rewrite_pending_tx) so the UI
    shows what will actually run."""
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
    """Explicit ``False`` in config overrides the Windows default.
    No surprise upgrade for users who deliberately disabled it."""
    import tbh_desktop.ui.config_editor as ce_mod
    monkeypatch.setattr(ce_mod.sys, "platform", "win32")
    editor = ConfigEditor()
    editor.load({**SAMPLE, "rewrite_pending_tx": False})
    assert editor._mode_form.chk_rewrite_pending.isChecked() is False