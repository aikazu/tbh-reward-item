"""Pure data classes for TBH proxy config — no addon, no side effects.

Config schema (v2 — Jul 2026, tbh.city migration)
================================================

Three rule buckets, each keyed by ``pool_id`` (the tbh.city ``drop_key``
that identifies a specific drop pool — e.g. ``9100111`` = Act 1 normal
monster pool, ``9301011`` = Act 1 act-boss pool). Plus a range replacement
that catches any itemId in [min, max] if no specific rule matched.

* ``normal_rules`` — Normal Reward. Targets monster_pool drop_keys.
  Prefix ``91xxxxxx`` (e.g. 9100111).
* ``boss_rules`` — Boss Reward. Targets boss_pool drop_keys at BOSS-typed
  stages. Prefix ``92xxxxxx`` (e.g. 9200111).
* ``act_rules`` — Act Reward. Targets boss_pool drop_keys at ACTBOSS-typed
  stages. Prefix ``93xxxxxx`` (e.g. 9301011, 9308511).
* ``range_replacement`` — Range replacement. Matches any itemId in
  [match_min_item_id, match_max_item_id] when no specific rule won.

Each rule: ``{enabled, name, pool_id, replacement_reward_item_ids}``.
The proxy matches the body's ``itemId`` field against ``pool_id`` directly
(they're the same integer namespace — ``itemId`` in the wire payload IS
the drop_key tbh.city used in ``pool_id``).

The proxy's client-side validator checks the last 3 digits of
``rewardItemId`` (rarity*100+tier). Pick replacements whose last-3 matches
the pool's original reward suffix, or the client ships
TamperedItemIdDetected. See docs/analysis/tbh-network-forensics.md §10.8.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable


CONFIG_PATH = Path(__file__).with_name("config.json")


def _pick(data: dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        if name in data:
            return data[name]
    return default


def _default_rewrite_pending_tx() -> bool:
    """Platform-aware default for Strategy B (pendingTx rewrite).

    Windows: ``True`` — process injection via local mode pairs naturally
        with the rewrite; without it, ``TamperedItemIdDetected`` fires
        on most reward pools when the replacement suffix doesn't match
        the box's original suffix. Cross-suffix swaps are the whole
        point of this tool, so we want fresh Windows installs to "just
        work" without forcing the user to find the checkbox.

    POSIX (Linux/macOS): ``False`` — historic default. Strategy B was
        originally opt-in until verified safe across many sessions; that
        verification was on the Linux/Proton path. Linux users who have
        completed testing can flip the checkbox explicitly. We don't
        want to surprise existing Linux users with a behavior change.
    """
    return sys.platform == "win32"


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


class PoolRule:
    """A rule that matches one or more tbh.city drop pools.

    ``pool_ids`` is the list of drop_keys (e.g. ``[9100511, 9103511,
    9105511]`` for Act 1/2/3 stage-1-9 Torment monster pools) that this
    rule targets. The proxy matches the body's ``itemId`` field against
    every entry in ``pool_ids`` (it's the same integer namespace —
    pool_id == itemId on the wire).

    The ``rule_kind`` field is set at parse time by the loader and used
    by the desktop editor for section grouping. The proxy treats all
    three kinds identically — the kind only governs UI organization.

    Jul 2026: switched from a single ``pool_id: int`` to ``pool_ids:
    tuple[int, ...]`` so a rule can cover the same reward concept
    across multiple acts / difficulties in one row (e.g. "Normal
    Reward" covers all 12 monster pools for stages 1-9 across 3 acts ×
    4 difficulty). The proxy picks the first matching pool_id.
    """

    __slots__ = (
        "enabled",
        "name",
        "pool_ids",
        "replacement_reward_item_ids",
        "rule_kind",
    )

    def __init__(
        self,
        enabled: bool,
        name: str,
        pool_ids: tuple[int, ...],
        replacement_reward_item_ids: tuple[int, ...],
        rule_kind: str,
    ) -> None:
        self.enabled = enabled
        self.name = name
        self.pool_ids = tuple(int(p) for p in pool_ids)
        self.replacement_reward_item_ids = replacement_reward_item_ids
        self.rule_kind = rule_kind


# Rule kinds — display label + machine name.
# Match tbh.city drop_key prefix conventions:
#   "normal" → 91xxxxxx (monster_pool)
#   "boss"   → 92xxxxxx (boss_pool at BOSS-typed stages)
#   "act"    → 93xxxxxx (boss_pool at ACTBOSS-typed stages)
RULE_KINDS: tuple[str, ...] = ("normal", "boss", "act")
RULE_KIND_LABELS: dict[str, str] = {
    "normal": "Normal Reward",
    "boss": "Boss Reward",
    "act": "Act Reward",
}


class RangeRule:
    """Range-replacement rule: matches any payload ``itemId`` whose
    drop_key (pool_id) falls within ``[min_pool_id, max_pool_id]``.

    Per Jul 2026 user feedback: this range matches by **pool_id**
    (drop_key, the value the game's backend carries in the
    ``itemId`` field of the POST payload) — NOT by item_id. The UI
    shows two spinboxes for drop_key bounds; changing them rewrites
    every pool key in the range.

    The replacement picker therefore exposes the FULL catalog when
    active target = RangeRule (the range catches multiple pools, so
    replacement can be drawn from any of those pools' drop tables).
    """

    __slots__ = (
        "enabled",
        "name",
        "min_pool_id",
        "max_pool_id",
        "replacement_reward_item_ids",
    )

    def __init__(
        self,
        enabled: bool,
        name: str,
        min_pool_id: int,
        max_pool_id: int,
        replacement_reward_item_ids: tuple[int, ...],
    ) -> None:
        self.enabled = enabled
        self.name = name
        self.min_pool_id = min_pool_id
        self.max_pool_id = max_pool_id
        self.replacement_reward_item_ids = replacement_reward_item_ids


class ProxyConfig:
    __slots__ = (
        "listen_port",
        "only_post",
        "require_boxes_marker",
        "url_contains",
        "normal_rules",
        "boss_rules",
        "act_rules",
        "range_replacement",
        "rewrite_pending_tx",
    )

    def __init__(
        self,
        listen_port: int,
        only_post: bool,
        require_boxes_marker: bool,
        url_contains: tuple[str, ...],
        normal_rules: tuple[PoolRule, ...],
        boss_rules: tuple[PoolRule, ...],
        act_rules: tuple[PoolRule, ...],
        range_replacement: RangeRule,
        rewrite_pending_tx: bool = False,
    ) -> None:
        self.listen_port = listen_port
        self.only_post = only_post
        self.require_boxes_marker = require_boxes_marker
        self.url_contains = url_contains
        self.normal_rules = normal_rules
        self.boss_rules = boss_rules
        self.act_rules = act_rules
        self.range_replacement = range_replacement
        self.rewrite_pending_tx = rewrite_pending_tx

    def all_pool_rules(self) -> tuple[PoolRule, ...]:
        """All three rule lists concatenated — used by the proxy to build
        the itemId → PoolRule lookup map.
        """
        return self.normal_rules + self.boss_rules + self.act_rules

    @staticmethod
    def load(path: Path = CONFIG_PATH) -> "ProxyConfig":
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            data = {}

        buckets: dict[str, list[PoolRule]] = {k: [] for k in RULE_KINDS}
        # JSON key per rule kind.
        kind_to_key = {
            "normal": ("normal_rules",),
            "boss": ("boss_rules",),
            "act": ("act_rules",),
        }
        for kind in RULE_KINDS:
            key_variants = kind_to_key[kind]
            raw_list = _pick(data, key_variants, []) or []
            for idx, raw_rule in enumerate(raw_list):
                if not isinstance(raw_rule, dict):
                    continue
                replacements = _as_int_list(
                    _pick(
                        raw_rule,
                        ("replacement_reward_item_ids", "ReplacementRewardItemIds"),
                        [],
                    )
                )
                # Accept either ``pool_ids: [int, ...]`` (new multi-pool
                # shape) or the legacy single ``pool_id: int`` field.
                # New writes always emit ``pool_ids``; legacy configs with
                # only ``pool_id`` get wrapped into a one-element tuple.
                legacy_pool_id = _pick(raw_rule, ("pool_id", "PoolId"), 0)
                raw_pool_ids = _pick(raw_rule, ("pool_ids", "PoolIds"), None)
                if isinstance(raw_pool_ids, list) and raw_pool_ids:
                    pool_ids = tuple(int(p) for p in raw_pool_ids)
                elif legacy_pool_id:
                    pool_ids = (int(legacy_pool_id),)
                else:
                    pool_ids = ()
                buckets[kind].append(
                    PoolRule(
                        enabled=bool(_pick(raw_rule, ("enabled", "Enabled"), True)),
                        name=str(
                            _pick(raw_rule, ("name", "Name"), f"{RULE_KIND_LABELS[kind]} {idx + 1}")
                        ),
                        pool_ids=pool_ids,
                        replacement_reward_item_ids=tuple(replacements),
                        rule_kind=kind,
                    )
                )

        raw_range = _pick(data, ("range_replacement", "RangeReplacement"), {}) or {}
        range_rule = RangeRule(
            enabled=bool(_pick(raw_range, ("enabled", "Enabled"), False)),
            name=str(_pick(raw_range, ("name", "Name"), "Range replacement")),
            min_pool_id=int(
                _pick(
                    raw_range,
                    ("min_pool_id", "MinPoolId",
                     # legacy aliases — the field used to be item-id
                     # range before the Jul 2026 rename.
                     "match_min_item_id", "MatchMinItemId"),
                    500000,
                )
            ),
            max_pool_id=int(
                _pick(
                    raw_range,
                    ("max_pool_id", "MaxPoolId",
                     "match_max_item_id", "MatchMaxItemId"),
                    950000,
                )
            ),
            replacement_reward_item_ids=tuple(
                _as_int_list(
                    _pick(
                        raw_range,
                        ("replacement_reward_item_ids", "ReplacementRewardItemIds"),
                        [],
                    )
                )
            ),
        )

        return ProxyConfig(
            listen_port=int(_pick(data, ("listen_port", "ListenPort"), 8877)),
            only_post=bool(_pick(data, ("only_post", "OnlyPost"), True)),
            require_boxes_marker=bool(_pick(data, ("require_boxes_marker", "RequireBoxesMarker"), True)),
            url_contains=_as_str_tuple(_pick(data, ("url_contains", "UrlContains"), ["/backend-function/base/v1"])),
            normal_rules=tuple(buckets["normal"]),
            boss_rules=tuple(buckets["boss"]),
            act_rules=tuple(buckets["act"]),
            range_replacement=range_rule,
            rewrite_pending_tx=bool(_pick(
                data,
                ("rewrite_pending_tx", "RewritePendingTx"),
                _default_rewrite_pending_tx(),
            )),
        )