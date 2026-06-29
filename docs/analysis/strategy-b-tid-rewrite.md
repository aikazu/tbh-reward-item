# Strategy B — Full Evasion via `pendingTx.tid` Rewrite

**Status**: analysis complete, implementation pending (next session)
**Prerequisite reading**: `docs/analysis/tbh-network-forensics.md` §10.12
**Created**: 2026-06-29 by the player

---

## 0. TL;DR

The `tid` ↔ `rewardItemId` mapping has been cracked:

```
gid == rewardItemId         (6-digit item ID)
tid  == rewardItemId * 1000 + 900
```

Strategy B rewrites **both** `rewardItemId` (in `processBoxV2` response)
and `gid`/`tid` (in `SteamItemInfo/mine` pendingTx) so the client
validator sees consistent values → no `TamperedItemIdDetected` → no ban
trail, **and** the reward is the high-tier item we actually want
(regardless of suffix mismatch).

This is the "real unlock" — it frees us from the suffix-matching
constraint of Strategy A (current suffix-aware picker).

---

## 1. Problem Statement

### Current state (v1 dumb + suffix-aware picker)

- Addon rewrites `rewardItemId` in `processBoxV2` response only.
- Client validator cross-checks against `pendingTx.tid`-derived truth.
- If suffix differs → `TamperedItemIdDetected` report.
- Suffix-aware picker mitigates by constraining replacements to
  same-suffix items → validator passes, but reward value is limited
  (can only swap within same tier+variant).

### What Strategy B adds

- Also rewrite `pendingTx.gid` and `pendingTx.tid` in
  `SteamItemInfo/mine` responses to match the new `rewardItemId`.
- Both sides agree → validator passes regardless of suffix.
- Can swap ANY item for ANY other item (e.g. Soulstone `190004` →
  Cosmic Axe `419171`) without triggering a report.

---

## 2. The `tid` mapping (verified)

### Source

`captures/cap-20260628-195045.flow` flow #7 (SteamItemInfo) + flow #9
(processBoxV2), confirmed against `captures/dump-20260628-201500.json`.

### Evidence

```
pendingTx entry:
  gid = 321111     (= rewardItemId, 6-digit item ID)
  tid = 321111900  (= gid * 1000 + 900)
  rid = 17432693923082523668  (requestId, 20-digit, NOT reward-derived)
  op  = additem
  sid = 76561198000000000     (Steam ID)
```

Offset `900` consistent across 3 pendingTx projections in the dump
(all reference the same single pendingTx entry, but projected via
different attribute combinations).

### Confidence

- n=1 unique pendingTx entry. Pattern is clean but needs n>1 to be
  certain the `900` offset is constant and not per-item or per-session.
- **Risk**: if `900` varies, derive it from observed
  `(tid - gid * 1000)` per entry instead of hardcoding.

---

## 3. Implementation plan

### 3.1 New interception target

Currently the addon only intercepts:
```
POST /backend-function/base/v1  (with "boxes" in body)
```

Strategy B adds a second interception target:
```
GET /data/gameinfo/v3.3/union/SteamItemInfo/mine  (with "pendingTx" in body)
```

### 3.2 Session rewrite map

Maintain an in-memory map populated when `processBoxV2` is rewritten:

```python
# {original_rewardItemId: new_rewardItemId}
self._rewrite_map: dict[int, int] = {}
```

When `processBoxV2` rewrites `rewardItemId` from `319171` → `419171`:
```python
self._rewrite_map[319171] = 419171
```

### 3.3 SteamItemInfo pendingTx rewrite

When `SteamItemInfo/mine` response contains `pendingTx` entries:

1. Parse the DynamoDB-formatted response (`{"L": [{"M": {...}}]}`)
2. For each entry, check if `gid` is in `_rewrite_map`
3. If yes:
   - Rewrite `gid` → `new_rewardItemId`
   - Rewrite `tid` → `new_rewardItemId * 1000 + 900`
   - Leave `rid`, `op`, `sid`, `qty` untouched
4. Re-serialize back to the response body

### 3.4 Code structure

New class in `src/tbh_reward_hook.py`:

```python
class PendingTxRewriter:
    """Rewrites pendingTx.gid + .tid to match rewritten rewardItemId.

    Maintains a session map {original_rid: new_rid} populated by
    RewardRewriter. When SteamItemInfo/mine returns pendingTx entries,
    rewrites gid/tid for any entry whose gid is in the map.
    """

    TID_OFFSET = 900  # tid = gid * 1000 + 900 (verified n=1, needs n>1)

    def __init__(self):
        self._rewrite_map: dict[int, int] = {}

    def record_rewrite(self, original_rid: int, new_rid: int):
        self._rewrite_map[original_rid] = new_rid

    def maybe_rewrite(self, flow) -> bool:
        """Check if this is a SteamItemInfo response; rewrite if so."""
        # 1. URL match: /data/gameinfo/v3.3/union/SteamItemInfo/mine
        # 2. Body contains "pendingTx"
        # 3. Parse, rewrite gid/tid, re-serialize
        ...
```

Wire into `TBHRewardHook.response()`:
```python
def response(self, flow):
    self._reload_if_changed()
    self.tamper_detector.maybe_log(flow)

    # Strategy B: rewrite pendingTx to match rewardItemId rewrites
    self.pending_tx_rewriter.maybe_rewrite(flow)

    # Existing: rewrite rewardItemId in processBoxV2
    ...
    for detail in result.details:
        self.pending_tx_rewriter.record_rewrite(
            detail.old_reward_item_id,
            detail.new_reward_item_id,
        )
```

### 3.5 Config flag

Add to `config.json`:
```json
{
    "rewrite_pending_tx": false
}
```

Default `false` — Strategy B is opt-in until verified safe.
When `true`, the addon intercepts `SteamItemInfo/mine` in addition to
`/backend-function/base/v1`.

### 3.6 Testing

- Unit test: `PendingTxRewriter` with synthetic DynamoDB-format response
  containing a known `gid` → verify `gid` and `tid` rewritten correctly.
- Integration: replay `captures/cap-20260628-195045.flow` through the
  addon → verify `pendingTx.tid` matches the rewritten `rewardItemId`.
- Live verification: run addon with `rewrite_pending_tx=true`, open
  boxes, check `captures/tamper-events.jsonl` for zero new reports.

---

## 4. Risk assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| `tid` offset `900` varies per item/session | Medium | Derive from `(tid - gid*1000)` per entry; log all observed offsets |
| Server uses `tid` for rate limiting / batch ID | Low-Medium | Monitor for 4xx/5xx responses after rewrite; if server rejects, fall back to suffix-aware (Strategy A) |
| Server has secondary heuristic (reward count histogram) | Unknown | Monitor `tamper-events.jsonl` + watch for ban signals over multiple sessions |
| `pendingTx` response format changes in game update | Low | Parser should be defensive (skip unknown fields, log parse errors) |
| `rid` (requestId) also needs rewriting | Low | `rid` is a 20-digit correlation ID, not reward-derived. Leave untouched unless validator complains. |

---

## 5. Verification checklist (for implementation session)

- [ ] Capture a fresh session with addon OFF — open 1 box, capture
      `processBoxV2` + the next `SteamItemInfo/mine`. Verify `tid`
      mapping holds for the new pendingTx entry (n=2).
- [ ] Implement `PendingTxRewriter` class
- [ ] Add `rewrite_pending_tx` config flag
- [ ] Wire into `TBHRewardHook.response()`
- [ ] Unit tests for `PendingTxRewriter` (DynamoDB parse + rewrite + re-serialize)
- [ ] Self-test extension with synthetic pendingTx fixture
- [ ] Live test: addon ON with `rewrite_pending_tx=true`, open boxes,
      verify zero `TamperedItemIdDetected` in `tamper-events.jsonl`
- [ ] Live test: swap cross-suffix (e.g. `190004` → `419171`) and
      confirm no tamper report
- [ ] Monitor for 3+ sessions for delayed ban signals

---

## 6. Why this is better than Strategy A (suffix-aware)

| | Strategy A (current) | Strategy B (proposed) |
|---|---|---|
| Evasion | Suffix must match | Any item → any item |
| Reward value | Limited to same-tier swaps | Full freedom |
| Implementation | Already done (picker toggle) | ~2-3 hours coding |
| Risk | Low (validator passes) | Medium (tid rewrite, server behavior unknown) |
| Ban trail | Zero (if suffix matches) | Zero (if mapping holds) |

Strategy A is the safe baseline. Strategy B is the upgrade path once
the `tid` mapping is confirmed with n>1 captures.

---

*Analysis by the player, 2026-06-29. Ready for implementation in a future session.*
