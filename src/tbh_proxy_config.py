"""Pure data classes for TBH proxy config — no addon, no side effects.

Extracted from tbh_reward_hook.py so the desktop editor (and any other
non-mitmproxy consumer) can validate config.json without triggering the
addon's constructor side effects (e.g. "loaded: N rules" log line at
import time).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


CONFIG_PATH = Path(__file__).with_name("config.json")


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