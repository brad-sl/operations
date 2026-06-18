# Gap Analysis: Phase 5.1 vs Current Phase 6 Implementation

**Document Type**: Strategic Gap Analysis  
**Created**: 2026-06-04  
**Author**: AI Collaborator (for Brad)  
**Purpose**: Identify features present in the Phase 5.x trading bot that were not carried forward into Phase 6, with prioritization and guidance for future handoff documents.

---

## Executive Summary

Phase 6 has significantly improved architecture (allocation engine, stop-loss coordination, dashboard caching, capital deployment). However, several **core trading signal and risk components** from the Phase 5.1 implementation were not migrated. The recent addition of `PriceHistoryManager` + RSI restored the most critical missing piece, but several valuable capabilities remain absent.

This document provides a structured gap list so that future work can be planned with clear handoff documents.

---

## Methodology

Compared the following Phase 5.1 files against the current `phase6/core/` structure:

- `phase5_multi_pair.py` + `phase5_multi_pair_FIXED.py`
- `phase5_full_spec.py`
- `phase5_scalable.py`
- `signal_generator.py`
- `src/indicators/rsi.py`
- Various backtest and harness scripts

---

## Gap Table

| # | Feature | Phase 5 Location | Current Phase 6 Status | Impact if Missing | Priority | Notes / References |
|---|---------|------------------|------------------------|-------------------|----------|--------------------|
| 1 | **Dedicated SignalGenerator** | `signal_generator.py` (`Signal` dataclass + `generate_signal`) | Not present | Signal logic is scattered; harder to test / evolve | High | Clean abstraction would improve maintainability |
| 2 | **ATR Calculation** | `phase5_full_spec.py` (`_calculate_atr`) | Missing | No volatility-adjusted position sizing or risk | High | Very useful for dynamic risk management |
| 3 | **Scenario / Regime Detection** | Multiple 5.x files + old `PHASE_6_IMPLEMENTATION_SPEC.md` | Not implemented | Static thresholds; no adaptive behavior | Medium-High | Could allow dynamic RSI buy/sell levels |
| 4 | **Reconciliation Tooling** | Mentioned in `TRADING_BOT_DOCS.md` | Not in current core | Hard to audit real vs recorded trades | Medium | Important for production hygiene |
| 5 | **Enhanced Performance / Backtest Metrics** | `phase5_full_spec.py` (`run_backtest`, `get_metrics`) | Limited (`performance_calculator.py` exists but basic) | Weak visibility into strategy performance | Medium | Would support better iteration |
| 6 | **Prometheus Metrics** | `phase5_multi_pair.py` (`_setup_prometheus_metrics`) | Not present | Reduced observability in production | Low-Medium | Nice for long-running instances |
| 7 | **PriceCache with TTL** | `phase5_scalable.py` | Replaced by `PriceHistoryManager` (persistent history) | Minor — current design is acceptable | Low | Not a regression |
| 8 | **Strict AND-gate Signal Logic** (optional) | `_determine_trade_signal` | Softened to multiplier approach | Not missing — intentional improvement | N/A | We deliberately moved away from this |

---

## Prioritized Recommendations

### Tier 1 – High Value / Core Trading Capability (Recommended Next)

1. **ATR / Volatility Module**  
   - Create `phase6/core/risk/atr_calculator.py`  
   - Integrate into allocation and position sizing  
   - Handoff candidate: High

2. **SignalGenerator Abstraction**  
   - Port and modernize `signal_generator.py` into `phase6/core/signal_generator.py`  
   - Support multiple signal sources (RSI + ATR + Sentiment)  
   - Handoff candidate: High

3. **Scenario / Regime Detector**  
   - Implement lightweight regime detection (volatility, trend, correlation)  
   - Allow dynamic adjustment of RSI thresholds or position sizes  
   - Handoff candidate: Medium-High

### Tier 2 – Production Hygiene & Observability

4. **Reconciliation Engine**  
   - Rebuild or adapt the old reconciliation tooling  
   - Compare TradeLedger vs actual Coinbase fills  
   - Handoff candidate: Medium

5. **Enhanced Performance Tracking**  
   - Expand `performance_calculator.py` with backtest-style metrics  
   - Support walk-forward style evaluation  
   - Handoff candidate: Medium

### Tier 3 – Nice-to-Haves (Lower Urgency)

6. **Prometheus Metrics Integration**  
   - Add optional Prometheus exporter to the runner  
   - Handoff candidate: Low

7. **Configurable Signal Modes**  
   - Allow switching between "Conservative AND", "Weighted", and "RSI Primary" modes via config  
   - Handoff candidate: Low

---

## Guidance for Future Handoff Documents

Each of the Tier 1 and Tier 2 items above is substantial enough to warrant its own handoff document. Recommended structure for each:

- **Goal**
- **Why it matters** (reference to Phase 5.1 behavior + current gap)
- **Files to create / modify**
- **Must Do / Must Not Do**
- **Success Criteria** (including how it appears in the dashboard / logs / reports)
- **Dependencies** (e.g., ATR should come before dynamic position sizing)
- **References** (old Phase 5 code locations + relevant docs)

---

## References

- `handoffs/phase6/Handoff_RSI_Pipeline_Restoration.md` (recent precedent)
- `docs/TRADING_BOT_DOCS.md` (Phase 6.01 architecture)
- `phase5_multi_pair.py`, `phase5_full_spec.py`, `signal_generator.py`
- `docs/PHASE_6_1_PRODUCTION_DEPLOYMENT_PLAN.md` (Section 8 now references RSI)

---

## Next Steps

1. Add prioritized tasks to `MASTER_TASK_TRACKING.md` (done in follow-up).
2. Create individual handoff documents for Tier 1 items when ready to execute.
3. Consider running a lightweight audit of the current runner against the original Phase 5.1 `run()` loop to catch any additional small gaps.

---

**Status**: Ready for task registration and future handoff creation.