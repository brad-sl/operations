# Handoff: Exchange Client & Order Execution Hardening

**Date:** 2026-06-01  
**Status:** Incomplete / High Priority  
**Owner:** TBD

## Objective
Complete the migration and hardening of `exchange_client.py` and `order_executor.py` so they are fully reliable in live mode.

## Must Do
- Review and stabilize `coinbase_advanced_client.py` (current uncommitted changes).
- Ensure `exchange_client.py` uses the hardened client.
- Add retry logic + circuit breaker for order placement.
- Integrate with the new `hybrid_rebalancer` and `live_portfolio_manager`.
- Add structured logging for every order attempt (success/failure/reason).
- Update `phase6_runner.py` to use the local modules (remove TODOs).

## Must Not Do
- Do not bypass the new `LivePortfolioManager` for position tracking.
- Do not hardcode API keys or credentials.

## Files to Touch
- `phase6/core/exchange_client.py`
- `phase6/core/order_executor.py`
- `phase6/core/coinbase_advanced_client.py`
- `phase6/core/phase6_runner.py`
- `phase6/core/live_portfolio_manager.py`

## Files to Protect
- Existing trade history in `trades/`
- `data/state/phase6_runner_state.json`

## Success Criteria
- All order types (market, limit, stop) execute reliably in live mode.
- Failed orders are retried or circuit-broken appropriately.
- Full audit trail exists in logs and `TradeLedger`.

## Validation Method
- Execute a small live test order (or shadow + manual verification).
- Confirm no unhandled exceptions in error logs.
- Verify positions in `LivePortfolioManager` match exchange state.