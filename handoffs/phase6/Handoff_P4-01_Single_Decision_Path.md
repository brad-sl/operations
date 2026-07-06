## Task Handoff Document

Task ID: P4-01
Parent Task: P4 (Architecture completion)
Assigned To: code-reviewer
Date Assigned: 2026-07-05

### Objective
Ensure a single rebalance decision path when `use_new_allocator=true` — no silent legacy divergence.

### Context & Background
Live runner uses ARCH-4 (`evaluate_universe` → `Allocator` → `TradePlan`) but legacy `deploy_capital` / old plan paths still exist (~1280+ in phase6_runner). MASTER P4 intent: no parallel decision paths.

### Scope & Boundaries

Must Do:
- Audit call graph: `_perform_daily_rebalance`, legacy `deploy_capital` block, ARCH-4 branch.
- Make legacy path explicit emergency fallback (config flag + loud log), not silent default when `use_new_allocator=true`.
- Ensure `_last_proposals` / DB persist only from `evaluate_universe` on the primary path.
- Extend `test_isolation_runner_wiring_arch4.py` — assert no `legacy_rebalance_plan` when flag true.
- Commit to repo; append evidence to `docs/MASTER_TASK_TRACKING.md`.

Must Not Do / Touch:
- Change live trading mode or flip `--confirm-live` without orchestrator sign-off.
- Fake prices, holdings, or proposal data in tests.

Files / Directories to Work In:
- `phase6/core/phase6_runner.py`
- `phase6/core/test_isolation_runner_wiring_arch4.py`
- prod/shadow config YAML as needed

Files / Directories to Leave Untouched:
- Unrelated dashboard/SQL paths unless required for proposal persist audit.

### Expected Deliverables
- Code patches + passing isolation test output.
- MASTER dated entry with log snippet or pytest summary.

### Success Criteria
- With `use_new_allocator=true`, rebalance cycle uses only ARCH-4 path in code audit + isolation test.
- Legacy path reachable only when explicit fallback flag set.

### Validation Method
- Run isolation test with real caches (project venv).
- Grep live/shadow config for flag state; optional one shadow cycle log review.

### Notes & Warnings for Sub-Agent
- Code isolation testing mandatory. Real data only. Update MASTER before marking Kanban done.