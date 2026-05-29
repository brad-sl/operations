# Live Rebalance Position Source

## Pattern for Daily Rebalance

**Rule**: Daily rebalance MUST always query real exchange account balances FIRST before computing deltas or generating moves.

### Implementation Requirements

1. **Live Mode Priority**:
   - Call `cb_client.get_accounts()` (or `list_accounts()` equivalent) to fetch full current holdings.
   - Include all assets in the target basket (even zero-balance pairs).
   - Convert balances + current prices -> current_allocs dict (pair -> usd_value).

2. **Fallback**:
   - ONLY use internal JSON state (`portfolio_state.json` or LivePortfolioManager.positions) for pure paper/shadow mode.

3. **Entry Point**:
   - `LivePortfolioManager.get_positions()` must implement this:
     - Prefer live query in live mode.
     - Return dict suitable for `rebalance_plan(current_allocs, ...)` 

4. **No Regression**:
   - Paper trader path unchanged.
   - Reconcile_positions still used for drift correction post-trade.

This fixes the "0 moves" / empty positions bug where rebalance sees Current Positions: {} .

Version: 1.0 - 2026-05-22