# Handoff: Live Deployment Prep - Phase 6 Basket + Allocator Stack (2026-07-03)

**Status:** Tested in shadow/paper; code centralizes on 11-pair basket; use_new_allocator=True; ready for --mode live --confirm-live.

**Preserved Tasks Closed (this batch):**
- centralize_basket_loader: load_trading_basket() in paths.py, used everywhere.
- update_scorer_default: DEFAULT dynamic from paths.
- patch_fetchers_runner: All use central.
- enhance_decision_tree: evaluate_universe uniform → Proposal.
- full_coverage_refresh: Multiple runs verified 11.
- verify_uniform_treatment: All 11 first-class in proposals/rebalance/plans.

**Evidence from Batch:**
- Verif script: 11 pairs, proposals=11, uniform=True.
- Shadow runs (force): allocator path, rotations, SL, 11 basket.
- Paper: multiple simulated trades.
- Config: use_new_allocator=True, full pairs.

**Live Cutover Steps:**
1. Ensure force_rebalance.flag handling and scheduler.
2. Run with: python3 phase6/core/phase6_runner.py --mode live --confirm-live (after shadow validation).
3. Monitor first cycles for proposals, allocator decisions, actual orders (expect tx IDs).
4. SL cancel-first before sells (per prior patterns).
5. Dynamic quantization in executor.

**Key Files:**
- phase6/core/phase6_runner.py (use_new_allocator, evaluate + allocator in rebalance)
- phase6/core/paths.py (load_trading_basket)
- config/trading_config.yaml (updated for live)
- scripts/run_shadow_rebalance_cycle.py (validation harness)
- run_paper.py (paper testing)

**Readiness Checklist:**
- [x] 11-pair uniform (no hardcodes in core)
- [x] New allocator primary in shadow
- [x] Multiple shadow + paper validated
- [x] Config hygiene + live_deployment section
- [ ] Real capital test (user to trigger with confirm)
- [ ] Order ID logging verified on live fills

**Next:** User to trigger live cutover after reviewing shadow logs. Update MASTER with production run results.

References: MASTER_TASK_TRACKING.md, previous Kanban cards t_64675d14 etc., phase6 handoffs.
