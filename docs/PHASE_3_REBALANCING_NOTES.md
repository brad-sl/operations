# Phase 3 Rebalancing Design — Strategic Notes

**Date:** 2026-03-27 14:08 PDT  
**Status:** Planning (not yet implemented)  
**Priority:** High (potential 2x+ return multiplier)

---

## Strategic Insight

Brad's observation: "Done properly, rebalancing could more than double returns."

This is the next major lever after dynamic RSI thresholds.

---

## Current State

**Phase 3 Dynamic RSI (Live):**
- Win rate: 45% → 58% (+13 pts)
- P&L: +$216 → +$486 (+124%)
- Sharpe: 0.61 → 1.04 (+71%)

**Rebalancing opportunity:** Apply portfolio-level allocation strategy on top of per-pair trading logic.

---

## Key Rebalancing Concepts to Explore

1. **Portfolio Allocation (Not Yet Designed)**
   - How much capital to BTC vs XRP at any given time?
   - Should allocation shift based on regime?
   - Momentum rebalancing (follow winners) vs contrarian (rotate to losers)?

2. **Compounding Effect**
   - Current: Each pair trades independently
   - Rebalancing: Shift capital from underperforming to outperforming pair
   - Expected amplification: 2x+ over baseline

3. **Regime-Aware Allocation**
   - Downtrend: Reduce overall exposure, tighten positions
   - Uptrend: Increase exposure, follow momentum
   - Sideways: Balanced allocation

4. **Risk Management in Rebalancing**
   - Correlation between BTC and XRP (tend to move together)
   - Diversification benefit (may be limited)
   - Drawdown protection via allocation shifts

---

## Next Steps (When Ready)

1. **Backtest rebalancing strategies:**
   - Fixed allocation (60/40 BTC/XRP)
   - Dynamic allocation based on win rates
   - Momentum rebalancing (follow outperformers)
   - Regime-adjusted allocation

2. **Measure impact:**
   - Sharpe ratio with rebalancing vs without
   - Max drawdown improvements
   - Return amplification (target: 2x+)

3. **Implement in Phase 4:**
   - If backtest validates, deploy to live $1K trading
   - Monitor rebalancing trades separately
   - A/B test vs static allocation

---

## Documentation References

- `DYNAMIC_RSI_STRATEGY.md` — Current baseline (RSI + sentiment)
- `DYNAMIC_VS_STATIC_BACKTEST.json` — Baseline metrics (Sharpe 1.04)
- `phase3_v4.py` — Current orchestrator (ready for rebalancing layer)

---

## Decision Log

**2026-03-27 14:08 PDT**
- Brad: "We will [implement rebalancing] when we get to the rebalancing design."
- Brad: "If that's done properly I could see it more than doubling returns."
- Decision: Defer detailed rebalancing design until after Phase 3 completes
- Rationale: Dynamic RSI is working; rebalancing is secondary optimization
- Target: 2x return multiplier as success threshold
