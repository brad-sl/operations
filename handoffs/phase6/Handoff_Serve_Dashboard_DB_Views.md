# Handoff: Serve Dashboard Layer — Source from SQL Views (Phase 6)

**Task ID**: DASH-SQL-SERVE-003
**Priority**: High (after runner persistence)
**Owner**: crypto-engineer
**Related**: Depends on schema + runner handoffs. Parallel benefit to RSI/Sentiment (dashboards/reports can consume same views).
**Date**: 2026-06-12

## Objective (one sentence)
Refactor `serve_dashboard.py` (and minimal HTML/JS if needed) to source balances, positions, totals, and enriched data primarily from the new DB VIEWS (`v_enriched_positions`, `v_phase6_dashboard` etc.) instead of (or in addition to) the JSON cache; keep the enrichment/PnL math out of Python; produce the same API shapes for the frontend.

## Scope & Boundaries
**Must Do**:
- Add sqlite3 queries in fetch_balances(), fetch_live_positions(), and related (e.g. for totals).
- Query v_latest_balances / v_enriched_positions / v_phase6_dashboard (or equivalent) for the data.
- Assemble the response dicts from the query results (light Python, no amount*price or pos_map loop logic).
- Support dual source: prefer DB if available and fresh (check ts), fall back to load_live_state() JSON.
- Update /api/balances, /api/positions, and any that use totals/positions.
- For sections still on other sources (trades from TradeLedger, sentiment, rebalances, recovery), leave as-is or note future DB table.
- Add simple freshness check (compare DB ts to now).
- Create/update isolation test `phase6/core/test_isolation_serve_dashboard_db.py` that mocks DB or uses real populated DB and asserts API responses match expected real data shape + numbers.
- Minimal change to phase6_dashboard.html (only if field names change; aim for zero).
- Log source ("Live (DB view)" vs "Live (cached JSON)").

**Must Not Do**:
- Re-implement enrichment logic here.
- Break existing JSON fallback or paper mode.
- Change runner.
- Major frontend rewrite (keep presentational).

## Success Criteria (measurable)
- After DB populated by runner, curl /api/positions returns real ETH-USD / XRP-USD with correct amounts/values from screenshot (~0.0857 / 18.637, values 142+/21+).
- Total in /api/balances matches ~777.68.
- No more "positions-USD" / "verified-USD" bogus rows in responses.
- Test passes comparing to previous verified manual wrapper + live client output.
- Frontend continues to render correctly (or with trivial update).

## Deliverables
- Updated `serve_dashboard.py` with DB query paths + dual fallback.
- Isolation test for the serve layer.
- Any small utils if extracted.
- Updated plan doc if API shape tweaks needed.
- Evidence in MASTER (test output, before/after API samples).

## Validation Method
- Populate DB via prior handoff steps + runner cycle.
- Call the APIs directly (or via the verify script).
- Assert exact match to real account numbers from user screenshot + 2026-06-12 diagnostics.
- Load the dashboard HTML and confirm no regressions in display (positions table, totals).
- Orchestrator verification using real tool output.

## Context & References
- Plan: `docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md`
- Prereqs: Schema handoff + runner persistence handoffs.
- Current buggy state (for reference): data/state/phase6_live_state.json (the one with positions-USD etc.), serve_dashboard.py fetch_live_positions + load_live_state.
- Goal alignment: Remove most logic from dashboard (per user query); keep in SQL views.
- RSI/Sentiment: Once their data is in DB tables, this layer can pull fresh rsi/sentiment too.
- Prior handoffs: Handoff_Dashboard_Dataflow_Fix.md, Handoff_Dashboard_Data_Quality.md (the problems this solves).

## Notes for Assignee
- Query the views directly for positions (they already have the computed value_usd).
- Keep response shapes identical to current JSON cache for zero frontend change.
- After this, full E2E + cutover handoff.

**Handoff per standard process: tight boundaries, isolation test, real data match to prior verified state, MASTER record.**