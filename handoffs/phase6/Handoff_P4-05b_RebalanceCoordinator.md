## P4-05b — RebalanceCoordinator extract

**Status:** Done (2026-07-06)

- `phase6/core/rebalance_coordinator.py` — daily rebalance body (CR-03 + ARCH-4 + legacy)
- `Phase6Runner._perform_daily_rebalance` → thin delegate (~1,061 LOC runner vs ~1,285 before)

**Test:** `phase6/tests/test_isolation_cycle_coordinator.py` (rebalance path exercised)