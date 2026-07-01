"""Stage picker dialog — list 120 stages from stages_index.json.

Used by the rule editor's ``Pick pool`` button. The user picks a
specific stage (act + stage_no + difficulty); the dialog fetches
that stage's detail page from the local cache to find the matching
drop_key for the active rule's kind (Normal / Boss / Act), then
returns the drop_key for the caller to set as the rule's pool_id.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tbh_desktop.paths import STAGES_DIR, STAGES_INDEX_CACHE
from tbh_desktop.ui.theme import MOCHA, section_heading_style


# tbh.city drop pool name → reward_kind label in this UI.
_POOL_BY_KIND: dict[str, str] = {
    "normal": "monster_pool",
    "boss": "boss_pool",
    "act": "boss_pool",  # act-boss stages use boss_pool with ACTBOSS type
}


def _load_stage_pool_drop_key(stage_id: int, kind: str) -> int | None:
    """Read the cached stage detail and return the drop_key for the
    pool matching ``kind`` (normal / boss / act).

    Returns None when the cache file is missing or the pool doesn't
    exist. The act-boss case is disambiguated by stage type — the
    boss_pool on an ACTBOSS stage is the Act Reward pool, on a BOSS
    or NORMAL stage it's the Boss Reward pool.
    """
    pool_name = _POOL_BY_KIND.get(kind)
    if pool_name is None:
        return None
    detail_path = STAGES_DIR / f"{stage_id}.json"
    if not detail_path.exists():
        return None
    try:
        data = json.loads(detail_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    drops = data.get("drops") or {}
    pool = drops.get(pool_name) or []
    if not pool:
        return None
    # For act reward, the stage itself must be ACTBOSS — the boss_pool
    # on a NORMAL stage is a different pool (the "stage boss" mini-boss).
    if kind == "act" and data.get("type") != "ACTBOSS":
        return None
    if kind in ("normal", "boss") and data.get("type") == "ACTBOSS":
        return None  # act stages' boss_pool is the act pool, not the boss pool
    for entry in pool:
        if isinstance(entry, dict):
            dk = entry.get("drop_key")
            if isinstance(dk, int):
                return dk
    return None


def _load_stages_index() -> list[dict[str, Any]]:
    """Load the stages index from cache. Empty list when absent."""
    if not STAGES_INDEX_CACHE.exists():
        return []
    try:
        payload = json.loads(STAGES_INDEX_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(payload, dict):
        stages = payload.get("stages") or []
        return [s for s in stages if isinstance(s, dict)]
    if isinstance(payload, list):
        return [s for s in payload if isinstance(s, dict)]
    return []


class StagePickerDialog(QDialog):
    """Modal list of stages grouped by act + difficulty-filterable.

    Jul 2026 layout:
      * Top: difficulty filter chips (All / Normal / Nightmare /
        Hell / Torment) so the user can scope to a single
        difficulty band.
      * List: grouped by act (header row per act), then by stage_no,
        then by difficulty in N → NM → H → T order. ACTBOSS rows
        tagged so they're easy to spot.

    Picking a stage reads the matching drop_key from the cached
    stage detail and emits ``pool_key_selected(int)`` on accept.
    """

    pool_key_selected = Signal(int)

    # Difficulty display order.
    _DIFFICULTIES = ("NORMAL", "NIGHTMARE", "HELL", "TORMENT")
    _DIFF_LABEL = {
        "NORMAL": "Normal",
        "NIGHTMARE": "Nightmare",
        "HELL": "Hell",
        "TORMENT": "Torment",
    }

    def __init__(
        self,
        reward_kind: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("stage_picker_dialog")
        self.setWindowTitle(f"Pick {reward_kind.title()} pool")
        self.setMinimumSize(560, 560)
        self._reward_kind = reward_kind
        self._active_difficulty: str | None = None  # None = "All"
        # Cache so we don't re-read on every filter click.
        self._all_stages: list[dict[str, Any]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        heading = QLabel(f"Pick a stage — its {reward_kind} drop pool will be set.")
        heading.setObjectName("panel_heading")
        heading.setStyleSheet(section_heading_style())
        outer.addWidget(heading)

        # ---- Difficulty filter chips -------------------------------
        # Radio-style within this row: click one chip to scope the
        # list to a single difficulty (or "All" for everything).
        diff_row = QHBoxLayout()
        diff_row.setSpacing(6)
        diff_label = QLabel("Difficulty")
        diff_label.setStyleSheet(
            f"color: {MOCHA['overlay1']}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 2px; padding-right: 6px;"
        )
        diff_row.addWidget(diff_label)
        self._diff_buttons: list[QPushButton] = []
        # "All" chip — pre-checked.
        all_btn = QPushButton("All")
        all_btn.setCheckable(True)
        all_btn.setProperty("toolbar_zone", "secondary")
        all_btn.setProperty("diff_value", "")
        all_btn.setChecked(True)
        all_btn.clicked.connect(self._on_diff_clicked)
        diff_row.addWidget(all_btn)
        self._diff_buttons.append(all_btn)
        for d in self._DIFFICULTIES:
            btn = QPushButton(self._DIFF_LABEL[d])
            btn.setCheckable(True)
            btn.setProperty("toolbar_zone", "secondary")
            btn.setProperty("diff_value", d)
            btn.clicked.connect(self._on_diff_clicked)
            diff_row.addWidget(btn)
            self._diff_buttons.append(btn)
        diff_row.addStretch()
        outer.addLayout(diff_row)

        # ---- Stage list (grouped by act) ----------------------------
        self.list_widget = QListWidget()
        self.list_widget.setUniformItemSizes(True)
        outer.addWidget(self.list_widget, stretch=1)

        # Load the stages index once, then render via _refresh_list so
        # difficulty clicks don't need to re-read the cache.
        self._all_stages = _load_stages_index()
        if not self._all_stages:
            placeholder = QListWidgetItem(
                "(stages_index.json missing — click Scrape data)"
            )
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(placeholder)
        else:
            self._refresh_list()

        self.list_widget.itemDoubleClicked.connect(self._on_accept_clicked)
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_cancel_stage_picker")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("btn_ok_stage_picker")
        self.btn_ok.setProperty("toolbar_zone", "primary")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._on_accept_clicked)
        btn_row.addWidget(self.btn_ok)
        outer.addLayout(btn_row)

    def _on_diff_clicked(self) -> None:
        clicked = self.sender()
        wanted = str(clicked.property("diff_value") or "")
        for btn in self._diff_buttons:
            btn.setChecked(str(btn.property("diff_value") or "") == wanted)
        self._active_difficulty = wanted or None
        self._refresh_list()

    def _refresh_list(self) -> None:
        """Rebuild the visible list honoring the active difficulty + reward_kind filters.

        Jul 2026 layout — grouped by **difficulty first**, then by act
        and stage within each difficulty (per user feedback — the user
        thinks 'Normal first, all stages, then the other difficulties'
        not 'Act 1 first, all difficulties, then the other acts'):

            [N] Normal
              Act 1
                  Stage 1  Pasture
                  Stage 2  Eerie Canyon
                  ...
                  Stage 10 Act 1 Boss (Act Boss)
              Act 2
              Act 3
            [NM] Nightmare
            [H] Hell
            [T] Torment

        When the user has activated a single-difficulty chip, only that
        one group is shown.
        """
        self.list_widget.clear()
        if not self._all_stages:
            return

        # Bucket by (act, stage_no, difficulty).
        by_key: dict[tuple[int, int, str], dict[str, Any]] = {}
        for s in self._all_stages:
            act = int(s.get("act", 0) or 0)
            stage_no = int(s.get("stage_no", 0) or 0)
            diff = str(s.get("difficulty", "")).upper()
            if act <= 0 or stage_no <= 0 or diff not in self._DIFFICULTIES:
                continue
            by_key[(act, stage_no, diff)] = s

        # Render: difficulty → act → stage.
        active_diffs = (
            [self._active_difficulty] if self._active_difficulty
            else list(self._DIFFICULTIES)
        )
        for diff in active_diffs:
            self._add_diff_header(diff, by_key)
            acts = sorted({k[0] for k in by_key if k[2] == diff})
            for act in acts:
                # Skip the act entirely if it has no rows after the
                # reward-kind filter (otherwise the user sees an empty
                # 'Act 2' header with nothing under it).
                if not any(
                    self._passes_kind_filter(by_key[(act, sno, diff)])
                    for sno in {k[1] for k in by_key if k[0] == act and k[2] == diff}
                ):
                    continue
                self._add_act_header(act, diff, by_key)
                stage_nos = sorted(
                    {k[1] for k in by_key if k[0] == act and k[2] == diff}
                )
                for stage_no in stage_nos:
                    stage = by_key.get((act, stage_no, diff))
                    if stage is None:
                        continue
                    if not self._passes_kind_filter(stage):
                        continue
                    self._add_stage_subheader(act, stage_no, diff, by_key)
                    self._add_stage_row(stage)

    def _add_diff_header(self, diff: str, by_key: dict) -> None:
        count = sum(
            1 for k in by_key
            if k[2] == diff and self._passes_kind_filter(by_key[k])
        )
        label = (
            f"━━━ {self._DIFF_LABEL[diff]} ━━━ {count} stage"
            f"{'s' if count != 1 else ''}"
        )
        item = QListWidgetItem(label)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setForeground(QBrush(QColor(MOCHA["lavender"])))
        font = item.font()
        font.setBold(True)
        font.setPointSize(12)
        item.setFont(font)
        self.list_widget.addItem(item)

    def _add_act_header(
        self, act: int, diff: str, by_key: dict,
    ) -> None:
        count = sum(
            1 for k in by_key
            if k[0] == act and k[2] == diff and self._passes_kind_filter(by_key[k])
        )
        label = f"  Act {act}  ({count})"
        item = QListWidgetItem(label)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setForeground(QBrush(QColor(MOCHA["blue"])))
        font = item.font()
        font.setBold(True)
        font.setPointSize(11)
        item.setFont(font)
        self.list_widget.addItem(item)

    def _add_stage_subheader(
        self, act: int, stage_no: int, diff: str, by_key: dict,
    ) -> None:
        """Lightweight stage subheader so the user can scan quickly."""
        stage = by_key.get((act, stage_no, diff))
        if stage is None or not self._passes_kind_filter(stage):
            return
        stype = str(stage.get("type", ""))
        label = f"      Stage {stage_no}"
        if stype == "ACTBOSS":
            label += "  (Act Boss)"
        item = QListWidgetItem(label)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setForeground(QBrush(QColor(MOCHA["subtext"])))
        font = item.font()
        font.setBold(True)
        font.setPointSize(10)
        item.setFont(font)
        self.list_widget.addItem(item)

    def _passes_kind_filter(self, stage: dict) -> bool:
        stype = str(stage.get("type", ""))
        if self._reward_kind in ("normal", "boss") and stype == "ACTBOSS":
            return False
        if self._reward_kind == "act" and stype != "ACTBOSS":
            return False
        return True

    def _add_stage_row(self, stage: dict) -> None:
        sid = stage.get("id")
        if not isinstance(sid, int):
            return
        name = stage.get("name") or {}
        if isinstance(name, dict):
            name = name.get("en", f"stage {sid}")
        item = QListWidgetItem(f"          {name}")
        item.setData(Qt.ItemDataRole.UserRole, sid)
        item.setForeground(QBrush(QColor(MOCHA["text"])))
        self.list_widget.addItem(item)

    def _on_accept_clicked(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(sid, int):
            return  # header row was double-clicked
        drop_key = _load_stage_pool_drop_key(sid, self._reward_kind)
        if drop_key is None:
            # Stage detail cache missing this stage — show in title and bail.
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Stage not scraped",
                f"Stage {sid} detail isn't in the cache yet. Run the\n"
                f"Scrape data button so all stage details are fetched.",
            )
            return
        self.pool_key_selected.emit(int(drop_key))
        self.accept()