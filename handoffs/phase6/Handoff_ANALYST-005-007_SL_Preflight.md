## ANALYST-20260705-005 / 007 — SL settlement poll + tick precision

**Status:** Done (2026-07-06)

- `phase6/core/sl_preflight.py` — risk-aware `settlement_poll_params`, `quantize_stop_bundle`
- `stop_loss_manager.attach_stop_loss` uses preflight module
- `stop_loss_coordinator` — `set_buy_order_ids`, passes `order_id` on re-attach
- `Phase6Runner._execute_trade_plan` records BUY `order_id` → coordinator

**Test:** `phase6/tests/test_isolation_sl_preflight.py`