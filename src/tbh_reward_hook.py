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
Read ``captures/tamper-events.jsonl`` after a session to see what got flagged.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from tbh_proxy_config import CONFIG_PATH, ProxyConfig, QueueRule, RangeRule

ITEM_FIELD_RE = re.compile(r'\\?"itemId\\?"\s*:\s*(?P<item_id>\d+)(?!\d)')
REWARD_FIELD_RE = re.compile(r'(\\?"rewardItemId\\?"\s*:\s*)(?P<reward_id>\d+)(?!\d)')


def log_info(message: str) -> None:
    print(f"[TBH] {message}", flush=True)


# --- Passive tamper detector ---
# Endpoint: POST /data/gameLog/v2/TemperedItem/90
# Body: {"msg":"TamperedItemIdDetected","data":{"mismatches":["<ik>:<orig>-><used>",...]}}
TAMPER_URL_MARKER = "/data/gameLog/v2/TemperedItem/"
TAMPER_EVENTS_PATH = Path(__file__).resolve().parent.parent / "captures" / "tamper-events.jsonl"

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

    Never modifies traffic. Reads responses matching the cheat-telemetry
    endpoint and appends structured records to captures/tamper-events.jsonl.
    """

    def __init__(self, events_path: Path = TAMPER_EVENTS_PATH):
        self._path = events_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._total = 0

    def maybe_log(self, flow) -> None:
        """Inspect a response; if it is a tamper report, log it."""
        request = flow.request
        response = flow.response
        if response is None:
            return
        url = getattr(request, "pretty_url", "") or getattr(request, "url", "")
        if TAMPER_URL_MARKER not in url:
            return
        try:
            body = response.get_text(strict=False)
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
        specific_queue_rules=(),
        range_replacement=RangeRule(
            enabled=False,
            name="Range replacement",
            match_min_item_id=500000,
            match_max_item_id=950000,
            replacement_reward_item_ids=(),
        ),
    )


class ReplacementDetail:
    __slots__ = ("rule_name", "item_id", "old_reward_item_id", "new_reward_item_id")

    def __init__(self, rule_name, item_id, old_reward_item_id, new_reward_item_id):
        self.rule_name = rule_name
        self.item_id = item_id
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

    For each ``itemId`` in the body, the rewriter checks:
    1. ``specific_queue_rules`` — keyed by exact itemId; if a rule matches
       and is enabled and has replacements, cycle through that rule's list.
    2. ``range_replacement`` — if itemId falls in [min, max] and the rule is
       enabled, cycle through the range's list.

    Each rule keeps its own cycle index, so different box kinds pick
    different replacements. Originals are not touched if no rule matches.
    """

    def __init__(self, config: ProxyConfig):
        self.config = config
        self._queue_indexes: dict[int, int] = {}
        self._range_index = 0

    def rewrite(self, body: str) -> RewriteResult:
        queue_rules = {
            rule.item_id: rule
            for rule in self.config.specific_queue_rules
            if rule.enabled and rule.item_id and rule.replacement_reward_item_ids
        }
        details: list[ReplacementDetail] = []
        pieces: list[str] = []
        copied_until = 0

        for item_match in ITEM_FIELD_RE.finditer(body):
            item_id = int(item_match.group("item_id"))
            replacement_id, chosen_name = self._pick_replacement(item_id, queue_rules)

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
                    item_id=item_id,
                    old_reward_item_id=old_reward_id,
                    new_reward_item_id=replacement_id,
                )
            )

        if not details:
            return RewriteResult(body=body, details=())

        pieces.append(body[copied_until:])
        return RewriteResult(body="".join(pieces), details=tuple(details))

    def _pick_replacement(self, item_id: int, queue_rules: dict[int, QueueRule]):
        # Specific rule for this exact box kind wins over range.
        rule = queue_rules.get(item_id)
        if rule is not None:
            idx = self._queue_indexes.get(item_id, 0)
            replacement_id = rule.replacement_reward_item_ids[idx % len(rule.replacement_reward_item_ids)]
            self._queue_indexes[item_id] = idx + 1
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
        self._log_load_state()
        try:
            import signal
            signal.signal(signal.SIGHUP, self._on_sighup)
        except (ValueError, OSError, AttributeError):
            pass

    def _log_load_state(self):
        active_specific = [r for r in self.config.specific_queue_rules
                           if r.enabled and r.replacement_reward_item_ids]
        range_active = (self.config.range_replacement.enabled
                        and bool(self.config.range_replacement.replacement_reward_item_ids))
        log_info(
            f"TBH Reward Proxy loaded: "
            f"{len(active_specific)} specific rules active, "
            f"range={'on' if range_active else 'off'}."
        )
        if not active_specific and not range_active:
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
                f"itemId={detail.item_id}: "
                f"rewardItemId={detail.old_reward_item_id}->{detail.new_reward_item_id}"
            )
        log_info(f"TBH Reward Proxy wrote {result.modified_count} replacement(s).")


def _extract_reward_ids(body: str):
    return [int(m.group("reward_id")) for m in REWARD_FIELD_RE.finditer(body)]


def run_self_test():
    # Specific rule: only the configured itemId gets rewritten.
    config = ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        specific_queue_rules=(
            QueueRule(
                enabled=True,
                name="Normal Box (manual)",
                item_id=910801,
                replacement_reward_item_ids=(419171, 419172),
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
    rewriter = RewardRewriter(config)

    body = (
        '{"boxes":['
        '{"itemId":910801,"rewardItemId":1001},'
        '{"itemId":910801,"rewardItemId":1002},'
        '{"itemId":920801,"rewardItemId":1003}'
        ']}'
    )
    result = rewriter.rewrite(body)
    assert result.modified_count == 2, result
    new_ids = _extract_reward_ids(result.body)
    assert new_ids == [419171, 419172, 1003], new_ids
    print(f"  specific rule: [419171, 419172, 1003]")

    # Range rule: any itemId in range gets rewritten.
    config_range = ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        specific_queue_rules=(),
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
        specific_queue_rules=(),
        range_replacement=RangeRule(
            enabled=False,
            name="Range replacement",
            match_min_item_id=500000,
            match_max_item_id=950000,
            replacement_reward_item_ids=(),
        ),
    )
    rewriter_empty = RewardRewriter(empty_config)
    body3 = '{"boxes":[{"itemId":910801,"rewardItemId":12345}]}'
    result3 = rewriter_empty.rewrite(body3)
    assert result3.modified_count == 0, result3
    assert _extract_reward_ids(result3.body) == [12345]
    print(f"  empty config: pass-through, original [12345] preserved")

    # No specific rule for itemId: pass-through.
    body4 = '{"boxes":[{"itemId":920801,"rewardItemId":12345}]}'
    result4 = rewriter.rewrite(body4)  # rewriter has specific rule for 910801 only
    assert result4.modified_count == 0, result4
    print(f"  no rule for itemId: pass-through")

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