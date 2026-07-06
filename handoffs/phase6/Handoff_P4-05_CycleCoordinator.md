## Task Handoff Document

Task ID: P4-05
Parent Task: P4 (Architecture completion)
Date: 2026-07-06

### Objective
Extract per-cycle orchestration into `CycleCoordinator`; fix legacy gaps (P4-02 runner wiring, ARCH-4 rebalance finalize, `__init__` state corruption).

### Delivered
- `phase6/core/cycle_coordinator.py` — unified eval, mid-cycle shadow, rebalance gate
- `Phase6Runner._run_cycle` delegates to coordinator
- P4-02 `mid_cycle_allocator_enabled` wired (shadow-only, no live exec)
- `_finalize_daily_rebalance` — ARCH-4 path now sets `last_rebalance_date` + events
- Fixed `persist_facts_to_db` accidentally resetting state on every DB write
- `use_new_allocator` default **True** when config omits flag (P4-01)
- Dashboard `arch4` JSON structure fixed
- `phase6/tests/test_isolation_cycle_coordinator.py`

### Validation
```bash
.venv/bin/python phase6/tests/test_isolation_cycle_coordinator.py
.venv/bin/python phase6/tests/test_isolation_mid_cycle_shadow.py
.venv/bin/python phase6/tests/test_isolation_runner_wiring_arch4.py
```

### Must Not (future)
- Mid-cycle **live** execution without explicit gate
- Further runner slimming (rebalance body still in runner — next waves)