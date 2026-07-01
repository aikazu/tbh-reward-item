"""TBH reward response rewrite — manual substitution.

How it works
============

You list the itemIds you want as replacements in ``config.json``. For each
box response, the addon cycles through the list and substitutes the original
``rewardItemId`` with the next entry. That's it.

The addon does NOT look at pools, suffix patterns, tier matching, or anything
else. It is a dumb string substitution driven entirely by your config.

If a config field is empty or its rule is disabled, the addon is a no-op
(passes the response through untouched).

What this means for cheating
============================

The server's client-side validator checks the last 3 digits of ``rewardItemId``
(rarity x 100 + tier, see docs/analysis/tbh-network-forensics.md §10.6). If
the original drop was 319171 and you swap in 419171 (different rarity digit),
the client ships a ``TamperedItemIdDetected`` telemetry to the server.

This addon has no idea whether your swap will trigger that. Pick replacements
whose last-3 matches what the box originally drops — or accept the reports.
Read ``logs/tamper-events.jsonl`` after a session to see what got flagged.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from tbh_proxy_config import CONFIG_PATH, ProxyConfig, PoolRule, RangeRule

ITEM_FIELD_RE = re.compile(r'\\?"itemId\\?"\s*:\s*(?P<item_id>\d+)(?!\d)')
REWARD_FIELD_RE = re.compile(r'(\\?"rewardItemId\\?"\s*:\s*)(?P<reward_id>\d+)(?!\d)')


def log_info(message: str) -> None:
    print(f"[TBH] {message}", flush=True)


# --- Passive tamper detector ---
# Endpoint: POST /data/gameLog/v2/TemperedItem/90
# Body: {"msg":"TamperedItemIdDetected","data":{"mismatches":["<ik>:<orig>-><used>",...]}}
TAMPER_URL_MARKER = "/data/gameLog/v2/TemperedItem/"
TAMPER_EVENTS_PATH = Path(__file__).resolve().parent.parent / "logs" / "tamper-events.jsonl"

_RARITY_NAMES = {
    "0": "Common", "1": "Uncommon", "2": "Rare", "3": "Legendary",
    "4": "Immortal", "5": "Arcana", "6": "Beyond", "7": "Celestial",
    "8": "Divine", "9": "Cosmic",
}


def _rarity_label(item_id: int) -> str:
    """3rd digit (C in ABCDEF) = rarity."""
    s = str(item_id)
    return _RARITY_NAMES.get(s[2], "Unknown") if len(s) == 6 else "Unknown"


def _tier_str(item_id: int) -> str:
    """Last 3 digits (DEF) = tier+slot."""
    return str(item_id)[-3:]


class TamperDetector:
    """Passive monitor: logs TamperedItemIdDetected telemetry to JSONL.

    Never modifies traffic. The client POSTs mismatch reports to
    /data/gameLog/v2/TemperedItem/90. The mismatch data lives in the
    REQUEST body (not response — server replies 204 No Content). This
    detector reads the request body and appends structured records to
    logs/tamper-events.jsonl.
    """

    def __init__(self, events_path: Path = TAMPER_EVENTS_PATH):
        self._path = events_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._total = 0

    def maybe_log(self, flow) -> None:
        """Inspect a flow; if it is a tamper report, log it.

        Checks the REQUEST body (not response) because the client sends
        the mismatch list as POST data and the server replies 204 No
        Content with an empty body.
        """
        request = flow.request
        url = getattr(request, "pretty_url", "") or getattr(request, "url", "")
        if TAMPER_URL_MARKER not in url:
            return
        try:
            body = request.get_text(strict=False)
        except Exception:
            return
        if not body or "TamperedItemIdDetected" not in body:
            return
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return
        mismatches = payload.get("data", {}).get("mismatches", [])
        if not mismatches:
            return
        ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with open(self._path, "a", encoding="utf-8") as fh:
            for entry in mismatches:
                record = self._parse_mismatch(entry, ts)
                if record is None:
                    continue
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                self._total += 1
        log_info(
            f"TAMPER WARNING: {len(mismatches)} mismatch(es) reported by client. "
            f"Session total: {self._total}. See {self._path.name}"
        )

    @staticmethod
    def _parse_mismatch(entry: str, ts: str) -> dict[str, Any] | None:
        """Parse '<itemKey>:<orig>-><used>' into a structured record."""
        m = re.match(r"^(\d+):(\d+)->(\d+)$", entry.strip())
        if not m:
            return None
        orig_id = int(m.group(2))
        used_id = int(m.group(3))
        return {
            "ts": ts,
            "itemKey": m.group(1),
            "original_id": orig_id,
            "original_rarity": _rarity_label(orig_id),
            "original_tier": _tier_str(orig_id),
            "used_id": used_id,
            "used_rarity": _rarity_label(used_id),
            "used_tier": _tier_str(used_id),
            "last3_preserved": (orig_id % 1000) == (used_id % 1000),
        }


def _safe_load_config(path: Path = CONFIG_PATH):
    try:
        return ProxyConfig.load(path)
    except Exception as exc:
        log_info(f"config load failed ({path}): {exc}")
        return None


def _empty_config():
    return ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        normal_rules=(),
        boss_rules=(),
        act_rules=(),
        range_replacement=RangeRule(
            enabled=False,
            name="Range replacement",
            match_min_item_id=500000,
            match_max_item_id=950000,
            replacement_reward_item_ids=(),
        ),
        rewrite_pending_tx=False,
    )


# --- Strategy B: pendingTx.tid rewrite ---
# SteamItemInfo/mine response carries DynamoDB-format pendingTx entries.
# When we rewrite rewardItemId in processBoxV2, the original gid/tid in
# pendingTx no longer match → client ships TamperedItemIdDetected.
# PendingTxRewriter fixes this by also rewriting gid + tid to match.

STEAMITEMINFO_URL_MARKER = "SteamItemInfo/mine"
TID_OFFSET = 900  # tid = gid * 1000 + 900 (verified n=1, see docs/analysis §10.12)

# DynamoDB format: "gid":{"N":"321111"} and "tid":{"N":"321111900"}
# \\? handles both plain JSON ("gid") and escaped JSON (\"gid\") from
# mitmproxy bodies. Same escaping style as ITEM_FIELD_RE above.
_GID_RE = re.compile(r'\\?"gid\\?"\s*:\s*\{\\?"N\\?"\s*:\s*\\?"(?P<gid>\d+)\\?"\s*\}')
_TID_RE = re.compile(r'\\?"tid\\?"\s*:\s*\{\\?"N\\?"\s*:\s*\\?"(?P<tid>\d+)\\?"\s*\}')


class PendingTxRewriter:
    """Rewrites pendingTx.gid + .tid to match a rewritten rewardItemId.

    Maintains a session map {original_rewardItemId: new_rewardItemId} populated
    by RewardRewriter. When SteamItemInfo/mine returns pendingTx entries,
    rewrites gid/tid for any entry whose gid is in the map.

    gid == rewardItemId (6-digit item ID)
    tid  == gid * 1000 + 900   (offset verified from single capture)

    Uses regex substitution on the raw body rather than full JSON round-trip:
    DynamoDB responses contain many fields we must not touch, and field order
    is not guaranteed. Regex targets only the gid/tid {"N":"..."} wrappers.
    """

    def __init__(self):
        self._rewrite_map: dict[int, int] = {}
        self._rewritten_count = 0

    def record_rewrite(self, original_rid: int, new_rid: int) -> None:
        """Called when RewardRewriter rewrites a rewardItemId. Stores the
        mapping so the next SteamItemInfo/mine response can be fixed up."""
        if original_rid != new_rid:
            self._rewrite_map[original_rid] = new_rid

    def maybe_rewrite(self, flow) -> int:
        """Check if this is a SteamItemInfo response; rewrite if so.

        Returns the number of pendingTx entries rewritten.
        """
        if not self._rewrite_map:
            return 0

        request = flow.request
        response = flow.response
        if response is None:
            return 0

        url = getattr(request, "pretty_url", "") or getattr(request, "url", "")
        if STEAMITEMINFO_URL_MARKER not in url:
            return 0

        try:
            body = response.get_text(strict=False)
        except Exception:
            return 0
        if not body or "pendingTx" not in body:
            return 0

        new_body, count = self._rewrite_body(body)
        if count > 0:
            response.set_text(new_body)
        return count

    def _rewrite_body(self, body: str) -> tuple[str, int]:
        """Find all gid values in the body. For any that are in the rewrite
        map, substitute both the gid and its associated tid.

        We match gid first, then search forward for the nearest tid within
        the same pendingTx entry (M block). To avoid cross-entry bleed, the
        tid search is bounded by the next gid match — if tid falls past it,
        we skip the tid rewrite for this entry.
        """
        gid_matches = list(_GID_RE.finditer(body))
        if not gid_matches:
            return body, 0

        count = 0
        pieces: list[str] = []
        cursor = 0

        for i, gid_match in enumerate(gid_matches):
            gid_val = int(gid_match.group("gid"))
            if gid_val not in self._rewrite_map:
                continue

            new_gid = self._rewrite_map[gid_val]
            new_tid = new_gid * 1000 + TID_OFFSET

            gid_start = gid_match.start("gid")
            gid_end = gid_match.end("gid")

            # Copy everything from cursor up to the gid value
            pieces.append(body[cursor:gid_start])
            pieces.append(str(new_gid))
            cursor = gid_end

            # Find the nearest tid AFTER this gid, but BEFORE the next gid
            # (same pendingTx M block). tid always follows gid in observed
            # DynamoDB structure, but we guard against cross-entry bleed.
            search_end = gid_matches[i + 1].start() if i + 1 < len(gid_matches) else len(body)
            tid_slice = body[gid_end:search_end]
            tid_match = _TID_RE.search(tid_slice)
            if tid_match is not None:
                # Adjust offsets to absolute body positions
                tid_start = gid_end + tid_match.start("tid")
                tid_end = gid_end + tid_match.end("tid")
                pieces.append(body[cursor:tid_start])
                pieces.append(str(new_tid))
                cursor = tid_end

            count += 1
            log_info(
                f"PendingTx rewrite: gid {gid_val}->{new_gid}, "
                f"tid {gid_val * 1000 + TID_OFFSET}->{new_tid}"
            )

        if count == 0:
            return body, 0

        pieces.append(body[cursor:])
        return "".join(pieces), count


class ReplacementDetail:
    __slots__ = ("rule_name", "pool_id", "old_reward_item_id", "new_reward_item_id")

    def __init__(self, rule_name, pool_id, old_reward_item_id, new_reward_item_id):
        self.rule_name = rule_name
        self.pool_id = pool_id
        self.old_reward_item_id = old_reward_item_id
        self.new_reward_item_id = new_reward_item_id


class RewriteResult:
    __slots__ = ("body", "details")

    def __init__(self, body, details):
        self.body = body
        self.details = details

    @property
    def modified_count(self):
        return len(self.details)


class RewardRewriter:
    """Manual substitution. Cycles through ``replacement_reward_item_ids`` per
    rule and substitutes the original ``rewardItemId`` with the next entry.

    For each ``itemId`` (= tbh.city pool_id) in the body, the rewriter checks:
    1. ``all_pool_rules`` — keyed by exact pool_id; if a rule matches
       and is enabled and has replacements, cycle through that rule's list.
    2. ``range_replacement`` — if itemId falls in [min, max] and the rule is
       enabled, cycle through the range's list.

    Each rule keeps its own cycle index, so different pool kinds pick
    different replacements. Originals are not touched if no rule matches.
    """

    def __init__(self, config: ProxyConfig):
        self.config = config
        self._pool_indexes: dict[int, int] = {}
        self._range_index = 0

    def rewrite(self, body: str) -> RewriteResult:
        # Multi-pool rule lookup. Each rule maps its pool_ids to the
        # same rule object — when an itemId on the wire matches any of
        # them, the rule fires and cycles through its replacement list.
        # Cycle index is per-pool (not per-rule) so two distinct pools
        # in the same rule don't sync their cycle positions.
        pool_rules: dict[int, PoolRule] = {}
        for rule in self.config.all_pool_rules():
            if not rule.enabled or not rule.pool_ids or not rule.replacement_reward_item_ids:
                continue
            for pool_id in rule.pool_ids:
                pool_rules[pool_id] = rule
        details: list[ReplacementDetail] = []
        pieces: list[str] = []
        copied_until = 0

        for item_match in ITEM_FIELD_RE.finditer(body):
            item_id = int(item_match.group("item_id"))
            replacement_id, chosen_name = self._pick_replacement(item_id, pool_rules)

            if replacement_id is None:
                continue

            reward_match = REWARD_FIELD_RE.search(body, item_match.end())
            if reward_match is None:
                continue

            reward_start = reward_match.start("reward_id")
            reward_end = reward_match.end("reward_id")
            if reward_start < copied_until:
                continue

            old_reward_id = int(reward_match.group("reward_id"))
            pieces.append(body[copied_until:reward_start])
            pieces.append(str(replacement_id))
            copied_until = reward_end
            details.append(
                ReplacementDetail(
                    rule_name=chosen_name,
                    pool_id=item_id,
                    old_reward_item_id=old_reward_id,
                    new_reward_item_id=replacement_id,
                )
            )

        if not details:
            return RewriteResult(body=body, details=())

        pieces.append(body[copied_until:])
        return RewriteResult(body="".join(pieces), details=tuple(details))

    def _pick_replacement(self, item_id: int, pool_rules: dict[int, PoolRule]):
        # Specific rule for this exact pool_id wins over range.
        rule = pool_rules.get(item_id)
        if rule is not None:
            idx = self._pool_indexes.get(item_id, 0)
            replacement_id = rule.replacement_reward_item_ids[idx % len(rule.replacement_reward_item_ids)]
            self._pool_indexes[item_id] = idx + 1
            return replacement_id, rule.name

        # Fallback: range match.
        range_rule = self.config.range_replacement
        if range_rule.enabled and range_rule.replacement_reward_item_ids:
            if range_rule.match_min_item_id <= item_id <= range_rule.match_max_item_id:
                pool = range_rule.replacement_reward_item_ids
                replacement_id = pool[self._range_index % len(pool)]
                self._range_index += 1
                return replacement_id, range_rule.name

        return None, ""


class TBHRewardHook:
    def __init__(self):
        self._config_path = CONFIG_PATH
        self._config_mtime = 0
        from config_setup import ensure_config
        ensure_config()
        loaded = _safe_load_config(self._config_path)
        if loaded is None:
            self.config = _empty_config()
            log_info("using fallback empty config (no rules active).")
        else:
            self.config = loaded
        self._config_mtime = self._read_mtime(self._config_path)
        self.rewriter = RewardRewriter(self.config)
        self.tamper_detector = TamperDetector()
        self.pending_tx_rewriter = PendingTxRewriter()
        self._log_load_state()
        try:
            import signal
            signal.signal(signal.SIGHUP, self._on_sighup)
        except (ValueError, OSError, AttributeError):
            pass

    def _log_load_state(self):
        active_pool = [r for r in self.config.all_pool_rules()
                       if r.enabled and r.replacement_reward_item_ids]
        range_active = (self.config.range_replacement.enabled
                        and bool(self.config.range_replacement.replacement_reward_item_ids))
        log_info(
            f"TBH Reward Proxy loaded: "
            f"{len(active_pool)} pool rules active "
            f"(normal={sum(1 for r in self.config.normal_rules if r.enabled)}, "
            f"boss={sum(1 for r in self.config.boss_rules if r.enabled)}, "
            f"act={sum(1 for r in self.config.act_rules if r.enabled)}), "
            f"range={'on' if range_active else 'off'}, "
            f"pendingTx rewrite={'on' if self.config.rewrite_pending_tx else 'off'}."
        )
        if not active_pool and not range_active:
            log_info("no replacements configured — addon is a pass-through.")

    @staticmethod
    def _read_mtime(path: Path) -> int:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return 0

    def _reload_if_changed(self):
        mtime = self._read_mtime(self._config_path)
        if mtime == self._config_mtime:
            return
        loaded = _safe_load_config(self._config_path)
        if loaded is None:
            self._config_mtime = mtime
            log_info("kept previous config (config.json invalid).")
            return
        self.config = loaded
        self.rewriter = RewardRewriter(self.config)
        self._config_mtime = mtime
        self._log_load_state()

    def _on_sighup(self, _signum, _frame):
        self._config_mtime = 0
        self._reload_if_changed()

    def response(self, flow):
        self._reload_if_changed()
        # Passive: log tamper telemetry (never modifies traffic).
        self.tamper_detector.maybe_log(flow)

        # Strategy B: rewrite pendingTx.gid/.tid to match rewardItemId rewrites.
        # Runs BEFORE the only_post/url_contains filters because SteamItemInfo/mine
        # is a GET request to a different endpoint than processBoxV2.
        if self.config.rewrite_pending_tx:
            self.pending_tx_rewriter.maybe_rewrite(flow)

        request = flow.request
        response = flow.response

        if self.config.only_post and request.method.upper() != "POST":
            return

        pretty_url = getattr(request, "pretty_url", "") or getattr(request, "url", "")
        if self.config.url_contains and not any(marker in pretty_url for marker in self.config.url_contains):
            return

        try:
            body = response.get_text(strict=False)
        except Exception as exc:
            log_info(f"TBH Reward Proxy skipped undecodable response: {exc}")
            return

        if body is None:
            return

        if self.config.require_boxes_marker and "boxes" not in body:
            return

        result = self.rewriter.rewrite(body)
        if result.modified_count <= 0:
            return

        response.set_text(result.body)
        for detail in result.details:
            log_info(
                f"TBH Reward Proxy replaced [{detail.rule_name}] "
                f"pool_id={detail.pool_id}: "
                f"rewardItemId={detail.old_reward_item_id}->{detail.new_reward_item_id}"
            )
            # Record mapping for Strategy B pendingTx rewrite
            if self.config.rewrite_pending_tx:
                self.pending_tx_rewriter.record_rewrite(
                    detail.old_reward_item_id, detail.new_reward_item_id
                )
        log_info(f"TBH Reward Proxy wrote {result.modified_count} replacement(s).")


def _extract_reward_ids(body: str):
    return [int(m.group("reward_id")) for m in REWARD_FIELD_RE.finditer(body)]


def run_self_test():
    # Normal rule: only the configured pool_id gets rewritten.
    config = ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        normal_rules=(
            PoolRule(
                enabled=True,
                name="Pasture normal",
                pool_ids=(9100111,),
                replacement_reward_item_ids=(419171, 419172),
                rule_kind="normal",
            ),
        ),
        boss_rules=(),
        act_rules=(),
        range_replacement=RangeRule(
            enabled=False,
            name="Range replacement",
            match_min_item_id=500000,
            match_max_item_id=950000,
            replacement_reward_item_ids=(),
        ),
    )
    rewriter = RewardRewriter(config)

    body = (
        '{"boxes":['
        '{"itemId":9100111,"rewardItemId":1001},'
        '{"itemId":9100111,"rewardItemId":1002},'
        '{"itemId":9200111,"rewardItemId":1003}'
        ']}'
    )
    result = rewriter.rewrite(body)
    assert result.modified_count == 2, result
    new_ids = _extract_reward_ids(result.body)
    assert new_ids == [419171, 419172, 1003], new_ids
    print(f"  normal rule: [419171, 419172, 1003]")

    # Range rule: any itemId in range gets rewritten.
    config_range = ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        normal_rules=(),
        boss_rules=(),
        act_rules=(),
        range_replacement=RangeRule(
            enabled=True,
            name="Range replacement",
            match_min_item_id=500000,
            match_max_item_id=950000,
            replacement_reward_item_ids=(419171,),
        ),
    )
    rewriter_range = RewardRewriter(config_range)
    body2 = '{"boxes":[{"itemId":700000,"rewardItemId":1},{"itemId":499999,"rewardItemId":2}]}'
    result2 = rewriter_range.rewrite(body2)
    assert result2.modified_count == 1, result2
    assert _extract_reward_ids(result2.body) == [419171, 2]
    print(f"  range rule: [419171, 2] (itemId 499999 below min)")

    # Empty config: pass-through.
    empty_config = ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        normal_rules=(),
        boss_rules=(),
        act_rules=(),
        range_replacement=RangeRule(
            enabled=False,
            name="Range replacement",
            match_min_item_id=500000,
            match_max_item_id=950000,
            replacement_reward_item_ids=(),
        ),
    )
    rewriter_empty = RewardRewriter(empty_config)
    body3 = '{"boxes":[{"itemId":9100111,"rewardItemId":12345}]}'
    result3 = rewriter_empty.rewrite(body3)
    assert result3.modified_count == 0, result3
    assert _extract_reward_ids(result3.body) == [12345]
    print(f"  empty config: pass-through, original [12345] preserved")

    # No specific rule for pool_id: pass-through.
    body4 = '{"boxes":[{"itemId":9200111,"rewardItemId":12345}]}'
    result4 = rewriter.rewrite(body4)  # rewriter has normal rule for 9100111 only
    assert result4.modified_count == 0, result4
    print(f"  no rule for pool_id: pass-through")

    # Cross-kind: act rule does NOT match normal pool (or vice versa).
    config_act_only = ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        normal_rules=(),
        boss_rules=(),
        act_rules=(
            PoolRule(
                enabled=True,
                name="Act 1 boss",
                pool_ids=(9301011,),
                replacement_reward_item_ids=(419171,),
                rule_kind="act",
            ),
        ),
        range_replacement=RangeRule(
            enabled=False,
            name="Range replacement",
            match_min_item_id=500000,
            match_max_item_id=950000,
            replacement_reward_item_ids=(),
        ),
    )
    rewriter_act = RewardRewriter(config_act_only)
    body5 = '{"boxes":[{"itemId":9301011,"rewardItemId":1},{"itemId":9100111,"rewardItemId":2}]}'
    result5 = rewriter_act.rewrite(body5)
    assert result5.modified_count == 1, result5
    assert _extract_reward_ids(result5.body) == [419171, 2]
    print(f"  act rule: only pool 9301011 rewritten, normal pool 9100111 untouched")

    # Strategy B: PendingTxRewriter rewrites gid + tid in DynamoDB-format
    # SteamItemInfo/mine responses to match the rewritten rewardItemId.
    # tid = gid * 1000 + 900 (verified from capture, see §10.12).
    tx_rewriter = PendingTxRewriter()
    # Simulate: rewardItemId 321111 was rewritten to 419171
    tx_rewriter.record_rewrite(321111, 419171)

    steamitem_body = (
        '{"rows":[{"pendingTx":{"L":[{"M":{'
        '"op":{"S":"additem"},'
        '"gid":{"N":"321111"},'
        '"qty":{"N":"1"},'
        '"rid":{"S":"17432693923082523668"},'
        '"tid":{"N":"321111900"},'
        '"sid":{"S":"76561198000000000"}'
        '}}]}}]}'
    )
    new_body, tx_count = tx_rewriter._rewrite_body(steamitem_body)
    assert tx_count == 1, f"expected 1 rewrite, got {tx_count}"
    # Verify gid rewritten
    assert '"gid":{"N":"419171"}' in new_body, "gid not rewritten"
    # Verify tid = 419171 * 1000 + 900 = 419171900
    assert '"tid":{"N":"419171900"}' in new_body, f"tid not rewritten correctly: {new_body}"
    # Verify other fields untouched
    assert '"rid":{"S":"17432693923082523668"}' in new_body, "rid was corrupted"
    assert '"sid":{"S":"76561198000000000"}' in new_body, "sid was corrupted"
    print(f"  Strategy B: gid 321111->419171, tid 321111900->419171900 (offset {TID_OFFSET})")

    # Strategy B: gid not in map → no rewrite
    tx_rewriter2 = PendingTxRewriter()
    tx_rewriter2.record_rewrite(999999, 888888)
    _, tx_count2 = tx_rewriter2._rewrite_body(steamitem_body)
    assert tx_count2 == 0, f"expected 0 rewrites for unmapped gid, got {tx_count2}"
    print(f"  Strategy B: unmapped gid → pass-through")

    print("Self-test OK.")


def main():
    parser = argparse.ArgumentParser(description="TBH reward response rewrite addon (manual substitution).")
    parser.add_argument("--self-test", action="store_true", help="run offline rewrite tests")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return 0
    print("Run this file with mitmdump:")
    print(r"  mitmdump -s tbh_reward_hook.py --listen-port 8877 --set block_global=false")
    return 0


addons = [TBHRewardHook()]


if __name__ == "__main__":
    raise SystemExit(main())