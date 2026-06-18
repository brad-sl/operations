# Handoff: FABLE5-P6-154 — `Rebalances attempted: 0` contradicts generated plans + accumulated positions

**Priority:** P1-Critical (paper evidence validity)
**Severity:** Medium
**Assigned:** crypto-engineer
**Source:** Fable 5 Re-Gate 2026-06-10

## Must Do
- Define clear semantics in harness and any mapping runner code:
  - `rebalances` / `rebalances_attempted` = number of *executed* rebalance plans that produced trades (or attempted execution in paper mode).
  - Plans can be generated every tick ("plan generated") but count only when `execute_rebalance` or equivalent actually returns non-empty executed list or modifies positions.
- In the harness loop:
  - After `executed = paper_trader.execute_rebalance(plan, prices...)`
  - `summary["rebalances"] += 1 if executed or len(plan) > 0 else 0` (prefer actual fill count for paper realism).
  - Ensure PaperTrader path that accumulates positions is the counted path.
- Update end-of-run print and summary JSON to reflect "executed rebalances".
- Add a small comment block explaining the metric (plan vs executed).

## Must Not Do
- Increment "rebalances" on every plan generation regardless of execution.
- Leave the counter at 0 while positions clearly change via the rebalance code path.

## Success Criteria
- Next paper run reports non-zero `Rebalances attempted: N > 0`.
- Positions accumulation matches the reported executed count within the paper trader's logic.
- Fable 5 or Scotty can cross-check counter vs. plan_len > 0 and final positions.

## Evidence
- Diffs + before/after run output
- Updated harness log showing positive rebalance count + plan samples + position changes

## Files
- scripts/phase6/paper_trading_harness.py (primary)
- (Optional) mirror logic comment in phase6/core/phase6_runner.py for live parity

## Owner
Scotty (sign-off + isolation before next re-gate).