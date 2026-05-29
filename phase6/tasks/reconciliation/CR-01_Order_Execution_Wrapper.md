# Task: CR-01 – Order Execution Wrapper Reconciliation

**Status:** Ready  
**Priority:** High  
**Labels:** reconciliation, execution, reliability

## Objective
Port and adapt the mature order execution patterns from Phase 5 into Phase 6 to improve reliability of live trading operations.

## Description
Phase 5’s `OrderExecutorWrapper` contained battle-tested logic for retries, rate limiting, error classification, and clear separation between planning and execution. Phase 6 currently has thinner execution paths. This task brings that robustness into the Phase 6 architecture.

## Scope
- Review `phase5_order_executor_wrapper.py`
- Design and implement a new `OrderExecutor` class in `phase6/core/`
- Add retry logic with exponential backoff
- Implement rate limit handling and error classification
- Integrate with existing `StopLossManager` and `TradeLedger`

## Implementation Guide

1. Analyze `phase5_order_executor_wrapper.py` and document key methods and strategies.
2. Create `phase6/core/order_executor.py`.
3. Define clean public methods: `execute_buy()`, `execute_sell()`, `execute_rebalance_plan()`.
4. Implement retry logic + structured error types.
5. Add client order ID generation for idempotency.
6. Wire the new executor into `phase6/core/phase6_runner.py`.
7. Update both `_handle_fresh_start()` and `_perform_daily_rebalance()`.

## Files Involved
- **Create:** `phase6/core/order_executor.py`
- **Modify:** `phase6/core/phase6_runner.py`, `phase6/core/exchange_client.py`

## Acceptance Criteria
- All live market orders go through the new `OrderExecutor`
- Retry and rate limit handling is active and logged
- No direct `place_market_buy()` calls remain in the runner for production paths
- Stop-loss attachment continues to work after buys

## Estimated Effort
6–8 hours

## Dependencies
None (can start immediately)