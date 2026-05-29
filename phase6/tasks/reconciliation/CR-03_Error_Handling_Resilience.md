# Task: CR-03 – Error Handling & Rate Limit Resilience

**Status:** Ready  
**Priority:** Medium-High  
**Labels:** reliability, resilience

## Objective
Standardize and strengthen error handling and rate limit management across the trading engine.

## Description
Phase 5 contained proven patterns for handling Coinbase rate limits, transient errors, and graceful degradation. Phase 6 needs a centralized, consistent approach.

## Scope
- Create centralized exception hierarchy
- Implement retry + backoff strategy
- Add circuit breaker for repeated failures on a pair
- Apply across exchange client, stop-loss manager, and order executor

## Implementation Guide

1. Create `phase6/core/exceptions.py` with custom exception classes.
2. Create `phase6/core/resilience.py` containing retry decorator and circuit breaker.
3. Apply resilience layer to critical methods.
4. Add structured logging for all retry attempts and failures.
5. Update monitoring agent to detect repeated failures.

## Files Involved
- **Create:** `phase6/core/exceptions.py`, `phase6/core/resilience.py`
- **Modify:** `phase6/core/exchange_client.py`, `phase6/core/stop_loss_manager.py`, `phase6/core/order_executor.py`

## Acceptance Criteria
- Consistent retry and backoff behavior across all components
- Circuit breaker triggers after repeated failures
- All errors are classified and logged clearly

## Estimated Effort
4–6 hours

## Dependencies
CR-01 (recommended)