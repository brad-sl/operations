# Handoff Document: Performance Dashboard (Multi-Period P&L)

**Work Package**: Performance Dashboard  
**Priority**: Medium (Post-Live)  
**Status**: Ready for Implementation  
**Scalability Target**: 1,000+ concurrent users

## Objective

Build a scalable dashboard feature that allows traders to view:
- Current account balances (cash + holdings)
- Realized + unrealized P&L across multiple time windows:
  - 1 day
  - 7 days
  - 1 month
  - 1 quarter
  - 1 year

The solution must be designed for horizontal scaling and support at least 1,000 users without performance degradation.

## Current State

- `TradeLedger` exists and logs trades (JSONL + daily CSV).
- Dashboard (`serve_dashboard.py`) currently shows static/hardcoded positions.
- No time-based P&L calculation exists.
- `CoinbaseExchangeClient` can fetch live balances.

## Must Do

- Create a `PerformanceCalculator` class that can efficiently compute P&L for any time window.
- Add new API endpoints:
  - `GET /api/performance?period=1d|7d|30d|90d|365d`
  - `GET /api/summary` (all periods + current balance)
- Update the frontend to display these metrics cleanly.
- Use efficient data access patterns (avoid full ledger scans on every request).
- Support both single-user and multi-user (per-user isolation).

## Must Not Do

- Do not load the entire trade history into memory for every request.
- Do not perform expensive calculations on the hot path for 1000+ users.
- Do not store sensitive user data in the dashboard process.

## Scalability Considerations (Critical)

- Pre-compute or cache daily/weekly snapshots where possible.
- Use efficient time-series queries on the ledger (index by timestamp).
- Consider background job to pre-calculate P&L for common periods.
- Use connection pooling and async where appropriate if moving to a proper web framework.
- Design so the feature can later be moved behind a dedicated analytics service.

## Expected Deliverables

1. `phase6/core/performance_calculator.py`
2. Updated `serve_dashboard.py` with new endpoints
3. Updates to `phase6_dashboard.html` (or equivalent frontend)
4. Basic unit tests for the calculator
5. Documentation in `FUNCTIONAL_SPEC.md`

## Verification

- A user can see accurate current balance.
- P&L for 1d, 7d, 30d, 90d, and 365d is correctly calculated.
- Response time stays under 200ms even under simulated load.
- No memory leaks when handling multiple users.

## Assignment

**Assigned to**: Future subagent / crypto-engineer  
**Related Handoffs**: Handoff_TradeLedger_Signature_Fix.md (dependency)  
**Target Branch**: `phase-6.1`

## Notes

This feature directly supports the core trader workflow of monitoring performance across different time horizons. It should be implemented after the limited live deployment is stable.