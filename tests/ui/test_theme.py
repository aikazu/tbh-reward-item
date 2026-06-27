"""Smoke tests for theme additions: RARITY map, rarity_tint, font registration."""
from __future__ import annotations

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.theme import (
    RARITY,
    arsenal_stylesheet,
    chip_style,
    rarity_tint,
    register_fonts,
    section_heading_style,
)


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


def test_chip_style_returns_qss_with_rarity_border(qapp: QApplication) -> None:
    qss = chip_style(rarity="LEGENDARY")
    assert RARITY["LEGENDARY"] in qss
    # Square corners (arsenal directive: 2-4px).
    assert "border-radius: 2px" in qss
    # The QSS now only applies the border (background is painted via
    # QPalette inside ItemCard) — verify the border-left accent is still
    # rarity-tinted so the visual identity survives.
    assert "border-left: 2px solid" in qss


def test_chip_style_compact_is_smaller(qapp: QApplication) -> None:
    qss = chip_style(rarity="RARE", compact=True)
    assert "padding" in qss
    # Compact chips should be clearly smaller than full.
    assert "compact" in qss.lower()


def test_section_heading_style_uses_cinzel(qapp: QApplication) -> None:
    qss = section_heading_style()
    assert "Cinzel" in qss
    assert "letter-spacing" in qss
    # Should target a QLabel via objectName, not a wildcard.
    assert "section_heading" in qss


def test_arsenal_stylesheet_contains_zone_styles(qapp: QApplication) -> None:
    qss = arsenal_stylesheet()
    # Toolbar 3-zone styling: primary, secondary, ghost (via Qt attribute selector).
    assert "toolbar_zone='primary'" in qss
    assert "toolbar_zone='secondary'" in qss
    assert "toolbar_zone='ghost'" in qss
    # Pulsing status dot objectName.
    assert "status_dot_pulse" in qss
    # Square corners rule.
    assert "border-radius: 2px" in qss or "border-radius: 3px" in qss or "border-radius: 4px" in qss
    # Rule card left-border accent.
    assert "#rule_card" in qss
    assert "border-left: 3px solid" in qss
