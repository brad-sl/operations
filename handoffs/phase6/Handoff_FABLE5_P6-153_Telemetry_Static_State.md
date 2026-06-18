# Handoff: FABLE5-P6-153 — Reserve telemetry static across 50 ticks despite accumulating positions

**Priority:** P1-Critical (paper evidence validity)
**Severity:** Medium-High
**Assigned:** crypto-engineer (Scotty verification)
**Source:** Fable 5 Post-Fix Re-Gate (2026-06-10)

## Must Do
- Root cause in harness + runner: telemetry block uses stale snapshot (paper_trader.cash at start of tick or before execute).
- Make telemetry source the *post-execution* state every tick:
  - After `paper_trader.execute_rebalance(...)`
  - Or after any buy/sell fill simulation
  - Recompute cash, positions_value, total, deployable *after* the step
- Add explicit "post-fill" comment in the telemetry line.
- Ensure the same post-fill values go into the final summary JSON and any runner state logging.
- Update any reserve enforcement/plan generation in the same loop to see the updated values (address P6-154 synergy).

## Must Not Do
- Keep the "before execution" cash/positions_value calculation.
- Print telemetry once per tick from a cached initial value.

## Success Criteria
- In the next 50-tick paper run, the telemetry line changes meaningfully across ticks (cash decreases when buys happen, total moves with simulated fills).
- No more identical `cash=$6500.00 total=$6500.50` for all 50 ticks.
- Isolation test (if separate) or harness dry-run with forced fills shows delta.

## Evidence
- Diff of paper_trading_harness.py
- Excerpts of new run telemetry showing variation
- Scotty sign-off comment on the associated Kanban card

## Files
- scripts/phase6/paper_trading_harness.py (main)
- phase6/core/phase6_runner.py (for any live telemetry consistency)

## Owner
Scotty — verify with new paper artifact.