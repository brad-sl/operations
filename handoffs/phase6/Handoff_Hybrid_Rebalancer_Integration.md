# Handoff: Hybrid Rebalancer Integration into Phase 6 Runner

**Task ID**: REBAL-002  
**Priority**: High  
**Created**: 2026-06-04  
**Status**: Ready for implementation

---

## Goal

Integrate the existing `HybridRebalancer` into `phase6/core/phase6_runner.py` as the primary rebalancing engine, replacing the current daily time-based logic. This formalizes the approach that delivered +159% P&L with only 27 rebalances in the 12-month backtest.

---

## Background

- `phase6/core/rebalancing/hybrid_rebalancer.py` already contains a production-grade `HybridRebalancer` class.
- Current runner (`phase6_runner.py`) uses simple daily time-based rebalancing (`_should_rebalance`).
- Backtest confirmed the Hybrid approach significantly outperforms both pure correlation and daily inverse-vol strategies.

---

## Must Do

1. Import `HybridRebalancer` and `RebalanceDecision` in `phase6_runner.py`.
2. Initialize `HybridRebalancer` in `__init__`.
3. Replace or augment `_should_rebalance()` to use `HybridRebalancer.should_rebalance()`.
4. Call the rebalancer inside `_run_cycle()` when triggered.
5. Log rebalance decisions with reason, confidence, and suggested actions.
6. Write rebalance metadata to `phase6_live_state.json` (last reason, correlation if available, etc.).
7. Respect the minimum interval (`min_rebalance_interval_hours`).

---

## Must Not Do

- Do not remove the existing daily fallback entirely until the hybrid is proven stable in shadow mode.
- Do not ignore the `ai_filter_enabled` and `ai_confidence_threshold` settings.
- Do not bypass the existing `deploy_capital` or allocation engine flows.

---

## Integration Points

**File**: `phase6/core/phase6_runner.py`

- Add import after other core imports
- Initialize in `__init__` after `self.config`
- Modify `_should_rebalance(self, now)` or create `_evaluate_hybrid_rebalance()`
- Update `_run_cycle()` to act on `RebalanceDecision`
- Enhance `_write_dashboard_cache()` with rebalance metadata

---

## Success Criteria

- Runner uses `HybridRebalancer` for rebalance decisions in both shadow and live mode.
- Rebalance events include clear `reason` and `confidence` in logs and dashboard cache.
- Rebalance frequency drops significantly vs daily (target < 60/year in normal conditions).
- No regression in existing capital deployment or stop-loss flows.

---

## Files to Modify

- `phase6/core/phase6_runner.py` (primary)
- `phase6/core/rebalancing/hybrid_rebalancer.py` (minor config tweaks if needed)
- `docs/PHASE_6_REBALANCING.md` (already updated)

---

## Validation Steps

1. Run in shadow mode for 7–14 days and review rebalance decisions.
2. Confirm rebalance reasons appear in `phase6_live_state.json` and dashboard.
3. Verify fee impact is lower than daily rebalancing.
4. Confirm no duplicate or conflicting rebalance logic remains.

---

**References**
- `phase6/core/rebalancing/hybrid_rebalancer.py`
- `docs/PHASE_6_REBALANCING.md` (updated section)
- Backtest results in `backtests/capital_allocation/rebalancing_strategy_comparison.py`