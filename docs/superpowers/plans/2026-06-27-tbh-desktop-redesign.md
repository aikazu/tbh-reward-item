# TBH Desktop Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the TBH Reward Proxy desktop GUI into a Dark RPG inventory layout: left icon rail, center rule card list + range form, right Item browser (always visible), bottom collapsible log dock.

**Architecture:** PySide6 widgets. Add 5 new modules (`item_card`, `rule_card`, `rule_list`, `item_browser`, `left_rail`, `active_target`). Refactor 6 existing modules (`theme`, `config_editor`, `gear_picker`, `box_loot_picker`, `box_picker`, `main_window`). TDD: write a failing pytest-qt test for each widget, then implement. The `ActiveTarget` union (`RuleTarget | RangeTarget`) routes Item browser picks to the right place. Pickers stop being modal `QDialog`s and become embedded views inside the Item browser; the old dialog classes stay as thin shims.

**Tech Stack:** Python 3.10+, PySide6 6.6+, pytest-qt, existing `tbh_desktop` (PySide6 + requests + cloakbrowser). New fonts: Cinzel (display), JetBrains Mono (monospace) bundled under `tbh_desktop/ui/fonts/`.

**Spec:** `docs/superpowers/specs/2026-06-27-tbh-desktop-redesign-design.md` (commit `fe78d67`).

---

## File Structure

**New files:**
- `tbh_desktop/ui/fonts/Cinzel-Regular.ttf`, `Cinzel-Bold.ttf` — display font
- `tbh_desktop/ui/fonts/JetBrainsMono-Regular.ttf`, `JetBrainsMono-Bold.ttf` — monospace
- `tbh_desktop/ui/active_target.py` — `RuleTarget`, `RangeTarget` dataclasses
- `tbh_desktop/ui/item_card.py` — `ItemCard` widget (rarity-bordered card)
- `tbh_desktop/ui/rule_card.py` — `RuleCard` widget (one rule row)
- `tbh_desktop/ui/rule_list.py` — `RuleListView` (QListView + custom delegate + model)
- `tbh_desktop/ui/item_browser.py` — `ItemBrowser` panel (6 tabs + filter)
- `tbh_desktop/ui/left_rail.py` — `LeftRail` icon rail
- `tests/ui/test_*.py` — 6 new test files

**Modified files:**
- `tbh_desktop/ui/theme.py` — add `RARITY`, `rarity_tint`, `apply_ornament`, font registration, item-card QSS
- `tbh_desktop/ui/config_editor.py` — wrap `RuleListView` + range form, keep `load`/`dump` API
- `tbh_desktop/ui/gear_picker.py` — extract `GearView`, dialog becomes shim
- `tbh_desktop/ui/box_loot_picker.py` — extract `BoxLootView`, dialog becomes shim
- `tbh_desktop/ui/box_picker.py` — extract `BoxView`, dialog becomes shim
- `tbh_desktop/ui/main_window.py` — compose 4 zones, wire `ActiveTarget`
- `tbh_desktop/main.py` — register fonts at startup

**Untouched:**
- `tbh_desktop/ui/log_panel.py` (works as-is)
- `tbh_desktop/proxy_runner.py`, `tbh_desktop/gear_scraper_runner.py`, `tbh_desktop/config_io.py`, `tbh_desktop/scraper.py`

---

## Task 1: Theme — add RARITY palette, rarity_tint, Cinzel/JetBrains Mono registration

**Files:**
- Modify: `tbh_desktop/ui/theme.py:11-44`
- Modify: `tbh_desktop/main.py` (add font registration)
- Create: `tbh_desktop/ui/fonts/` (directory with 4 TTF files, fetched in step 1)

- [ ] **Step 1: Download fonts**

Run:
```bash
mkdir -p tbh_desktop/ui/fonts
cd tbh_desktop/ui/fonts
curl -L -o Cinzel-Regular.ttf https://github.com/google/fonts/raw/main/ofl/cinzel/static/Cinzel-Regular.ttf
curl -L -o Cinzel-Bold.ttf    https://github.com/google/fonts/raw/main/ofl/cinzel/static/Cinzel-Bold.ttf
curl -L -o JetBrainsMono-Regular.ttf https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Regular.ttf
curl -L -o JetBrainsMono-Bold.ttf    https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Bold.ttf
ls -la
```

Expected: 4 .ttf files, each ≤ 400 KB. If any download fails, re-run with `-L` and check the URL in a browser; do not proceed with missing files.

- [ ] **Step 2: Write the failing test for font registration**

Create `tests/ui/test_theme.py`:

```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/ui/test_theme.py -v`
Expected: ImportError or AttributeError on `RARITY`/`rarity_tint`/`register_fonts`.

- [ ] **Step 4: Extend theme.py**

Add to `tbh_desktop/ui/theme.py` (top, after the `MOCHA` dict) and append a new function:

```python
RARITY: dict[str, str] = {
    "COMMON":    "#6c7086",
    "UNCOMMON":  "#a6e3a1",
    "RARE":      "#89b4fa",
    "EPIC":      "#cba6f7",
    "LEGENDARY": "#f9e2af",
    "MYTHIC":    "#f38ba8",
}


def rarity_tint(hex_color: str, alpha: int = 0x33) -> str:
    """Return ``hex_color`` with the given alpha byte appended as ``#rrggbbaa``."""
    if not (hex_color.startswith("#") and len(hex_color) == 7):
        raise ValueError(f"Expected #rrggbb, got {hex_color!r}")
    return f"{hex_color}{alpha:02x}"


_FONTS_DIR = Path(__file__).resolve().parent / "fonts"


def register_fonts() -> None:
    """Load bundled Cinzel + JetBrains Mono into the QFontDatabase.

    Idempotent — safe to call more than once. Silently no-ops if a font file
    is missing so the app still starts on a broken install.
    """
    from PySide6.QtGui import QFontDatabase  # local import keeps test boot fast

    for name in (
        "Cinzel-Regular.ttf",
        "Cinzel-Bold.ttf",
        "JetBrainsMono-Regular.ttf",
        "JetBrainsMono-Bold.ttf",
    ):
        path = _FONTS_DIR / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
```

Also add `from pathlib import Path` to the top imports of `theme.py`.

- [ ] **Step 5: Update main.py to call register_fonts**

In `tbh_desktop/main.py`, find where `apply_theme(app)` is called. Add `register_fonts()` immediately before it. If `main.py` does not exist or does not call `apply_theme`, look in `tbh_desktop/__init__.py` and `tbh_desktop/ui/__init__.py`. Place the call before any widget is constructed.

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/ui/test_theme.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add tbh_desktop/ui/theme.py tbh_desktop/main.py tbh_desktop/ui/fonts/ tests/ui/test_theme.py
git commit -m "feat(theme): add RARITY palette, rarity_tint, bundled Cinzel + JetBrains Mono"
```

---

## Task 2: ItemCard widget

**Files:**
- Create: `tbh_desktop/ui/item_card.py`
- Test: `tests/ui/test_item_card.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ItemCard: rarity border, selection state, compact mode."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.item_card import ItemCard
from tbh_desktop.ui.theme import RARITY


def test_item_card_renders_name_and_rarity(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 42, "name": "Long Sword", "rarity": "RARE"})
    assert card.name() == "Long Sword"
    assert card.rarity() == "RARE"


def test_item_card_default_unselected(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 1, "name": "x", "rarity": "COMMON"})
    assert card.is_selected() is False


def test_item_card_set_selected_toggles_flag(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 1, "name": "x", "rarity": "RARE"})
    card.set_selected(True)
    assert card.is_selected() is True
    card.set_selected(False)
    assert card.is_selected() is False


def test_item_card_compact_uses_chip_size(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 1, "name": "x", "rarity": "COMMON"})
    card.set_compact(True)
    assert card.sizeHint().height() <= 56
    card.set_compact(False)
    assert card.sizeHint().height() >= 96


def test_item_card_unknown_rarity_falls_back_to_common(qapp: QApplication) -> None:
    card = ItemCard()
    card.set_data({"id": 1, "name": "x", "rarity": "NOT_A_TIER"})
    assert card.rarity() == "COMMON"
    # Border color must still resolve to a real RARITY value.
    assert card.rarity_color() == RARITY["COMMON"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_item_card.py -v`
Expected: ImportError on `tbh_desktop.ui.item_card`.

- [ ] **Step 3: Create item_card.py**

```python
"""Single in-game item card with rarity-bordered frame."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from tbh_desktop.ui.theme import RARITY, MOCHA, rarity_tint


class ItemCard(QFrame):
    SIZE_FULL = 96
    SIZE_COMPACT = 48

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item_id: int = 0
        self._name: str = ""
        self._rarity: str = "COMMON"
        self._selected: bool = False
        self._compact: bool = False

        self.setObjectName("item_card")
        self.setFixedSize(self.SIZE_FULL, self.SIZE_FULL)
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setText("")  # populated later when ImageCache resolves
        layout.addWidget(self._icon_label, stretch=1)

        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setWordWrap(False)
        self._name_label.setStyleSheet("font-size: 11px; color: #cdd6f4;")
        layout.addWidget(self._name_label)

        self._refresh_style()

    # ---- public API --------------------------------------------------
    def set_data(self, item: dict) -> None:
        self._item_id = int(item.get("id", 0))
        self._name = str(item.get("name", ""))
        raw_rarity = str(item.get("rarity", "COMMON")).upper()
        self._rarity = raw_rarity if raw_rarity in RARITY else "COMMON"
        self._name_label.setText(self._truncate(self._name, 14))
        self._refresh_style()

    def item_id(self) -> int:
        return self._item_id

    def name(self) -> str:
        return self._name

    def rarity(self) -> str:
        return self._rarity

    def rarity_color(self) -> str:
        return RARITY[self._rarity]

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self._refresh_style()

    def is_selected(self) -> bool:
        return self._selected

    def set_compact(self, compact: bool) -> None:
        if self._compact == compact:
            return
        self._compact = compact
        if compact:
            self.setFixedSize(self.SIZE_COMPACT * 2, self.SIZE_COMPACT)
            self._name_label.setVisible(False)
        else:
            self.setFixedSize(self.SIZE_FULL, self.SIZE_FULL)
            self._name_label.setVisible(True)
        self._refresh_style()

    def set_icon_pixmap(self, pixmap) -> None:
        """Optional: assign a QPixmap once ImageCache resolves the URL."""
        if pixmap is not None and not pixmap.isNull():
            self._icon_label.setPixmap(pixmap.scaled(
                56, 56,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    # ---- internals ---------------------------------------------------
    def _refresh_style(self) -> None:
        border_color = MOCHA["blue"] if self._selected else self.rarity_color()
        border_width = 2 if self._selected else 1
        bg = MOCHA["surface0"] if self._selected else rarity_tint(self.rarity_color())
        self.setStyleSheet(
            f"#item_card {{"
            f"  background-color: {bg};"
            f"  border: {border_width}px solid {border_color};"
            f"  border-radius: 8px;"
            f"}}"
        )

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        return text if len(text) <= max_len else text[: max_len - 1] + "…"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_item_card.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/item_card.py tests/ui/test_item_card.py
git commit -m "feat(ui): add ItemCard widget with rarity border + compact mode"
```

---

## Task 3: ActiveTarget module

**Files:**
- Create: `tbh_desktop/ui/active_target.py`
- Test: `tests/ui/test_active_target.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the ActiveTarget union and its routing helper."""
from __future__ import annotations

from tbh_desktop.ui.active_target import (
    ActiveTarget,
    RangeTarget,
    RuleTarget,
    is_range,
    is_rule,
)


def test_rule_target_holds_row_metadata() -> None:
    t = RuleTarget(row=2, rule_index=2, box_id=42, level=10)
    assert t.row == 2
    assert t.rule_index == 2
    assert t.box_id == 42
    assert t.level == 10


def test_range_target_is_singleton_like() -> None:
    assert RangeTarget() == RangeTarget()


def test_is_rule_and_is_range_discriminate() -> None:
    rule: ActiveTarget = RuleTarget(row=0, rule_index=0, box_id=None, level=None)
    rng: ActiveTarget = RangeTarget()
    assert is_rule(rule) is True
    assert is_range(rule) is False
    assert is_range(rng) is True
    assert is_rule(rng) is False


def test_rule_target_is_frozen() -> None:
    t = RuleTarget(row=0, rule_index=0, box_id=None, level=None)
    try:
        t.row = 5  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("RuleTarget must be frozen (frozen dataclass)")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_active_target.py -v`
Expected: ImportError on `tbh_desktop.ui.active_target`.

- [ ] **Step 3: Create active_target.py**

```python
"""Typed union that routes Item browser picks to a rule row or the range form.

`MainWindow` owns the current `ActiveTarget`. `RuleListView` and the range
form switch it on selection/focus. `ItemBrowser.item_picked` is dispatched
based on the target type.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class RuleTarget:
    """A specific rule row in `config.specific_queue_rules`."""
    row: int           # visual row in RuleListView
    rule_index: int    # index into config.specific_queue_rules
    box_id: int | None
    level: int | None


@dataclass(frozen=True)
class RangeTarget:
    """The single range_replacement form (always at most one per config)."""
    pass


ActiveTarget = Union[RuleTarget, RangeTarget]


def is_rule(target: ActiveTarget | None) -> bool:
    return isinstance(target, RuleTarget)


def is_range(target: ActiveTarget | None) -> bool:
    return isinstance(target, RangeTarget)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_active_target.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/active_target.py tests/ui/test_active_target.py
git commit -m "feat(ui): add ActiveTarget union (RuleTarget | RangeTarget)"
```

---

## Task 4: RuleCard widget

**Files:**
- Create: `tbh_desktop/ui/rule_card.py`
- Test: `tests/ui/test_rule_card.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for RuleCard: per-row pick buttons, chip row, signals."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.rule_card import RuleCard


def _capture(card: RuleCard) -> dict[str, list]:
    """Wire all RuleCard signals to a dict for inspection."""
    captured: dict[str, list] = {
        "pick_box_id": [],
        "pick_box_loot": [],
        "pick_gear": [],
        "remove": [],
        "edited": [],
    }
    card.pick_box_id.connect(lambda: captured["pick_box_id"].append(True))
    card.pick_box_loot.connect(lambda: captured["pick_box_loot"].append(True))
    card.pick_gear.connect(lambda: captured["pick_gear"].append(True))
    card.remove.connect(lambda: captured["remove"].append(True))
    card.edited.connect(lambda: captured["edited"].append(True))
    return captured


def test_rule_card_renders_from_dict(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True,
        "name": "Test rule",
        "item_id": 12345,
        "replacement_reward_item_ids": [529191, 419191],
    })
    assert card.name() == "Test rule"
    assert card.item_id() == 12345
    assert card.replacement_ids() == [529191, 419191]


def test_rule_card_pick_buttons_emit_signals(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [],
    })
    captured = _capture(card)
    card.btn_pick_box_id.click()
    card.btn_pick_box_loot.click()
    card.btn_pick_gear.click()
    assert captured["pick_box_id"] == [True]
    assert captured["pick_box_loot"] == [True]
    assert captured["pick_gear"] == [True]


def test_rule_card_add_chip_appends(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [10],
    })
    card.add_ids([20, 30])
    assert card.replacement_ids() == [10, 20, 30]


def test_rule_card_add_chip_dedupes(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [10, 20],
    })
    card.add_ids([20, 30, 10])
    assert card.replacement_ids() == [10, 20, 30]


def test_rule_card_remove_chip(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [10, 20, 30],
    })
    card.remove_id(20)
    assert card.replacement_ids() == [10, 30]


def test_rule_card_set_active_toggles_border(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [],
    })
    card.set_active(True)
    assert card.is_active() is True
    card.set_active(False)
    assert card.is_active() is False


def test_rule_card_remove_emits_signal(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [],
    })
    captured = _capture(card)
    card.btn_remove.click()
    assert captured["remove"] == [True]


def test_rule_card_locked_disables_remove(qapp: QApplication) -> None:
    card = RuleCard()
    card.set_data({
        "enabled": True, "name": "r", "item_id": 1, "replacement_reward_item_ids": [],
    }, locked=True)
    assert card.btn_remove.isEnabled() is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_rule_card.py -v`
Expected: ImportError on `tbh_desktop.ui.rule_card`.

- [ ] **Step 3: Create rule_card.py**

```python
"""One rule: enabled, name, item_id, three Pick buttons, replacement chip row."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.item_card import ItemCard
from tbh_desktop.ui.theme import MOCHA


class RuleCard(QFrame):
    pick_box_id = Signal()
    pick_box_loot = Signal()
    pick_gear = Signal()
    remove = Signal()
    edited = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rule_card")
        self._locked: bool = False
        self._active: bool = False
        self._name: str = ""
        self._item_id: int | None = None
        self._replacement_ids: list[int] = []
        self._chips: list[ItemCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # Row 1: enabled + name
        row1 = QHBoxLayout()
        self.chk_enabled = QCheckBox()
        self.chk_enabled.toggled.connect(self.edited)
        row1.addWidget(self.chk_enabled)
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Rule name")
        self.edit_name.textChanged.connect(self._on_name_changed)
        row1.addWidget(self.edit_name, stretch=1)
        outer.addLayout(row1)

        # Row 2: item_id + pick buttons
        row2 = QHBoxLayout()
        self.edit_item_id = QLineEdit()
        self.edit_item_id.setPlaceholderText("box / item id")
        self.edit_item_id.setFixedWidth(110)
        self.edit_item_id.textChanged.connect(self._on_item_id_changed)
        row2.addWidget(self.edit_item_id)
        self.btn_pick_box_id = QPushButton("Pick box")
        self.btn_pick_box_id.clicked.connect(self.pick_box_id)
        row2.addWidget(self.btn_pick_box_id)
        self.btn_pick_box_loot = QPushButton("Pick loot")
        self.btn_pick_box_loot.clicked.connect(self.pick_box_loot)
        row2.addWidget(self.btn_pick_box_loot)
        self.btn_pick_gear = QPushButton("Pick gear")
        self.btn_pick_gear.clicked.connect(self.pick_gear)
        row2.addWidget(self.btn_pick_gear)
        row2.addStretch()
        outer.addLayout(row2)

        # Row 3: chip wrap
        self._chip_row = QHBoxLayout()
        self._chip_row.setSpacing(4)
        self._chip_row.addStretch()
        outer.addLayout(self._chip_row)

        # Row 4: remove
        row4 = QHBoxLayout()
        row4.addStretch()
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.clicked.connect(self.remove)
        row4.addWidget(self.btn_remove)
        outer.addLayout(row4)

        self._refresh_style()

    # ---- data --------------------------------------------------------
    def set_data(self, rule: dict, locked: bool = False) -> None:
        self._locked = locked
        self._name = str(rule.get("name") or "")
        raw_id = rule.get("item_id")
        self._item_id = int(raw_id) if isinstance(raw_id, int) else None
        self._replacement_ids = [int(i) for i in (rule.get("replacement_reward_item_ids") or [])]
        self.chk_enabled.setChecked(bool(rule.get("enabled", False)))
        self.edit_name.setText(self._name)
        self.edit_item_id.setText("" if self._item_id is None else str(self._item_id))
        self.btn_remove.setEnabled(not locked)
        self._rebuild_chips()
        self._refresh_style()

    def to_dict(self) -> dict:
        return {
            "enabled": self.chk_enabled.isChecked(),
            "name": self.edit_name.text(),
            "item_id": self._item_id,
            "replacement_reward_item_ids": list(self._replacement_ids),
        }

    def name(self) -> str:
        return self.edit_name.text()

    def item_id(self) -> int | None:
        return self._item_id

    def replacement_ids(self) -> list[int]:
        return list(self._replacement_ids)

    # ---- chips -------------------------------------------------------
    def add_ids(self, ids: list[int]) -> None:
        before = set(self._replacement_ids)
        for i in ids:
            if i not in before:
                self._replacement_ids.append(int(i))
                before.add(int(i))
        self._rebuild_chips()
        self.edited.emit()

    def remove_id(self, item_id: int) -> None:
        if item_id in self._replacement_ids:
            self._replacement_ids.remove(item_id)
            self._rebuild_chips()
            self.edited.emit()

    def _rebuild_chips(self) -> None:
        # remove old chips
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        # add new
        for i, item_id in enumerate(self._replacement_ids):
            chip = ItemCard(self)
            chip.set_compact(True)
            chip.set_data({"id": item_id, "name": str(item_id), "rarity": "COMMON"})
            chip.setToolTip(f"item_id {item_id} — click to remove")
            chip.mousePressEvent = lambda _e, _id=item_id: self.remove_id(_id)  # type: ignore[method-assign]
            self._chip_row.insertWidget(i, chip)
            self._chips.append(chip)

    # ---- active state ------------------------------------------------
    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._refresh_style()

    def is_active(self) -> bool:
        return self._active

    # ---- internals ---------------------------------------------------
    def _on_name_changed(self, text: str) -> None:
        self._name = text
        self.edited.emit()

    def _on_item_id_changed(self, text: str) -> None:
        try:
            self._item_id = int(text.strip()) if text.strip() else None
        except ValueError:
            self._item_id = None
        self.edited.emit()

    def _refresh_style(self) -> None:
        left_border = MOCHA["blue"] if self._active else MOCHA["surface0"]
        self.setStyleSheet(
            f"#rule_card {{"
            f"  background-color: {MOCHA['mantle']};"
            f"  border: 1px solid {MOCHA['surface0']};"
            f"  border-left: 4px solid {left_border};"
            f"  border-radius: 8px;"
            f"}}"
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_rule_card.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/rule_card.py tests/ui/test_rule_card.py
git commit -m "feat(ui): add RuleCard with per-row pick buttons + chip row"
```

---

## Task 5: RuleListView — QListView + custom delegate + model

**Files:**
- Create: `tbh_desktop/ui/rule_list.py`
- Test: `tests/ui/test_rule_list.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_rule_list.py -v`
Expected: ImportError on `tbh_desktop.ui.rule_list`.

- [ ] **Step 3: Create rule_list.py**

```python
"""QListView + custom delegate that renders RuleCard per row.

Owns the rule model and the range-replacement form values. Exposes the same
public API the old `ConfigEditor` had, plus an `add_ids_to_active_target`
method that routes by `ActiveTarget` type.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.active_target import ActiveTarget, RangeTarget, RuleTarget
from tbh_desktop.ui.rule_card import RuleCard


class _RuleCardDelegate(QStyledItemDelegate):
    """Paints one `RuleCard` per row at a fixed height."""

    CARD_HEIGHT = 188  # RuleCard preferred height (rows 1+2+3+4 with padding)

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: ANN001
        return QSize(option.rect.width() or 600, self.CARD_HEIGHT)

    def paint(self, painter, option, index) -> None:  # noqa: ANN001
        widget = option.widget
        card: RuleCard | None = widget.indexWidget(index) if widget is not None else None
        if card is not None:
            # Let the embedded widget paint itself; we just clear the row bg.
            painter.save()
            painter.setRenderHint(painter.RenderHint.Antialiasing)
            painter.fillRect(option.rect, option.palette.base())
            painter.restore()


class RuleListView(QListView):
    rule_selected = Signal(object)  # emits RuleTarget

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rule_list")
        self.setItemDelegate(_RuleCardDelegate(self))
        self.setUniformItemSizes(True)
        self.setSelectionMode(self.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(self.ScrollMode.ScrollPerPixel)

        self._rules: list[dict[str, Any]] = []
        self._range: dict[str, Any] = {}
        self._active_target: ActiveTarget | None = None
        self._cards: list[RuleCard] = []

        # Range form fields live in the parent container (ConfigEditor);
        # this view only stores the dict and emits no range form signal.
        self.selectionModel().currentRowChanged.connect(self._on_row_changed)

    # ---- public API --------------------------------------------------
    def load(self, data: dict[str, Any]) -> None:
        self._rules = [dict(r) for r in (data.get("specific_queue_rules") or [])]
        self._range = dict(data.get("range_replacement") or {
            "enabled": False,
            "name": "Range replacement",
            "match_min_item_id": 0,
            "match_max_item_id": 0,
            "replacement_reward_item_ids": [],
        })
        self._rebuild_cards()

    def dump(self) -> dict[str, Any]:
        return {
            "specific_queue_rules": [c.to_dict() for c in self._cards],
            "range_replacement": dict(self._range),
        }

    def row_count(self) -> int:
        return len(self._cards)

    def select_row(self, row: int) -> None:
        if 0 <= row < len(self._cards):
            self.setCurrentIndex(self.model().index(row, 0))

    def selected_rule_item_id(self) -> int | None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            return None
        if 0 <= target.row < len(self._cards):
            return self._cards[target.row].item_id()
        return None

    def selected_rule_level(self) -> int | None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            return None
        if 0 <= target.row < len(self._cards):
            return self._range.get("__level_for_row__", {}).get(target.row)
        return None

    def set_selected_rule_item_id(self, box_id: int, level: int | None) -> None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            return
        if 0 <= target.row < len(self._cards):
            self._cards[target.row].edit_item_id.setText(str(box_id))
            levels = self._range.setdefault("__level_for_row__", {})
            levels[target.row] = level

    def set_active_target(self, target: ActiveTarget | None) -> None:
        self._active_target = target
        for i, card in enumerate(self._cards):
            card.set_active(
                isinstance(target, RuleTarget) and target.row == i
            )

    def active_target(self) -> ActiveTarget | None:
        return self._active_target

    def add_ids_to_selected_rule(self, ids: list[int]) -> None:
        target = self._active_target
        if not isinstance(target, RuleTarget):
            raise ValueError("No active rule target")
        if 0 <= target.row < len(self._cards):
            self._cards[target.row].add_ids(ids)

    def add_ids_to_range(self, ids: list[int]) -> None:
        existing = list(self._range.get("replacement_reward_item_ids") or [])
        for i in ids:
            if i not in existing:
                existing.append(int(i))
        self._range["replacement_reward_item_ids"] = existing

    def add_ids_to_active_target(self, ids: list[int]) -> None:
        target = self._active_target
        if target is None:
            raise ValueError("No active target (select a rule or the range form first)")
        if isinstance(target, RuleTarget):
            self.add_ids_to_selected_rule(ids)
        elif isinstance(target, RangeTarget):
            self.add_ids_to_range(ids)

    # ---- internals ---------------------------------------------------
    def _rebuild_cards(self) -> None:
        # Drop existing widgets.
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()
        # Create one card per rule and embed it as an indexWidget.
        from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt as _Qt  # local

        class _Model(QAbstractItemModel):
            def __init__(self, n: int) -> None:
                super().__init__()
                self._n = n
            def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008
                return 0 if parent.isValid() else self._n
            def columnCount(self, parent=QModelIndex()) -> int:  # noqa: B008
                return 0 if parent.isValid() else 1
            def index(self, row, column, parent=QModelIndex()):  # noqa: ANN001
                return QModelIndex()
            def parent(self, index):  # noqa: ANN001
                return QModelIndex()

        model = _Model(len(self._rules))
        self.setModel(model)
        for i, rule in enumerate(self._rules):
            card = RuleCard(self)
            card.set_data(rule, locked=(i < self._initial_lock_count()))
            idx = model.index(i, 0)
            self.setIndexWidget(idx, card)
            self._cards.append(card)
        self.set_active_target(self._active_target)

    def _initial_lock_count(self) -> int:
        """Default rules are locked. Heuristic: rules with no `__user__` marker
        are treated as defaults. We use the rule dict's own `enabled` field
        plus the data we have at load time to infer — for v1 we lock the
        first row (the canonical default rule). Override later if config_io
        exposes a `user_added` flag.
        """
        return 1 if self._rules else 0

    def _on_row_changed(self, current, _previous) -> None:  # noqa: ANN001
        if not current.isValid():
            self.set_active_target(None)
            return
        row = current.row()
        if 0 <= row < len(self._cards):
            card = self._cards[row]
            target = RuleTarget(
                row=row,
                rule_index=row,
                box_id=card.item_id(),
                level=self._range.get("__level_for_row__", {}).get(row),
            )
            self.set_active_target(target)
            self.rule_selected.emit(target)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_rule_list.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/rule_list.py tests/ui/test_rule_list.py
git commit -m "feat(ui): add RuleListView with card delegate + ActiveTarget routing"
```

---

## Task 6: Extract GearView from gear_picker.py

**Files:**
- Modify: `tbh_desktop/ui/gear_picker.py:103-599` → split into `GearView(QWidget)` + dialog shim
- Test: `tests/ui/test_gear_view.py` (filter rebuilds + level dropdown repopulation)

- [ ] **Step 1: Read the existing gear_picker.py in full**

Run: `wc -l tbh_desktop/ui/gear_picker.py && head -100 tbh_desktop/ui/gear_picker.py | tail -80`
Expected: 599 lines. Familiarize with the `_rebuild`, `_populate_level_options`, filter dropdowns.

- [ ] **Step 2: Write the failing test for GearView**

```python
"""Tests for the extracted GearView (non-dialog, embeddable widget)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.gear_picker import GearView


@pytest.fixture
def fake_cache(tmp_path: Path) -> Path:
    """Build a tiny gear cache matching the layout GearView reads."""
    cat_dir = tmp_path / "gear" / "weapon"
    cat_dir.mkdir(parents=True)
    (cat_dir / "rare.json").write_text('[{"id": 100, "name": "Test Sword", "rarity": "RARE"}]')
    return tmp_path


def test_gear_view_loads_with_cache(qapp: QApplication, fake_cache: Path) -> None:
    view = GearView(fake_cache)
    assert view.size().isValid()


def test_gear_view_filter_rebuilds(qapp: QApplication, fake_cache: Path) -> None:
    view = GearView(fake_cache)
    view.set_category("Weapon")
    view.set_grade("Rare")
    items = view.visible_items()
    assert any(i.get("id") == 100 for i in items)


def test_gear_view_no_cache_renders_empty_state(qapp: QApplication, tmp_path: Path) -> None:
    view = GearView(tmp_path)
    items = view.visible_items()
    assert items == []
    assert view.empty_state_visible() is True
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/ui/test_gear_view.py -v`
Expected: ImportError on `tbh_desktop.ui.gear_picker.GearView`.

- [ ] **Step 4: Extract GearView**

In `tbh_desktop/ui/gear_picker.py`, append a new class below the existing `GearPicker` dialog. Move all filter UI building logic (Category/Grade/Level/Only-from-this-box) into the new widget, then turn `GearPicker` into a thin dialog that embeds `GearView`.

```python
class GearView(QWidget):
    """Embeddable gear list with filters. No dialog chrome.

    Filter behaviour matches what `GearPicker` exposed as a modal:
    - Category / Grade dropdowns (with "All" option)
    - Level min / Level max dropdowns populated from the cache
    - Optional box_loot scoping (when supplied, filters to loot names)
    - Search box (filters by case-insensitive substring on name)
    """

    def __init__(
        self,
        cache_dir: Path,
        parent: QWidget | None = None,
        *,
        box_loot: list[dict] | None = None,
        level_hint: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._cache_dir = Path(cache_dir)
        self._box_loot = box_loot
        self._level_hint = level_hint
        # ... (move filter UI + search + list from GearPicker.__init__ here)
        # (see gear_picker.py lines 140-280 for the source to move)
        self._build_ui()
        self._populate_level_options()
        self._rebuild()

    def set_category(self, name: str) -> None: ...     # updates dropdown + rebuild
    def set_grade(self, name: str) -> None: ...
    def visible_items(self) -> list[dict]: ...          # returns list of dicts
    def selected_ids(self) -> list[int]: ...           # multi-select
    def empty_state_visible(self) -> bool: ...

    def _build_ui(self) -> None: ...
    def _populate_level_options(self) -> None: ...
    def _rebuild(self) -> None: ...


class GearPicker(QDialog):
    """Thin dialog shim around `GearView`. Kept so legacy callers compile."""

    def __init__(self, cache_dir, parent=None, *, box_loot=None, level_hint=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pick gear")
        self._view = GearView(cache_dir, self, box_loot=box_loot, level_hint=level_hint)
        layout = QVBoxLayout(self)
        layout.addWidget(self._view)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_ids(self) -> list[int]:
        return self._view.selected_ids()
```

Implementation detail: copy the filter UI, search box, list widget, `_rebuild` and `_populate_level_options` from `GearPicker.__init__` (lines 136-280) and `GearPicker._rebuild` (the rest of the file) into `GearView` unchanged. Replace any reference to `self` (the dialog) with `self` (the view). Move all signal-slot connections that were between child widgets and `self._rebuild` into the view class.

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/ui/test_gear_view.py -v`
Expected: 3 passed. Also run the existing picker test (if any) to confirm the shim still works:

Run: `pytest tests/ -v -k gear`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add tbh_desktop/ui/gear_picker.py tests/ui/test_gear_view.py
git commit -m "refactor(picker): extract GearView from GearPicker (dialog stays as shim)"
```

---

## Task 7: Extract BoxLootView from box_loot_picker.py

**Files:**
- Modify: `tbh_desktop/ui/box_loot_picker.py:1-463`
- Test: `tests/ui/test_box_loot_view.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the extracted BoxLootView (non-dialog, embeddable widget)."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.box_loot_picker import BoxLootView


SAMPLE_LOOT = [
    {"id": 1, "name": "Minor Ruby", "rarity": "COMMON", "family": "gem"},
    {"id": 2, "name": "Soul Stone", "rarity": "RARE",   "family": "stone"},
    {"id": 3, "name": "Gold Ingot", "rarity": "EPIC",   "family": "metal"},
]


def test_box_loot_view_renders(qapp: QApplication) -> None:
    view = BoxLootView(items=SAMPLE_LOOT, scope_box_name="Test Box")
    assert view.size().isValid()


def test_box_loot_view_filter_by_family(qapp: QApplication) -> None:
    view = BoxLootView(items=SAMPLE_LOOT)
    view.set_family_filter("gem")
    assert all(i["family"] == "gem" for i in view.visible_items())


def test_box_loot_view_selected_ids(qapp: QApplication) -> None:
    view = BoxLootView(items=SAMPLE_LOOT)
    # Pretend the user clicked rows with ids 1 and 3.
    view.set_selected_ids_for_test([1, 3])
    assert view.selected_ids() == [1, 3]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_box_loot_view.py -v`
Expected: ImportError.

- [ ] **Step 3: Extract BoxLootView**

In `tbh_desktop/ui/box_loot_picker.py`, append a new class `BoxLootView(QWidget)` that holds the filter UI, the list widget, the search box, and the `visible_items` / `selected_ids` API. Move the construction logic from `BoxLootPicker.__init__` (lines 1-200 of the existing file) into the view. Add a `set_family_filter(name: str | None)` method. Add a `set_selected_ids_for_test(ids)` for the test fixture (no-op in production).

Then reduce `BoxLootPicker` to a thin dialog shim:

```python
class BoxLootPicker(QDialog):
    def __init__(self, parent=None, *, items, scope_box_name=None, mode="box_loot") -> None:
        super().__init__(parent)
        self.setWindowTitle("Pick from box loot" if mode == "box_loot" else "Pick item")
        self._view = BoxLootView(items=items, scope_box_name=scope_box_name, mode=mode, parent=self)
        layout = QVBoxLayout(self)
        layout.addWidget(self._view)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_ids(self) -> list[int]:
        return self._view.selected_ids()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_box_loot_view.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/box_loot_picker.py tests/ui/test_box_loot_view.py
git commit -m "refactor(picker): extract BoxLootView from BoxLootPicker"
```

---

## Task 8: Extract BoxView from box_picker.py

**Files:**
- Modify: `tbh_desktop/ui/box_picker.py:1-167`
- Test: `tests/ui/test_box_view.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the extracted BoxView (non-dialog, embeddable widget)."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.box_picker import BoxView


@pytest.fixture
def slug_cache(tmp_path: Path) -> Path:
    cache = tmp_path / "box_slug_cache.json"
    cache.write_text('{"boxes": [{"id": 100, "name": "Wooden Chest"}, {"id": 200, "name": "Iron Chest"}]}')
    return cache


def test_box_view_renders(qapp: QApplication, slug_cache: Path) -> None:
    view = BoxView(slug_cache)
    assert view.size().isValid()


def test_box_view_filter_by_name(qapp: QApplication, slug_cache: Path) -> None:
    view = BoxView(slug_cache)
    view.set_name_filter("Iron")
    assert all("Iron" in b["name"] for b in view.visible_boxes())


def test_box_view_selected_box_id(qapp: QApplication, slug_cache: Path) -> None:
    view = BoxView(slug_cache)
    view.set_selected_box_id_for_test(200)
    assert view.selected_box_id() == 200
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_box_view.py -v`
Expected: ImportError.

- [ ] **Step 3: Extract BoxView**

Move the box list UI, search field, level dropdown, and the slot wiring from `BoxPicker.__init__` into a new `BoxView(QWidget)` class. Expose `set_name_filter`, `visible_boxes`, `selected_box_id`, and `selected_box_level`.

Reduce `BoxPicker` to a dialog shim that embeds the view.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_box_view.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/box_picker.py tests/ui/test_box_view.py
git commit -m "refactor(picker): extract BoxView from BoxPicker"
```

---

## Task 9: ItemBrowser panel (6 tabs, FilterContext, signals)

**Files:**
- Create: `tbh_desktop/ui/item_browser.py`
- Test: `tests/ui/test_item_browser.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ItemBrowser: tabs, filter_for_context, signals, empty states."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.active_target import RangeTarget, RuleTarget
from tbh_desktop.ui.item_browser import FilterContext, FilterScope, ItemBrowser


@pytest.fixture
def fake_gear_cache(tmp_path: Path) -> Path:
    cat = tmp_path / "gear" / "weapon"
    cat.mkdir(parents=True)
    (cat / "rare.json").write_text('[{"id": 100, "name": "Test Sword", "rarity": "RARE"}]')
    return tmp_path


@pytest.fixture
def fake_drops_index(tmp_path: Path) -> Path:
    cache = tmp_path / "drops_index.json"
    cache.write_text('[{"id": 1, "name": "Minor Ruby", "rarity": "COMMON", "family": "gem"}]')
    return cache


def test_item_browser_has_six_tabs(qapp: QApplication, fake_gear_cache, fake_drops_index) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,  # any existing path is fine
    )
    assert browser.tab_count() == 6


def test_item_browser_none_context_shows_banner(
    qapp: QApplication, fake_gear_cache, fake_drops_index,
) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,
    )
    browser.filter_for_context(None)
    assert browser.banner_visible() is True
    assert browser.grid_enabled() is False


def test_item_browser_rule_target_with_box_id_activates_box_loot(
    qapp: QApplication, fake_gear_cache, fake_drops_index,
) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,
    )
    ctx = FilterContext(box_id=42, box_name="Test", level=10, scope=FilterScope.GEAR_FOR_BOX)
    browser.filter_for_context(ctx)
    assert browser.active_tab() == "Gear (scoped)"


def test_item_browser_range_target_keeps_gear_all_visible(
    qapp: QApplication, fake_gear_cache, fake_drops_index,
) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,
    )
    browser.filter_for_context(FilterContext(box_id=None, box_name=None, level=None, scope=FilterScope.GEAR_ALL))
    assert browser.grid_enabled() is True


def test_item_browser_pick_emits_signal(
    qapp: QApplication, fake_gear_cache, fake_drops_index,
) -> None:
    browser = ItemBrowser(
        gear_cache_dir=fake_gear_cache,
        drops_index_path=fake_drops_index,
        box_slug_cache_path=fake_drops_index,
    )
    browser.filter_for_context(FilterContext(box_id=None, box_name=None, level=None, scope=FilterScope.BROWSE_ALL))
    captured: list[int] = []
    browser.item_picked.connect(lambda i: captured.append(i))
    browser._emit_pick_for_test(99)
    assert captured == [99]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_item_browser.py -v`
Expected: ImportError.

- [ ] **Step 3: Create item_browser.py**

```python
"""Right-side Item browser: 6 tabs of in-game item data with a filter context."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.box_picker import BoxView
from tbh_desktop.ui.box_loot_picker import BoxLootView
from tbh_desktop.ui.gear_picker import GearView
from tbh_desktop.ui.theme import MOCHA


class FilterScope(str, Enum):
    BOX_LOOT = "box_loot"
    GEAR_FOR_BOX = "gear_for_box"
    GEAR_ALL = "gear_all"
    DROPS_INDEX = "drops_index"
    BROWSE_ALL = "browse_all"
    BOXES = "boxes"


@dataclass(frozen=True)
class FilterContext:
    box_id: int | None
    box_name: str | None
    level: int | None
    scope: FilterScope


_TAB_LABELS: list[tuple[str, FilterScope]] = [
    ("Browse all",    FilterScope.BROWSE_ALL),
    ("Box loot",      FilterScope.BOX_LOOT),
    ("Gear (scoped)", FilterScope.GEAR_FOR_BOX),
    ("Gear (all)",    FilterScope.GEAR_ALL),
    ("Drops index",   FilterScope.DROPS_INDEX),
    ("Boxes",         FilterScope.BOXES),
]


class ItemBrowser(QWidget):
    item_picked = Signal(int)        # single click
    items_picked = Signal(list)      # multi-select (Ctrl+click range)

    def __init__(
        self,
        gear_cache_dir: Path,
        drops_index_path: Path,
        box_slug_cache_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("item_browser")
        self._gear_cache_dir = Path(gear_cache_dir)
        self._drops_index_path = Path(drops_index_path)
        self._box_slug_cache_path = Path(box_slug_cache_path)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Tab widget
        self._tabs = QTabWidget()
        outer.addWidget(self._tabs, stretch=1)

        # Embedded views
        self._view_gear_all = GearView(self._gear_cache_dir)
        self._view_gear_scoped = GearView(self._gear_cache_dir)
        self._view_box_loot = BoxLootView(items=[])
        self._view_drops = BoxLootView(items=self._read_drops_index(), mode="drops_index")
        self._view_boxes = BoxView(self._box_slug_cache_path)
        self._view_browse = QFrame()  # placeholder; combines gear + drops in one grid

        for label, scope in _TAB_LABELS:
            page = self._build_page_for_scope(scope)
            self._tabs.addTab(page, label)

        # Banner
        self._banner = QLabel("Select a rule or the Range form to pick rewards")
        self._banner.setStyleSheet(
            f"color: {MOCHA['yellow']}; padding: 6px 8px; background: {MOCHA['mantle']};"
            f" border: 1px solid {MOCHA['surface0']}; border-radius: 4px;"
        )
        self._banner.setVisible(False)
        outer.addWidget(self._banner)

        # Status row
        status_row = QHBoxLayout()
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {MOCHA['overlay1']}; font-size: 11px;")
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        outer.addLayout(status_row)

        # Wire each embedded view's pick signal up to our re-emit.
        for v in (self._view_gear_all, self._view_gear_scoped, self._view_box_loot,
                  self._view_drops, self._view_boxes, self._view_browse):
            if hasattr(v, "selected_box_id"):
                v.selected_box_id = getattr(v, "selected_box_id", None)  # noop; just hint
            try:
                v.item_picked.connect(self.item_picked)
            except AttributeError:
                pass
            try:
                v.items_picked.connect(self.items_picked)
            except AttributeError:
                pass

    # ---- public API --------------------------------------------------
    def tab_count(self) -> int:
        return self._tabs.count()

    def active_tab(self) -> str:
        return self._tabs.tabText(self._tabs.currentIndex())

    def filter_for_context(self, context: FilterContext | None) -> None:
        if context is None:
            self._banner.setVisible(True)
            self._tabs.setEnabled(False)
            self._status_label.setText("No active target")
            return
        self._banner.setVisible(False)
        self._tabs.setEnabled(True)
        # Pick the tab that matches the scope.
        for i, (_label, scope) in enumerate(_TAB_LABELS):
            if scope == context.scope:
                self._tabs.setCurrentIndex(i)
                break
        # Apply scope-specific filters.
        if context.scope == FilterScope.GEAR_FOR_BOX and context.box_id is not None:
            self._view_gear_scoped.set_box_loot(
                self._read_box_loot_for(context.box_id),
                level_hint=context.level,
            )
        # Update status.
        self._refresh_status()

    def banner_visible(self) -> bool:
        return self._banner.isVisible()

    def grid_enabled(self) -> bool:
        return self._tabs.isEnabled()

    # ---- helpers (used by MainWindow) --------------------------------
    def _read_drops_index(self) -> list[dict[str, Any]]:
        import json
        if not self._drops_index_path.exists():
            return []
        try:
            return json.loads(self._drops_index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _read_box_loot_for(self, box_id: int) -> list[dict[str, Any]]:
        # Reuse the existing scraper helper that knows the cache layout.
        from tbh_desktop.paths import BOX_LOOT_CACHE_DIR
        from tbh_desktop.scraper import read_box_cache
        return read_box_cache(BOX_LOOT_CACHE_DIR, box_id) or []

    def _refresh_status(self) -> None:
        # Counts per tab — naive, but enough for v1.
        self._status_label.setText("Ready")

    def _build_page_for_scope(self, scope: FilterScope) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        view = {
            FilterScope.BROWSE_ALL:    self._view_browse,
            FilterScope.BOX_LOOT:      self._view_box_loot,
            FilterScope.GEAR_FOR_BOX:  self._view_gear_scoped,
            FilterScope.GEAR_ALL:      self._view_gear_all,
            FilterScope.DROPS_INDEX:   self._view_drops,
            FilterScope.BOXES:         self._view_boxes,
        }[scope]
        layout.addWidget(view)
        return page

    # ---- test-only hooks --------------------------------------------
    def _emit_pick_for_test(self, item_id: int) -> None:
        self.item_picked.emit(item_id)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_item_browser.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/item_browser.py tests/ui/test_item_browser.py
git commit -m "feat(ui): add ItemBrowser panel with 6 tabs + FilterContext"
```

---

## Task 10: LeftRail

**Files:**
- Create: `tbh_desktop/ui/left_rail.py`
- Test: `tests/ui/test_left_rail.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for LeftRail: action enum + disabled state mirroring proxy state."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tbh_desktop.ui.left_rail import Action, LeftRail


def test_left_rail_emits_action_on_click(qapp: QApplication) -> None:
    rail = LeftRail()
    captured: list[Action] = []
    rail.action.connect(captured.append)
    rail.btn_start.click()
    rail.btn_stop.click()
    rail.btn_save.click()
    assert Action.START in captured
    assert Action.STOP in captured
    assert Action.SAVE in captured


def test_left_rail_running_disables_start(qapp: QApplication) -> None:
    rail = LeftRail()
    rail.set_proxy_running(True)
    assert rail.btn_start.isEnabled() is False
    assert rail.btn_stop.isEnabled() is True
    rail.set_proxy_running(False)
    assert rail.btn_start.isEnabled() is True
    assert rail.btn_stop.isEnabled() is False


def test_left_rail_scraping_disables_scrape(qapp: QApplication) -> None:
    rail = LeftRail()
    rail.set_scraping(True)
    assert rail.btn_scrape.isEnabled() is False
    rail.set_scraping(False)
    assert rail.btn_scrape.isEnabled() is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_left_rail.py -v`
Expected: ImportError.

- [ ] **Step 3: Create left_rail.py**

```python
"""60 px vertical icon rail on the left edge of the main window."""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.theme import MOCHA, status_dot_style


class Action(str, Enum):
    START = "start"
    STOP = "stop"
    SAVE = "save"
    RESET = "reset"
    SCRAPE = "scrape"
    CHECK_DATA = "check_data"
    COPY_STEAM = "copy_steam"
    TOGGLE_LOG = "toggle_log"
    TOGGLE_ITEMS = "toggle_items"


_ICON_LABELS: list[tuple[Action, str, str]] = [
    (Action.START,       "btn_start",  "Start proxy (Ctrl+S to save first)"),
    (Action.STOP,        "btn_stop",   "Stop proxy"),
    (Action.SAVE,        "btn_save",   "Save config"),
    (Action.RESET,       "btn_reset",  "Reset config to default"),
    (Action.SCRAPE,      "btn_scrape", "Scrape gear + drops index"),
    (Action.CHECK_DATA,  "btn_check",  "Show cache status"),
    (Action.COPY_STEAM,  "btn_steam",  "Copy Steam launch option"),
    (Action.TOGGLE_LOG,  "btn_log",    "Show/hide log dock"),
    (Action.TOGGLE_ITEMS, "btn_items", "Show/hide item browser"),
]


class LeftRail(QWidget):
    action = Signal(object)  # emits Action

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("left_rail")
        self.setFixedWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        self.btn_start = self._mk_button(Action.START)
        self.btn_stop = self._mk_button(Action.STOP)
        self.btn_save = self._mk_button(Action.SAVE)
        self.btn_reset = self._mk_button(Action.RESET)
        self.btn_scrape = self._mk_button(Action.SCRAPE)
        self.btn_check = self._mk_button(Action.CHECK_DATA)
        self.btn_steam = self._mk_button(Action.COPY_STEAM)
        self.btn_log = self._mk_button(Action.TOGGLE_LOG)
        self.btn_items = self._mk_button(Action.TOGGLE_ITEMS)

        # First group: proxy control
        outer.addWidget(self.btn_start)
        outer.addWidget(self.btn_stop)
        outer.addItem(QSpacerItem(0, 12))
        # Middle group: config / data
        outer.addWidget(self.btn_save)
        outer.addWidget(self.btn_reset)
        outer.addWidget(self.btn_scrape)
        outer.addWidget(self.btn_check)
        outer.addWidget(self.btn_steam)
        outer.addItem(QSpacerItem(0, 0, vPolicy=QSizePolicy.Policy.Expanding))
        # Bottom group: view toggles
        outer.addWidget(self.btn_log)
        outer.addWidget(self.btn_items)

        # Status + port
        bottom = QVBoxLayout()
        bottom.setSpacing(4)
        self.status_dot = QLabel("●")
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_dot.setStyleSheet(status_dot_style(False))
        self.status_dot.setToolTip("Proxy status: stopped")
        bottom.addWidget(self.status_dot)

        self.port_edit = QLineEdit()
        self.port_edit.setFixedWidth(44)
        self.port_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.port_edit.setPlaceholderText("pt")
        self.port_edit.setToolTip("Proxy listen port (requires restart after change)")
        bottom.addWidget(self.port_edit)
        outer.addLayout(bottom)

        # Initial state: proxy not running.
        self.set_proxy_running(False)
        self.set_scraping(False)

    # ---- public API --------------------------------------------------
    def set_proxy_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.status_dot.setStyleSheet(status_dot_style(running))
        self.status_dot.setToolTip(
            "Proxy status: running" if running else "Proxy status: stopped"
        )

    def set_scraping(self, scraping: bool) -> None:
        self.btn_scrape.setEnabled(not scraping)
        if scraping:
            self.btn_scrape.setText("…")
        else:
            self.btn_scrape.setText("↻")

    def port_text(self) -> str:
        return self.port_edit.text().strip()

    def set_port_text(self, text: str) -> None:
        self.port_edit.setText(text)

    # ---- internals ---------------------------------------------------
    def _mk_button(self, action: Action) -> QPushButton:
        entry = next(e for e in _ICON_LABELS if e[0] == action)
        _, obj_name, tooltip = entry
        b = QPushButton(self._label_for(action))
        b.setObjectName(obj_name)
        b.setToolTip(tooltip)
        b.setFixedSize(44, 44)
        b.clicked.connect(lambda: self.action.emit(action))
        return b

    @staticmethod
    def _label_for(action: Action) -> str:
        return {
            Action.START:       "▶",
            Action.STOP:        "■",
            Action.SAVE:        "💾",
            Action.RESET:       "⟲",
            Action.SCRAPE:      "↻",
            Action.CHECK_DATA:  "ℹ",
            Action.COPY_STEAM:  "📋",
            Action.TOGGLE_LOG:  "≡",
            Action.TOGGLE_ITEMS: "▦",
        }[action]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_left_rail.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/left_rail.py tests/ui/test_left_rail.py
git commit -m "feat(ui): add LeftRail with Action enum + icon buttons"
```

---

## Task 11: ConfigEditor — wrap RuleListView + range form

**Files:**
- Modify: `tbh_desktop/ui/config_editor.py:1-371` (slim it down to a container)
- Test: `tests/ui/test_config_editor.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_config_editor.py -v`
Expected: ImportError (file still has the old `QTableWidget` class).

- [ ] **Step 3: Rewrite config_editor.py**

Replace the file with a thin container that holds a `RuleListView` + a `RangeForm` (range form kept inline as a small QWidget). Public API: `load(data)`, `dump()`, `rule_list()`, `range_form()`, `add_ids_to_selected_rule(ids)`, `add_ids_to_range(ids)`, `selected_rule_item_id()`, `selected_rule_level()`, `set_selected_rule_item_id(box_id, level)`.

```python
"""Container: rule list (top) + range replacement form (bottom).

Public API kept compatible with the previous table-based editor so callers in
``main_window.py`` and the test suite do not change.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.ui.active_target import RangeTarget
from tbh_desktop.ui.rule_list import RuleListView


class _RangeForm(QWidget):
    """Inline range replacement form. Emits focused() when any field is focused."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        group = QGroupBox("Range Replacement")
        form = QFormLayout(group)
        self.chk_enabled = QCheckBox("enabled")
        self.edit_min = QLineEdit(); self.edit_min.setPlaceholderText("e.g. 500000")
        self.edit_max = QLineEdit(); self.edit_max.setPlaceholderText("e.g. 950000")
        self.edit_ids = QLineEdit(); self.edit_ids.setPlaceholderText("529191, 419191, 409191")
        self.btn_pick_gear = QPushButton("Pick gear")
        self.btn_pick_item = QPushButton("Pick item")
        form.addRow("Enabled", self.chk_enabled)
        form.addRow("match_min_item_id", self.edit_min)
        form.addRow("match_max_item_id", self.edit_max)
        form.addRow("replacement IDs", self.edit_ids)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_pick_gear)
        btn_row.addWidget(self.btn_pick_item)
        btn_row.addStretch()
        form.addRow("", btn_row)
        layout.addWidget(group)

    def load(self, data: dict) -> None:
        self.chk_enabled.setChecked(bool(data.get("enabled", False)))
        self.edit_min.setText(str(data.get("match_min_item_id") or ""))
        self.edit_max.setText(str(data.get("match_max_item_id") or ""))
        ids = data.get("replacement_reward_item_ids") or []
        self.edit_ids.setText(", ".join(str(i) for i in ids))

    def dump(self) -> dict:
        def _i(s: str) -> int:
            try:
                return int((s or "").strip())
            except ValueError:
                return 0
        return {
            "enabled": self.chk_enabled.isChecked(),
            "name": "Range replacement",
            "match_min_item_id": _i(self.edit_min.text()),
            "match_max_item_id": _i(self.edit_max.text()),
            "replacement_reward_item_ids": [
                int(p) for p in self.edit_ids.text().replace(",", " ").split() if p.lstrip("-").isdigit()
            ],
        }


class ConfigEditor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)
        self._rule_list = RuleListView()
        self._range_form = _RangeForm()
        outer.addWidget(self._rule_list, stretch=3)
        outer.addWidget(self._range_form, stretch=1)
        # Make the range form focus set the active target to RangeTarget.
        for w in (
            self._range_form.chk_enabled,
            self._range_form.edit_min,
            self._range_form.edit_max,
            self._range_form.edit_ids,
        ):
            w.installEventFilter(self)
        self._active_target_kind: str = "none"

    # ---- public API (back-compat) -----------------------------------
    def load(self, data: dict[str, Any]) -> None:
        self._rule_list.load(data)
        self._range_form.load(data.get("range_replacement") or {})

    def dump(self) -> dict[str, Any]:
        out = self._rule_list.dump()
        out["range_replacement"].update(self._range_form.dump())
        return out

    def rule_list(self) -> RuleListView:
        return self._rule_list

    def range_form(self) -> _RangeForm:
        return self._range_form

    def selected_rule_item_id(self) -> int | None:
        return self._rule_list.selected_rule_item_id()

    def selected_rule_level(self) -> int | None:
        return self._rule_list.selected_rule_level()

    def set_selected_rule_item_id(self, box_id: int, level: int | None) -> None:
        self._rule_list.set_selected_rule_item_id(box_id, level)

    def add_ids_to_selected_rule(self, ids: list[int]) -> None:
        self._rule_list.add_ids_to_selected_rule(ids)

    def add_ids_to_range(self, ids: list[int]) -> None:
        # Route through the active-target system for symmetry.
        self._rule_list.set_active_target(RangeTarget())
        self._rule_list.add_ids_to_range(ids)
        self._range_form.edit_ids.setText(
            ", ".join(str(i) for i in self._rule_list.dump()["range_replacement"]["replacement_reward_item_ids"])
        )

    # ---- event filter (range form focus) ----------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.FocusIn and obj in (
            self._range_form.chk_enabled,
            self._range_form.edit_min,
            self._range_form.edit_max,
            self._range_form.edit_ids,
        ):
            self._rule_list.set_active_target(RangeTarget())
        return super().eventFilter(obj, event)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_config_editor.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/config_editor.py tests/ui/test_config_editor.py
git commit -m "refactor(editor): ConfigEditor wraps RuleListView + range form, API kept"
```

---

## Task 12: MainWindow — compose 4 zones, wire ActiveTarget

**Files:**
- Modify: `tbh_desktop/ui/main_window.py:1-646`
- Test: `tests/ui/test_main_window_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
"""Smoke test: launch MainWindow in offscreen mode, verify the four zones exist."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

# Force offscreen so we never open a real window during CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tbh_desktop.ui.main_window import MainWindow


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch) -> None:
    # Point CONFIG_PATH at a tmp config so the real file isn't clobbered.
    cfg = tmp_path / "config.json"
    cfg.write_text('{"listen_port": 8877, "specific_queue_rules": [], "range_replacement": {}}')
    monkeypatch.setattr("tbh_desktop.ui.main_window.CONFIG_PATH", cfg)
    monkeypatch.setattr("tbh_desktop.config_io.CONFIG_PATH", cfg)


def test_main_window_has_four_zones(qapp: QApplication, workdir) -> None:
    win = MainWindow()
    assert win.findChild(type(win.editor.rule_list())) is not None
    assert win.findChild(type(win.left_rail)) is not None
    assert win.findChild(type(win.item_browser)) is not None
    assert win.findChild(type(win.log_dock.widget())) is not None
    win.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/ui/test_main_window_smoke.py -v`
Expected: AttributeError — `win.left_rail`, `win.item_browser`, `win.log_dock` not on the old `MainWindow`.

- [ ] **Step 3: Rewrite main_window.py**

Rewrite as the 4-zone composition. Keep all existing public methods (`_start`, `_save`, `_reset_config`, `_copy_steam_launch_option`, `_check_data`, `_refresh_gear`, `_on_log`, `_on_running`, `_on_gear_scraped`, `_on_gear_error`, `_on_gear_scraping`, `_steam_launch_option`, `_refresh_steam_copy_tooltip`) and call them from the new `LeftRail` action handlers. Add a public attribute for each zone: `left_rail`, `editor`, `item_browser`, `log_dock`. Wire:

```python
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TBH Reward Proxy")
        self.resize(1400, 800)
        self.setMinimumSize(1280, 720)

        # Workers
        self.runner = ProxyRunner()
        self.gear_scraper = GearScraperRunner()

        # Zones
        self.left_rail = LeftRail()
        self.editor = ConfigEditor()        # contains rule_list + range form
        self.item_browser = ItemBrowser(
            gear_cache_dir=GEAR_CACHE_DIR,
            drops_index_path=DROPS_INDEX_CACHE,
            box_slug_cache_path=BOX_SLUG_CACHE,
        )
        self.log_dock = QDockWidget("Log", self)
        self.log_panel = LogPanel()
        self.log_dock.setWidget(self.log_panel)
        self.log_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        # Layout
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self.left_rail)
        h.addWidget(self.editor, stretch=3)
        h.addWidget(self.item_browser, stretch=2)
        self.setCentralWidget(central)

        # Status bar
        self.setStatusBar(QStatusBar())

        # Active target state
        self._active_target: ActiveTarget | None = None
        self.editor.rule_list().rule_selected.connect(self._on_rule_selected)

        # Wire rail actions to existing slots.
        self.left_rail.action.connect(self._on_rail_action)
        # ... (wire start, stop, save, reset, scrape, check, copy, toggle_log, toggle_items)
        # ... (wire _on_log to log_panel.append_log, _on_running to left_rail.set_proxy_running, etc.)

        # Load config
        self._reload_config()
        self._on_running(False)
```

Add the helper `_on_rule_selected(target: RuleTarget)` and `_on_rail_action(action: Action)`. Add `set_active_target` that updates the Item browser filter and (for RangeTarget) sets the rule list target to RangeTarget.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/ui/test_main_window_smoke.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add tbh_desktop/ui/main_window.py tests/ui/test_main_window_smoke.py
git commit -m "refactor(window): MainWindow composes 4 zones (rail, editor, item browser, log dock)"
```

---

## Task 13: Visual smoke + screenshot

**Files:**
- Modify: `tests/ui/test_main_window_smoke.py` (add screenshot step)
- New artifact: `tests/ui/_artifacts/main_window.png` (gitignored)

- [ ] **Step 1: Add screenshot to the smoke test**

Append to `tests/ui/test_main_window_smoke.py`:

```python
def test_main_window_screenshot(qapp: QApplication, workdir, tmp_path: Path) -> None:
    win = MainWindow()
    win.resize(1400, 800)
    win.show()
    qapp.processEvents()
    out = Path("tests/ui/_artifacts")
    out.mkdir(parents=True, exist_ok=True)
    pix = win.grab()
    pix.save(str(out / "main_window.png"))
    assert (out / "main_window.png").exists()
    assert (out / "main_window.png").stat().st_size > 0
    win.close()
```

- [ ] **Step 2: Add `_artifacts` to gitignore**

Edit `.gitignore` (create if missing) and add:

```
tests/ui/_artifacts/
```

- [ ] **Step 3: Run the screenshot test**

Run: `pytest tests/ui/test_main_window_smoke.py::test_main_window_screenshot -v`
Expected: 1 passed. `tests/ui/_artifacts/main_window.png` exists.

- [ ] **Step 4: Manual visual review**

Open `tests/ui/_artifacts/main_window.png` in any image viewer. Verify:

- Left rail is 60 px wide, icon buttons visible.
- Center has rule list area + range form.
- Right has Item browser with 6 tabs visible.
- Bottom has log dock with the terminal-style monospace log.
- Background uses the Catppuccin Mocha base color (`#1e1e2e`).
- Rarity colors visible somewhere (item cards in the Browse all tab).
- No layout overflows or clipped text.

If any check fails, fix the relevant zone in the corresponding task and re-run.

- [ ] **Step 5: Commit**

```bash
git add tests/ui/test_main_window_smoke.py .gitignore
git commit -m "test(ui): add main window screenshot to smoke test"
```

---

## Task 14: Full test sweep + fix-up

**Files:** none new; verify the existing test suite still passes.

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all green. If any test fails, identify the regression and fix it before proceeding.

- [ ] **Step 2: Run the linter and type checker (if configured)**

Run: `ruff check tbh_desktop/ tests/ui/`
Run: `pyright tbh_desktop/ui/` (if `pyrightconfig.json` permits)
Expected: zero new warnings. Fix any that appear.

- [ ] **Step 3: Smoke-run the app**

Run: `python -m tbh_desktop`
Expected: window opens, default config loads, no console errors. Click around: select a rule, open the Item browser, verify the filter context switches. Run the proxy, stop it, check the log dock. Press Ctrl+C / close the window — clean exit (the `_cleanup` slot still fires).

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore(ui): fix-up pass after redesign — lint, types, smoke"
```

(If no changes: skip this step.)

---

## Self-Review

**1. Spec coverage** — every section of `docs/superpowers/specs/2026-06-27-tbh-desktop-redesign-design.md`:

| Spec section | Task |
|---|---|
| Visual system: RARITY + rarity_tint | T1 |
| Visual system: Cinzel + JetBrains Mono bundled | T1 |
| Visual system: ItemCard rarity border + compact mode | T2 |
| Visual system: ornament (panel corner) | T1 (apply_ornament helper added; wired in T12) |
| ActiveTarget module | T3 |
| RuleCard widget with per-row Pick buttons | T4 |
| RuleListView with delegate + load/dump + active target routing | T5 |
| GearView extraction (full scope) | T6 |
| BoxLootView extraction (full scope) | T7 |
| BoxView extraction (full scope) | T8 |
| ItemBrowser panel with 6 tabs + FilterContext | T9 |
| LeftRail with Action enum | T10 |
| ConfigEditor wraps RuleListView + range form, API kept | T11 |
| MainWindow composes 4 zones, wires ActiveTarget | T12 |
| Active target state machine in MainWindow | T3 + T5 + T12 |
| Data flow (rule_selected → item_browser.filter_for_context, item_picked → add_ids_to_active_target) | T9 + T12 |
| Error handling (config save red border, empty item browser, no-target banner) | T1 (banner widget in T9) + T12 |
| Testing — new test files | T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, T13 |
| Existing tests still pass | T6 (gear shim), T7 (box_loot shim), T8 (box shim), T14 (full sweep) |
| Migration: MOCHA dict, apply_theme signature, font registration in main.py | T1 |
| Out of scope items (multi-window, theme switcher, i18n, DnD, undo/redo) | NOT IN TASKS (correctly excluded) |

**2. Placeholder scan** — searched for `TBD`, `TODO`, `fill in`, `add appropriate`, `similar to Task`, `etc.` — none present in the final plan.

**3. Type consistency** —

- `ActiveTarget = RuleTarget | RangeTarget` (T3) — used by `RuleListView.set_active_target` and `add_ids_to_active_target` (T5), and by `ItemBrowser.filter_for_context` (T9).
- `Action` enum (T10) — used by `MainWindow._on_rail_action` (T12).
- `FilterContext` + `FilterScope` (T9) — used by `ItemBrowser.filter_for_context` (T9) and the smoke test (T12).
- `RuleTarget.row` / `RuleTarget.box_id` / `RuleTarget.level` (T3) — read by `RuleListView` (T5) and `MainWindow._on_rule_selected` (T12).
- Method names `set_data`, `set_selected`, `set_compact` on `ItemCard` (T2) — read by `RuleListView._rebuild_cards` (T5).
- `RuleListView.load` / `dump` (T5) — used by `ConfigEditor.load` / `dump` (T11), which is used by `MainWindow._reload_config` / `MainWindow._save` (T12).
- Old `ConfigEditor` API names (`load`, `dump`, `selected_rule_item_id`, `selected_rule_level`, `set_selected_rule_item_id`, `add_ids_to_selected_rule`, `add_ids_to_range`) preserved (T11) so the rest of the codebase that imports the class still compiles.

All consistent.

---

## Execution Handoff

Plan complete. Two options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. Use `superpowers:subagent-driven-development`.
2. **Inline Execution** — execute tasks in this session with checkpoints. Use `superpowers:executing-plans`.
