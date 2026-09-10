# Platform reliability: Settlement / Naked Bag / Episode ID (P0)

**Date:** 2026-09-10  
**Owner:** Grok  
**Audience:** Hermes agents, Implementers  
**Status:** **A1/A3/A4 shipped (code+isolation); A2 thin slice only**  
**Objective:** Close remaining P0 reliability holes that introduce process tax by ensuring:
1.  A buy fill is never immediately followed by an unattached SL ("naked bag").
2.  Every lot has a clear identity through its lifecycle ("episode identity").
3.  All fills (buy/sell) correctly update the ledger.
4.  No stale registry stops persist for flat pairs.

## A1. Post-fill settlement / Naked Bag (P0) — **DONE**

**Problem:** Buy fills occur, but the immediate post-buy stop-loss attach fails (e.g., `available=0` settlement issue), leaving the position temporarily unprotected ("naked bag").

**Shipped:**
- After verified fresh-buy fill, poll `get_crypto_available` until size is tradable (`naked_bag_settle_timeout_s`, default 15s).
- If still short: **fail-closed** — cancel open stops best-effort, market-sell flatten, return False (no unprotected attach continue).
- Fresh-buy attach size resolve → 0 (no hold lock): same fail-closed.
- Exhausted SL retries on fresh buy: fail-closed flatten attempt.
- Isolation: `scripts/phase6/test_isolation_naked_bag_p0.py` (4/4 PASS).

**Files:** `phase6/core/stop_loss_manager.py`

## A2. Episode Identity — **THIN SLICE ONLY**

**Full architectural bag_id propagation (ratchet/live_state/ledger filter) remains open.**

**Shipped thin slice:**
- `register_protective_order(..., bag_id=)` — defaults to `{pair}:{buy_order_id}` when buy id present.
- Fresh-buy attach registers `bag_id` on protective registry row.

**Not done (deferred design/implement):** ratchet filter by bag_id, ledger schema bag_id on every leg, live_state keyed by bag_id. Do not half-refactor those without a dedicated grill.

## A3. Fill-recon Order Attribution (P0 residual) — **DONE**

**Problem:** limit-first LINK buys missed ledger attribution (`order_type=LIMIT` rejected; weak bot attribution).

**Shipped:**
- `is_coinbase_trading_bot_order` also accepts `client_order_id` prefix `phase6-` / `phase6_`.
- `build_ledger_row_from_market_buy` accepts market **and** limit fills; reason `limit_first_buy` for LIMIT.
- Isolation: `scripts/phase6/test_isolation_fill_recon_p0_closeout.py`.

**Files:** `phase6/core/exchange_fill_reconciler.py`

## A4. Ghost Registry Close-on-Flat — **DONE**

**Shipped:**
- `_maybe_close_flat_registry` after sell ingest paths (`_ingest_row` + `reconcile_filled_stops`).
- Calls existing `close_open_stops_for_flat_pair` when holdings appear flat (or unknown after verified sell).
- Isolation covered in fill-recon P0 closeout test.

**Files:** `phase6/core/exchange_fill_reconciler.py`, `phase6/core/protective_orders_registry.py`

---

## Verify

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_naked_bag_p0.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_fill_recon_p0_closeout.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_sl_floor_ratchet.py
```

## Live notes

- **No live knobs changed.** Fail-closed market sell only fires on **fresh_buy** attach failure paths.
- Runner restart not required for fill-recon paths picked up on next cycle import; SL manager change needs process reload to take effect.
- A2 full episode identity stays queued — not a same-day multi-file rewrite.
