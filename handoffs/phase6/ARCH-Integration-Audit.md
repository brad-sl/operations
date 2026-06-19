# Handoff: ARCH Integration Audit & Baseline (Phase 0)

## Goal
Confirm exactly how much of the new Evaluation (evaluate_universe) and Allocator (RotationStrategy + RebalanceStrategy) is wired and active in the live runner vs. legacy paths. Establish clean baseline before further changes.

## Background
- ARCH-1/2 skeletons exist and look good (evaluation.py, allocator.py).
- Runner has `use_new_allocator` flag (default False) and conditional calls.
- Legacy paths (HybridRebalancer, direct deploy_capital, old signal logging) still primary.
- Dynamic basket ~11-12 pairs from config.
- Current live activity is low (small/shadow trades).

## Tasks
1. Map all call sites in phase6_runner.py for:
   - evaluate_universe
   - create_allocator / Allocator
   - Legacy signal / rebalance paths
2. Check config for `use_new_allocator`.
3. Determine current active basket size and proposal generation in real runs.
4. Run existing isolation tests related to evaluation/allocator.
5. Produce a short audit report with evidence (which paths are live, which are shadow).

## Success Criteria
- Clear document or update to MASTER_TASK_TRACKING.md stating current integration level.
- List of gaps between planned ARCH layers and actual code paths.
- Evidence files or logs from current state.
- Recommendation on safe next step (e.g., "enable in shadow for paper testing").

## References
- phase6/core/phase6_runner.py (ARCH-4 wiring sections around lines 77-84, 135-139, 754-784, 1049+)
- phase6/core/evaluation.py
- phase6/core/allocator.py
- config/trading_config_phase6.json (global_settings / phase_6_specific)
- data/state/phase6_runner_state.json
- ARCHITECTURE_ISOLATED_COMPONENTS.md
- MASTER_TASK_TRACKING.md (ARCH-0 evidence)

## Verification
- Run the audit script or manual inspection.
- `python -c "from phase6.core... import ..."` succeeds for new modules.
- Current runner in shadow mode can produce proposals via new path when flag enabled.

## Handoff Notes
Keep scope to audit + evidence only. Do not yet change production behavior. Coordinate with aggressive logic and full wiring tasks.

Owner: crypto-bot-project Kanban
Priority: High (foundation for all subsequent ARCH work)
