# Phase 6 Single Source of Truth Audit
**Date:** 2026-05-18  
**Purpose:** Establish definitive sources for all major Phase 6 components to prevent future regressions and overwrites.

## Audit Summary

After reviewing code, docs, and backup files, the project has significant fragmentation. Multiple files implement similar functionality with varying degrees of completeness.

---

## 1. Rebalancing & Forced Deployment

| Component                        | Best Source                                      | Status          | Recommendation |
|----------------------------------|--------------------------------------------------|-----------------|----------------|
| Correlation Rebalancing Logic    | `docs/PHASE_6_REBALANCING.md`                    | Excellent       | Make authoritative spec |
| Rebalance Implementation         | `scripts/phase6_runner.py` (`_perform_daily_rebalance`) | Good            | Promote as reference implementation |
| Inverse Volatility Allocation    | `src/core/allocation_engine.py`                  | Solid           | Keep as canonical module |
| Fresh Start Deployment           | `scripts/phase6_runner.py` (`_handle_fresh_start`) | Good            | Use as baseline |
| Weekly Rebalance Trigger         | `docs/PHASE_5_1_REBALANCE_FEATURE_SPEC.md`       | Excellent       | Adopt thresholds & logic |

**Winner for Rebalancing:** `scripts/phase6_runner.py` + supporting docs in `PHASE_6_REBALANCING.md`

---

## 2. Basket Management & Dynamic Selection

| Component                        | Best Source                                      | Status       | Recommendation |
|----------------------------------|--------------------------------------------------|--------------|----------------|
| Dynamic Basket Logic             | `coin_selector.py` + `dynamic_backtest.py`       | Good         | Extract into `basket_manager.py` |
| Fixed vs Dynamic Basket Config   | `docs/PHASE6.md`                                 | Clear        | Use as reference |
| Sentiment-Adjusted Weights       | `scripts/phase6_runner.py` (uses `sentiment_scorer`) | Implemented | Keep pattern |

---

## 3. Scenario Detection (Fresh Start / Takeover)

| Component                        | Best Source                                      | Status          | Recommendation |
|----------------------------------|--------------------------------------------------|-----------------|----------------|
| Scenario Detection + Init        | `PHASE_6_IMPLEMENTATION_SPEC.md`                 | Well documented | Restore into `scenario_detector.py` |
| Fresh Start Handler              | `scripts/phase6_runner.py`                       | Working         | Keep and improve |
| Account State Detection          | Older `phase6_account_initializer.py` (archived) | Lost            | Re-implement from spec |

---

## 4. Current Runner Comparison

| File                              | Quality | Features Included                          | Recommendation |
|-----------------------------------|---------|--------------------------------------------|----------------|
| `scripts/phase6/phase6.py`        | Medium  | Strong observability, weak strategy        | Deprecate or merge into runner |
| `scripts/phase6_runner.py`        | High    | Fresh Start + Daily Rebalance + Config     | **Promote as primary runner** |
| `PHASE_6_TASK_0_REBALANCING_CODE.py` | Medium | Task-specific rebalancing code             | Archive after integration |

---

## 5. Recommended Canonical Sources (Going Forward)

| Feature Area                     | Single Source of Truth File                          | Notes |
|----------------------------------|------------------------------------------------------|-------|
| Main Orchestrator                | `scripts/phase6_runner.py`                           | Most complete recent implementation |
| Allocation & Rebalancing         | `src/core/allocation_engine.py`                      | Keep and import from here |
| Rebalancing Strategy             | `docs/PHASE_6_REBALANCING.md`                        | Authoritative design doc |
| Fresh Start / Scenario Logic     | `docs/PHASE_6_IMPLEMENTATION_SPEC.md`                | Restore implementation from this |
| Dynamic Basket                   | `coin_selector.py`                                   | Extract into Phase 6 module |
| Configuration                    | `config/trading_config_phase6.json`                  | Already good |
| Observability & Logging          | `scripts/phase6/logging_config.py` + `telegram_alerts.py` | Keep |

---

## 6. Action Plan

1. **Designate `scripts/phase6_runner.py`** as the primary Phase 6 entry point.
2. **Create** `phase6/core/` directory and move/adapt the best modules there.
3. **Update** `PHASE6_REINTEGRATION_PLAN.md` with the above Single Source table.
4. **Archive** conflicting older files (`phase6.py` in scripts/phase6, backup files, etc.).
5. **Add version headers** to all canonical files.

---

**Status:** Audit complete. Ready for implementation phase.