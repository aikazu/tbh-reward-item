"""Strategy A v3 — suffix-aware replacement pool.
Read pool from captures/real-reward-pool.json and find a same-tier-variant
replacement for each box rewardId. Fall back through tiers if needed.
"""
from __future__ import annotations
import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from tbh_proxy_config import CONFIG_PATH, ProxyConfig, QueueRule, RangeRule

POOL_PATH = Path(__file__).parent.parent / "captures" / "real-reward-pool.json"
TAMPER_LOG_PATH = Path(__file__).parent.parent / "captures" / "tamper-events.jsonl"
ITEM_CATALOG_PATH = Path(__file__).parent.parent / "captures" / "item-catalog.json"

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
        self.detector = TamperDetector()
        log_info(
            f"TBH Reward Proxy v3 loaded: {len(self.config.specific_queue_rules)} queue rules, "
            f"range mode={'on' if self.config.range_replacement.enabled else 'off'}, "
            f"pool has {len(self.rewriter._by_cat_tier_var)} cat×tier×var buckets, "
            f"{len(self.rewriter._by_tier_var)} tier×var buckets."
        )
        log_info(f"Tamper detector: log={self.detector._log_path}")
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

        # Always scan for tamper reports first — they come from a different
        # endpoint and we want to log even on requests we didn't rewrite.
        self.detector.report(flow)

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
            # Sanity: warn if validator check would fail (last-3 differs)
            old_s = str(detail.old_reward_item_id).zfill(6)
            new_s = str(detail.new_reward_item_id).zfill(6)
            if old_s[-3:] != new_s[-3:]:
                log_info(
                    f"RISK WARNING  last-3 differs: {old_s} ({old_s[-3:]}) -> "
                    f"{new_s} ({new_s[-3:]}) — likely to trigger TamperedItemIdDetected"
                )
        log_info(f"TBH Reward Proxy wrote {result.modified_count} replacement(s).")

    def done(self) -> None:
        """mitmdump lifecycle hook — called when the addon is being unloaded."""
        self.detector.close()


def _extract_reward_ids(body: str):
    return [int(m.group("reward_id")) for m in REWARD_FIELD_RE.finditer(body)]


class TamperDetector:
    """Listens for TamperedItemIdDetected reports from the game client.

    When the client ships POST /data/gameLog/v2/TemperedItem/90 with a
    mismatches list, we:
    - emit a WARNING line to stdout for each mismatch
    - append a structured JSONL record to TAMPER_LOG_PATH with full context

    The log is append-only so multiple addon runs accumulate into one file
    that can be diffed across captures / accounts.
    """

    RARITY_NAMES = [
        "Common", "Uncommon", "Rare", "Legendary", "Immortal",
        "Arcana", "Beyond", "Celestial", "Divine", "Cosmic",
    ]

    def __init__(self, log_path: Path = TAMPER_LOG_PATH,
                 catalog_path: Path = ITEM_CATALOG_PATH):
        self._log_path = log_path
        self._names = self._load_names(catalog_path)
        self._write_handle = None
        # total + per-rarity counters (in-process stats)
        self.total = 0
        self.by_rarity: dict[int, int] = {r: 0 for r in range(10)}

    @staticmethod
    def _load_names(catalog_path: Path) -> dict[int, str]:
        """Build {itemId: name} from catalog for human-readable warnings."""
        if not catalog_path.exists():
            return {}
        try:
            data = json.loads(catalog_path.read_text())
            return {c["itemId"]: c.get("name", "?") for c in data.get("catalog", [])}
        except Exception:
            return {}

    @staticmethod
    def parse_reward(rid: int) -> dict:
        s = str(rid).zfill(6)
        return {
            "category2": s[:2],
            "rarity_digit": int(s[2]),
            "tier2": s[-3:-1],
            "variant": s[-1],
            "last3": s[-3:],
        }

    def rarity_name(self, digit: int) -> str:
        return self.RARITY_NAMES[digit] if 0 <= digit < 10 else f"r{digit}"

    def lookup_name(self, rid: int) -> str:
        return self._names.get(rid, "<not in catalog>")

    def _open(self):
        if self._write_handle is None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_handle = self._log_path.open("a", encoding="utf-8")

    def _write(self, record: dict) -> None:
        self._open()
        handle = self._write_handle
        assert handle is not None  # _open() guarantees this
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()

    def report(self, flow) -> int:
        """Inspect a response for a TamperedItemIdDetected report.

        Returns the number of mismatches found (0 if not a tamper report).
        """
        request = getattr(flow, "request", None)
        response = getattr(flow, "response", None)
        if request is None or response is None:
            return 0
        pretty_url = getattr(request, "pretty_url", "") or getattr(request, "url", "")
        if "/data/gameLog/v2/TemperedItem/90" not in pretty_url:
            return 0
        if request.method.upper() != "POST":
            return 0
        try:
            body = json.loads(response.get_text(strict=False))
        except Exception:
            return 0
        if body.get("msg") != "TamperedItemIdDetected":
            return 0

        mismatches = body.get("data", {}).get("mismatches", []) or []
        ts = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
        for entry in mismatches:
            try:
                _, pair = entry.split(":", 1)
                original_str, used_str = pair.split("->")
                original = int(original_str)
                used = int(used_str)
            except ValueError:
                continue
            orig_info = self.parse_reward(original)
            used_info = self.parse_reward(used)
            rarity = orig_info["rarity_digit"]
            self.total += 1
            self.by_rarity[rarity] = self.by_rarity.get(rarity, 0) + 1
            orig_name = self.lookup_name(original)
            used_name = self.lookup_name(used)
            record = {
                "ts": ts,
                "itemKey_match": entry.split(":", 1)[0],
                "original_id": original,
                "original_name": orig_name,
                "original_rarity": self.rarity_name(rarity),
                "original_tier": orig_info["tier2"],
                "used_id": used,
                "used_name": used_name,
                "used_rarity": self.rarity_name(used_info["rarity_digit"]),
                "used_tier": used_info["tier2"],
                "last3_preserved": orig_info["last3"] == used_info["last3"],
            }
            self._write(record)
            log_info(
                f"TAMPER WARNING  itemKey={record['itemKey_match']}  "
                f"original={original} ({orig_name}, {record['original_rarity']} tier {orig_info['tier2']})  "
                f"used={used} ({used_name}, {record['used_rarity']} tier {used_info['tier2']})  "
                f"last3={'PRESERVED' if record['last3_preserved'] else 'BROKEN'}"
            )
        if mismatches:
            log_info(
                f"TAMPER WARNING  batch total: {len(mismatches)} mismatches "
                f"(session total: {self.total}); log: {self._log_path}"
            )
        return len(mismatches)

    def close(self) -> None:
        if self._write_handle is not None:
            self._write_handle.close()
            self._write_handle = None

    def warn_no_match(self, original_id: int, item_id: int) -> None:
        """Log a structural warning when rewriter couldn't find a safe replacement.

        These are NOT server reports — they indicate cases where our pool lacked
        a matching (tier, variant) entry for this reward. Future captures should
        harvest these itemIds into the pool so they don't slip through.
        """
        info = self.parse_reward(original_id)
        rarity = info["rarity_digit"]
        name = self.lookup_name(original_id)
        log_info(
            f"NO-MATCH WARNING  itemId={item_id} rewardItemId={original_id} "
            f"({name}, {self.rarity_name(rarity)} tier {info['tier2']}) — "
            f"no pool entry, original left untouched"
        )
        self._write({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "event": "no_match",
            "itemId": item_id,
            "rewardItemId": original_id,
            "name": name,
            "rarity": self.rarity_name(rarity),
            "tier": info["tier2"],
            "reason": "pool lacked matching tier+variant entry",
        })


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

    # TamperDetector self-test: feed it a fake TemperedItemIdDetected response
    class _FakeFlow:
        class _Req:
            method = "POST"
            pretty_url = "https://api.thebackend.io/data/gameLog/v2/TemperedItem/90"
        class _Resp:
            def __init__(self, body): self._b = body
            def get_text(self, strict=False): return self._b
        def __init__(self, body):
            self.request = _FakeFlow._Req()
            self.response = _FakeFlow._Resp(body)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as log_f:
        log_path = Path(log_f.name)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as cat_f:
        json.dump({"catalog": [
            {"itemId": 319171, "name": "Dimensional Bow (Cosmic)"},
            {"itemId": 522171, "name": "Dimensional Staff (Rare)"},
        ]}, cat_f)
        cat_path = Path(cat_f.name)

    detector = TamperDetector(log_path=log_path, catalog_path=cat_path)
    fake_body = json.dumps({
        "msg": "TamperedItemIdDetected",
        "data": {"mismatches": ["7453:319171->522171"]},
    })
    n = detector.report(_FakeFlow(fake_body))
    assert n == 1, f"expected 1 mismatch, got {n}"
    detector.close()

    log_lines = log_path.read_text().strip().splitlines()
    assert len(log_lines) == 1, f"expected 1 log line, got {len(log_lines)}"
    record = json.loads(log_lines[0])
    assert record["original_id"] == 319171
    assert record["original_name"] == "Dimensional Bow (Cosmic)"
    assert record["original_rarity"] == "Cosmic"
    assert record["used_id"] == 522171
    assert record["used_name"] == "Dimensional Staff (Rare)"
    assert record["used_rarity"] == "Rare"
    assert record["last3_preserved"] is True
    assert record["itemKey_match"] == "7453"
    print(f"  tamper-detector: 7453 319171(Dimensional Bow Cosmic) -> 522171(Dimensional Staff Rare)  "
          f"last3=PRESERVED")

    # Test no_match warning path too
    detector2 = TamperDetector(log_path=log_path, catalog_path=cat_path)
    detector2.warn_no_match(319171, 910801)
    detector2.close()
    log_lines = log_path.read_text().strip().splitlines()
    assert len(log_lines) == 2
    record2 = json.loads(log_lines[1])
    assert record2["event"] == "no_match"
    assert record2["rewardItemId"] == 319171
    print(f"  tamper-detector: no_match warning recorded for 319171")

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