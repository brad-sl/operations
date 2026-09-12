# Platform reliability: Settlement / Naked Bag / Episode ID (P0)

**Date:** 2026-09-10  
**Owner:** Grok  
**Audience:** Hermes agents, Implementers  
**Status:** **A1/A2/A3/A4 shipped (code+isolation)**  
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

## A2. Episode Identity — **DONE (full)**

**Design (short grill, 2026-09-11):**
- Canonical `bag_id = {PAIR}:{buy_order_id}` via `phase6/core/episode_identity.py`.
- Missing bag_id stays valid (legacy rows) → fall back to entry/fresh_buy heuristics.
- When **both** sides know bag_id and they **differ** → hard reject prior-bag stop/peak.
- No live-state key rewrite; peak_lot gains optional `bag_id` field on pair key.

**Shipped:**
- `episode_identity.py` helpers (`make_bag_id`, `coerce_bag_id`, `bag_ids_conflict`, `stamp_bag_id_on_trade`).
- Ledger BUY rows stamp `bag_id` + `buy_order_id`; SELL rows resolve from protective registry or last BUY.
- `TradeLedger.log_trade` stamps bag_id defense-in-depth.
- Ratchet `usable_existing_stop_for_ratchet` / `apply_ratchet_to_stop_bundle` gate on bag_id mismatch.
- `stop_loss_manager` passes registry/current bag_id; continuous_bag requires no bag conflict.
- `peak_lot` binds `bag_id`; `sanitize_peak_r_for_lots` resets on `bag_id_changed` even when entry_px identical (UNI-class).
- `PositionMark.bag_id` + registry open-row resolve.
- Isolation: `scripts/phase6/test_isolation_episode_identity_a2.py` (5/5 PASS).

**Files:** `episode_identity.py`, `trade_ledger.py`, `exchange_fill_reconciler.py`, `sl_floor_ratchet.py`, `stop_loss_manager.py`, `protective_orders_registry.py`, `shadow_tp.py`

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
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_episode_identity_a2.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_naked_bag_p0.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_fill_recon_p0_closeout.py
PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_sl_floor_ratchet.py
bash scripts/hermes/pre_ship_quality.sh
```

## Live notes

- **No live knobs changed.** Fail-closed market sell only fires on **fresh_buy** attach failure paths.
- Runner restart picks up SL manager + peak/ratchet bag_id gates.
- A2 full shipped under `PC-01-EPISODE-IDENTITY-A2-20260911` / PLATFORM-COMPLETENESS.
