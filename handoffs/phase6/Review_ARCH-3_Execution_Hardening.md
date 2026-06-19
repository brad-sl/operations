# Review Handoff: ARCH-3 Execution Layer Hardening + SL Orthogonality

**Date**: 2026-06-19 (Reviewer: code-reviewer)
**Role**: Pure review only. Identify gaps in TradePlan execution, SL coordination, reserve enforcement for the new stack.

## Success Criteria (from MASTER)
- Execution takes a TradePlan and handles safety (reserve check, cooldown, SL suspend via coordinator, order placement).
- StopLossCoordinator wraps any trade window (CR-03 preserved).
- Isolation test feeds plan and verifies orders (shadow) + SL re-attach.
- Ledger entries include provenance (which proposal/strategy triggered).
- Thin wrapper for allocator output.

## Current State Evidence
- TradePlan dataclass exists and is produced by Allocator (ARCH-2).
- Skeleton `_execute_trade_plan` in runner (maps actions).
- Most safety (reserve, deploy caps, SL) still lives inside legacy `deploy_capital.py` and runner rebalance path.
- No dedicated isolation test exercising full new TradePlan → execution + SL for ARCH-3.
- In live Allocator run: plans are produced but fall through to deploy_capital fallback in current conditions.

## Gaps & Reviewer Findings
1. **No end-to-end new-path execution test** — TradePlan not driving real (or paper) orders independently.
2. **SL orthogonality incomplete for new stack** — Hard stops in RotationStrategy are score-based placeholders; no integration with StopLossCoordinator for plan actions.
3. **Provenance missing** — TradePlan actions lack clear "triggered_by: proposal X from ARCH-1" in ledger.
4. **Reserve / cooldown** — Applied in legacy path only.
5. **Edge cases**:
   - Plan with mixed BUY/SELL (rotations).
   - Low cash after stops.
   - Plan rejected by reserve → graceful handling.
6. **Maintainability**: Execution logic duplicated or scattered.

## Recommendations
- Create `test_isolation_execution_plan.py` that feeds a real TradePlan from Allocator and exercises executor + SL wrapper.
- Enhance TradePlan with `provenance` / `strategy` metadata.
- Wire SL coordinator around new plan execution.
- Document how legacy deploy_capital gates map to new TradePlan processing.

## Verification
- Run new execution isolation test with real plan.
- Confirm SL re-attach on stop from rotation.
- Update MASTER with before/after evidence.

References: phase6/core/allocator.py (TradePlan), phase6/core/phase6_runner.py (execute skeleton), core/stop_loss*, scripts/deploy_capital.py, ARCHITECTURE doc.
