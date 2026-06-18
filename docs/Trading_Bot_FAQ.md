# Trading Bot FAQ

This document captures operational knowledge, gotchas, and recommended patterns for the Phase 6 trading system.

## Stop-Loss Orders

### Can you have multiple stop-loss orders on the same trading pair?

**Yes**, Coinbase Advanced Trade allows multiple stop orders on the same pair.

However, this is generally discouraged for the following reasons:

- Stops are independent — if one triggers, others remain active.
- It can lead to overlapping or conflicting risk management.
- The exchange may reject additional stop orders with "INSUFFICIENT_FUND" if it cannot validate sufficient balance for all open protective orders.
- Tracking and auditing risk becomes significantly harder.

### Recommended Pattern: "One Active Stop Per Position"

For rebalancing systems, the cleanest and most reliable approach is:

**Maintain exactly one active stop-loss order per open position.**

**Rebalance Flow:**
1. **Detect** any existing protective orders for the pairs being rebalanced.
2. **Suspend** (cancel) existing stops before executing trades.
3. Perform the buy/sell rebalance.
4. **Re-attach a single updated stop** on the *new total position size*.

This pattern:
- Avoids duplicate/redundant stops
- Prevents insufficient funds errors during re-attach
- Keeps risk management simple and auditable
- Works well with the CR-03 atomic suspend → rebalance → reattach coordinator

**Future enhancements** (not currently implemented):
- Laddered stops at multiple risk levels
- Trailing stops
- Reduce-only stops when adding to existing positions

---

*Last updated: 2026-06-05*