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
    """Modal list of stages grouped by act. The user picks one; we
    look up the matching drop_key from the cached stage detail and
    emit ``pool_key_selected(int)`` on accept.
    """

    pool_key_selected = Signal(int)

    def __init__(
        self,
        reward_kind: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("stage_picker_dialog")
        self.setWindowTitle(f"Pick {reward_kind.title()} pool")
        self.setMinimumSize(480, 520)
        self._reward_kind = reward_kind

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        heading = QLabel(f"Pick a stage — its {reward_kind} drop pool will be set.")
        heading.setObjectName("panel_heading")
        heading.setStyleSheet(section_heading_style())
        outer.addWidget(heading)

        # Build a list per act so the user can scan quickly.
        stages = _load_stages_index()
        self.list_widget = QListWidget()
        self.list_widget.setUniformItemSizes(True)
        if not stages:
            placeholder = QListWidgetItem("(stages_index.json missing — click Scrape data)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(placeholder)
        else:
            # Stable order: by act, then stage_no, then difficulty variant.
            diff_order = {"NORMAL": 0, "NIGHTMARE": 1, "HELL": 2, "TORMENT": 3}
            stages.sort(key=lambda s: (
                int(s.get("act", 0) or 0),
                int(s.get("stage_no", 0) or 0),
                diff_order.get(str(s.get("difficulty", "")).upper(), 9),
            ))
            for s in stages:
                sid = s.get("id")
                if not isinstance(sid, int):
                    continue
                name = s.get("name") or {}
                if isinstance(name, dict):
                    name = name.get("en", f"stage {sid}")
                act = s.get("act")
                stage_no = s.get("stage_no")
                diff = s.get("difficulty", "")
                stype = s.get("type", "")
                # For normal/boss rules, skip ACTBOSS stages. For the
                # act rule, skip NORMAL stages. That way each dialog
                # only shows stages that have the matching pool.
                if self._reward_kind in ("normal", "boss") and stype == "ACTBOSS":
                    continue
                if self._reward_kind == "act" and stype != "ACTBOSS":
                    continue
                line = f"Act {act} · Stage {stage_no} · {diff.title()}"
                if stype == "ACTBOSS":
                    line += "  (Act Boss)"
                item = QListWidgetItem(f"{sid:>5}   {line}")
                item.setData(Qt.ItemDataRole.UserRole, sid)
                self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(self._on_accept_clicked)
        outer.addWidget(self.list_widget, stretch=1)

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

    def _on_accept_clicked(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(sid, int):
            return
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