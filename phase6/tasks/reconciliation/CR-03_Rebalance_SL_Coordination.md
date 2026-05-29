# CR-03: Rebalance + SL/TP Coordination

**Status:** Proposed  
**Priority:** High  
**Owner:** Agent (Scotty)  
**Created:** 2026-05-23

## Problem
Daily rebalance currently ignores existing stop-limit orders. When a position is fully liquidated by a stop (e.g. BTC leg at Order ID `118c33c2-b41a-43e5-9e8d-f6b7aaac1418`), the runner reports near-target weights and emits 0 moves even though the basket is now significantly imbalanced.

## Desired Behavior
On every rebalance trigger the system must:
1. Detect and suspend any active SL/TP orders for pairs being rebalanced
2. Compute new target allocations from live exchange balances
3. Execute rebalance moves
4. Re-attach fresh stop-limit orders on the resulting positions using current RiskEngine parameters

## Scope
- Modify `_perform_daily_rebalance()` in `phase6_runner.py`
- Integrate with `RiskEngine` and `OrderExecutor`
- Ensure no orphaned stops on closed positions
- Maintain current daily rebalance frequency

## Success Criteria
- After a full position liquidation, the next rebalance generates the correct buy(s)
- No SL/TP orders are left on pairs with zero balance
- New stops are attached post-rebalance with updated prices
- All actions are clearly logged (order IDs + actions)
- No increase in fee drag or accidental double-fills

## Constraints
- Must work with existing Coinbase live trading path
- Must not increase risk parameters without explicit approval
- Must remain compatible with Fresh Start + Daily Rebalance strategy

## Validation Steps
1. Simulate full BTC liquidation
2. Trigger manual rebalance
3. Verify suspend → rebalance → re-attach sequence in logs
4. Confirm new stops are live on exchange

## Out of Scope
- Changing rebalance frequency
- Modifying RiskEngine parameters
- Multi-exchange support

## Handoff Notes
- Primary files: `phase6/core/phase6_runner.py`, `src/core/live_portfolio_manager.py`
- Related backtest evidence: `backtest_phase6_results.json` (Fresh Start + Daily)
- Next: Delegate implementation after this document is approved

---
**Next Action:** Delegate implementation to sub-agent once user confirms.