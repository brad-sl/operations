# FABLE5 Review Handoff: P6-002 — Withdrawal Reserve Enforcement Dead Code (P0-Critical)

**Task ID**: FABLE5-P6-002  
**Priority**: P0-Critical  
**Parent**: Fable 5 External Review 2026-06-10  
**Handoff Date**: 2026-06-10  
**Assigned To**: crypto-engineer  
**Source**: Fable 5 Batch 0

---

## Objective
Make the withdrawal reserve check (the documented ~$250 floor) actually work and block rebalancing when violated. Currently it is completely dead code due to NameError + swallowed exception.

---

## Current State
From the runner in `_perform_daily_rebalance`:

```python
if not info.get("allowed", True):
    logger.warning(f"[HARDENING] Withdrawal reserve violation: {reserve_check}")
    return
except Exception as e:
    logger.warning(f"[HARDENING] Withdrawal reserve check skipped: {e}")
```

- `reserve_check` is undefined → NameError.
- Bare `except` catches it → logs "skipped" → continues.
- Call site passes empty `target_allocations_usd={}`.
- Later `new_capital = min(rebalance_cap, cash)` can still include the protected dollars.

Standing constraint violated in the main daily rebalance path.

---

## Must Do
- Fix the f-string to use the actual `info` dict (or the correct variable name returned by `enforce_withdrawal_reserve`).
- Pass real current target allocations / planned deployment values to the reserve check function.
- Compute a hard `deployable_cash = max(0, usd_balance - min_reserve_usd)` and enforce it for `new_capital` used in redeployment and rebalance planning.
- Add an early `return` or block that actually stops the rebalance when reserve would be breached.
- Add a **Code Isolation Test** or unit test that calls the reserve enforcement with scenarios that should block and asserts the function returns early / raises / logs violation properly.
- Ensure the check runs **before** any SELL/BUY planning and capital calculations.
- Update logs to be useful (show current balance, reserve, intended deploy amount).
- Update MASTER_TASK_TRACKING.md.

---

## Must Not Do
- Do not weaken the reserve floor.
- Do not allow reserve money to be part of deployable capital in rebalance.
- Do not bypass the check on error paths.
- Do not touch Fresh Start logic in this task (separate card).

---

## Expected Deliverables
- Corrected `_perform_daily_rebalance` (and any helper) in phase6/core/phase6_runner.py.
- Calls to `enforce_withdrawal_reserve` with proper inputs.
- New test (isolation style preferred) proving violation blocks.
- Evidence in a runner shadow run that the check now triggers correctly.
- MASTER update.

---

## Success Criteria
- When cash is close to the reserve, rebalance either skips or caps deployment properly.
- Test demonstrates the NameError bug is gone and the block happens.
- No "skipped" warning on a normal run.
- Reserve is never deployable.

---

## Validation Method
- Run the new test.
- Scotty or user triggers a simulated rebalance with low cash scenario.
- Confirm logs show enforcement working.
- Scotty performs final review before any live rebalance re-enabled.

**Handoff complete. Read the current enforce_withdrawal_reserve usage first.**
