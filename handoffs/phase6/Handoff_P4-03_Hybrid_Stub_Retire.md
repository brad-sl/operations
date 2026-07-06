## Task Handoff Document

Task ID: P4-03
Parent Task: P4 (Architecture completion)
Assigned To: code-reviewer
Date Assigned: 2026-07-05

### Objective
Retire or thin-delegate `hybrid_rebalancer.generate_rebalance_plan` so rebalance plans flow through `Allocator` + `RebalanceStrategy`.

### Context & Background
`HybridRebalancer.evaluate` remains the hybrid trigger; `generate_rebalance_plan` is a stub/parallel path. P4-03 folds stub into allocator stack.

### Scope & Boundaries

Must Do:
- Grep all consumers of `generate_rebalance_plan`.
- Route callers to `Allocator` + `RebalanceStrategy` (or delete dead stub).
- Keep `test_isolation_hybrid_trigger.py` passing; no dummy vol paths in hybrid plan generation.
- MASTER evidence + commit on `phase-6.1` branch.

Must Not Do / Touch:
- Remove hybrid **trigger** evaluation (`_evaluate_hybrid_rebalance`) without replacement.
- Live order execution changes (P4-04 scope).

Files / Directories to Work In:
- `phase6/core/hybrid_rebalancer.py` (or equivalent)
- `phase6/core/phase6_runner.py`
- `phase6/core/test_isolation_hybrid_trigger.py`

### Expected Deliverables
- Refactor diff + passing hybrid isolation test.

### Success Criteria
- No production caller uses stub plan gen with dummy vols; allocator is canonical for plan bodies.

### Validation Method
- `pytest` hybrid + runner wiring tests; grep confirms zero stub consumers.

### Notes & Warnings for Sub-Agent
- Can run in parallel with P4-01 after P4-06 docs land; both are wave 1 low-risk cleanup.