"""Tests for RuleListView: round-trip, selection signal, target routing."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.active_target import RuleTarget, RangeTarget
from tbh_desktop.ui.rule_list import RuleListView

SAMPLE = {
    "specific_queue_rules": [
        {"enabled": True,  "name": "Default A", "item_id": 100, "replacement_reward_item_ids": [1, 2]},
        {"enabled": False, "name": "User B",    "item_id": 200, "replacement_reward_item_ids": [3]},
    ],
    "range_replacement": {
        "enabled": False,
        "name": "Range replacement",
        "match_min_item_id": 500000,
        "match_max_item_id": 950000,
        "replacement_reward_item_ids": [7, 8],
    },
}


def test_rule_list_loads_rows(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    assert view.row_count() == 2


def test_rule_list_round_trip(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    out = view.dump()
    assert out["specific_queue_rules"] == SAMPLE["specific_queue_rules"]
    assert out["range_replacement"] == SAMPLE["range_replacement"]


def test_rule_list_selection_emits_target(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    captured = {"targets": []}
    view.rule_selected.connect(lambda t: captured["targets"].append(t))
    view.select_row(0)
    assert len(captured["targets"]) == 1
    assert isinstance(captured["targets"][0], RuleTarget)
    assert captured["targets"][0].rule_index == 0


def test_rule_list_add_to_active_rule_target(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    view.select_row(1)
    view.set_active_target(RuleTarget(row=1, rule_index=1, box_id=200, level=None))
    view.add_ids_to_active_target([99])
    out = view.dump()
    assert 99 in out["specific_queue_rules"][1]["replacement_reward_item_ids"]


def test_rule_list_add_to_active_range_target(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    view.set_active_target(RangeTarget())
    view.add_ids_to_active_target([42, 43])
    out = view.dump()
    assert 42 in out["range_replacement"]["replacement_reward_item_ids"]
    assert 43 in out["range_replacement"]["replacement_reward_item_ids"]


def test_rule_list_no_target_raises(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    try:
        view.add_ids_to_active_target([1])
    except ValueError:
        return
    raise AssertionError("Expected ValueError when no active target is set")


def test_rule_list_set_box_id_writes_to_row(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    view.select_row(0)
    view.set_active_target(RuleTarget(row=0, rule_index=0, box_id=None, level=None))
    view.set_selected_rule_item_id(555, level=15)
    out = view.dump()
    assert out["specific_queue_rules"][0]["item_id"] == 555


def test_rule_list_set_box_id_does_not_leak_level_into_dump(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    view.select_row(0)
    view.set_active_target(RuleTarget(row=0, rule_index=0, box_id=None, level=None))
    view.set_selected_rule_item_id(555, level=15)
    out = view.dump()
    assert out["specific_queue_rules"][0]["item_id"] == 555
    # Regression: __level_for_row__ sentinel must NOT appear in dump output
    assert "__level_for_row__" not in out["range_replacement"]
    assert "__level_for_row__" not in out


def test_model_data_does_not_raise(qapp: QApplication) -> None:
    """Regression: QAbstractItemModel.data is pure virtual. The previous
    implementation overrode index/parent/rowCount/columnCount but omitted
    data(), so Qt's QListView raised NotImplementedError on first paint
    or selection query, which crashed the whole window during show().

    setIndexWidget is the sole paint path, but Qt still queries data()
    for hit-testing, accessibility, and currentRowChanged handling.
    """
    view = RuleListView()
    view.load(SAMPLE)
    model = view.model()
    idx = model.index(0, 0)
    assert idx.isValid()
    # Must not raise NotImplementedError for any role Qt commonly queries.
    for role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole,
                 Qt.ItemDataRole.AccessibleTextRole, Qt.ItemDataRole.ToolTipRole):
        # Returning None is fine — the paint path is setIndexWidget.
        assert model.data(idx, role) is None or model.data(idx, role) is not None
    # flags() must also be implemented so the row is selectable.
    assert model.flags(idx) & Qt.ItemFlag.ItemIsSelectable
