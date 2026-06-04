# Phase 6 Master Task Tracking List

**Primary Durable Record** (per user preference — Kanban has been unreliable/corrupt in the past)

**Last Updated:** 2026-06-01
**Source of Truth:** This file + individual handoff documents in `handoffs/phase6/`

## Active Tasks (Max 2-3 at a time)


### Dashboard Data Completeness Plan (High Priority)

**Overall Goal**: Make the Phase 6 dashboard show real, complete, live data from actual account holdings + trading activity, with honest empty states where data does not yet exist.

**Reference Document**: `handoffs/phase6/Handoff_Dashboard_Dataflow_Fix.md`
**Note (2026-06-03)**: All four tasks (D-01 to D-04) have been marked complete on the Kanban board by the assigned agents. Awaiting final inspection and validation from the user (dashboard not reachable at time of update). Once verified, mark plan as complete and archive.



---

#### Task D-01: Make Runner Cache the Complete Single Source of Truth
- **Owner**: Sub-agent
- **Status**: Ready
- **Description**: Expand `_write_dashboard_cache()` + `get_enriched_positions()` so the cache contains **all current holdings** (not just bot-originated positions), with full fields: amount, current_price, value_usd, entry_price (if known), unrealized_pnl_pct, side.
- **Validation**:
  1. Restart runner
  2. `curl http://localhost:8503/api/positions` returns real holdings matching Coinbase app
  3. `total_holdings_value` + `cash_usd` are correct
- **Success Criteria**: Dashboard shows actual portfolio value (~$863) instead of $0 or partial data.

#### Task D-02: Fix All Dashboard API Endpoints
- **Owner**: Sub-agent
- **Status**: Ready
- **Description**: Update `/api/trades`, `/api/performance`, and `/api/sentiment` to return real data from TradeLedger + sentiment cache files (or honest "no data yet" states).
- **Validation**:
  - `curl http://localhost:8503/api/trades` → real trades or empty list
  - `curl http://localhost:8503/api/performance` → real win ratio or "no closed trades"
  - `curl http://localhost:8503/api/sentiment` → real sentiment or fallback message
- **Success Criteria**: No hardcoded or dummy values in any endpoint response.

#### Task D-03: Frontend Rendering Updates
- **Owner**: Sub-agent
- **Status**: Ready
- **Description**: Update `phase6_dashboard.html` so all sections (Positions table, Performance KPIs, Recent Trades, Sentiment) correctly render data from the APIs. Remove any remaining hardcoded values.
- **Validation**:
  - Hard refresh of dashboard
  - All sections show either real data or clear "no data" messaging
  - Total value matches actual portfolio
- **Success Criteria**: Dashboard is visually accurate and trustworthy.

#### Task D-04: End-to-End Validation & Stability
- **Owner**: Sub-agent
- **Status**: Ready
- **Description**: Run full verification cycle (runner + dashboard) and document that the system remains stable over multiple cycles with no regressions.
- **Validation**:
  - Runner runs for 3+ cycles without errors
  - Dashboard reflects correct data after each cycle
  - Update `MASTER_TASK_TRACKING.md` with completion
- **Success Criteria**: System is stable and data is reliable.



### Capital Deployment Integration (High Priority) — NEW
- **Handoff:** `handoffs/phase6/Handoff_Capital_Deployment_Integration.md`
- **Goal**: Integrate the `deploy_capital()` module into the Phase 6 runner and rebalancing logic so that freed capital (from liquidations, deposits, or reserve) is automatically and intelligently redeployed according to the rules defined in `CAPITAL_DEPLOYMENT.md`.
- **Status**: Ready
- **Owner**: Sub-agent
- **Created**: 2026-06-03
- **Key Requirements**:
  - Respect existing holdings (no forced renormalization)
  - Stronger sentiment required for new pairs
  - Reserve source only deploys to non-negative sentiment pairs
  - Called from rebalancing and liquidation paths
- **Validation**:
  1. Unit test `deploy_capital()` with various scenarios
  2. Wire into `_rebalance_if_needed` and liquidation handler
  3. Verify via logs that capital is deployed correctly
  4. Update `MASTER_TASK_TRACKING.md` on completion
- **Success Criteria**: Capital is automatically redeployed without manual intervention, following the documented rules.


### 1. Enhance Dashboard Data Cache (High Priority) — Superseded by plan above
- **Handoff:** `handoffs/phase6/Handoff_Dashboard_Dataflow_Fix.md`
- **Goal:** Expand `_write_dashboard_cache()` in the runner so `phase6_live_state.json` contains rich, complete data (enriched positions with value/PnL, recent activity, full holdings breakdown) instead of the current minimal snapshot.
- **Status:** Ready for execution
- **Owner:** Sub-agent / Crypto Engineer
- **Created:** 2026-06-02 (evening)
- **Related Doc:** `handoffs/phase6/Handoff_Dashboard_Dataflow_Fix.md` (full data mapping, target schema, and verification steps)
- **Success Criteria:** Cache includes enriched positions, total holdings value, and activity history. Dashboard can render a complete real-time view.


### 1. Stop-Loss Migration (High Priority)
- **Handoff:** `handoffs/phase6/Handoff_Stop_Loss_Migration.md`
- **Kanban Task:** `t_b546ce3e`
- **Status:** Unblocked after model fix
- **Owner:** crypto-engineer (Kanban)
- **Started:** 2026-06-01
- **Completed:** —
- **Record:** `handoffs/phase6/DELEGATION_Stop_Loss_Migration.md`
- **Subagent Prompt:** `handoffs/phase6/SUBAGENT_PROMPT_Stop_Loss_Migration.md`
- **Fix Applied:** `google/gemini-3.1-flash-lite` on crypto-engineer

### 2. Exchange Client & Order Execution Hardening (High Priority)
- **Handoff:** `handoffs/phase6/Handoff_Exchange_Order_Execution.md`
- **Kanban Task:** `t_f30c67b7`
- **Status:** Unblocked after model fix
- **Owner:** crypto-orchestrator (Kanban)
- **Started:** 2026-06-01
- **Completed:** —
- **Fix Applied:** Added `google/gemini-3.1-flash-lite` (OpenRouter) to crypto-orchestrator config (was trying to use paid Claude Opus with no credits)

### 3. Observability & Alerting Improvements

### 4. Dashboard End-to-End Dataflow Fix (High Priority)
- **Handoff:** `handoffs/phase6/Handoff_Dashboard_Dataflow_Fix.md`
- **Status:** Ready for execution
- **Owner:** Sub-agent
- **Created:** 2026-06-02
- **Goal:** Make every dashboard section use real live trading data or honest empty states
- **Includes:** Data mapping table, dataflow diagram, step-by-step verification with live data testing

- **Handoff:** `handoffs/phase6/Handoff_Observability_Alerting.md`
- **Kanban Task:** `t_ae83a970`
- **Status:** Unblocked after model fix
- **Owner:** crypto-orchestrator (Kanban)
- **Started:** 2026-06-01
- **Completed:** —
- **Fix Applied:** Same as above

## Completed / Archived Tasks
- Handoff_Allocation_Engine_Enhancement.md
- Handoff_Rebalancing_Logic_Upgrade.md
- Handoff_Sentiment_System_Restoration.md
- Handoff_Proportional_vs_NewPair_Backtest.md
- Handoff_Overall_Parity_Audit.md
- Handoff_Signal_Quality_Investigation.md

## Kanban Status
- All three tasks are now in `ready` status with working models.
- Primary tracking remains this file + handoffs.
## Backlog CRs (from xAI Code Review – 2026-06-02)
- **CR-06**: Make CR-03 `suspend_reattach_context` a no-op in shadow mode.
- **CR-07**: Narrower error handling + rate-limit circuit breaker in runner.
- **CR-08**: Add staleness/age validation on sentiment scores from cron.
- **CR-09**: Add explicit early `if not shadow_mode` guard in order_executor/exchange_client.
- **CR-10**: Minor logging duplication cleanup in phase6_runner.py.
- **CR-11**: Add unit tests for shadow → live transition and $1000 capital edge cases.

**Last Updated:** 2026-06-02 (post TradeLedger fix + reserve guard + code review)

## Future / Deferred Features (Post-Live)

### Intelligent Re-Deploy (Reserve Opportunity Engine)
**Status:** Deferred until after limited live trading is stable  
**Priority:** High (once live)  
**Owner:** TBD  
**Description:** Event-driven logic that intelligently deploys reserve cash on high-conviction opportunities instead of keeping it idle. Rebalancer runs 2× per hour but only acts on strong signals.

**Ranked ROI Methods (do not lose):**
1. **Sentiment + Momentum Breakout** — Top-quartile sentiment + price breaking recent high with volume.
2. **Sentiment Divergence + Mean Reversion Setup** — Strong sentiment but price still 8–15% below range high.
3. **Volatility Contraction + Sentiment Spike** — ATR collapse + sudden sentiment jump (coiled spring).
4. **Cross-Pair Relative Strength** — One pair materially outperforming the universe on sentiment + price.
5. **Funding Rate / Basis Extreme** — Extreme positive funding/basis on already high-sentiment pair (requires extra data).

**Implementation Notes:**
- Should live in `phase6/core/rebalancing/hybrid_rebalancer.py` or enhanced allocation_engine.
- Temporarily increase deploy_pct or explicitly pull from min_reserve_usd when opportunity score is very high.
- Must respect proportional scaling and never breach hard withdrawal reserve floor.

**Dependencies:** Hybrid rebalancer (Handoff_Rebalancing_Logic_Upgrade.md), stable live trading data.


### Performance Dashboard (Multi-Period P&L)
**Handoff:** `handoffs/phase6/Handoff_Performance_Dashboard.md`  
**Status:** Deferred (Post-Live)  
**Scalability:** Designed for 1,000+ users  
**Description:** Current balances + P&L over 1d / 7d / 30d / 90d / 365d windows. Must use efficient queries and caching.



### Task DASH-005: Improve Active Positions Table + Cash Visibility
- **Status**: Ready
- **Description**: 
  - Redesign Active Positions table to show: Pair, Qty, Current Price, Value (USD), PnL %
  - Show USD and USDC as separate "Cash" rows at the top of the positions table
  - Ensure Total Portfolio Value = Cash + Holdings
- **Owner**: User request
- **Created**: 2026-06-03

---

#### Task RSI-001: Restore RSI Primary Signal Pipeline

- **Owner**: TBD
- **Status**: Ready (Handoff created)
- **Handoff Document**: `handoffs/phase6/Handoff_RSI_Pipeline_Restoration.md`
- **Description**: Restore RSI as the primary signal driver (per Phase 6.01 architecture in TRADING_BOT_DOCS.md). Create PriceHistoryManager, integrate `src/indicators/rsi.py`, use sentiment as conviction multiplier instead of hard AND gate. Expose RSI values to live state and Trading Intelligence Report.
- **References**:
  - `docs/TRADING_BOT_DOCS.md` (Phase 6.01 cycle steps 1–5)
  - `phase5_multi_pair.py` (_calculate_rsi, _determine_trade_signal)
  - `src/indicators/rsi.py` (preferred implementation)
- **Success Criteria**:
  1. Fresh RSI values appear in Trading Intelligence Report
  2. `phase6_live_state.json` contains `rsi` field
  3. Signals generated primarily from RSI with sentiment as multiplier
  4. Price history persists across restarts

