"""Tests for the redesigned RuleDetailPanel — right-pane rule editor.

Jul 2026 — tbh.city migration: panel now displays a single numeric
``pool_id`` (= tbh.city drop_key) instead of v1's ``item_id`` + ``level``
pair. ``reward_kind`` (Normal/Boss/Act) is shown in the subtitle.
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
        name="foo", reward_kind="normal", pool_id=9100111, replacement_ids=[100, 200]
    )
    assert panel.form.isVisibleTo(panel) is True
    panel.show_empty()
    assert panel.form.isVisibleTo(panel) is False
    assert "no rule selected" in panel.banner_name.text().lower()


def test_panel_show_range_summary(qapp) -> None:
    panel = RuleDetailPanel()
    panel.show_range_summary()
    assert panel.form.isVisibleTo(panel) is False
    assert "range" in panel.banner_name.text().lower()


def test_panel_set_rule_data_populates_form(qapp) -> None:
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="Pasture normal",
        reward_kind="normal",
        pool_id=9100111,
        replacement_ids=[114004, 605041],
    )
    assert panel.form.isVisibleTo(panel) is True
    assert panel.banner_name.text() == "Pasture normal"
    assert panel.item_id_value.text() == "9100111"
    assert "2 IDs" in panel.chip_count_label.text()
    assert len(panel.chip_row._chips) == 2
    assert "normal" in panel.subtitle_label.text().lower()


def test_panel_set_rule_data_handles_no_pool_id(qapp) -> None:
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="Empty", reward_kind="boss", pool_id=None, replacement_ids=[]
    )
    assert panel.form.isVisibleTo(panel) is True
    assert panel.item_id_value.text() == "—"
    assert "0 IDs" in panel.chip_count_label.text()
    assert panel.chip_row._chips == []


def test_panel_set_rule_data_act_kind(qapp) -> None:
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="Act 1 boss", reward_kind="act", pool_id=9301011, replacement_ids=[]
    )
    assert "act" in panel.subtitle_label.text().lower()


def test_panel_banner_hides_pool_id_when_none(qapp) -> None:
    """The banner's pool-id chip disappears when no pool id is set,
    so the layout doesn't read as 'missing value'."""
    panel = RuleDetailPanel()
    panel.set_rule_data(name="r", reward_kind="normal", pool_id=None, replacement_ids=[])
    assert panel.banner_id.isHidden() is True
    panel.set_rule_data(name="r", reward_kind="normal", pool_id=9301011, replacement_ids=[])
    assert panel.banner_id.isHidden() is False
    assert panel.banner_id.text() == "9301011"


def test_panel_pick_buttons_emit_signals(qapp) -> None:
    """Pick pool / Pick gear / Pick item each emit their own signal
    so MainWindow can route to the right CatalogPopup pre-scope."""
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="r", reward_kind="normal", pool_id=9100111, replacement_ids=[]
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
        name="r", reward_kind="normal", pool_id=9100111, replacement_ids=[10, 20, 30]
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