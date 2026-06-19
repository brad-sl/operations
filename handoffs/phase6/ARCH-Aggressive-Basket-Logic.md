# Handoff: Integrate Aggressive Basket Recovery Logic (ARCH-2)

## Goal
Make the "more aggressive when basket drops below 4 (or ≤2) active pairs" behavior a first-class, reliable part of the Allocator so that signals + low basket actually trigger meaningful new entries and rotations.

## Background
- User noted a "newly built method" for aggressive trading on low basket was tested but not implemented in production.
- deploy_capital.py already has emergency_recovery logic:
  - if len(current_allocations) <= 2:
    - relax min_new_pair_sentiment
    - increase max_new_pairs
    - use RECOVERY_CANDIDATES
    - log "[EMERGENCY RECOVERY]"
- This is currently a leaf in deploy_capital (used by legacy and allocator fallback).
- Not promoted to RotationStrategy or a dedicated strategy/mode in the new Allocator.
- Opportunity scanner has related basket expansion ideas (mostly shadow).

## Required Changes
1. Extract or extend the aggressive logic into RotationStrategy (or a new AggressiveRecoveryStrategy) inside allocator.py.
2. Make it trigger on "current meaningful active pairs < 4" (define "meaningful" clearly, e.g. allocation > threshold).
3. Ensure it produces real TradePlan entries when high-score proposals exist.
4. Wire into Allocator so it can be selected or auto-activated.
5. Add tunables (relaxed thresholds, max aggressive size, cooldown between aggressive bursts).
6. Create/update isolation test that feeds a low-basket snapshot + real proposals and asserts aggressive deployment.

## Success Criteria
- Allocator in "rotation" or aggressive mode, when given <4 active + good proposals, produces BUY actions for new or under-allocated pairs with relaxed gates.
- Evidence from isolation test (before/after or specific low-basket test).
- No regression on normal basket sizes (churn controls still respected).
- Documented in code and MASTER.

## References
- phase6/core/allocator.py (RotationStrategy.decide, Allocator)
- phase6/scripts/deploy_capital.py (emergency_recovery section + RECOVERY_CANDIDATES)
- phase6/core/evaluation.py (for feeding proposals)
- phase6/core/phase6_runner.py (how Allocator is called)
- ARCHITECTURE_ISOLATED_COMPONENTS.md (RotationStrategy description, catch-the-wave)
- Existing isolation tests in phase6/core/ and phase6/tests/

## Verification
- Run dedicated isolation test with synthetic low-basket state.
- Manual invocation of Allocator with low active pairs + proposals.
- (Later) Shadow run showing new entries when basket is small.

## Notes for Worker
Focus on making the logic callable and testable inside the new architecture. Preserve the existing deploy_capital behavior as fallback/building block. Coordinate with the Integration Audit task.

Owner: crypto-bot-project Kanban
Priority: Medium-High (directly addresses idle capital + "signals don't trade" problem)
