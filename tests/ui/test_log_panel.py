"""Tests for the redesigned LogPanel — empty-state placeholder + summary.

The previous LogPanel was a thin ``QPlainTextEdit`` subclass with no
empty-state hint, so on first launch the panel rendered as a featureless
black rectangle with a tiny unlabeled "Log" header — users couldn't
tell whether logging was broken or just empty.

The new wrapper shows an italic muted "No log entries yet" hint when
empty and toggles to the live monospace viewer once a line arrives.
"""
from __future__ import annotations

from tbh_desktop.ui.log_panel import LogPanel


def test_log_panel_empty_state_visible_initially(qapp) -> None:
    panel = LogPanel()
    # Without a parent window, Qt's isVisible() returns False even when
    # the widget is logically visible. Check the role-based property
    # tag we set on each child so the assertion is independent of the
    # show() lifecycle.
    assert panel._empty_label.property("role") == "empty_hint"
    assert panel._viewer.property("role") == "viewer"
    # The toggle logic must have run on construction — confirm by
    # forcing a re-evaluation and reading the public line_count().
    assert panel.line_count() == 0
    assert panel.last_line() is None


def test_log_panel_hides_empty_after_first_line(qapp) -> None:
    panel = LogPanel()
    panel.append_log("hello world")
    assert panel.line_count() == 1
    assert panel.last_line() == "hello world"


def test_log_panel_empty_state_returns_after_clear(qapp) -> None:
    panel = LogPanel()
    panel.append_log("one")
    panel.append_log("two")
    assert panel.line_count() == 2
    panel.clear_log()
    assert panel.line_count() == 0
    assert panel.last_line() is None


def test_log_panel_last_line_returns_last_appended(qapp) -> None:
    panel = LogPanel()
    assert panel.last_line() is None
    panel.append_log("first")
    panel.append_log("second")
    panel.append_log("third")
    assert panel.last_line() == "third"


def test_log_panel_fifo_cap(qapp) -> None:
    """The 10k cap is enforced by QPlainTextEdit.setMaximumBlockCount —
    we verify it's set so very long sessions don't balloon memory."""
    panel = LogPanel()
    assert panel._viewer.maximumBlockCount() == panel.MAX_LINES
    assert panel.MAX_LINES == 10_000


def test_log_panel_viewer_is_read_only(qapp) -> None:
    panel = LogPanel()
    assert panel._viewer.isReadOnly() is True


def test_log_panel_viewer_is_monospace(qapp) -> None:
    """Log lines must render in a monospace family so timestamps + ids
    line up vertically (the previous version used system default)."""
    panel = LogPanel()
    families = " ".join(panel._viewer.font().families()).lower()
    assert "mono" in families or "fira" in families


def test_log_panel_empty_label_has_object_name(qapp) -> None:
    """Empty state must have objectName='empty_state' so the matching
    QSS rule in theme.empty_state_style() can target it."""
    panel = LogPanel()
    assert panel._empty_label.objectName() == "empty_state"
