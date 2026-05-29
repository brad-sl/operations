# Task: CR-02 – Daily Rebalance Execution Hardening

**Status:** Ready  
**Priority:** High  
**Labels:** reconciliation, rebalance

## Objective
Bring daily rebalancing execution to production quality, matching the maturity of Fresh Start logic.

## Description
The current `_perform_daily_rebalance()` method still contains placeholder logic for sells and lacks proper position reconciliation. Phase 5 had working live rebalance execution that we should leverage.

## Scope
- Review rebalancing execution in `phase5_multi_pair_minimal.py`
- Implement real sell execution
- Add pre-rebalance position reconciliation
- Ensure stop-losses are maintained or re-attached after rebalance moves
- Improve reporting of actual executed moves

## Implementation Guide

1. Extract rebalance execution patterns from Phase 5.
2. Implement `execute_sell()` in the Order Executor (from CR-01).
3. Add position reconciliation step before generating rebalance plan.
4. Handle stop-loss attachment/adjustment on rebalanced positions.
5. Enhance Telegram digest with before/after positions and actual moves.

## Files Involved
- **Modify:** `phase6/core/phase6_runner.py`
- **Depends on:** CR-01 (OrderExecutor)

## Acceptance Criteria
- Rebalance can execute both buys and sells in live mode
- Stop-losses remain attached after rebalance
- Clear before/after position reporting in logs and Telegram

## Estimated Effort
5–7 hours

## Dependencies
CR-01 – Order Execution Wrapper Reconciliation