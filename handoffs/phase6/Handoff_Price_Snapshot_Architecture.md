# Handoff: Price Snapshot Architecture (PRICE-001)

**Date**: 2026-06-04
**Priority**: Critical — Foundational
**Status**: Design locked, implementation pending
**Related Task**: PRICE-001 in `docs/MASTER_TASK_TRACKING.md`

## Problem
The dashboard and all downstream systems (rebalancing, stop-loss, PnL) are showing incorrect portfolio values because `get_enriched_positions()` uses hardcoded fallback prices in live mode:

- Dashboard shows: **$964.34 total / $714.75 holdings**
- Real Coinbase values: **$840.39 total / $590.80 holdings**

Root cause: `exchange_client.py:get_price()` in live mode returns static 2025-era fallbacks instead of real market data, and `get_enriched_positions()` calls it directly.

## Architectural Rule (Locked In)
**Prices used for valuation, total portfolio, holdings value, unrealized PnL, trade records, and performance metrics must come exclusively from the most recent prices captured by the runner during its last cycle (the "world snapshot").**

- Never make a fresh Coinbase price call inside `get_enriched_positions()`, dashboard cache writer, or any valuation path.
- This guarantees exact arithmetic consistency across all numbers.
- The runner is the single source of truth for the "state of the world" at decision time.

## Why This Matters
This is foundational for the entire trading system. Getting pricing consistency right now prevents:
- Drift between "price at enrichment" vs "price used for signals/rebalancing"
- Inconsistent PnL and performance reporting
- Audit/reconciliation nightmares later
- Subtle bugs in capital deployment and risk logic

## Current State
- Runner already has `PriceHistoryManager` + `get_recent_prices()` (public endpoint) that seeds and updates every cycle.
- `_write_dashboard_cache()` in `phase6_runner.py` writes positions but currently pulls prices via the broken `get_price()` path.
- `get_enriched_positions()` lives in `exchange_client.py` and is the canonical enrichment method.
- Dashboard reads exclusively from `data/state/phase6_live_state.json` (cache-first).

## Correct Implementation Approach
1. At the end of every runner cycle, persist the **latest known prices** for held assets into the dashboard cache (alongside positions).
2. Modify the enrichment logic inside the runner (or make `get_enriched_positions()` accept a price snapshot parameter) so it sources prices from the stored runner snapshot.
3. Keep `get_price()` as a fallback only for non-runner contexts or when history is empty for an asset.
4. After the change, a clean restart must show:
   - Dashboard total = **$840.39**
   - Holdings = **$590.80**
   - All downstream numbers (balances, PnL, etc.) add exactly with no drift.

## Files to Touch
- `phase6/core/phase6_runner.py` — `_write_dashboard_cache()` and cycle-end logic
- `phase6/core/exchange_client.py` — `get_enriched_positions()` and possibly `get_price()` fallback behavior
- `docs/MASTER_TASK_TRACKING.md` — register/update PRICE-001

## Validation Checklist
- [ ] Runner writes prices from its own snapshot into `phase6_live_state.json`
- [ ] Dashboard shows exact Coinbase totals after restart
- [ ] No price-related drift in totals, PnL, or trade records over multiple cycles
- [ ] Rebalancing and stop-loss logic continue to work with the new price source

## Notes for Future Agents
This rule applies to **all** valuation paths going forward. If any module needs a "current price," it must come through the runner's snapshot mechanism. Fresh API calls for pricing are only acceptable for signal generation (RSI, etc.) inside the runner itself, never for post-hoc enrichment.

**Do not relax this rule** — it is a core invariant for system integrity.