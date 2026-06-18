# Handoff: Dashboard SQL E2E Verification, Isolation Suite, Cutover & Ops Integration (Phase 6)

**Task ID**: DASH-SQL-E2E-004
**Priority**: High (final gate)
**Owner**: crypto-orchestrator / crypto-engineer + ops review
**Related**: Final step after schema/runner/serve handoffs. Ties everything to RSI/Sentiment queues.
**Date**: 2026-06-12

## Objective (one sentence)
Complete Code Isolation Test suite for the full path (DB facts → SQL views → serve APIs), E2E run with real data, dual-write stability, cutover (deprecate complex JSON enrichment), update all docs/MASTER/ops, and get sign-off so dashboard sources are reliably in SQL.

## Scope & Boundaries
**Must Do**:
- Expand/combine isolation tests from prior handoffs into a full suite (runner persist + views + serve queries + end-to-end numbers match).
- Run full E2E: start refresh (if RSI scripts), runner cycle (live or paper with real holdings), query serve APIs, assert dashboard state matches user screenshot + prior manual wrapper (USD 613.72, ETH 0.0857 value 142.89, XRP 18.637 value 21.08, total ~777.68, clean positions list, no bogus keys).
- Verify dual-write period (JSON + DB) for at least one full cycle + monitor.
- Cutover: make DB the primary in serve; keep JSON as thin fallback only; update runner comment to "facts to DB; enrichment in views".
- Update `docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md`, MASTER_TASK_TRACKING.md, RSI plan (note shared tables), any runbooks.
- Ops: Add to ops-engineer checks (query DB freshness?); create trouble ticket if needed; update cron/monitor if new scripts.
- Performance/smoke: confirm no slowdown in runner cycle or dashboard load.
- Sign-off: orchestrator re-runs key verification steps (like prior 2026-06-12 balance diagnostics); log in MASTER.

**Must Not Do**:
- Skip isolation tests.
- Cutover without passing E2E + real data match.
- Leave dangling JSON logic that recomputes values.

## Success Criteria (measurable)
- Full test suite passes with real data.
- `curl localhost:8502/api/positions` (after runner) returns correct real holdings from DB views.
- Dashboard HTML (refreshed) shows correct total ~$777+ and 2 real positions (ETH/XRP) instead of 4 bogus.
- MASTER updated with completion + links to tests/artifacts.
- No regression in RSI/Sentiment flows (they can now write to same tables).
- Ops verification command or script updated.

## Deliverables
- Combined test file(s) in phase6/core/ (e.g. test_isolation_dashboard_sql_full.py).
- E2E run log / output in reports/ or attached to MASTER.
- Updated serve/runner with cutover comments.
- All docs/MASTER/ops artifacts.
- Handoff sign-off + kanban complete.

## Validation Method
- Orchestrator executes the E2E steps using tools (manual wrapper for ground truth, DB queries, serve API calls, previous diagnostic scripts).
- Compare side-by-side to user-provided screenshot and 2026-06-12 verified numbers.
- Confirm in MASTER under "Dashboard SQL View Refactor" + RSI section.
- Run ops-engineer style check if available.

## Context & References
- Overarching plan: `docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md`
- Prereq handoffs: the schema, runner, serve ones.
- RSI/Sentiment: docs/RSI_SENTIMENT_RELIABILITY_PLAN.md (integrate data writes; shared benefit).
- Current problems fixed: bogus positions in cache (from earlier read of phase6_live_state.json), logic in _write_dashboard_cache and fetch_*.
- User request: "SQL View component, correct values populated in the view and just surfaced in the dashboard. Remove most the logic from the dashboard and keep the logic in SQL" + queue with RSI tasks.
- Code Isolation + real data + MASTER durable + tight handoffs (all enforced).

## Notes for Assignee
- This is the integration + sign-off lane. Use previous verify scripts + manual wrapper as ground truth.
- After complete, the dashboard is thin over SQL, aligned with signal pipelines.
- Create any final kanban card for review if needed.

**Standard Kanban handoff: explicit success via real verification, no shortcuts on tests, permanent docs in MASTER.**