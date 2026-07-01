"""Tests for the redesigned RuleDetailPanel — right-pane rule editor.

Jul 2026 — tbh.city migration: panel displays multi-pool rules
via a chip strip on the pool field row, plus a range form (min/max)
for the range replacement rule. ``reward_kind`` (Normal/Boss/Act)
is shown in the subtitle.
"""
from __future__ import annotations

from PySide6.QtCore import Qt

from tbh_desktop.ui.rule_detail_panel import RuleDetailPanel


def test_panel_imports_and_starts_empty(qapp) -> None:
    panel = RuleDetailPanel()
    # Default state: empty label visible, form hidden, banner says "no rule".
    assert panel.empty_label.isVisibleTo(panel) is True
    assert panel.form.isVisibleTo(panel) is False
    assert "no rule selected" in panel.banner_name.text().lower()


def test_panel_show_empty_method(qapp) -> None:
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="foo", reward_kind="normal", pool_ids=[9100111],
        replacement_ids=[100, 200],
    )
    assert panel.form.isVisibleTo(panel) is True
    panel.show_empty()
    assert panel.form.isVisibleTo(panel) is False
    assert "no rule selected" in panel.banner_name.text().lower()


def test_panel_set_range_data_populates_form(qapp) -> None:
    """set_range_data renders the same panel with min/max instead of
    pool chips — there's no separate 'range summary' half-state.
    The enabled checkbox lives on the rule-list card (single
    source of truth), so the detail panel only shows min/max + chips."""
    panel = RuleDetailPanel()
    panel.set_range_data(
        enabled=True,
        match_min=100,
        match_max=999,
        replacement_ids=[11, 22],
    )
    assert panel.form.isVisibleTo(panel) is True
    assert "range" in panel.banner_name.text().lower()
    assert panel.range_min_value.value() == 100
    assert panel.range_max_value.value() == 999
    # Pick pool is hidden for range (range matches by itemId, not
    # pool — offering it would be misleading).
    assert panel.btn_pick_pool_id.isVisible() is False
    assert len(panel.chip_row._chips) == 2


def test_panel_set_rule_data_populates_form(qapp) -> None:
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="Pasture normal",
        reward_kind="normal",
        pool_ids=[9100111],
        replacement_ids=[114004, 605041],
    )
    assert panel.form.isVisibleTo(panel) is True
    assert panel.banner_name.text() == "Pasture normal"
    assert panel.banner_id.text() == "9100111"
    assert "2 IDs" in panel.chip_count_label.text()
    assert len(panel.chip_row._chips) == 2
    assert "normal" in panel.subtitle_label.text().lower()


def test_panel_set_rule_data_handles_no_pool_id(qapp) -> None:
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="Empty", reward_kind="boss", pool_ids=None, replacement_ids=[]
    )
    assert panel.form.isVisibleTo(panel) is True
    assert panel.banner_id.isHidden() is True  # no pool → no banner id
    assert "0 IDs" in panel.chip_count_label.text()
    assert panel.chip_row._chips == []


def test_panel_set_rule_data_multi_pool(qapp) -> None:
    """A rule covering several pools renders each as a chip in the
    pool field row."""
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="Act 1 stages 1-9 monster",
        reward_kind="normal",
        pool_ids=[9100111, 9100121, 9100131, 9100141],
        replacement_ids=[],
    )
    # Banner summarises count when there are multiple pools.
    assert "4 pools" in panel.banner_id.text()
    # Pool chip strip mirrors the rule's pool_ids list.
    pool_ids_in_chips = [chip._item_id for chip in panel.pool_chip_row._chips]
    assert pool_ids_in_chips == [9100111, 9100121, 9100131, 9100141]


def test_panel_set_rule_data_act_kind(qapp) -> None:
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="Act 1 boss", reward_kind="act", pool_ids=[9301011], replacement_ids=[]
    )
    assert "act" in panel.subtitle_label.text().lower()


def test_panel_pick_buttons_emit_signals(qapp) -> None:
    """Pick pool / Pick gear / Pick item each emit their own signal
    so MainWindow can route to the right CatalogPopup pre-scope."""
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="r", reward_kind="normal", pool_ids=[9100111], replacement_ids=[]
    )
    captured = {"pool_id": 0, "gear": 0, "item": 0}
    panel.pick_pool_id.connect(lambda: captured.__setitem__("pool_id", captured["pool_id"] + 1))
    panel.pick_gear.connect(lambda: captured.__setitem__("gear", captured["gear"] + 1))
    panel.pick_item.connect(lambda: captured.__setitem__("item", captured["item"] + 1))
    panel.btn_pick_pool_id.click()
    panel.btn_pick_gear.click()
    panel.btn_pick_item.click()
    assert captured == {"pool_id": 1, "gear": 1, "item": 1}


def test_panel_remove_chip_emits_signal(qapp) -> None:
    """Clicking a chip in the detail panel should emit ``remove_id_requested``
    with that chip's item id, so MainWindow can drop it from the rule."""
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QMouseEvent
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="r", reward_kind="normal", pool_ids=[9100111], replacement_ids=[10, 20, 30]
    )
    captured: list[int] = []
    panel.remove_id_requested.connect(lambda i: captured.append(int(i)))
    chip = panel.chip_row._chips[1]  # id=20
    chip.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, QPoint(5, 5),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    ))
    assert captured == [20]


def test_panel_pool_chip_remove_emits_pool_id_changed(qapp) -> None:
    """Clicking a pool chip emits pool_id_changed with the new list
    (minus the removed id) so main_window can persist the edit."""
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QMouseEvent
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="multi", reward_kind="normal",
        pool_ids=[9100111, 9100121, 9100131],
        replacement_ids=[],
    )
    captured: list[list[int]] = []
    panel.pool_id_changed.connect(lambda ids: captured.append(list(ids)))
    chip = panel.pool_chip_row._chips[1]  # 9100121
    chip.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, QPoint(5, 5),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    ))
    assert captured == [[9100111, 9100131]]