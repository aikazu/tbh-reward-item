from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from tbh_proxy_config import CONFIG_PATH, ProxyConfig, QueueRule, RangeRule


ITEM_FIELD_RE = re.compile(r'\\?"itemId\\?"\s*:\s*(?P<item_id>\d+)(?!\d)')
REWARD_FIELD_RE = re.compile(r'(\\?"rewardItemId\\?"\s*:\s*)(?P<reward_id>\d+)(?!\d)')


def log_info(message: str) -> None:
    print(f"[TBH] {message}", flush=True)


def _safe_load_config(path: Path = CONFIG_PATH) -> "ProxyConfig | None":
    """Load config; return None (and log) on any failure so callers can fall back."""
    try:
        return ProxyConfig.load(path)
    except Exception as exc:
        log_info(f"config load failed ({path}): {exc}")
        return None


def _empty_config() -> "ProxyConfig":
    """Safe default config with no rules. Used when config.json is missing or corrupt."""
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

    def __init__(
        self,
        rule_name: str,
        item_id: int,
        old_reward_item_id: int,
        new_reward_item_id: int,
    ) -> None:
        self.rule_name = rule_name
        self.item_id = item_id
        self.old_reward_item_id = old_reward_item_id
        self.new_reward_item_id = new_reward_item_id
 
 
class RewriteResult:
    __slots__ = ("body", "details")
 
    def __init__(self, body: str, details: tuple[ReplacementDetail, ...]) -> None:
        self.body = body
        self.details = details
 
    @property
    def modified_count(self) -> int:
        return len(self.details)
 
 
class RewardRewriter:
    def __init__(self, config: ProxyConfig):
        self.config = config
        self._range_index = 0
 
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
 
            rule = queue_rules.get(item_id)
            if rule is not None:
                index = queue_indexes.get(item_id, 0)
                replacement_id = rule.replacement_reward_item_ids[index % len(rule.replacement_reward_item_ids)]
                queue_indexes[item_id] = index + 1
                chosen_name = rule.name
            elif self._range_matches(item_id):
                pool = self.config.range_replacement.replacement_reward_item_ids
                replacement_id = pool[self._range_index % len(pool)]
                self._range_index += 1
                chosen_name = self.config.range_replacement.name
 
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
 
    def _range_matches(self, item_id: int) -> bool:
        rule = self.config.range_replacement
        if not rule.enabled or not rule.replacement_reward_item_ids:
            return False
        return rule.match_min_item_id <= item_id <= rule.match_max_item_id
 
 
class TBHRewardHook:
    def __init__(self) -> None:
        self._config_path = CONFIG_PATH
        self._config_mtime = 0
        from config_setup import ensure_config
        ensure_config()
        loaded = _safe_load_config(self._config_path)
        if loaded is None:
            self.config = _empty_config()
            log_info("using fallback empty config (no rules active). Fix config.json and save to reload.")
        else:
            self.config = loaded
        self._config_mtime = self._read_mtime(self._config_path)
        self.rewriter = RewardRewriter(self.config)
        log_info(
            f"TBH Reward Proxy loaded: {len(self.config.specific_queue_rules)} queue rules, "
            f"range mode={'on' if self.config.range_replacement.enabled else 'off'}."
        )
        # SIGHUP forces immediate reload (manual: pkill -HUP -f mitmdump)
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

    def _reload_if_changed(self) -> None:
        """Re-read config.json when its mtime changes. Hot reload, no restart needed.

        On corrupt/invalid config: keep the current config running and log the error,
        so a bad edit never takes the proxy down or breaks active interception.
        """
        mtime = self._read_mtime(self._config_path)
        if mtime == self._config_mtime:
            return
        loaded = _safe_load_config(self._config_path)
        if loaded is None:
            # Keep current config; advance mtime so we don't retry-spam every request
            # on the same broken file, but still reload once the user fixes and saves it.
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

    def _on_sighup(self, _signum: int, _frame: Any) -> None:
        self._config_mtime = 0
        self._reload_if_changed()
 
    def response(self, flow: Any) -> None:
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
            # URL matched but no replacement rules fired. This is the common
            # case during gameplay (heartbeats, state polls with no item IDs
            # we want to rewrite). Logging it every time floods stdout and
            # wastes I/O. Skipped — the periodic "wrote N replacement(s)"
            # line below covers the interesting case.
            return

        response.set_text(result.body)
        for detail in result.details:
            log_info(
                "TBH Reward Proxy replaced "
                f"{detail.rule_name}: itemId={detail.item_id}, "
                f"rewardItemId={detail.old_reward_item_id}->{detail.new_reward_item_id}"
            )
        log_info(f"TBH Reward Proxy wrote {result.modified_count} replacement(s).")
 
 
def _extract_reward_ids(body: str) -> list[int]:
    return [int(match.group("reward_id")) for match in REWARD_FIELD_RE.finditer(body)]
 
 
def run_self_test() -> None:
    # Self-test uses a fixed fixture config instead of the live config.json,
    # so it stays green regardless of which rules are toggled in production.
    white_rule = QueueRule(
        enabled=True,
        name="White box",
        item_id=910801,
        replacement_reward_item_ids=(910801,),
    )
    blue_rule = QueueRule(
        enabled=True,
        name="Blue box",
        item_id=920801,
        replacement_reward_item_ids=(920801,),
    )
    config = ProxyConfig(
        listen_port=8877,
        only_post=True,
        require_boxes_marker=True,
        url_contains=("/backend-function/base/v1",),
        specific_queue_rules=(white_rule, blue_rule),
        range_replacement=RangeRule(
            enabled=False,
            name="Range replacement",
            match_min_item_id=500000,
            match_max_item_id=950000,
            replacement_reward_item_ids=(),
        ),
    )
    rewriter = RewardRewriter(config)

    rules = {r.item_id: r for r in config.specific_queue_rules if r.enabled and r.replacement_reward_item_ids}

    def _expected(item_ids: list[int]) -> list[int]:
        idx: dict[int, int] = {}
        out: list[int] = []
        for iid in item_ids:
            rule = rules.get(iid)
            assert rule is not None, f"no enabled specific_queue_rule for itemId {iid} in fixture config"
            k = idx.get(iid, 0)
            out.append(rule.replacement_reward_item_ids[k % len(rule.replacement_reward_item_ids)])
            idx[iid] = k + 1
        return out

    normal_body = (
        '{"boxes":['
        '{"itemId":910801,"rewardItemId":1001},'
        '{"itemId":920801,"rewardItemId":1002},'
        '{"itemId":910801,"rewardItemId":1003}'
        ']}'
    )
    normal_result = rewriter.rewrite(normal_body)
    assert normal_result.modified_count == 3, normal_result
    assert _extract_reward_ids(normal_result.body) == _expected([910801, 920801, 910801]), normal_result.body

    escaped_body = (
        r'{"boxes":[{"itemId":910801,"rewardItemId":2001},'
        r'{"itemId":920801,"rewardItemId":2002}]}'
    )
    escaped_result = rewriter.rewrite(escaped_body)
    assert escaped_result.modified_count == 2, escaped_result
    expected_white = _expected([910801])[0]
    assert f'"rewardItemId":{expected_white}' in escaped_result.body, escaped_result.body
 
    range_config = ProxyConfig(
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
            replacement_reward_item_ids=(529191, 419191),
        ),
    )
    range_result = RewardRewriter(range_config).rewrite(
        '{"boxes":[{"itemId":529999,"rewardItemId":1},{"itemId":499999,"rewardItemId":2}]}'
    )
    assert range_result.modified_count == 1, range_result
    assert _extract_reward_ids(range_result.body) == [529191, 2], range_result.body
 
    print("Self-test OK.")
 
 
def main() -> int:
    parser = argparse.ArgumentParser(description="TBH reward response rewrite addon for mitmproxy.")
    parser.add_argument("--self-test", action="store_true", help="run offline rewrite tests")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return 0

    print("Run this file with mitmdump:")
    print(r"  mitmdump -s tbh_reward_hook.py --listen-port 8877 --set block_global=false")
    return 0


# mitmdump reads this attribute once when loading the addon via
# ``mitmdump -s tbh_reward_hook.py``. The desktop editor does not import
# this module (it uses tbh_proxy_config for data validation), so the
# constructor here only fires when the proxy is actually being started.
addons = [TBHRewardHook()]


if __name__ == "__main__":
    raise SystemExit(main())