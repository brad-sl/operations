# PHASE 6: Native Coinbase Stop-Loss Orders Implementation Spec

**Date:** 2026-05-06
**Context:** Post 1-year backtest SL/TP analysis. Prioritize native server-side SL to eliminate client polling risk and ensure protection even if bot crashes (key lesson from 80% prior loss).

## Recommended Approach
Use Coinbase Advanced Trade API (v3) order types:
- `stop_loss_limit` (preferred for guaranteed execution control)
- Or `stop` (market stop) for simplicity

### Order Payload Example (stop_loss_limit)
```json
{
  "client_order_id": "sl-btc-20260506-001",
  "product_id": "BTC-USD",
  "side": "SELL",
  "order_configuration": {
    "stop_limit_stop_limit_gtc": {
      "base_size": "0.001",
      "limit_price": "62000.00",
      "stop_price": "62500.00",
      "stop_direction": "STOP_DIRECTION_STOP_DOWN"
    }
  }
}
```

### Mapping from Backtest to Live
- **ATR-based SL:** Compute 14-period ATR on entry, set `stop_price = entry_price - (atr * 2.0)`, `limit_price = stop_price * 0.995` (small buffer for fill).
- **Fixed % SL:** `stop_price = entry_price * (1 - 0.03)`, `limit_price = stop_price * 0.99`.
- Use `post_only: false` for immediate protection.

### Implementation Steps (Next)
1. Extend `coinbase_wrapper.py` or `order_executor.py` with `place_stop_loss_order(pair, entry_price, sl_price, size)` method.
2. Integrate into `phase6.py` / `live_portfolio_manager.py` — on every BUY entry, immediately place the corresponding native SL (and optional TP as `take_profit_limit`).
3. Add SL monitoring in `phase6_monitor.db` or state manager (track open SL orders).
4. Fallback: If API rejects, log critical alert and use internal tracking (but prefer native).
5. Sandbox test: Use `test_coinbase_auth.py` + new unit test for SL placement + fill simulation.
6. Risk: Always size SL so worst loss <= 2-3% of account (from backtest recommendation).

### Files to Modify/Add
- `coinbase_wrapper.py` — add `place_native_sl(...)`
- `order_executor.py` — call native SL on entry
- `PHASE_6_SL_IMPLEMENTATION.md` — detailed code + test plan (follow-up task)

**Safest config for live (from backtest):** Fixed 3% or ATR 2x SL + No TP (let winners run). Deploy native SL immediately on entry.

This eliminates the single point of failure that caused the prior 80% drawdown.