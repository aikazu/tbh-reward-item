"""Smoke tests for theme additions: RARITY map, rarity_tint, font registration."""
from __future__ import annotations

from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.theme import RARITY, rarity_tint, register_fonts


def test_rarity_has_six_tiers(qapp: QApplication) -> None:
    assert set(RARITY.keys()) == {"COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "MYTHIC"}
    for hex_color in RARITY.values():
        assert hex_color.startswith("#")
        assert len(hex_color) == 7


def test_rarity_tint_blends_with_mantle(qapp: QApplication) -> None:
    tinted = rarity_tint(RARITY["RARE"])
    # Returns a #rrggbbaa hex string.
    assert tinted.startswith("#")
    assert len(tinted) == 9


def test_register_fonts_loads_cinzel_and_jetbrains(qapp: QApplication) -> None:
    register_fonts()
    families = set(QFontDatabase.families())
    assert "Cinzel" in families
    assert "JetBrains Mono" in families
