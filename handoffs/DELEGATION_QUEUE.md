# Phase 6 Delegation Queue

**Date:** 2026-06-12 (updated)
**Status:** Active — new SQL Dashboard track added parallel to RSI/Sentiment

## Active Delegations

### 1. Stop-Loss Migration (High Priority)
**Handoff:** `handoffs/phase6/Handoff_Stop_Loss_Migration.md`
**Goal:** Migrate stop-loss logic from `src/` into `phase6/core/`
**Assigned to:** [Pending]
**Status:** Not started

### 2. Exchange Client & Order Execution Hardening (High Priority)
**Handoff:** `handoffs/phase6/Handoff_Exchange_Order_Execution.md`
**Goal:** Stabilize order execution in live mode
**Assigned to:** [Pending]
**Status:** Not started

### 3. RSI + Sentiment Freshness & Scalability (High Priority — per RSI_SENTIMENT_RELIABILITY_PLAN.md)
**Handoffs:** Multiple (see docs/RSI_SENTIMENT_RELIABILITY_PLAN.md + handoffs/phase6/Handoff_Canonical_Sentiment_Refresh_Cron.md etc.)
**Goal:** Canonical pipelines, 30min/15min crons, freshness, isolation tests, provider
**Assigned to:** crypto-engineer + analyst profiles (parallel)
**Status:** In progress (Phases 0-1 mostly done; crons + Phase 2 pending)

### 4. Dashboard SQL View + DB Persistence Refactor (New — Parallel to RSI/Sentiment)
**Handoffs:** 
- `handoffs/phase6/Handoff_Dashboard_SQL_Schema_and_Views.md` (DASH-SQL-SCHEMA-001 — P0, schema + migration + isolation test first)
- `handoffs/phase6/Handoff_Runner_DB_Fact_Persistence.md` (DASH-SQL-RUNNER-002)
- `handoffs/phase6/Handoff_Serve_Dashboard_DB_Views.md` (DASH-SQL-SERVE-003)
- `handoffs/phase6/Handoff_Dashboard_SQL_E2E_Tests_Cutover.md` (DASH-SQL-E2E-004)
**Goal:** Move dashboard enrichment (positions, values, totals) to SQL facts + VIEWs. Runner persists raw (balances, holdings, prices, rsi, sentiment). Serve is thin query layer. Aligns with RSI plan for shared tables. Full isolation tests + real data match to screenshot/manual wrapper.
**Assigned to:** crypto-engineer (schema first, then sequential deps). Orchestrator for E2E/sign-off.
**Status:** Design + Handoffs complete. Ready for delegation/kanban_create. See docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md for full schema, breakdown, and queueing with RSI tasks.
**Success Criteria:** Views produce correct real numbers (ETH 0.0857 value ~142.89, XRP 18.637 ~21.08, total ~777 from user screenshot); no more bogus positions in dashboard; isolation tests pass; dual-write stable then cutover.

## Completed Handoffs (Reference)
- Handoff_Allocation_Engine_Enhancement.md
- Handoff_Rebalancing_Logic_Upgrade.md
- Handoff_Sentiment_System_Restoration.md
- Handoff_Proportional_vs_NewPair_Backtest.md
- Handoff_Overall_Parity_Audit.md
- Handoff_Signal_Quality_Investigation.md
- Handoff_Dashboard_Dataflow_Fix.md
- Handoff_Dashboard_Data_Quality.md
- ... (see MASTER for full history)

## Kanban / Delegation Notes
- Primary durable record: docs/MASTER_TASK_TRACKING.md (updated with new SQL track).
- All new work uses tight handoff template + Code Isolation Testing + real data verification (compare to manual wrapper + live client + screenshots).
- New SQL track is explicitly parallel to RSI/Sentiment for shared price/rsi/sentiment tables and decoupled pipelines.
- Use kanban_create (or equivalent) to fan out to profiles (crypto-engineer for impl, orchestrator for review/sign-off).
- After schema, runner persistence can proceed (dependent); serve after that; E2E last.

## Next Step
1. Delegate DASH-SQL-SCHEMA-001 (schema + test) via kanban or direct.
2. Once complete, chain to runner + serve handoffs.
3. Full E2E + cutover as final gate.
4. Update MASTER on progress.

Run `delegate_task` or kanban tools with the handoff paths for execution. Master list takes precedence for tracking.