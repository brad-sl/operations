# Phase 6 Dashboard Data Spec — Source → Computation → Destination Mapping

**Version:** 2026-06-28 (post user directive: fix underlying data first)
**Purpose:** Single source of truth for what data feeds dashboard. All P&L, performance, positions, etc. must be *computed and surfaced* in reliable stores (live_state.json + DB fact tables/views) before any dashboard wiring. Dashboard is thin consumer.
**Principle:** Source data (fills, trades, prices, holdings) → explicit computation (runner/ledger/DB views) → canonical fields in live_state + DB views → APIs → HTML. No hardcodes, no fallbacks that lose real data.

## Core Data Domains & Required Fields for "Zero Values" Resolution

### 1. Positions & Unrealized PnL (Active Positions table zeros)
- **Required fields per position:** pair, amount, entry_price (real fill/cost basis), current_price, value_usd, unrealized_pnl_pct, side
- **Source data:**
  - TradeLedger (BUY records with actual fill `entry_price` + `qty` from order fills)
  - OrderExecutor / exchange fills (average_filled_price)
  - LivePortfolioManager / exchange.get_enriched_positions (amounts + prices)
  - Runner price_snapshot (current_price)
- **Computation:**
  - Weighted avg entry from TradeLedger buys (see runner._calculate_average_entry_prices)
  - pnl_pct = ((current_price - entry_price) / entry_price) if entry > 0 else 0
  - value_usd = amount * current_price
- **Destinations (must surface here):**
  - live_state.json: `positions[]` array (with entry_price, unrealized_pnl_pct)
  - DB: holdings (amounts) + prices (current) + new/ extended for entries; v_enriched_positions (compute pnl_pct)
  - /api/positions, /api/balances (via fetch_live_positions / fetch_from_db)
  - HTML: #positions-table (Asset, Size, Value, PnL columns)

### 2. Portfolio Performance & Period PnL (KPI cards: Today/24h/7d/30d + Win Ratio = 0)
- **Required fields:** today, h24, d7, d30 (realized + Δunrealized), win_ratio, total_trades, daily_pnl_est
- **Source data:**
  - TradeLedger (closed trades with `pnl`, `pnl_pct`, timestamps; buys for entries)
  - live_state performance_metrics (partial)
  - Runner cycle snapshots (holdings value changes over time via prices)
- **Computation:**
  - From closed trades: realized PnL bucketed by time windows (today = trades since midnight, etc.)
  - Unrealized delta: current total_holdings_value - prior cycle or day-start
  - win_ratio = (positive pnl trades) / (trades with pnl)
- **Destinations:**
  - live_state.json: `performance_metrics` {daily_pnl_est, win_rate, ...}
  - DB: trades table (with pnl/ts) + new performance_metrics or v_phase6_performance view
  - /api/performance (must compute or pull real values, not hardcode 0)
  - HTML: #pnl-today etc. cards + win-ratio

### 3. Trades / Activity (Recent Trades, Buy/Sell indicators)
- **Source:** TradeLedger (full records on every BUY/SELL/SL)
- **Computation:** Recent buys/sells lists; indicators from side
- **Destinations:**
  - live_state: bought_indicators, sold_indicators
  - /api/trades
  - HTML: activity, trades-list

### 4. Sentiment & RSI (0.00 values)
- **Source:** sentiment_scores table / rsi_values (from refreshers + runner)
- **Destinations:** /api/sentiment, /api/rsi, live_state.rsi, HTML grids

### 5. Other (Recovery, Rebalances, Balances)
- Balances: account_balances table + live_state
- Rebalances: rebalance_history
- Etc.

## Full Source → Destination Mapping (Priority for P&L Zeros)

| Domain / Field                  | Primary Sources (raw)                          | Computation Location                  | Canonical Store(s)                          | API Endpoint          | HTML Consumer                  | Notes / Gaps to Fix |
|--------------------------------|------------------------------------------------|---------------------------------------|---------------------------------------------|-----------------------|--------------------------------|---------------------|
| Position entry_price           | Order fills (executor/exchange get_order_fill_details), TradeLedger BUYs (entry_price + qty) | runner._calculate_average_entry_prices + TradeLedger | live_state.positions[].entry_price<br>DB: trades + (future) current_positions or holdings extension | /api/positions       | positions-table                | Currently often = current_price or 0 in tests. Must log real fills. |
| Position unrealized_pnl_pct    | entry + current_price                          | runner (pnl_pct calc); DB view        | live_state.positions[].unrealized_pnl_pct<br>v_enriched_positions (SQL) | /api/positions       | positions-table PnL %          | Hardcoded 0 in current view. |
| Portfolio period PnL (today etc.) | TradeLedger closed pnls + holdings value deltas over time | runner (or dedicated calc); DB aggregation on trades + prices | live_state.performance_metrics<br>DB: performance_metrics table or view | /api/performance (must not hardcode) | KPI cards (#pnl-*)             | Currently hardcoded 0 in serve. |
| Win Ratio                      | TradeLedger trades with pnl >0                 | runner or serve from ledger           | live_state + DB trades                      | /api/performance     | #win-ratio                     | Depends on closed trades logged with pnl. |
| daily_pnl_est / total_trades   | Recent TradeLedger pnl sums                    | runner._write_dashboard_cache         | live_state.performance_metrics              | (via performance)    | (used in cards)                | Partial today. |
| Bought/Sold indicators         | TradeLedger recent side                        | runner                                  | live_state.bought/sold_indicators           | /api/positions       | activity-indicators            | Shows TEST now. |
| Current prices / values        | price_history / prices table, exchange         | runner price_snapshot + persist         | live_state + v_latest_prices + holdings     | /api/balances        | values in table                | Good. |
| Balances / totals              | account_balances, holdings sums                | persist_facts_to_db + runner            | live_state + v_phase6_dashboard             | /api/balances        | total-balance, table           | Good base. |

## Required Fixes to Surface Data (Data Layer First)

1. **Trade logging completeness (OrderExecutor + runner rebalance/fresh paths):**
   - Always log BUY with real `entry_price` (prefer fill.average_filled_price), `qty`, `side: "BUY"`, influence etc.
   - On exits/SL/TP: log `exit_price`, computed `pnl`, `pnl_pct`.
   - Remove TEST placeholders.

2. **Persist facts to DB (runner.persist_facts_to_db + _write):**
   - Extend to persist recent trades (with entry/exit/pnl) to `trades` table.
   - Add/ populate entry_price in holdings or a new `current_positions` table (ts, pair, amount, entry_price, ...).
   - Call on every cycle.

3. **DB Views (migrate_dashboard_db.py):**
   - Update v_enriched_positions to support entry_price (join to latest trades or dedicated table) and compute:
     `unrealized_pnl_pct = (current_price - entry_price) / entry_price` (handle 0).
   - Add or extend v_phase6_performance or metrics views for period PnL summaries (aggregate trades by time windows + mark-to-market).
   - Re-run migration after changes.

4. **Runner state & calcs:**
   - Ensure _calculate_average_entry_prices always has good data from ledger.
   - Always write full computed positions + performance_metrics to live_state (no fallbacks overwriting real entries).
   - Improve period calcs (e.g. bucket recent_trades by age for today/24h etc.).

5. **If sources insufficient for views:**
   - Add fact table `trade_fills` or extend `holdings` with entry on insert.
   - Runner must write entry alongside amounts in persist.

## Dashboard Consumption (Re-wire AFTER data is surfaced)
- serve_dashboard.py: Prefer DB views for positions/balances/performance. Fall back to live_state only for freshness. Remove all hardcodes (periods=0, pnl=0).
- Use live_state.performance_metrics where available.
- HTML: Already structured for the fields; will light up once data present.
- Mode: live vs paper; always surface "source" for debugging.

## Verification
- After data fixes: `cat data/state/phase6_live_state.json | jq '.positions[] | {pair, entry_price, unrealized_pnl_pct, value_usd}'`
- DB: `sqlite3 data/phase6.db "SELECT pair, entry_price, unrealized_pnl_pct FROM v_enriched_positions;"`
- Dashboard reload should show non-zero where price moved since entry or realized trades exist.
- Performance API returns real numbers.
- No TEST-USD.

## Related
- Handoff_Dashboard_Data_Quality.md, Handoff_Dashboard_Dataflow_Fix.md
- PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md
- scripts/phase6/migrate_dashboard_db.py (DDL)
- phase6/core/phase6_runner.py (_write_dashboard_cache, persist, _calculate_average...)
- phase6/core/trade_ledger.py, order_executor.py

This spec is the contract. All changes must populate these paths. Dashboard re-wiring only after data flows are complete and verified.
