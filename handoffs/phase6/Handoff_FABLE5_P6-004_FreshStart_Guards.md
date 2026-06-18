# FABLE5 Review Handoff: P6-004 — Fresh Start Error Swallowing + Synthetic Data + Force Flag (P0-Critical)

**Task ID**: FABLE5-P6-004  
**Priority**: P0-Critical  
**Parent**: Fable 5 External Review 2026-06-10  
**Handoff Date**: 2026-06-10  
**Assigned To**: crypto-engineer  
**Source**: Fable 5 Batch 0

---

## Objective
Make Fresh Start **truly safe** — it should only trigger when we have independently verified zero holdings on the exchange, never on transient API errors. Also remove synthetic volatility, hardcoded cash thresholds, force-on-restart behavior, and non-atomic state risks in the bootstrap path.

---

## Current Issues (multiple related P0s from model)
- LivePortfolioManager.refresh() and exchange_client.get_holdings/get_account_balance swallow exceptions → return {}.
- Runner: `if not has_positions: self._handle_fresh_start()` treats any failure as "no positions".
- `self._force_next_rebalance = True` hardcoded → restarts (or crash loops under systemd) immediately force a full rebalance.
- Fresh Start path uses hardcoded volatility=0.65 for every pair (violates "real data only").
- Fresh Start deploys using full `cash` instead of a computed `deployable_cash` that respects the $250 reserve.
- Hardcoded cash threshold of 800 in some places (conflicts with standing 250).
- SELL execution in rebalance does not check success status before counting the leg as executed.
- State writes are non-atomic in several critical paths.

Standing constraint: "Fresh Start is bootstrap-only (when there are **truly** zero holdings on exchange)".

---

## Must Do (grouped for one cohesive task)
1. **Detection hardening**:
   - Change get_holdings / refresh to distinguish "verified zero holdings" from "error / unknown".
   - Preferred: raise or return a sentinel (e.g. None or special empty-with-flag) on API failure.
   - Runner must only call `_handle_fresh_start` when holdings were successfully confirmed empty.
   - On error during refresh, log loudly, notify via error_notifier, and **skip** any rebalance/Fresh Start this tick.

2. **Remove dangerous force behavior**:
   - Remove or heavily guard `_force_next_rebalance = True`.
   - Rebalances should only happen on schedule + conditions (or explicit manual trigger).

3. **Real data for Fresh Start**:
   - Pull real ATR / rolling volatility or inverse-vol scores (use the price_history_manager or regime code) for allocation weights.
   - Do not hardcode 0.65.

4. **Reserve + deployable discipline in bootstrap**:
   - Use the same `enforce_withdrawal_reserve` logic + deployable_cash calculation as the normal path.
   - Deploy no more than what the reserve allows.

5. **Order success discipline**:
   - In any SELL leg (Fresh Start or rebalance), check the result from order_executor before incrementing "executed" counters or proceeding to BUY legs.

6. **Atomicity / state**:
   - Minimally improve critical writes (e.g. write positions after successful orders, not before; use temp + rename or explicit commit where possible). At minimum add comments + failure paths that leave the system in a consistent state.

- Create Code Isolation Test(s) covering:
  - API failure during refresh → no Fresh Start, clear error path.
  - Verified zero holdings + sufficient cash → correct deployment with real vol + reserves respected.
  - Partial sell failure → no further BUYs, correct accounting.

---

## Must Not Do
- Do not use synthetic anything in the Fresh Start allocation.
- Do not allow an API error (timeout, 5xx, missing client) to ever be interpreted as "zero holdings".
- Do not re-introduce force-on-every-restart behavior.
- Leave the existing live_portfolio_manager.shadow + real_client separation intact.

---

## Expected Deliverables
- Hardened get_holdings / refresh + runner condition.
- Real volatility source wired into Fresh Start allocation (document the source).
- deployable_cash / reserve respected in bootstrap path.
- Success-checked SELL legs in the relevant paths.
- 1-2 strong isolation tests for the above.
- Updates to phase6_runner.py, live_portfolio_manager.py, exchange_client.py.
- MASTER_TASK_TRACKING.md entry + this handoff marked complete only after tests + shadow evidence.

---

## Success Criteria
- A deliberately broken exchange client during startup produces an error log + Telegram alert, no positions opened.
- Confirmed real zero-holding situation + cash > reserve does a correct (small) Fresh Start using observed ATR, leaves the reserve intact.
- Test demonstrates partial order failure aborts deployment cleanly.
- No more hard-coded 0.65 or 800 magic numbers in the decision path.
- `self._force_next_rebalance` no longer forces on every process start.

---

## Validation Method
- Run the dedicated isolation tests and show output.
- Use the phase6_live_harness or direct runner in shadow mode with injected failures.
- Scotty reviews the changes + runs end-to-end shadow verification (this card + integration review card).
- Only promote after clean evidence and user sign-off before any live Fresh Start usage.

**Handoff complete. Start by locating `_handle_fresh_start`, `refresh`, and the force flag.**
