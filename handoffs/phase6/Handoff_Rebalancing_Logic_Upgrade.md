# Handoff Document: Rebalancing Logic Upgrade (Hybrid Threshold + AI Filter)

**Work Package**: 2  
**Priority**: High  
**Status**: Blocked → Ready (after this document)

## Objective
Upgrade the rebalancing system from pure correlation-based logic to a **hybrid threshold + AI filter** model that combines:
- Hard thresholds (e.g., sentiment delta, volatility, drawdown)
- AI-assisted confirmation (lightweight model or rule-based filter)
- Time-decayed sentiment signals

This makes rebalancing more reliable across market regimes and directly tied to the restored sentiment system.

## Original Source Code (Phase 4/5)
- `phase6/core/allocation_engine.py` and `PHASE_6_REBALANCING.md` (current Phase 6 implementation)
- Phase 5 backtesting reports and `dynamic_backtest.py`
- Original hybrid rebalancing recommendations in trading docs
- `live_portfolio_manager.py` (rebalance trigger logic)

## Scope & Boundaries

### Must Do
- Implement hybrid rebalancing scheduler in `phase6/core/rebalancing/`
- Support configurable thresholds (sentiment change > X, volatility spike, etc.)
- Integrate 15-min (X) and 60-min (Reddit) time-decayed sentiment
- Add AI filter layer (simple rules or small model call)
- Write unit tests and a smoke test script
- Update `phase6_runner.py` to use the new scheduler

### Must Not Do
- Replace the entire allocation engine in one go
- Remove existing correlation-based fallback without tests

## Expected Deliverables
1. `phase6/core/rebalancing/hybrid_rebalancer.py`
2. Updated `phase6/core/allocation_engine.py` (or new hybrid module)
3. `phase6/scripts/test_hybrid_rebalance.py`
4. Updated `PHASE6_RESTORATION_CHECKLIST.md`
5. Git commit on `phase-6.1` referencing this Handoff

## Git Requirements
- Commit all changes to the `phase-6.1` branch
- Clear commit message referencing `Handoff_Rebalancing_Logic_Upgrade.md`

## Verification
- Hybrid scheduler triggers correctly on test data
- Time decay from sentiment cache is respected
- No regression in existing correlation logic (fallback still works)
- All artifacts saved to designated directories only

## Notes
This task was previously blocked due to missing detailed Handoff content. Now unblocked.