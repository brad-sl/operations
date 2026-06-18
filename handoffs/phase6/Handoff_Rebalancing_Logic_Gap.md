# Handoff: Rebalancing Logic Implementation Gap (Phase 6)

**Task ID**: REBAL-001  
**Priority**: High (Material impact on backtested edge)  
**Created**: 2026-06-04  
**Owner**: TBD  
**Status**: Ready for decision & implementation

---

## Goal

Align the live Phase 6 rebalancing implementation with (or explicitly evolve from) the documented correlation-driven strategy in `docs/PHASE_6_REBALANCING.md`, which delivered **+3.3% annual outperformance** vs monthly rebalancing in backtests, primarily through better correlation risk management and dramatically lower fee drag.

---

## Background & Why This Matters

The Phase 6 rebalancing thesis was one of the **highest-impact components** in the 1-year backtest:

- Weekly correlation-triggered rebalancing beat monthly by **+3.3%**
- It beat daily by avoiding **~1.6% annual fee drag**
- Core mechanism: Detect when average pairwise correlation > 0.7 → reduce exposure to clustered pairs → park capital in reserve → redeploy via sentiment

**Current state**: The live runner uses daily time-based rebalancing with inverse-volatility allocation. While functional, it has abandoned the correlation trigger and the specific reserve-shift mechanics that drove the backtest edge.

This is not a minor drift — it changes the risk and cost profile of the strategy.

---

## Current State vs Spec

| Dimension | Documented Spec (`PHASE_6_REBALANCING.md`) | Current Implementation | Gap |
|-----------|--------------------------------------------|------------------------|-----|
| **Trigger** | Correlation > 0.7 (event-driven) | Daily at fixed time (`09:00`) | Fundamental |
| **Core Logic** | Correlation clustering + 50% allocation shift to reserve | Inverse-vol weighting + hybrid sentiment/vol filter | Fundamental |
| **Frequency** | ~52× per year | Daily (~365× per year) | High cost impact |
| **Reserve Role** | Tactical buffer fed by high-corr pairs | Static `min_reserve_usd` guard | Tactical vs static |
| **Sentiment Role** | Primary redeployment driver | One of several hybrid inputs | Diluted |
| **Correlation Code** | Specified in algorithm | `rolling_correlation.py` exists but unused in main loop | Unused asset |

---

## Must Do

1. Make an explicit decision: **Restore** the correlation-triggered approach, **Evolve** it into the hybrid rebalancer, or **Hybridize** both.
2. If restoring correlation logic:
   - Wire `rolling_correlation.py` into the decision path
   - Implement the 0.7 average correlation trigger
   - Implement the 50% allocation shift to reserve
3. Reduce rebalance frequency to something closer to weekly (or event-driven) to protect the fee advantage proven in backtesting.
4. Ensure any new rebalancing logic is **configurable** (thresholds, window, shift %, frequency) so it can be tuned and backtested.
5. Update `_run_cycle()` and `_should_rebalance()` to support the chosen trigger.

---

## Must Not Do

- Do **not** keep daily rebalancing as the default without acknowledging the fee drag risk highlighted in the spec.
- Do **not** leave `rolling_correlation.py` as dead code.
- Do **not** implement changes without updating the live state cache and dashboard so rebalance decisions are observable.
- Do **not** ignore the reserve-shift mechanic — it was central to the documented strategy.

---

## Recommended Remediation Options

### Option A: Restore Core Correlation Logic (Highest fidelity to backtest)
- Make correlation the primary trigger
- Keep hybrid filter as a secondary confirmation layer
- Target ~weekly or event-driven frequency

### Option B: Evolve Hybrid Rebalancer (Current direction)
- Formally update `PHASE_6_REBALANCING.md` to reflect the new philosophy
- Add correlation as one of the hybrid thresholds
- Accept daily frequency but add strong minimum interval guards

### Option C: Hybrid Approach (Recommended pragmatic path)
- Use correlation > 0.7 as a **strong trigger** that can force a rebalance even outside the daily window
- Keep daily as a fallback/safety net
- Use the 50% shift + sentiment redeploy mechanic when correlation spikes

---

## Success Criteria

- Rebalancing decisions are driven (at least partially) by measurable correlation regime
- Rebalance frequency is materially lower than daily (target < 100×/year or event-driven)
- `phase6_live_state.json` includes clear rebalance metadata (`last_rebalance_reason`, `avg_correlation`, `reserve_shift`)
- Dashboard shows when and why rebalances occurred
- Fee drag is visibly lower than a daily schedule would produce

---

## Files to Create / Modify

**High Priority:**
- `phase6/core/rebalancing/correlation_rebalancer.py` (or integrate into `hybrid_rebalancer.py`)
- `phase6/core/phase6_runner.py` — update `_should_rebalance()` and `_run_cycle()`

**Supporting:**
- `phase6/core/risk/rolling_correlation.py` — ensure it is production-ready
- `docs/PHASE_6_REBALANCING.md` — either implement against it or update it
- `handoffs/phase6/Handoff_Rebalancing_Logic_Gap.md` (this document)

---

## Validation Steps

1. Run the bot through a period with known high-correlation regimes and verify it triggers.
2. Compare rebalance count over 30 days vs daily baseline.
3. Confirm reserve balance changes when correlation spikes.
4. Verify Trading Intelligence Report and dashboard reflect rebalance reasons.

---

## References

- `docs/PHASE_6_REBALANCING.md` (primary spec)
- `phase6/core/rebalancing/hybrid_rebalancer.py`
- `phase6/core/risk/rolling_correlation.py`
- `phase6/core/allocation_engine.py`
- `phase6/core/phase6_runner.py` (`_should_rebalance`, `_run_cycle`)
- Backtest results cited in `PHASE_6_REBALANCING.md` (+3.3% weekly edge)

---

**Next Action**: Decide on Option A/B/C, then create a detailed implementation handoff for the chosen path. This is one of the highest-leverage remaining gaps in the Phase 6 system.