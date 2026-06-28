"""Tests for ConfigEditor: keeps load/dump API, delegates to RuleListView."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.config_editor import ConfigEditor


SAMPLE = {
    "specific_queue_rules": [
        {"enabled": True, "name": "R1", "item_id": 100, "replacement_reward_item_ids": [1, 2]},
    ],
    "range_replacement": {
        "enabled": False, "name": "Range replacement",
        "match_min_item_id": 0, "match_max_item_id": 0,
        "replacement_reward_item_ids": [7],
    },
}


def test_config_editor_load_dump_round_trip(qapp: QApplication) -> None:
    editor = ConfigEditor()
    editor.load(SAMPLE)
    out = editor.dump()
    assert out["specific_queue_rules"] == SAMPLE["specific_queue_rules"]
    assert out["range_replacement"]["replacement_reward_item_ids"] == [7]


def test_config_editor_exposes_rule_list(qapp: QApplication) -> None:
    editor = ConfigEditor()
    editor.load(SAMPLE)
    assert editor.rule_list().row_count() == 1


def test_range_form_has_section_heading(qapp: QApplication) -> None:
    """Arsenal directive: the range form shows a Cinzel section heading."""
    editor = ConfigEditor()
    heading = editor.range_form().findChild(type(editor.range_form().section_heading))
    assert heading is not None
    assert heading.objectName() == "section_heading"
    assert "RANGE" in heading.text().upper()


def test_range_form_mono_inputs_have_from_to_labels(qapp: QApplication) -> None:
    """match_min / match_max use mono font + have explicit 'from'/'to' sublabels."""
    editor = ConfigEditor()
    rf = editor.range_form()
    families = " ".join(rf.edit_min.font().families()).lower()
    assert "mono" in families or "jetbrains" in families
    assert rf.lbl_min.text().lower() == "from"
    assert rf.lbl_max.text().lower() == "to"


def test_range_form_pick_buttons_are_ghost_zone(qapp: QApplication) -> None:
    """Pick gear / Pick item must declare toolbar_zone='ghost' so they pick
    up the outline-only QSS from arsenal_stylesheet()."""
    editor = ConfigEditor()
    rf = editor.range_form()
    assert rf.btn_pick_gear.property("toolbar_zone") == "ghost"
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


def test_range_form_pick_buttons_emit_signals(qapp: QApplication) -> None:
    """Clicking Pick gear / Pick item on the range form must emit its
    signal so MainWindow can open the picker dialog. Regression guard
    for the case where the buttons were rendered but never wired."""
    editor = ConfigEditor()
    rf = editor.range_form()
    captured = []
    rf.pick_gear.connect(lambda: captured.append("gear"))
    rf.pick_item.connect(lambda: captured.append("item"))
    rf.btn_pick_gear.click()
    rf.btn_pick_item.click()
    assert captured == ["gear", "item"]