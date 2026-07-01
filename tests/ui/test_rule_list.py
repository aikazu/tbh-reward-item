"""Tests for RuleListView: round-trip, selection signal, target routing.

Jul 2026 — tbh.city migration: rules live in three buckets
(normal_rules / boss_rules / act_rules) keyed by ``pool_id`` (= tbh.city
drop_key). The list view flattens them into a single row stream; the
``reward_kind`` field on ``RuleTarget`` lets callers bucket picks.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.active_target import RuleTarget, RangeTarget
from tbh_desktop.ui.rule_list import RuleListView

SAMPLE = {
    "normal_rules": [
        {"enabled": True,  "name": "Default A", "reward_kind": "normal",
         "pool_id": 9100111, "replacement_reward_item_ids": [1, 2]},
    ],
    "boss_rules": [
        {"enabled": False, "name": "User B", "reward_kind": "boss",
         "pool_id": 9200111, "replacement_reward_item_ids": [3]},
    ],
    "act_rules": [],
    "range_replacement": {
        "enabled": False,
        "name": "Pool range",
        "match_min_item_id": 500000,
        "match_max_item_id": 950000,
        "replacement_reward_item_ids": [7, 8],
    },
}


def test_rule_list_loads_rows(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    # 1 normal + 1 boss = 2 rows (act is empty).
    assert view.row_count() == 2


def test_rule_list_round_trip(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    out = view.dump()
    # Each kind bucket present (some may be empty lists).
    assert "normal_rules" in out
    assert "boss_rules" in out
    assert "act_rules" in out
    assert out["range_replacement"]["replacement_reward_item_ids"] == [7, 8]


def test_rule_list_selection_emits_target(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    captured = {"targets": []}
    view.rule_selected.connect(lambda t: captured["targets"].append(t))
    view.select_row(0)
    assert len(captured["targets"]) == 1
    assert isinstance(captured["targets"][0], RuleTarget)
    assert captured["targets"][0].reward_kind == "normal"
    assert captured["targets"][0].pool_id == 9100111


def test_rule_list_selection_emits_target_for_boss(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    captured = {"targets": []}
    view.rule_selected.connect(lambda t: captured["targets"].append(t))
    view.select_row(1)  # boss row
    assert captured["targets"][0].reward_kind == "boss"


def test_rule_list_add_to_active_rule_target(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    view.select_row(1)
    view.set_active_target(RuleTarget(row=1, rule_index=0, reward_kind="boss", pool_id=9200111))
    view.add_ids_to_active_target([99])
    out = view.dump()
    assert 99 in out["boss_rules"][0]["replacement_reward_item_ids"]


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


def test_rule_list_set_pool_id_writes_to_row(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    view.select_row(0)
    view.set_active_target(RuleTarget(row=0, rule_index=0, reward_kind="normal", pool_id=None))
    view.set_selected_rule_pool_id(555)
    out = view.dump()
    assert out["normal_rules"][0]["pool_ids"] == [555]


def test_rule_list_set_pool_id_no_level_sentinel(qapp: QApplication) -> None:
    """Regression: v1 had a ``__level_for_row__`` sentinel that leaked into
    the dump. v2 has no per-row level concept (pool id only) so we just
    verify no stray sentinels appear in the output.
    """
    view = RuleListView()
    view.load(SAMPLE)
    view.select_row(0)
    view.set_active_target(RuleTarget(row=0, rule_index=0, reward_kind="normal", pool_id=None))
    view.set_selected_rule_pool_id(555)
    out = view.dump()
    assert "__level_for_row__" not in out
    assert "__level_for_row__" not in str(out)


def test_rule_list_add_rule_new_kind(qapp: QApplication) -> None:
    view = RuleListView()
    view.load(SAMPLE)
    row = view.add_rule("act", {
        "enabled": True, "name": "New Act", "reward_kind": "act",
        "pool_ids": [9301011], "replacement_reward_item_ids": [42],
    })
    assert row == 2  # normal=0, boss=1, new act=2
    out = view.dump()
    assert out["act_rules"][-1]["pool_ids"] == [9301011]


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