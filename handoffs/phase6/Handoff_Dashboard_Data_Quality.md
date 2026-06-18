# Handoff: Dashboard Data Quality & Rendering

**Date:** 2026-06-04  
**Owner:** crypto-engineer  
**Status:** Ready for execution  
**Related Kanban:** TBD

---

## Goal

Make the Phase 6 dashboard display accurate, real-time data from the live runner’s world snapshot, with correct positions, entry prices, PnL, performance metrics, and proper handling of cash vs holdings.

---

## Background & Current State

The dashboard at port 8503 is currently showing a mix of correct and stale/incorrect data:

- **Total Portfolio Value** ($964.34) matches the runner cache.
- **Positions table** shows old fallback prices ($145 / $0.52 / $3200) and treats USD as a position.
- **Performance metrics** (Today/24h/7d/30d/Win Ratio) are all zero.
- **Sentiment** and **Recent Trades** sections have partial real data.
- The runner is now writing a `price_snapshot` and enriched positions, but the dashboard is not fully consuming this data correctly.

Previous attempts to fix the frontend (`phase6_dashboard.html`) and API layer (`serve_dashboard.py`) have been made, but they have not produced lasting improvements because the underlying data produced by the runner was incomplete or inconsistent.

---

## Files to Examine

| File | Purpose | Current State |
|------|---------|---------------|
| `serve_dashboard.py` | Flask API endpoints (`/api/positions`, `/api/balances`, etc.) | Cache-first, but some endpoints still have legacy logic |
| `phase6_dashboard.html` | Frontend rendering | Shows fallback prices and incorrect side for USD |
| `phase6/core/phase6_runner.py` | `_write_dashboard_cache()` | Now uses `price_snapshot` from `PriceHistoryManager` |
| `phase6/core/exchange_client.py` | `get_enriched_positions()` | Accepts `price_snapshot` parameter |
| `phase6/core/live_portfolio_manager.py` | Caching layer | Forwards `price_snapshot` |
| `data/state/phase6_live_state.json` | Live cache written by runner | Contains `positions`, `balances`, `total_usd`, etc. |

---

## Data Mapping Table (Current vs Expected)

| Dashboard Field | Current Source | Expected Source | Gap |
|-----------------|----------------|------------------|-----|
| Position prices | Old fallback values | `price_snapshot` from runner | Runner is writing snapshot, but dashboard not always using it |
| Entry price | Hardcoded or missing | Real fill price from TradeLedger | Not being populated |
| Unrealized PnL % | Always 0.00% | `(current_price - entry_price) / entry_price` | No entry_price in cache |
| Performance metrics | Not wired | TradeLedger closed trades | Performance calculator not integrated |
| USD row | Shown as "Short" position | Excluded or shown as separate Cash row | Frontend bug + data shape issue |
| Total Portfolio Value | Runner cache | Runner cache | Working |
| Active Positions count | Runner cache | Runner cache | Working |

---

## Data Gaps That Must Be Addressed

1. **Entry Price & PnL**
   - The runner does not currently store `entry_price` or calculate `unrealized_pnl_pct` when writing the cache.
   - Need to either:
     - Pull from TradeLedger on cache write, or
     - Store entry prices when positions are opened.

2. **Performance Metrics**
   - No closed trade data is being surfaced to the dashboard.
   - `TradeLedger` has the data, but `/api/performance` is not consuming it.

3. **USD / Cash Handling**
   - `get_enriched_positions()` returns cash balances separately.
   - Dashboard should show USD/USDC as "Cash" rows, not as positions.

4. **Price Snapshot Consistency**
   - Ensure the runner always writes `current_price` from `price_snapshot` (not from `get_price()` fallback).

---

## Must Do

- Create a clear data contract between the runner’s cache and the dashboard.
- Update `_write_dashboard_cache()` to include `entry_price` and `unrealized_pnl_pct` (even if initially 0 or from TradeLedger).
- Fix `phase6_dashboard.html` to:
  - Exclude USD/USDC from the positions table or render them as Cash.
  - Use real prices from the cache.
- Wire performance metrics from `TradeLedger`.
- Add validation steps that compare dashboard output against known live account state.

---

## Must Not Do

- Do not continue making frontend-only changes without first ensuring the runner produces the required fields.
- Do not assume `get_enriched_positions()` data is sufficient without verifying the snapshot path.

---

## Success Criteria

- Dashboard positions table shows real current prices from the runner’s `price_snapshot`.
- All positions show correct `entry_price` and non-zero `unrealized_pnl_pct` (where applicable).
- USD and USDC appear as Cash rows, not as positions.
- Performance metrics (at minimum Win Ratio and 24h PnL) reflect real closed trades.
- A clean live runner restart results in the dashboard matching the actual Coinbase account within 1–2 cycles.

---

## Validation Steps

1. Restart live runner.
2. Wait for 2 full cycles.
3. Compare:
   - `curl http://localhost:8503/api/positions`
   - Dashboard UI
   - Actual Coinbase app balances
4. Confirm no fallback prices remain in the positions table.
5. Confirm performance section shows real data or clear “no closed trades” state.

---

## References

- `handoffs/phase6/Handoff_Price_Snapshot_Architecture.md`
- `handoffs/phase6/Handoff_Dashboard_Dataflow_Fix.md`
- `docs/MASTER_TASK_TRACKING.md` (PRICE-001, PRICE-002, D-01–D-04)
- `data/state/phase6_live_state.json` (current cache example)

---

**Next Action:** Owner should begin with a full read of the files listed above, then produce an implementation plan or begin fixes.