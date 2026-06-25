from __future__ import annotations
 
import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

 
CONFIG_PATH = Path(__file__).with_name("config.json")
 
ITEM_FIELD_RE = re.compile(r'\\?"itemId\\?"\s*:\s*(?P<item_id>\d+)(?!\d)')
REWARD_FIELD_RE = re.compile(r'(\\?"rewardItemId\\?"\s*:\s*)(?P<reward_id>\d+)(?!\d)')
 
 
def _pick(data: dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        if name in data:
            return data[name]
    return default
 
 
def _as_int_list(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        raw_values = [part.strip() for part in value.split(",")]
    else:
        raw_values = list(value)
 
    result: list[int] = []
    for raw in raw_values:
        if raw == "":
            continue
        result.append(int(raw))
    return result
 
 
def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
 
 
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


class QueueRule:
    __slots__ = ("enabled", "name", "item_id", "replacement_reward_item_ids")
 
    def __init__(
        self,
        enabled: bool,
        name: str,
        item_id: int,
        replacement_reward_item_ids: tuple[int, ...],
    ) -> None:
        self.enabled = enabled
        self.name = name
        self.item_id = item_id
        self.replacement_reward_item_ids = replacement_reward_item_ids
 
 
class RangeRule:
    __slots__ = (
        "enabled",
        "name",
        "match_min_item_id",
        "match_max_item_id",
        "replacement_reward_item_ids",
    )
 
    def __init__(
        self,
        enabled: bool,
        name: str,
        match_min_item_id: int,
        match_max_item_id: int,
        replacement_reward_item_ids: tuple[int, ...],
    ) -> None:
        self.enabled = enabled
        self.name = name
        self.match_min_item_id = match_min_item_id
        self.match_max_item_id = match_max_item_id
        self.replacement_reward_item_ids = replacement_reward_item_ids
 
 
class ProxyConfig:
    __slots__ = (
        "listen_port",
        "only_post",
        "require_boxes_marker",
        "url_contains",
        "specific_queue_rules",
        "range_replacement",
    )
 
    def __init__(
        self,
        listen_port: int,
        only_post: bool,
        require_boxes_marker: bool,
        url_contains: tuple[str, ...],
        specific_queue_rules: tuple[QueueRule, ...],
        range_replacement: RangeRule,
    ) -> None:
        self.listen_port = listen_port
        self.only_post = only_post
        self.require_boxes_marker = require_boxes_marker
        self.url_contains = url_contains
        self.specific_queue_rules = specific_queue_rules
        self.range_replacement = range_replacement
 
    @staticmethod
    def load(path: Path = CONFIG_PATH) -> "ProxyConfig":
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            data = {}
 
        specific_rules = []
        for idx, raw_rule in enumerate(_pick(data, ("specific_queue_rules", "SpecificQueueRules"), [])):
            replacements = _as_int_list(
                _pick(raw_rule, ("replacement_reward_item_ids", "ReplacementRewardItemIds"), [])
            )
            specific_rules.append(
                QueueRule(
                    enabled=bool(_pick(raw_rule, ("enabled", "Enabled"), True)),
                    name=str(_pick(raw_rule, ("name", "Name"), f"Queue {idx + 1}")),
                    item_id=int(_pick(raw_rule, ("item_id", "ItemId"), 0)),
                    replacement_reward_item_ids=tuple(replacements),
                )
            )
 
        raw_range = _pick(data, ("range_replacement", "RangeReplacement"), {}) or {}
        range_rule = RangeRule(
            enabled=bool(_pick(raw_range, ("enabled", "Enabled"), False)),
            name=str(_pick(raw_range, ("name", "Name"), "Range replacement")),
            match_min_item_id=int(_pick(raw_range, ("match_min_item_id", "MatchMinItemId"), 500000)),
            match_max_item_id=int(_pick(raw_range, ("match_max_item_id", "MatchMaxItemId"), 950000)),
            replacement_reward_item_ids=tuple(
                _as_int_list(_pick(raw_range, ("replacement_reward_item_ids", "ReplacementRewardItemIds"), []))
            ),
        )
 
        return ProxyConfig(
            listen_port=int(_pick(data, ("listen_port", "ListenPort"), 8877)),
            only_post=bool(_pick(data, ("only_post", "OnlyPost"), True)),
            require_boxes_marker=bool(_pick(data, ("require_boxes_marker", "RequireBoxesMarker"), True)),
            url_contains=_as_str_tuple(_pick(data, ("url_contains", "UrlContains"), ["/backend-function/base/v1"])),
            specific_queue_rules=tuple(specific_rules),
            range_replacement=range_rule,
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
            log_info(f"TBH Reward Proxy matched URL but found no replaceable reward item: {pretty_url}")
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
    config = ProxyConfig.load()
    rewriter = RewardRewriter(config)

    # Derive expected reward IDs from the loaded config (per-item_id cycling),
    # so the self-test stays valid when rules are edited on the fly.
    rules = {
        r.item_id: r
        for r in config.specific_queue_rules
        if r.enabled and r.replacement_reward_item_ids
    }

    def _expected(item_ids: list[int]) -> list[int]:
        idx: dict[int, int] = {}
        out: list[int] = []
        for iid in item_ids:
            rule = rules.get(iid)
            assert rule is not None, (
                f"no enabled specific_queue_rule for itemId {iid} in config.json — "
                "self-test needs White(910801)+Blue(920801) rules enabled"
            )
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
 
 
addons = [TBHRewardHook()]
 
 
if __name__ == "__main__":
    raise SystemExit(main())