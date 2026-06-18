# Handoff: FABLE5-P6-152 — max_deployable_usd cap not enforced in deployable computation

**Priority:** P0-Critical (for paper gate closure + live blocker)
**Severity:** High
**Assigned:** crypto-engineer (Scotty to verify isolation + shadow)
**Source:** Fable 5 Post-Fix Re-Gate Review (2026-06-10), Batch 4 GRAND + 50-tick paper artifact
**Status:** Ready — fix required before next paper run counts as evidence

## Must Do
- In phase6/core/phase6_runner.py (_perform_daily_rebalance and any Fresh_Start paths) and in scripts/phase6/paper_trading_harness.py (telemetry + allocation path):
  - Load `max_deployable_usd` from config `withdrawal_reserve` (or global_settings fallback).
  - After computing `cash - min_reserve`, clamp: `deployable_cash = min(cash - min_reserve, max_deployable_usd)`.
  - Pass the clamped value into `enforce_withdrawal_reserve`, `deploy_capital`, and rebalance_plan targets.
  - Update harness telemetry to show the *clamped* deployable_after_reserve and reflect it in plan sizing.
- Add/ update Code Isolation Test: `scripts/test_fable5_p6_152_max_deployable_cap.py` that asserts:
  - When cash - reserve > max_deployable, deployable is exactly max_deployable.
  - When smaller, normal min-reserve logic applies.
- Run the test before marking complete; record output.
- Update harness to use the same config block for consistency.
- Log the clamp explicitly in runner/harness when it binds.

## Must Not Do
- Do not hard-code 800 or any magic number in code (config is source of truth).
- Do not bypass the clamp for "Fresh Start" or "recovery" paths.
- Do not leave deployable = cash - min_reserve when the cap is configured to be tighter.

## Success Criteria
- Isolation test passes with explicit cap-hit case.
- 50+ tick paper run (next one) shows **non-~6300** deployable values when cash is high; "cap applied" log lines appear.
- Fable 5 re-gate or Scotty verification confirms cap is visible in telemetry and affects plan sizes.
- No change to min_reserve logic (200 remains the floor).

## Evidence to Capture
- Diffs of runner.py + harness.py + config (if needed)
- Full isolation test output
- Excerpt from next paper run showing clamp in action
- Update to MASTER_TASK_TRACKING.md with ticket closure + link to this handoff

## Files
- phase6/core/phase6_runner.py
- scripts/phase6/paper_trading_harness.py
- config/trading_config_phase6.json (already has the key)
- src/capital_allocation/withdrawal_reserve.py (verify it accepts/uses cap if passed)
- scripts/test_fable5_p6_152_max_deployable_cap.py (new)

## Handoff Document Owner
Scotty (orchestrator reviewer) — will review evidence, run isolation, and confirm before promoting card.