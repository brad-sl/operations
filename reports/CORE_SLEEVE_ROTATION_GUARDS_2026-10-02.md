# Core-sleeve rotation guards — Brad GO 2026-10-02

**Trigger:** BTC sold via `exit_weak_for_rotation` (RSI>70 → ROTATE_OUT conf 0.4) into a continuation grind; capital layer stamped `manual_liquidation_to_cash` + 48h rebuy block; decision_context logged `holdings_before.BTC-USD = 0.023` (coin qty) vs ~$370 sell.

**Brad GO:** implement items 1–4.

## Shipped

### 1. Core sleeve — no full-bag rotate on RSI>70 alone
- `phase6/core/allocator.py` — `RotationStrategy._is_rsi_overbought_only_rotate_out`
- ROTATE_OUT/SELL from **RSI overbought only** (no negative sentiment) is **held**, not weak-exit
- Dual-peak/meat (4%) and SL/structure still own real exits
- Confirmed bearish (RSI OB + negative sent) **still rotates** when a ≥min_buy IN exists
- Notes stamp: `core_sleeve_rsi_ob_hold=[...]`

### 2. Rotation ≠ manual 48h block
- `phase6/core/runner_capital_events.py` — `_reason_is_strategy_rotation`
- Tokens: `exit_weak_for_rotation`, `arch4_rotation`, `rotation_catch_wave`, hard_stop_*, etc.
- Folded into `_reason_is_strategy_profit_exit` → disposition classifies as TP-path (**no cash hold, no 48h manual cooldown**)

### 3. Sell-only rotation → hold core
- Same `RotationStrategy.decide`: if weak candidates exist but **no** ROTATE_IN ≥ min_buy (0.55 normal / relaxed emergency), **clear weak list** and hold
- Hard stops still fire; emergency recovery (≤2 bags) can still free weak
- Notes stamp: `core_sleeve_sell_only_hold=1`

### 4. holdings_before USD map
- Root cause: `_holdings_usd` / `normalize_position_values` / coordinator `norm_allocs` fell back to **`amount` (coin qty)** as USD
- Fixed in:
  - `phase6/core/rotation_shadow.py` (`_usd_from_position_row` + list/dict shapes)
  - `phase6/core/portfolio_disposition.py`
  - `phase6/core/rebalance_coordinator.py` (allocator input path)
- Prefer `value_usd` / `usd_value`; else `qty * current_price`; **never** bare qty alone

## Proof (isolation)

```
PYTHONPATH=. python3 scripts/phase6/test_isolation_core_sleeve_rotation_guards.py
→ ALL PASS (5/5)

PYTHONPATH=. python3 scripts/phase6/test_isolation_stop_exchange_disposition.py
→ ALL PASS (incl. exit_weak_for_rotation not manual)

PYTHONPATH=. python3 scripts/phase6/test_isolation_capital_disposition_cooldown.py
→ OK

PYTHONPATH=. python3 scripts/phase6/test_isolation_manual_disposition.py
→ ALL PASS
```

## Replay of 2026-10-01 BTC snapshot (post-fix)

| Gate | Before | After |
|------|--------|-------|
| RSI OB ROTATE_OUT 0.4 alone | full SELL | **hold** core_sleeve |
| ADA 0.499 / LINK 0.314 IN | sell-only cash park | **hold** (if weak survived) |
| capital disposition | manual 48h | **strategy / no manual block** |
| holdings_before BTC | 0.023 qty | **~$370 value_usd** |

## Not changed
- Live book / no orders this ship
- BTC rebuy already lifted earlier this session (C)
- Dual-peak meat % / SL paths
- SignalGenerator weights (product rule fixed at allocator, not score cosmetics)

## Rollback
- Revert the four modules + two test files above
- Kill is code revert; no config knob
