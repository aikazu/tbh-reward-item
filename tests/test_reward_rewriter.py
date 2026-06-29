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
    PendingTxRewriter,
    _extract_reward_ids,
    TAMPER_EVENTS_PATH,
    TID_OFFSET,
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


# ─── PendingTxRewriter tests (Strategy B) ────────────────────────────

# Real DynamoDB-format SteamItemInfo/mine response body (from capture
# cap-20260628-195045.flow, anonymized). gid=321111, tid=321111900.
_STEAMITEMINFO_BODY = json.dumps({
    "serverTime": "2026-06-28T12:51:45.043Z",
    "rows": [{
        "marketData": {"L": []},
        "steamSlot": {"M": {"1": {"S": "2026-06-26T21:35:34Z"}}},
        "pendingTx": {"L": [{"M": {
            "op": {"S": "additem"},
            "gid": {"N": "321111"},
            "siid": {"S": ""},
            "qty": {"N": "1"},
            "rid": {"S": "17432693923082523668"},
            "tid": {"N": "321111900"},
            "sid": {"S": "76561198000000000"}
        }}]},
        "inDate": {"S": "2026-06-25T15:01:20.082Z"}
    }],
    "firstKey": None
})


def _make_flow(url: str, body: str) -> MagicMock:
    """Build a mock mitmproxy flow with the given URL and response body."""
    flow = MagicMock()
    flow.request.pretty_url = url
    flow.request.url = url
    flow.response.get_text.return_value = body
    return flow


class TestPendingTxRewriter:
    def test_rewrites_gid_and_tid_when_gid_in_map(self):
        rewriter = PendingTxRewriter()
        rewriter.record_rewrite(321111, 419171)

        flow = _make_flow(
            "https://gameinfo.thebackend.io/data/gameinfo/v3.3/union/SteamItemInfo/mine",
            _STEAMITEMINFO_BODY,
        )
        count = rewriter.maybe_rewrite(flow)
        assert count == 1

        new_body = flow.response.set_text.call_args[0][0]
        data = json.loads(new_body)
        entry = data["rows"][0]["pendingTx"]["L"][0]["M"]
        assert entry["gid"]["N"] == "419171"
        assert entry["tid"]["N"] == str(419171 * 1000 + TID_OFFSET)
        # Other fields untouched
        assert entry["op"]["S"] == "additem"
        assert entry["rid"]["S"] == "17432693923082523668"
        assert entry["sid"]["S"] == "76561198000000000"

    def test_no_rewrite_when_map_empty(self):
        rewriter = PendingTxRewriter()
        flow = _make_flow(
            "https://gameinfo.thebackend.io/data/gameinfo/v3.3/union/SteamItemInfo/mine",
            _STEAMITEMINFO_BODY,
        )
        count = rewriter.maybe_rewrite(flow)
        assert count == 0
        flow.response.set_text.assert_not_called()

    def test_no_rewrite_when_url_not_steamiteminfo(self):
        rewriter = PendingTxRewriter()
        rewriter.record_rewrite(321111, 419171)

        flow = _make_flow(
            "https://api.thebackend.io/backend-function/base/v1",
            _STEAMITEMINFO_BODY,
        )
        count = rewriter.maybe_rewrite(flow)
        assert count == 0
        flow.response.set_text.assert_not_called()

    def test_no_rewrite_when_no_pendingtx_in_body(self):
        rewriter = PendingTxRewriter()
        rewriter.record_rewrite(321111, 419171)

        flow = _make_flow(
            "https://gameinfo.thebackend.io/data/gameinfo/v3.3/union/SteamItemInfo/mine",
            '{"serverTime":"2026-06-28T12:51:45.043Z","rows":[{"marketData":{"L":[]}}]}',
        )
        count = rewriter.maybe_rewrite(flow)
        assert count == 0

    def test_no_rewrite_when_gid_not_in_map(self):
        rewriter = PendingTxRewriter()
        rewriter.record_rewrite(999999, 419171)  # different gid

        flow = _make_flow(
            "https://gameinfo.thebackend.io/data/gameinfo/v3.3/union/SteamItemInfo/mine",
            _STEAMITEMINFO_BODY,
        )
        count = rewriter.maybe_rewrite(flow)
        assert count == 0
        flow.response.set_text.assert_not_called()

    def test_record_rewrite_ignores_identity(self):
        rewriter = PendingTxRewriter()
        rewriter.record_rewrite(321111, 321111)  # same → no-op
        assert rewriter._rewrite_map == {}

    def test_multiple_entries_all_rewritten(self):
        """Two pendingTx entries with different gids, both in the map."""
        body = json.dumps({
            "rows": [{
                "pendingTx": {"L": [
                    {"M": {"gid": {"N": "100001"}, "tid": {"N": "100001900"}, "op": {"S": "additem"}}},
                    {"M": {"gid": {"N": "200002"}, "tid": {"N": "200002900"}, "op": {"S": "additem"}}}
                ]}
            }]
        })
        rewriter = PendingTxRewriter()
        rewriter.record_rewrite(100001, 500001)
        rewriter.record_rewrite(200002, 600002)

        flow = _make_flow(
            "https://gameinfo.thebackend.io/data/gameinfo/v3.3/union/SteamItemInfo/mine",
            body,
        )
        count = rewriter.maybe_rewrite(flow)
        assert count == 2

        new_body = flow.response.set_text.call_args[0][0]
        data = json.loads(new_body)
        entries = data["rows"][0]["pendingTx"]["L"]
        assert entries[0]["M"]["gid"]["N"] == "500001"
        assert entries[0]["M"]["tid"]["N"] == str(500001 * 1000 + TID_OFFSET)
        assert entries[1]["M"]["gid"]["N"] == "600002"
        assert entries[1]["M"]["tid"]["N"] == str(600002 * 1000 + TID_OFFSET)

    def test_multiple_entries_only_matching_rewritten(self):
        """Two entries, only one in the map → only that one rewritten."""
        body = json.dumps({
            "rows": [{
                "pendingTx": {"L": [
                    {"M": {"gid": {"N": "100001"}, "tid": {"N": "100001900"}}},
                    {"M": {"gid": {"N": "200002"}, "tid": {"N": "200002900"}}}
                ]}
            }]
        })
        rewriter = PendingTxRewriter()
        rewriter.record_rewrite(100001, 500001)  # only 100001

        flow = _make_flow(
            "https://gameinfo.thebackend.io/data/gameinfo/v3.3/union/SteamItemInfo/mine",
            body,
        )
        count = rewriter.maybe_rewrite(flow)
        assert count == 1

        new_body = flow.response.set_text.call_args[0][0]
        data = json.loads(new_body)
        entries = data["rows"][0]["pendingTx"]["L"]
        assert entries[0]["M"]["gid"]["N"] == "500001"
        assert entries[0]["M"]["tid"]["N"] == str(500001 * 1000 + TID_OFFSET)
        # Second entry untouched
        assert entries[1]["M"]["gid"]["N"] == "200002"
        assert entries[1]["M"]["tid"]["N"] == "200002900"

    def test_tid_mapping_formula(self):
        """Verify tid = gid * 1000 + 900 with the real capture value."""
        gid = 321111
        tid = 321111900
        assert tid == gid * 1000 + TID_OFFSET

    def test_rewritten_tid_matches_new_gid(self):
        """After rewrite, the new tid must equal new_gid * 1000 + 900."""
        rewriter = PendingTxRewriter()
        rewriter.record_rewrite(321111, 419171)

        flow = _make_flow(
            "https://gameinfo.thebackend.io/data/gameinfo/v3.3/union/SteamItemInfo/mine",
            _STEAMITEMINFO_BODY,
        )
        rewriter.maybe_rewrite(flow)

        new_body = flow.response.set_text.call_args[0][0]
        data = json.loads(new_body)
        entry = data["rows"][0]["pendingTx"]["L"][0]["M"]
        new_gid = int(entry["gid"]["N"])
        new_tid = int(entry["tid"]["N"])
        assert new_tid == new_gid * 1000 + TID_OFFSET
