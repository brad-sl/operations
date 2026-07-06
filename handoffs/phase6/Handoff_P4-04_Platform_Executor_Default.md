## Task Handoff Document

Task ID: P4-04
Parent Task: P4 (Architecture completion)
Assigned To: code-reviewer
Date Assigned: 2026-07-05

### Objective
Make `trading.factory` + `TradeExecutor` the default execution boundary when ARCH-4 is active; legacy `OrderExecutor` only on explicit fallback flag.

### Context & Background
ARCH-4 can use platform executor but path is not sole/default. P4-04 closes execution boundary divergence (medium risk).

### Scope & Boundaries

Must Do:
- Wire `_execute_trade_plan` to prefer platform executor when ARCH-4 active.
- Config: `use_platform_executor: true` in prod config (with fallback flag documented).
- Run `test_isolation_allocator_platform_executor.py` + one shadow rebalance.
- Post-live or shadow check: order_ids / ledger provenance from platform path where applicable.
- MASTER entry + commit.

Must Not Do / Touch:
- Mid-cycle live trading (P4-02).
- Runner LOC refactor (P4-05).

Files / Directories to Work In:
- `phase6/core/phase6_runner.py`
- `trading/` factory and executor modules
- prod config YAML
- `phase6/tests/test_isolation_allocator_platform_executor.py`

### Success Criteria
- Shadow rebalance + isolation test pass with platform executor as default when flags set.
- Legacy OrderExecutor only when fallback flag true.

### Validation Method
- Pytest isolation + shadow cycle evidence in MASTER.

### Notes
- **Depends on P4-02** (wave 3). Live runner must stay stable — no big-bang cutover without tests.