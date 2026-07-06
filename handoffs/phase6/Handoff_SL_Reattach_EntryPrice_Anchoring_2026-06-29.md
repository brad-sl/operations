# Handoff: SL Re-attach Entry Price Anchoring (Highest Immediate Risk)

**Date**: 2026-06-29  
**Priority**: P0 / Highest immediate risk (as selected from Recommended Next Steps)  
**Related**: User's #1 from list (re-attach entry_price anchoring issue), CR-03, prior SL hardening work, ANALYST proposals on SL reliability.  
**Status**: Targeted fix drafted + partially implemented in active Phase 6 paths. Verification needed on live rebalances.

## Problem / Risk
When suspending and re-attaching protective stops during rebalances (CR-03), Fresh Start, or position restores, the SL was sometimes calculated from the *current market price* instead of the *original entry/fill price*.

This causes "moving target" erosion:
- Original intent: 3% stop from buy price.
- After price drift + re-attach using current price: effective protection drifts (e.g., now only 1% below original entry or worse).
- Violates "get out of the pair and reallocate" on meaningful loss.
- Highest risk on repeated re-attach cycles (rebalances, volatility).

Evidence from live_state (historical): positions carry `entry_price` (e.g. OP ~0.095 from Jun 20 backfill), but not always honored in re-attach paths.

Older src/ coordinator passed raw entry_price without preference for original.

## Targeted Solution (Implemented in Phase 6 Core)
The fix is concentrated in the active CR-03 path:

**File: `phase6/core/stop_loss_coordinator.py` — `reattach_protective_orders`**

Key logic (as of 2026-06-29):
```python
if isinstance(value, dict):
    amount = ...
    intended_entry = value.get("entry_price") or value.get("original_entry") or 0.0
    current_p = value.get("current_price") or value.get("price", 0)
    entry_for_calc = intended_entry if intended_entry > 0 else current_p
...
if intended_entry > 0 and current_p > 0 and abs(intended_entry - current_p) > 0.005:
    logger.info(f"[SL-ANCHOR #1] {pair}: using original entry ${intended_entry:.4f} for SL (current ${current_p:.4f})")

success = self.sl_manager.attach_stop_loss(
    pair=pair,
    entry_price=float(entry_for_calc),
    size=...,
    sl_pct=None,
    anchor_entry=float(intended_entry) if intended_entry > 0 else None
)

# Post-attach verify
if success and intended_entry > 0:
    v = self.sl_manager.verify_protective_stop(pair, intended_entry)
```

**Supporting in `phase6/core/stop_loss_manager.py`**:
- `attach_stop_loss(..., anchor_entry=None)` now uses `calc_base = anchor_entry if ... else entry_price`
- `get_sl_pct` for adaptive (ties to #3).
- `verify_protective_stop` added for post-attach check (shadow/live).
- Quantization + pre-flight (from recent 001 work).

**Call sites**:
- Runner uses `suspend_reattach_context(basket, pre_positions)` where `pre_positions` come from `get_enriched_positions()` (should carry entry_price from ledger/state).
- Post-buy in order_executor should pass real fill price.

## Targeted Patch (Ready to Apply / Review)
If gaps remain (e.g. non-enriched dicts passed, or missing entry in some restores):

**Small robust extraction helper patch** (suggested addition to coordinator or a shared util):

```diff
diff --git a/phase6/core/stop_loss_coordinator.py b/phase6/core/stop_loss_coordinator.py
index ...
--- a/phase6/core/stop_loss_coordinator.py
+++ b/phase6/core/stop_loss_coordinator.py
@@
+    def _get_original_entry(self, pair: str, value: Any, live_state: Optional[dict] = None) -> float:
+        """Robust original entry lookup. Prefers enriched, then ledger, then current as last resort."""
+        if isinstance(value, dict):
+            for k in ("entry_price", "original_entry", "buy_fill_price"):
+                if (v := value.get(k)) and v > 0:
+                    return float(v)
+        # Fallback to trade ledger or live_state (implement as needed)
+        # e.g. ledger = TradeLedger(); entry = ledger.get_entry_price(pair)
+        return 0.0
+
     def reattach_protective_orders(self, positions: Dict[str, Any]) -> Dict[str, Any]:
         ...
-        intended_entry = value.get("entry_price") or ...
+        intended_entry = self._get_original_entry(pair, value)
```

Apply via `patch` or manual. Prioritize passing fully enriched positions from `live_portfolio_manager.get_enriched_positions()` (it already attempts to carry entry from state/ledger).

## Verification Steps (Concrete)
1. Load real positions from `data/state/phase6_live_state.json` (has entry_price).
2. `python -c 'from phase6.core.stop_loss_coordinator import ... ; c = ...; c.reattach_protective_orders(enriched_pos)'` in shadow.
3. Check logs for `[SL-ANCHOR #1]` when entry != current.
4. Confirm stop calc in shadow: `stop = entry * (1 - pct)` not current * (1-pct).
5. Run full suspend_reattach_context in a test rebalance wrapper.
6. Post-live: After next rebalance, inspect open stops vs original entries in state.

**Success criteria**: No re-attach uses current price when original entry >0 is available. All re-attaches log anchor decision. Verify reports "anchored_ok".

## Related / Follow-on
- Ties directly to user's original list #1 (Harden + verify SL attachment end-to-end).
- Complements recent work on adaptive SL (#3) and pre-flight/tick (ANALYST-001).
- Next: Gate all restores/entries to pass enriched with entry; persist entry_price more durably in live_state on every fill.
- Full list items 2,4,5 still open (drawdown hard stops, allocator strengthening, entry gating).

## Handoff Owner
Brad / crypto-orchestrator profile.  
Apply patch, run verification with real data, update MASTER + kanban.

**Evidence artifacts**: This handoff + coordinator.py lines 87-122 (as read 2026-06-29) + manager anchor logic + shadow attach tests.
