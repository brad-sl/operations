# Review Handoff: ARCH-5 Optimization, Backtesting, and Cleanup

**Date**: 2026-06-19 (Reviewer: code-reviewer)
**Role**: Review only. Audit backtest coverage of new stack, A/B readiness, deprecation plan.

## Success Criteria (from MASTER)
- Backtest harness replays real proposal streams through new allocator vs legacy.
- A/B framework or config flags for evaluation/allocator strategies.
- Capital utilization targets met in tests.
- All reviews/Fable findings closed.
- Old paths deprecated after verification.
- Final isolation suite for full stack.

## Current Evidence
- ARCH-0/1/2 isolation tests exist with real data (some from 2026-06-15).
- Rotation catch-the-wave validated historically (+8.89% in isolation).
- Current live Allocator produces plans but no full 12mo backtest using *live proposal streams* from evaluate_universe + Allocator.
- No active A/B in config/runner for new vs old.
- Churn experiments exist but not integrated into new defaults.
- Many old handoffs and duplicate logic still present.

## Gaps (Reviewer)
1. **No comprehensive new-stack backtest** — missing replay of real historical proposals through Allocator on full 12mo data with current sentiment/RSI.
2. **No A/B harness** — cannot easily toggle strategies or compare P&L/utilization.
3. **Cleanup stalled** — legacy paths, hybrid stubs, duplicate scoring not removed.
4. **Metrics & targets** — no tracked utilization % or proposal-to-trade conversion in new architecture.
5. **Optimization not exercised** — churn controls (min_move, score_delta) tuned only in old experiments.

## Recommendations
- Build or extend backtest to feed evaluate_universe snapshots → Allocator → simulate fills.
- Add config flags: evaluation_mode, allocator_strategy.
- Run side-by-side on last 120 days + full period.
- Produce report comparing utilization, rotations, returns.
- Create deprecation checklist in MASTER.
- Update all consumers to new facades.

## Verification
- Backtest script run + JSON report appended to MASTER.
- Utilization >70% in opportunities (or documented why not).
- Git history / diff showing old path cleanup.

References: phase6/tests/ (existing isolation), phase6/core/evaluation.py + allocator.py, older backtest scripts (layer0_*, sentiment_enhanced), data/state/arch* evidence files.
