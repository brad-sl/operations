## ANALYST-20260705-006 / 008 — Pre-rebalance data refresh

**Status:** Done (2026-07-06)

- `phase6/core/pre_rebalance_data_refresh.py` — `assess_basket_coverage`, `ensure_basket_signals_ready` (15s cap)
- `CycleCoordinator` calls refresh before `_perform_daily_rebalance` on rebalance cycles
- Runner exposes `runner._data_coverage` for dashboard/ops

**Test:** `phase6/tests/test_isolation_pre_rebalance_refresh.py`