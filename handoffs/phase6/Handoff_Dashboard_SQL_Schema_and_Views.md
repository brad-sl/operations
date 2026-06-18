# Handoff: Dashboard SQL Schema, Migration Script + Core VIEWs (Phase 6)

**Task ID**: DASH-SQL-SCHEMA-001
**Priority**: P0 (foundational for the refactor; blocks runner + serve work)
**Owner**: crypto-engineer (or sub-agent)
**Related**: Parallel to RSI/Sentiment Refactor (docs/RSI_SENTIMENT_RELIABILITY_PLAN.md). See master plan `docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md`.
**Date**: 2026-06-12
**Status**: Ready for delegation (design in plan doc; implement + test)

## Objective (one sentence)
Implement the designed SQLite schema (fact tables for holdings/prices/balances/rsi/sentiment + the key SQL VIEWs `v_enriched_positions` and `v_phase6_dashboard`) plus a migration script, using the existing `db/` models as reference where possible, so that dashboard enrichment logic can move to SQL.

## Scope & Boundaries
**Must Do**:
- Create / use `data/phase6.db` (or target `phase6_monitor.db` after review).
- Implement the exact base tables from the plan (account_balances, holdings, prices, rsi_values, sentiment_scores, optional trades).
- Implement the VIEWS: v_latest_*, v_current_holdings, v_enriched_positions (core amount*price math in SQL), v_phase6_dashboard (or equivalent that produces positions list shape).
- Provide a simple migration script (`scripts/phase6/migrate_dashboard_db.py` or in db/migrations) that creates tables + views idempotently.
- Extend or reference `db/models.py` (add comments or stub models for future SQLAlchemy).
- Write a Code Isolation Test `phase6/core/test_isolation_dashboard_sql_schema.py` that:
  - Creates DB in /tmp.
  - Inserts sample real-like data (from previous manual wrapper test: USD 613.72, ETH 0.0857, XRP 18.637, prices).
  - Asserts VIEW queries return correct enriched values and totals matching screenshot numbers.
  - Verifies no fabrication (zero holdings case returns empty or proper sentinel).
- Update README or inline docs in the script.
- Commit to repo; permanent artifact in data/ or scripts/.

**Must Not Do**:
- Change runner or serve_dashboard.py yet (separate handoff).
- Touch production data/state JSON without dual-write plan.
- Use heavy ORM in runtime code (keep sqlite3 simple for inserts).
- Assume full JSON1 for complex nesting if it complicates; provide row-based views + note for Python assembly.

## Success Criteria (measurable)
- `python -c "import sqlite3; conn=sqlite3.connect('data/phase6.db'); print(conn.execute('SELECT name FROM sqlite_master WHERE type=\"view\";').fetchall())"` shows the views.
- Isolation test passes with real numbers: total_usd ~777.68, ETH value ~142.89, XRP ~21.08 (matches prior verified live client + user screenshot).
- Zero-amount case produces clean empty positions (no bogus "positions-USD" rows).
- Migration script is idempotent and documented.
- Schema aligns with RSI plan tables (prices, rsi_values, sentiment_scores names match for sharing).

## Deliverables
- `data/phase6.db` (or chosen target) with tables + views created.
- `scripts/phase6/migrate_dashboard_db.py` (or equivalent) + usage in plan.
- `phase6/core/test_isolation_dashboard_sql_schema.py` (standalone, runnable, passes with real data).
- Updated `docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md` with any schema tweaks.
- Entry in MASTER_TASK_TRACKING.md (orchestrator will do).
- Handoff sign-off comment when complete.

## Validation Method
- Run the isolation test yourself (or via tool) and confirm output matches previous manual test wrapper numbers (USD 613.72 + ETH 0.08572777 + XRP 18.637483).
- `sqlite3 data/phase6.db "SELECT * FROM v_enriched_positions;"` shows correct rows.
- Compare to current patched `get_enriched_positions()` output.
- No changes to runner/serve until this is verified.
- Log results + test output to MASTER under this handoff.

## Context & References
- Full design + table DDL: `docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md` (Schema section).
- Current logic to replace: phase6/core/phase6_runner.py lines ~807-905 (_write... enrichment, price_snapshot, pos_map loop, total_usd calc).
- Prior dashboard handoffs: handoffs/phase6/Handoff_Dashboard_Dataflow_Fix.md, Handoff_Dashboard_Data_Quality.md.
- RSI alignment: docs/RSI_SENTIMENT_RELIABILITY_PLAN.md (use same table names for prices/rsi/sentiment).
- Existing DB foundation: db/models.py (Price, Trade etc.), phase6_monitor.db (review if to reuse).
- Code Isolation Testing rule (user pref): standalone test first, real data, compare to manual wrapper.

## Notes for Assignee
- Use the previous diagnostic `/tmp/verify_balances.py` or coinbase_wrapper_FIXED as source of "known good" numbers for test data.
- Keep it lightweight — runner will INSERT facts; views do the math.
- If using JSON1 for positions_json in v_phase6_dashboard, note SQLite version requirements.
- After this, next handoff (runner persistence) can wire the writes.

**Handoff created by orchestrator per user Kanban prefs (tight contracts, isolation tests, MASTER as durable record). Ready for kanban_create + delegation.**