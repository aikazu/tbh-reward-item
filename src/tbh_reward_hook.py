"""Strategy A v3 — suffix-aware replacement pool.
Read pool from captures/real-reward-pool.json and find a same-tier-variant
replacement for each box rewardId. Fall back through tiers if needed.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

from tbh_proxy_config import CONFIG_PATH, ProxyConfig, QueueRule, RangeRule

POOL_PATH = Path(__file__).parent.parent / "captures" / "real-reward-pool.json"

ITEM_FIELD_RE = re.compile(r'\\?"itemId\\?"\s*:\s*(?P<item_id>\d+)(?!\d)')
REWARD_FIELD_RE = re.compile(r'(\\?"rewardItemId\\?"\s*:\s*)(?P<reward_id>\d+)(?!\d)')


def log_info(message: str) -> None:
    print(f"[TBH] {message}", flush=True)


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
    __slots__ = ("rule_name", "item_id", "old_reward_item_id", "new_reward_item_id", "strategy")

    def __init__(self, rule_name, item_id, old_reward_item_id, new_reward_item_id, strategy):
        self.rule_name = rule_name
        self.item_id = item_id
        self.old_reward_item_id = old_reward_item_id
        self.new_reward_item_id = new_reward_item_id
        self.strategy = strategy


class RewriteResult:
    __slots__ = ("body", "details")

    def __init__(self, body, details):
        self.body = body
        self.details = details

    @property
    def modified_count(self):
        return len(self.details)


class RewardRewriter:
    """Strategy A v3 — suffix-aware pool selection.

    For each original rewardId, find a replacement with same (category, tier, variant).
    Falls back to (tier, variant), then leaves original unchanged.
    """

    def __init__(self, config, pool_path: Path = POOL_PATH):
        self.config = config
        self._range_index = 0
        self._pool = self._load_pool(pool_path)
        # Index by lookup keys for O(1) access
        self._by_cat_tier_var = self._pool.get("by_cat_tier_var", {})
        self._by_tier_var = self._pool.get("by_tier_var", {})

    @staticmethod
    def _load_pool(path: Path) -> dict:
        """Load pool and build lookup indexes."""
        if not path.exists():
            log_info(f"pool file missing: {path}, addon will leave originals unchanged.")
            return {"by_cat_tier_var": {}, "by_tier_var": {}}
        data = json.loads(path.read_text())
        rewards = data.get("rewards", {})

        by_cat_tier_var = {}
        by_tier_var = {}
        for rid_str, info in rewards.items():
            rid = int(rid_str)
            cat2 = info["category2"]
            tier2 = info["tier2"]
            variant = info["variant"]
            cat_tier_var_key = f"{cat2}|{tier2}|{variant}"
            tier_var_key = f"{tier2}|{variant}"
            by_cat_tier_var.setdefault(cat_tier_var_key, []).append(rid)
            by_tier_var.setdefault(tier_var_key, []).append(rid)
        return {"by_cat_tier_var": by_cat_tier_var, "by_tier_var": by_tier_var}

    def _parse_reward(self, rid: int) -> dict:
        s = str(rid).zfill(6)
        return {
            "category2": s[:2],
            "tier2": s[-3:-1],
            "variant": s[-1],
        }

    def _pick_replacement(self, original_rid: int, item_id: int) -> tuple[int | None, str]:
        """Try (cat,tier,var) match first, then (tier,var), then None."""
        info = self._parse_reward(original_rid)
        cat_tier_var_key = f"{info['category2']}|{info['tier2']}|{info['variant']}"
        pool1 = [r for r in self._by_cat_tier_var.get(cat_tier_var_key, []) if r != original_rid]
        if pool1:
            return pool1[self._range_index % len(pool1)], "cat_tier_var"

        tier_var_key = f"{info['tier2']}|{info['variant']}"
        pool2 = [r for r in self._by_tier_var.get(tier_var_key, []) if r != original_rid]
        if pool2:
            return pool2[self._range_index % len(pool2)], "tier_var"

        return None, "no_match"

    def rewrite(self, body: str) -> RewriteResult:
        queue_rules = {
            rule.item_id: rule
            for rule in self.config.specific_queue_rules
            if rule.enabled and rule.item_id and rule.replacement_reward_item_ids
        }
        queue_indexes: dict[int, int] = {}
        details: list[ReplacementDetail] = []
        pieces: list[str] = []
        copied_until = 0

        for item_match in ITEM_FIELD_RE.finditer(body):
            item_id = int(item_match.group("item_id"))
            chosen_name = ""
            replacement_id: int | None = None
            strategy = ""

            # Strategy 1: per-box specific rules (legacy v1 behavior)
            rule = queue_rules.get(item_id)
            if rule is not None:
                index = queue_indexes.get(item_id, 0)
                replacement_id = rule.replacement_reward_item_ids[index % len(rule.replacement_reward_item_ids)]
                queue_indexes[item_id] = index + 1
                chosen_name = rule.name
                strategy = "queue_rule"
            elif self._range_matches(item_id):
                # Strategy 2: range replacement with v3 suffix-aware pool
                # The legacy range pool was a flat list of IDs; here we use
                # the suffix-aware lookup per-reward
                # First, find the next rewardItemId in the body that follows this itemId
                reward_match = REWARD_FIELD_RE.search(body, item_match.end())
                if reward_match is not None:
                    original_reward = int(reward_match.group("reward_id"))
                    candidate, strat = self._pick_replacement(original_reward, item_id)
                    if candidate is not None:
                        replacement_id = candidate
                        chosen_name = self.config.range_replacement.name
                        strategy = strat
                        self._range_index += 1

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
                    strategy=strategy,
                )
            )

        if not details:
            return RewriteResult(body=body, details=())

        pieces.append(body[copied_until:])
        return RewriteResult(body="".join(pieces), details=tuple(details))

    def _range_matches(self, item_id: int) -> bool:
        rule = self.config.range_replacement
        if not rule.enabled:
            return False
        return rule.match_min_item_id <= item_id <= rule.match_max_item_id


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
        log_info(
            f"TBH Reward Proxy v3 loaded: {len(self.config.specific_queue_rules)} queue rules, "
            f"range mode={'on' if self.config.range_replacement.enabled else 'off'}, "
            f"pool has {len(self.rewriter._by_cat_tier_var)} cat×tier×var buckets, "
            f"{len(self.rewriter._by_tier_var)} tier×var buckets."
        )
        try:
            import signal
            signal.signal(signal.SIGHUP, self._on_sighup)
        except (ValueError, OSError, AttributeError):
            pass

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
        log_info(
            f"TBH Reward Proxy reloaded: {len(self.config.specific_queue_rules)} queue rules, "
            f"range mode={'on' if self.config.range_replacement.enabled else 'off'}."
        )

    def _on_sighup(self, _signum, _frame):
        self._config_mtime = 0
        self._reload_if_changed()

    def response(self, flow):
        self._reload_if_changed()
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
                f"TBH Reward Proxy [{detail.strategy}] "
                f"itemId={detail.item_id}: "
                f"rewardItemId={detail.old_reward_item_id}->{detail.new_reward_item_id}"
            )
        log_info(f"TBH Reward Proxy wrote {result.modified_count} replacement(s).")


def _extract_reward_ids(body: str):
    return [int(m.group("reward_id")) for m in REWARD_FIELD_RE.finditer(body)]


def run_self_test():
    # Strategy v3 self-test: use a small built-in pool
    import tempfile
    pool = {
        "rewards": {
            "319171": {"category2": "31", "tier2": "17", "variant": "1"},
            "311171": {"category2": "31", "tier2": "17", "variant": "1"},
            "310171": {"category2": "31", "tier2": "17", "variant": "1"},
            "506111": {"category2": "50", "tier2": "11", "variant": "1"},
            "501111": {"category2": "50", "tier2": "11", "variant": "1"},
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(pool, f)
        pool_path = Path(f.name)

    config = ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        specific_queue_rules=(),
        range_replacement=RangeRule(
            enabled=True,
            name="Suffix-aware range",
            match_min_item_id=910801,
            match_max_item_id=930999,
            replacement_reward_item_ids=(),  # ignored in v3, pool drives selection
        ),
    )
    rewriter = RewardRewriter(config, pool_path=pool_path)

    body = '{"boxes":[{"itemId":910801,"rewardItemId":319171},{"itemId":910801,"rewardItemId":506111}]}'
    result = rewriter.rewrite(body)
    assert result.modified_count == 2, result
    new_ids = _extract_reward_ids(result.body)
    assert new_ids[0] in (311171, 310171), f"expected 31-cat tier17 var1, got {new_ids[0]}"
    assert new_ids[1] == 501111, f"expected 50-cat tier11 var1, got {new_ids[1]}"
    print(f"  self-test: 319171→{new_ids[0]}, 506111→{new_ids[1]}")
    print("Self-test OK.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TBH reward response rewrite addon v3 (suffix-aware pool).")
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