# Handoff: FABLE5-P6-117 + P6-118 (P1-Critical block)

**Title**: Wrapper order reconciliation impossible — wrong get_orders endpoint, JWT includes query string, no cancel/get_order/fill methods at all

**From**: Fable 5 Batch 2

**Objective**: Make the Coinbase Advanced Trade wrapper able to list open orders correctly, cancel them, retrieve fills, and expose a consistent `OrderResponse` schema. This is a hard blocker for CR-03, P6-105, P6-113, P6-114, stop reconciliation, and accurate accounting.

**Must Do**:
- Fix `get_orders` / `get_open_orders`: use correct endpoint `/api/v3/brokerage/orders/historical/batch?order_status=OPEN` (or current equivalent).
- Strip query string before building the JWT `uri` claim (`path.split('?')[0]`).
- Add `cancel_orders(order_ids: list)` using `/orders/batch_cancel`.
- Add `get_order(order_id)` using `/orders/historical/{order_id}`.
- Add fill retrieval (e.g. `/orders/historical/fills?order_id=...`).
- Standardize *all* placement and query returns on the existing `OrderResponse` dataclass (success, order_id, status, error, raw, plus new fields: filled_size, average_filled_price, total_fees).
- Poll market IOC orders once immediately after placement to capture actual fill data before returning.
- Update all callers that rely on raw dicts: exchange_client, order_executor, stop_loss_* modules.

**Must Not Do**:
- Do not leave `get_orders` hitting a non-existent or wrong path.
- Do not continue returning inconsistent `{'id': ...}` vs `{'order_id': ...}` shapes.
- Do not treat error payloads or missing responses as "no orders".

**Files in scope**:
- coinbase_wrapper_FIXED.py
- phase6/core/exchange_client.py (wrapping layer + cancel/get_open_orders)
- phase6/core/order_executor.py
- phase6/core/stop_loss_coordinator.py and stop_loss_manager.py

**Deliverables**:
1. Corrected endpoints + JWT query stripping in wrapper.
2. cancel / get_order / fills methods.
3. Unified OrderResponse usage everywhere.
4. Isolation test that places a real (shadow) order, lists it, cancels it, and retrieves fills.
5. MASTER ingest + Kanban card (may be one card covering the wrapper hardening epic).
6. Scotty verification that CR-03 suspend/reattach now works end-to-end in shadow with real order shapes.

**Success Criteria**:
- `get_open_orders()` returns the correct open stop/limit orders from Coinbase (or realistic shadow).
- `cancel_order(id)` succeeds against an open order created in the same session.
- Post-market-IOC placement, fill price/size/fees are populated (not PENDING forever).
- No more schema branching in consumers for id vs order_id.

**Standing Constraints**:
- Real data preference (authenticated smoke test allowed for verification).
- Code Isolation Testing + Scotty sign-off.
- Blocks multiple prior P1 findings (105,113,114).

**Priority**: P1 but critical path (currently listed in top 3 live-safety risks by Fable 5 in Batch 2).