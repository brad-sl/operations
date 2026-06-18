# Handoff: Runner Fact Persistence to DB (Phase 6 Dashboard SQL)

**Task ID**: DASH-SQL-RUNNER-002
**Priority**: P0 (after schema handoff)
**Owner**: crypto-engineer
**Related**: Parallel to RSI/Sentiment (refresh scripts will also write to these tables). Depends on DASH-SQL-SCHEMA-001.
**Date**: 2026-06-12

## Objective (one sentence)
Add a `persist_facts_to_db()` method (or equivalent) in Phase6Runner that writes the *raw facts* (balances, holdings from LPM, prices from price_history, rsi_values, sentiment if available) to the new phase6 DB tables after the schema is live; keep the existing JSON cache write for transition (dual-write); call it from `_write_dashboard_cache` and relevant refresh paths.

## Scope & Boundaries
**Must Do**:
- After schema handoff complete, implement persistence using sqlite3 (simple, consistent with other project scripts).
- Insert into account_balances, holdings, prices, rsi_values, sentiment_scores (use current timestamps or ISO).
- Use real data from self.exchange, self.portfolio, self.price_history, self.rsi_values.
- Add a config or flag for DB path (default data/phase6.db).
- Update _write_dashboard_cache to call persist after building snapshot (or before).
- Wire to existing RSI refresh path if possible (from RSI plan scripts/refresh_rsi_prices.py).
- Create/update Code Isolation Test `phase6/core/test_isolation_runner_db_persist.py` that:
  - Mocks or uses real (via manual wrapper) holdings/prices.
  - Calls persist.
  - Asserts DB rows exist with correct values (compare to previous verified numbers).
  - Tests idempotency / latest wins.
- Keep JSON write unchanged for now (dual source during cutover).
- Update runner logs to mention DB persist success.

**Must Not Do**:
- Remove JSON cache yet.
- Move enrichment math into runner persistence (that's in the VIEWS from schema handoff).
- Change serve_dashboard.py (next handoff).
- Touch production without isolation test passing first.
- Assume full sentiment data if not present in runner context.

## Success Criteria (measurable)
- Isolation test passes: after persist, `sqlite3 ... "SELECT * FROM v_enriched_positions;"` (or direct table query) matches the numbers from manual wrapper test (ETH 0.0857 value ~142.89, etc.).
- Runner cycle completes without error; log shows "DB facts persisted".
- No regression in existing live_state.json output.
- Data in DB is real (no 0s for actual holdings from screenshot).

## Deliverables
- Updated `phase6/core/phase6_runner.py` with persistence logic + call site.
- `phase6/core/test_isolation_runner_db_persist.py` (standalone, passes, uses real data comparison).
- Any small helper in phase6/core/ (e.g. db_utils.py if it grows).
- Log evidence + test output appended to MASTER.
- Handoff sign-off.

## Validation Method
- Run the new isolation test.
- Manually trigger a runner cycle (or use the verify script from prior diagnostics) and query the DB views/tables.
- Compare output to the "known good" from `coinbase_wrapper_FIXED` + patched exchange_client (as done in 2026-06-12 diagnostics).
- Confirm dual-write (JSON still correct, DB has facts).
- Orchestrator re-runs key verification before marking complete.

## Context & References
- Main plan: `docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md`
- Schema handoff (prereq): handoffs/phase6/Handoff_Dashboard_SQL_Schema_and_Views.md (tables/views ready).
- Current computation to source facts from: phase6/core/phase6_runner.py _write_dashboard_cache (~807-943), get_account_balance (now total=avail+hold), portfolio.get_enriched_positions, price_history, rsi_values.
- RSI tie-in: scripts/refresh_rsi_prices.py and RSI plan Phase 2 (decoupled refresh will also INSERT to prices/rsi_values).
- Prior: Handoff_Dashboard_Dataflow_Fix.md, user screenshot + manual test results (numbers to match).
- Code Isolation rule: test before/after changes; real data; permanent artifacts in repo.

## Notes for Assignee
- Make persistence cheap (one connection, batch inserts).
- Handle the LPM wrapper normalization in the VIEW (not here) — just write the raw from get_holdings_verified().
- After this, the serve refactor handoff can start querying.
- Coordinate table names with any active RSI/Sentiment work.

**Handoff created per Kanban process + user prefs (tight scope, isolation test mandatory, MASTER durable record, real-data verification).**