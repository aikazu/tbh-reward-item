"""Tests for RewardRewriter (v1 dumb substitution) and TamperDetector.

These exercise the core rewrite logic without mitmproxy. The self-test in
``src/tbh_reward_hook.py`` covers the same logic, but these run under pytest
so regressions are caught in CI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure src/ is importable
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tbh_proxy_config import ProxyConfig, QueueRule, RangeRule  # type: ignore[import-not-found]
from tbh_reward_hook import (  # type: ignore[import-not-found]
    RewardRewriter,
    TamperDetector,
    _extract_reward_ids,
    TAMPER_EVENTS_PATH,
)


# ─── helpers ──────────────────────────────────────────────────────────

def _make_config(
    specific: tuple[QueueRule, ...] = (),
    range_rule: RangeRule | None = None,
) -> ProxyConfig:
    if range_rule is None:
        range_rule = RangeRule(
            enabled=False,
            name="Range replacement",
            match_min_item_id=500000,
            match_max_item_id=950000,
            replacement_reward_item_ids=(),
        )
    return ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        specific_queue_rules=specific,
        range_replacement=range_rule,
    )


def _box_body(pairs: list[tuple[int, int]]) -> str:
    """Build a minimal box response body from (itemId, rewardItemId) pairs."""
    entries = ",".join(
        f'{{"itemId":{iid},"rewardItemId":{rid}}}' for iid, rid in pairs
    )
    return '{"boxes":[' + entries + "]}"


# ─── RewardRewriter tests ─────────────────────────────────────────────

class TestSpecificRuleCycle:
    def test_cycles_through_replacements(self):
        config = _make_config(
            specific=(
                QueueRule(
                    enabled=True,
                    name="Normal Box",
                    item_id=910801,
                    replacement_reward_item_ids=(419171, 519171),
                ),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(910801, 100), (910801, 200), (910801, 300)])
        result = rewriter.rewrite(body)
        assert result.modified_count == 3
        ids = _extract_reward_ids(result.body)
        assert ids == [419171, 519171, 419171]  # cycles modulo len

    def test_single_replacement_repeats(self):
        config = _make_config(
            specific=(
                QueueRule(True, "Single", 910801, (419171,)),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(910801, 1), (910801, 2)])
        result = rewriter.rewrite(body)
        ids = _extract_reward_ids(result.body)
        assert ids == [419171, 419171]

    def test_disabled_rule_is_noop(self):
        config = _make_config(
            specific=(
                QueueRule(False, "Disabled", 910801, (419171,)),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(910801, 999)])
        result = rewriter.rewrite(body)
        assert result.modified_count == 0
        assert _extract_reward_ids(result.body) == [999]

    def test_empty_replacements_is_noop(self):
        config = _make_config(
            specific=(
                QueueRule(True, "Empty", 910801, ()),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(910801, 999)])
        result = rewriter.rewrite(body)
        assert result.modified_count == 0

    def test_no_rule_for_itemid_passes_through(self):
        config = _make_config(
            specific=(
                QueueRule(True, "Normal Box", 910801, (419171,)),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(920801, 12345)])  # different box kind
        result = rewriter.rewrite(body)
        assert result.modified_count == 0
        assert _extract_reward_ids(result.body) == [12345]


class TestRangeRule:
    def test_range_matches_and_cycles(self):
        config = _make_config(
            range_rule=RangeRule(
                enabled=True,
                name="Range",
                match_min_item_id=500000,
                match_max_item_id=950000,
                replacement_reward_item_ids=(419171, 440017),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(700000, 1), (800000, 2), (600000, 3)])
        result = rewriter.rewrite(body)
        assert result.modified_count == 3
        ids = _extract_reward_ids(result.body)
        assert ids == [419171, 440017, 419171]

    def test_range_below_min_not_rewritten(self):
        config = _make_config(
            range_rule=RangeRule(
                enabled=True,
                name="Range",
                match_min_item_id=500000,
                match_max_item_id=950000,
                replacement_reward_item_ids=(419171,),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(499999, 1), (500000, 2)])
        result = rewriter.rewrite(body)
        assert result.modified_count == 1
        ids = _extract_reward_ids(result.body)
        assert ids == [1, 419171]

    def test_range_above_max_not_rewritten(self):
        config = _make_config(
            range_rule=RangeRule(
                enabled=True,
                name="Range",
                match_min_item_id=500000,
                match_max_item_id=950000,
                replacement_reward_item_ids=(419171,),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(950001, 1), (950000, 2)])
        result = rewriter.rewrite(body)
        assert result.modified_count == 1
        ids = _extract_reward_ids(result.body)
        assert ids == [1, 419171]

    def test_range_disabled_is_noop(self):
        config = _make_config(
            range_rule=RangeRule(
                enabled=False,
                name="Range",
                match_min_item_id=500000,
                match_max_item_id=950000,
                replacement_reward_item_ids=(419171,),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(700000, 999)])
        result = rewriter.rewrite(body)
        assert result.modified_count == 0


class TestSpecificOverRange:
    def test_specific_wins_over_range(self):
        config = _make_config(
            specific=(
                QueueRule(True, "Normal Box", 910801, (419171,)),
            ),
            range_rule=RangeRule(
                enabled=True,
                name="Range",
                match_min_item_id=500000,
                match_max_item_id=950000,
                replacement_reward_item_ids=(999999,),
            ),
        )
        rewriter = RewardRewriter(config)
        # 910801 falls in range [500000, 950000] but specific rule wins
        body = _box_body([(910801, 1), (700000, 2)])
        result = rewriter.rewrite(body)
        ids = _extract_reward_ids(result.body)
        assert ids == [419171, 999999]


class TestEmptyConfig:
    def test_empty_config_passes_through(self):
        config = _make_config()
        rewriter = RewardRewriter(config)
        body = _box_body([(910801, 12345)])
        result = rewriter.rewrite(body)
        assert result.modified_count == 0
        assert _extract_reward_ids(result.body) == [12345]


class TestDetailTracking:
    def test_details_capture_old_and_new(self):
        config = _make_config(
            specific=(
                QueueRule(True, "Test", 910801, (419171,)),
            )
        )
        rewriter = RewardRewriter(config)
        body = _box_body([(910801, 100)])
        result = rewriter.rewrite(body)
        assert len(result.details) == 1
        d = result.details[0]
        assert d.rule_name == "Test"
        assert d.item_id == 910801
        assert d.old_reward_item_id == 100
        assert d.new_reward_item_id == 419171


# ─── TamperDetector tests ─────────────────────────────────────────────

class TestTamperDetector:
    def test_logs_mismatch_to_jsonl(self, tmp_path: Path):
        events_path = tmp_path / "tamper-events.jsonl"
        detector = TamperDetector(events_path)

        # Build a mock flow matching the tamper endpoint
        flow = MagicMock()
        flow.request.pretty_url = "https://api.thebackend.io/data/gameLog/v2/TemperedItem/90"
        flow.response.get_text.return_value = json.dumps({
            "msg": "TamperedItemIdDetected",
            "data": {
                "mismatches": [
                    "6743:319171->522171",
                    "6655:419171->112004",
                ]
            }
        })

        detector.maybe_log(flow)

        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        rec0 = json.loads(lines[0])
        assert rec0["itemKey"] == "6743"
        assert rec0["original_id"] == 319171
        assert rec0["used_id"] == 522171
        assert rec0["original_rarity"] == "Cosmic"  # 319171, digit 3 = 9
        assert rec0["used_rarity"] == "Rare"  # 522171, digit 3 = 2
        assert rec0["last3_preserved"] is True  # 171 == 171

        rec1 = json.loads(lines[1])
        assert rec1["original_id"] == 419171
        assert rec1["used_id"] == 112004
        assert rec1["last3_preserved"] is False  # 171 != 004

    def test_ignores_non_tamper_url(self, tmp_path: Path):
        events_path = tmp_path / "tamper-events.jsonl"
        detector = TamperDetector(events_path)

        flow = MagicMock()
        flow.request.pretty_url = "https://api.thebackend.io/backend-function/base/v1"
        flow.response.get_text.return_value = '{"boxes":[]}'

        detector.maybe_log(flow)
        assert not events_path.exists() or events_path.read_text() == ""

    def test_ignores_response_without_tamper_marker(self, tmp_path: Path):
        events_path = tmp_path / "tamper-events.jsonl"
        detector = TamperDetector(events_path)

        flow = MagicMock()
        flow.request.pretty_url = "https://api.thebackend.io/data/gameLog/v2/TemperedItem/90"
        flow.response.get_text.return_value = '{"msg":"something_else"}'

        detector.maybe_log(flow)
        assert not events_path.exists() or events_path.read_text() == ""

    def test_handles_empty_mismatches(self, tmp_path: Path):
        events_path = tmp_path / "tamper-events.jsonl"
        detector = TamperDetector(events_path)

        flow = MagicMock()
        flow.request.pretty_url = "https://api.thebackend.io/data/gameLog/v2/TemperedItem/90"
        flow.response.get_text.return_value = json.dumps({
            "msg": "TamperedItemIdDetected",
            "data": {"mismatches": []}
        })

        detector.maybe_log(flow)
        assert not events_path.exists() or events_path.read_text() == ""

    def test_total_counter_increments(self, tmp_path: Path):
        events_path = tmp_path / "tamper-events.jsonl"
        detector = TamperDetector(events_path)

        flow = MagicMock()
        flow.request.pretty_url = "https://api.thebackend.io/data/gameLog/v2/TemperedItem/90"
        flow.response.get_text.return_value = json.dumps({
            "msg": "TamperedItemIdDetected",
            "data": {"mismatches": ["1:100->200", "2:300->400"]}
        })

        detector.maybe_log(flow)
        assert detector._total == 2

    def test_malformed_mismatch_entry_skipped(self, tmp_path: Path):
        events_path = tmp_path / "tamper-events.jsonl"
        detector = TamperDetector(events_path)

        flow = MagicMock()
        flow.request.pretty_url = "https://api.thebackend.io/data/gameLog/v2/TemperedItem/90"
        flow.response.get_text.return_value = json.dumps({
            "msg": "TamperedItemIdDetected",
            "data": {"mismatches": ["garbage", "6743:319171->522171"]}
        })

        detector.maybe_log(flow)
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1  # only the valid one
        assert json.loads(lines[0])["itemKey"] == "6743"
