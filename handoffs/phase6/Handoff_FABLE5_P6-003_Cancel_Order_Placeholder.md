# FABLE5 Review Handoff: P6-003 — cancel_order Placeholder (P0-Critical)

**Task ID**: FABLE5-P6-003  
**Priority**: P0-Critical (gates safe rebalancing + stop loss CR-03)  
**Parent**: Fable 5 External Review 2026-06-10  
**Handoff Date**: 2026-06-10  
**Assigned To**: crypto-engineer  
**Source**: Fable 5 Batch 0 (cross-referenced with stop-loss work)

---

## Objective
Replace the empty `cancel_order` placeholder in exchange_client with a real implementation against Coinbase so that StopLossManager / coordinator can actually suspend protective orders before rebalancing.

---

## Current State
In `phase6/core/exchange_client.py`:

```python
def cancel_order(self, order_id: str) -> bool:
    """Cancel a specific order by ID. Placeholder."""
    # returns None implicitly
```

`get_open_orders` similarly thin.

Stop-loss suspend logic (CR-03) and the coordinator call/ expect this. On Coinbase, unfilled stop-limit sells still reserve the base currency. Without real cancel, rebalance SELLs can fail "insufficient available balance" or leave the system believing protective orders were removed when they weren't.

This is especially dangerous right after the key-mismatch fix (P6-001) because rebalancing will actually start issuing SELLs again.

---

## Must Do
- Implement real `cancel_order(self, order_id: str) -> bool` using the appropriate Coinbase Advanced Trade endpoint (likely POST /api/v3/brokerage/orders/batch_cancel or single cancel with the new order IDs).
- Implement `get_open_orders(self, pair: str = None) -> list` with usable return (list of dicts with id, status, product_id, etc.).
- Return explicit `True` on success, `False` on any failure.
- Make callers in stop_loss_manager / coordinator treat `False` or exception as hard failure: abort the rebalance body, notify via error_notifier.
- Add verification step: after cancel, call `get_open_orders` and assert the order is gone.
- Add logging with order ids.
- Add isolation test / fixture test for cancel path (mock client or real paper if safe).
- Coordinate lightly with existing stop_loss_coordinator.py and DELEGATION_Stop_Loss_Migration.md if still relevant.
- Update MASTER and close Kanban only after working suspend → trade → re-attach in shadow.

---

## Must Not Do
- Do not leave it as a placeholder or "TODO".
- Do not assume the old legacy Coinbase API swap patterns.
- Do not change stop logic itself — only the transport.
- Do not enable live rebalancing until this + P6-001 are green.

---

## Expected Deliverables
- Real cancel + get_open_orders in exchange_client.py (shadow/live paths).
- Updates (or confirmation no change needed) in stop_loss_manager.py and stop_loss_coordinator.py.
- Test coverage for the cancel flow.
- Evidence from a shadow run that suspend actually removes protective orders.
- MASTER_TASK_TRACKING update.

---

## Success Criteria
- `exchange_client.cancel_order(id)` returns True and the order no longer appears in open orders.
- Rebalance does not proceed if cancel fails for a protective order that would block the sell.
- Logs prove the sequence worked or was correctly aborted.
- Existing CR-03 stop re-attach tests (if any) now pass end-to-end in shadow.

---

## Validation Method
- Isolation test + full suspend + attempted rebalance dry-run.
- Scotty reviews the implementation + test output, runs shadow verification.
- Only after evidence, promote to done and allow live rebalance consideration.

**Handoff complete. Audit the current callsites to suspend_active_protective_orders before editing.**
