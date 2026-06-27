"""Tests for the redesigned RuleDetailPanel — right-pane rule editor."""
from __future__ import annotations

import pytest

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
        name="foo", item_id=42, level=5, replacement_ids=[100, 200]
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
        name="Normal Box", item_id=910901, level=15, replacement_ids=[114004, 605041]
    )
    assert panel.form.isVisibleTo(panel) is True
    assert panel.banner_name.text() == "Normal Box"
    assert panel.item_id_value.text() == "910901"
    assert panel.level_value.text() == "15"
    assert "2 IDs" in panel.chip_count_label.text()
    assert len(panel.chip_row._chips) == 2


def test_panel_set_rule_data_handles_no_item_id(qapp) -> None:
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="Empty", item_id=None, level=None, replacement_ids=[]
    )
    assert panel.form.isVisibleTo(panel) is True
    assert panel.item_id_value.text() == "—"
    assert panel.level_value.text() == "—"
    assert "0 IDs" in panel.chip_count_label.text()
    assert panel.chip_row._chips == []


def test_panel_pick_buttons_emit_signals(qapp) -> None:
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="r", item_id=1, level=None, replacement_ids=[]
    )
    captured = {"box_id": 0, "box_loot": 0, "gear": 0}
    panel.pick_box_id.connect(lambda: captured.__setitem__("box_id", captured["box_id"] + 1))
    panel.pick_box_loot.connect(lambda: captured.__setitem__("box_loot", captured["box_loot"] + 1))
    panel.pick_gear.connect(lambda: captured.__setitem__("gear", captured["gear"] + 1))
    panel.btn_pick_box_id.click()
    panel.btn_pick_box_loot.click()
    panel.btn_pick_gear.click()
    assert captured == {"box_id": 1, "box_loot": 1, "gear": 1}


def test_panel_remove_chip_emits_signal(qapp) -> None:
    """Clicking a chip in the detail panel should emit ``remove_id_requested``
    with that chip's item id, so MainWindow can drop it from the rule."""
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QMouseEvent
    panel = RuleDetailPanel()
    panel.set_rule_data(
        name="r", item_id=1, level=None, replacement_ids=[10, 20, 30]
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


# Late import for Qt constants inside the test above.
from PySide6.QtCore import Qt  # noqa: E402
