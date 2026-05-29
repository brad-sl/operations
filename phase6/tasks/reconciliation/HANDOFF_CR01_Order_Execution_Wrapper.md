# HANDOFF DOCUMENT: CR-01 – Order Execution Wrapper Reconciliation

**Task ID:** CR-01  
**Title:** Order Execution Wrapper Reconciliation  
**Priority:** High  
**Owner:** Sub-agent  
**Created:** 2026-05-19

---

## Objective

Create a robust `OrderExecutor` class for Phase 6 that incorporates the proven execution patterns from Phase 5’s `OrderExecutorWrapper` while aligning with the current Phase 6 architecture (use of `CoinbaseExchangeClient`, `StopLossManager`, structured logging, etc.).

---

## Background & Rationale

Phase 5 had a mature `OrderExecutorWrapper` that handled:
- Sandbox vs Live separation
- Structured result dictionaries
- CSV audit logging
- Defensive error handling around order placement

Phase 6 currently has thinner execution logic in `phase6_runner.py` and `exchange_client.py`. We need to extract the reliability patterns and implement them in a clean, reusable class.

---

## Scope

### In Scope
- Design and implement `phase6/core/order_executor.py`
- Support `execute_buy()`, `execute_sell()`, and `execute_rebalance_plan()`
- Add retry logic with exponential backoff
- Implement basic rate limit awareness and error classification
- Generate `client_order_id` for every order
- Integrate with existing `StopLossManager` (attach SL after successful buys)
- Return structured results for logging and reconciliation
- Update `phase6/core/phase6_runner.py` to use the new executor

### Out of Scope
- Full sell execution logic (can be stubbed for now)
- Advanced circuit breaker (deferred to CR-03)
- Full reconciliation engine (CR-05)

---

## Success Criteria

1. New `OrderExecutor` class exists and is importable.
2. All live buys in Fresh Start and Daily Rebalance go through `OrderExecutor`.
3. Retry logic is active and logged on failure.
4. Stop-loss is attached after every successful buy (via `StopLossManager`).
5. Structured result objects are returned and logged.
6. No direct `place_market_buy()` calls remain in the runner for production paths.

---

## Implementation Guide

### Step 1: Analysis (30–45 min)
- Review `phase5_order_executor_wrapper.py` thoroughly.
- Document key methods, error handling patterns, and result structure.
- Identify what to keep vs modernize for Phase 6.

### Step 2: Design (30 min)
- Create class `OrderExecutor` in `phase6/core/order_executor.py`
- Define public interface:
  - `execute_buy(pair, usd_amount) -> dict`
  - `execute_sell(pair, size) -> dict`
  - `execute_rebalance_plan(plan) -> list[dict]`
- Define result schema (status, order_id, price, error, etc.)

### Step 3: Implementation
- Use `self.exchange` (CoinbaseExchangeClient) for actual calls.
- Add retry decorator or loop (3 attempts, exponential backoff).
- Generate `client_order_id` using `secrets.token_hex(16)`.
- After successful buy, call `self.stop_loss_manager.attach_stop_loss(...)`.
- Log every attempt and outcome.

### Step 4: Integration
- Modify `phase6/core/phase6_runner.py`:
  - Instantiate `OrderExecutor` in `__init__`
  - Replace direct buy calls in `_handle_fresh_start()` and `_perform_daily_rebalance()`

### Step 5: Testing
- Test in shadow mode first.
- Then run a small live test (1–2 pairs) if safe.

---

## Files to Modify / Create

**Create:**
- `phase6/core/order_executor.py`

**Modify:**
- `phase6/core/phase6_runner.py`

**Reference (read only):**
- `phase5_order_executor_wrapper.py`
- `phase6/core/exchange_client.py`
- `phase6/core/stop_loss_manager.py`

---

## Constraints & Preferences

- Follow existing Phase 6 naming and structure.
- Prefer composition over inheritance.
- Use structured logging (not just print).
- Make the class testable in shadow mode.
- Keep the interface clean and well-documented.

---

## Validation

After completion, the reviewer should:
- Confirm the new executor is used in both Fresh Start and Rebalance paths.
- Verify retry behavior in logs.
- Check that stop-loss attachment still works.
- Run the diagnostic script `test_fresh_start_stop_loss.py` in shadow mode.

---

## Notes for Sub-agent

- You have full liberty to improve the design as long as the success criteria are met.
- If you find better patterns than Phase 5, use them.
- Document any deviations from this handoff in your summary.

---

**Handoff Prepared By:** Hermes Agent  
**Date:** 2026-05-19