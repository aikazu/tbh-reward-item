"""Tests for main_window."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QMessageBox

from tbh_desktop.paths import GEAR_CACHE_DIR
from tbh_desktop.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot):
    with patch("tbh_desktop.ui.main_window.config_io") as mock_cio, patch(
        "tbh_desktop.ui.main_window.scraper"
    ), patch("tbh_desktop.ui.main_window.ProxyRunner") as mock_runner_cls:
        mock_cio.load_config.return_value = {
            "listen_port": 8877,
            "specific_queue_rules": [],
            "range_replacement": {},
        }
        mock_cio.save_config.return_value = MagicMock(ok=True, error=None)
        w = MainWindow()
        qtbot.addWidget(w)
        yield w, mock_runner_cls.return_value, mock_cio


def test_start_starts_directly_when_port_unchanged(window, monkeypatch):
    w, mock_runner, mock_cio = window
    # Port unchanged: config 8877, port_edit shows 8877.
    w.port_edit.setText("8877")

    question = MagicMock(return_value=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("tbh_desktop.ui.main_window.QMessageBox.question", question)

    w.btn_start.click()

    question.assert_not_called()
    mock_runner.start.assert_called_once()


def test_start_prompts_when_port_changed(window, monkeypatch):
    w, mock_runner, mock_cio = window
    # Config port 8877, user edits to 9999 without saving.
    w.port_edit.setText("9999")

    question = MagicMock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr("tbh_desktop.ui.main_window.QMessageBox.question", question)

    w.btn_start.click()

    question.assert_called_once()
    # Confirm prompt text mentions port/save context.
    args, _ = question.call_args
    prompt_text = " ".join(str(a) for a in args).lower()
    assert "port" in prompt_text or "save" in prompt_text
    # User chose No -> runner must not start.
    mock_runner.start.assert_not_called()
    mock_cio.save_config.assert_not_called()


def test_start_saves_and_starts_on_yes(window, monkeypatch):
    w, mock_runner, mock_cio = window
    # Config port 8877, user edits to 9999 without saving.
    w.port_edit.setText("9999")

    question = MagicMock(return_value=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("tbh_desktop.ui.main_window.QMessageBox.question", question)

    w.btn_start.click()

    question.assert_called_once()
    mock_cio.save_config.assert_called_once()
    mock_runner.start.assert_called_once()


def test_scrape_gear_button_calls_refresh_gear_full(qtbot):
    """btn_refresh_gear ('Scrape gear') must call scraper.refresh_gear_full
    with GEAR_CACHE_DIR and log a progress message.
    """
    mock_scraper = MagicMock()
    mock_scraper.refresh_gear_full.return_value = {
        "weapon_legendary": [{"id": 1}],
        "offhand_immortal": [{"id": 2}],
    }
    logs: list[str] = []
    with patch("tbh_desktop.ui.main_window.config_io") as mock_cio, patch(
        "tbh_desktop.ui.main_window.scraper", mock_scraper
    ), patch("tbh_desktop.ui.main_window.ProxyRunner"):
        mock_cio.load_config.return_value = {
            "listen_port": 8877,
            "specific_queue_rules": [],
            "range_replacement": {},
        }
        w = MainWindow()
        qtbot.addWidget(w)
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(w, "_on_log", lambda msg: logs.append(msg))

        w.btn_refresh_gear.click()

    mock_scraper.refresh_gear_full.assert_called_once()
    call_args, _ = mock_scraper.refresh_gear_full.call_args
    assert call_args[0] == GEAR_CACHE_DIR
    # Button label updated to "Scrape gear".
    assert w.btn_refresh_gear.text() == "Scrape gear"
    assert any("Gear scraped" in msg or "scraped" in msg.lower() for msg in logs)


def test_pick_gear_uses_cache_dir_picker(qtbot, monkeypatch, tmp_path):
    """GearPicker must be instantiated with the GEAR_CACHE_DIR path, not flat items.
    Uses a fresh window with GearPicker patched out so the dialog never actually shows.
    """
    fake_picker = MagicMock()
    fake_picker.exec.return_value = False  # user cancels
    captured_args = {}

    def _ctor(cache_dir, parent=None):
        captured_args["cache_dir"] = cache_dir
        captured_args["parent"] = parent
        return fake_picker

    monkeypatch.setattr("tbh_desktop.ui.main_window.GearPicker", _ctor)
    # Ensure the cache dir has at least one gear file so the guard passes.
    monkeypatch.setattr(
        "tbh_desktop.ui.main_window.GEAR_CACHE_DIR", tmp_path
    )
    (tmp_path / "gear_weapon_legendary.json").write_text("[]", encoding="utf-8")

    with patch("tbh_desktop.ui.main_window.config_io") as mock_cio, patch(
        "tbh_desktop.ui.main_window.scraper"
    ), patch("tbh_desktop.ui.main_window.ProxyRunner"):
        mock_cio.load_config.return_value = {
            "listen_port": 8877,
            "specific_queue_rules": [],
            "range_replacement": {},
        }
        w = MainWindow()
        qtbot.addWidget(w)

    w.editor.btn_pick_gear_rule.click()

    assert "cache_dir" in captured_args
    assert captured_args["cache_dir"] == tmp_path


def test_pick_gear_empty_cache_logs_hint(qtbot, monkeypatch, tmp_path):
    """No gear cache files -> _on_log emits the 'No gear cache' hint and the
    picker is never opened.
    """
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr("tbh_desktop.ui.main_window.GEAR_CACHE_DIR", empty_dir)

    picker_calls = MagicMock()

    def _ctor(*args, **kwargs):
        picker_calls()
        dlg = MagicMock()
        dlg.exec.return_value = False
        return dlg

    monkeypatch.setattr("tbh_desktop.ui.main_window.GearPicker", _ctor)

    logs: list[str] = []
    with patch("tbh_desktop.ui.main_window.config_io") as mock_cio, patch(
        "tbh_desktop.ui.main_window.scraper"
    ), patch("tbh_desktop.ui.main_window.ProxyRunner"):
        mock_cio.load_config.return_value = {
            "listen_port": 8877,
            "specific_queue_rules": [],
            "range_replacement": {},
        }
        w = MainWindow()
        qtbot.addWidget(w)
        # Capture log lines via the runner's log_line signal path (_on_log).
        monkeypatch.setattr(w, "_on_log", lambda msg: logs.append(msg))

    w.editor.btn_pick_gear_rule.click()

    assert any("No gear cache" in msg for msg in logs)
    picker_calls.assert_not_called()
