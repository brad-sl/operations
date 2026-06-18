# Pair Selection Decision Matrix (Phase 6)

**Status:** Proposed  
**Date:** 2026-06-05  
**Owner:** Brad  
**Related:** P6-HC-02 (rebalance cap scope), Hybrid Rebalancer, `deploy_capital.py`

## Philosophy

The goal is to build a **volatility-driven, market-timing-resilient** system that can generate returns through both longs and shorts across a diverse set of pairs. The system should favor **proactive** opportunity capture over reactive cash deployment, while maintaining strong diversification.

Key principles:
- Prioritize **volatility** as a core selection signal.
- Maintain **segment and correlation diversity**.
- Keep the matrix simple enough to backtest reliably (complication = fragility).
- Support both long and short sides symmetrically where possible.

## Candidate Universe

- **Size**: 10–20 trading pairs
- **Source**: Static list in config (initially), with potential for periodic refresh based on volume/volatility
- **Segments** (target diversity): Layer-1, DeFi, Meme, AI/Infrastructure, Payments, Gaming, RWA, etc.

## Long-Side Selection Matrix

A pair is considered for addition (or increased allocation) if it meets **all** of the following:

| Filter                        | Threshold                          | Notes |
|------------------------------|------------------------------------|-------|
| **Volatility**               | Top 40–60% of candidate universe   | Measured by 30-day realized volatility or ATR |
| **Correlation**              | ≤ 0.70 with any currently held pair | Prevents cluster risk |
| **Sentiment**                | ≥ +0.15                            | Time-decayed sentiment from unified cache |
| **RSI (15m or 1h)**          | 25 – 75                            | Avoids extreme oversold/overbought |
| **Min New Pair Sentiment**   | ≥ +0.20                            | Stricter gate from `deploy_capital.py` |
| **Liquidity**                | 24h volume > $50M (configurable)   | Ensures tradability |
| **Segment Limit**            | Max 2–3 pairs per segment          | Enforces diversity |

## Short-Side Selection Matrix

Symmetric to the long side, with inverted signals:

| Filter                        | Threshold                          | Notes |
|------------------------------|------------------------------------|-------|
| **Volatility**               | Top 40–60% of candidate universe   | Same as long side |
| **Correlation**              | ≤ 0.70 with any currently held short | Avoid short clusters |
| **Sentiment**                | ≤ -0.15                            | Negative sentiment |
| **RSI (15m or 1h)**          | 25 – 75                            | Same guardrails |
| **Max New Pair Sentiment**   | ≤ -0.20                            | Stricter negative gate |
| **Liquidity**                | 24h volume > $50M                  | Same |
| **Segment Limit**            | Max 2–3 pairs per segment          | Same |

## Additional Rules

- **Rebalance Cap Interaction**: When using the broad interpretation of `rebalance_cap_usd`, both new pair additions and reductions count toward the total reallocation budget.
- **"Let It Ride" Alignment**: New pairs added under this matrix are expected to be held longer-term. Take-profit logic remains disabled by default.
- **Minimum Holding Period** (optional future): Consider a 7–14 day minimum hold before considering rotation out of a newly added pair.

## Backtesting Requirements

Before implementation, the following comparisons should be run:

1. Current Hybrid Rebalancer (5-pair fixed universe) vs. Expanded matrix with 10–15 pairs.
2. Narrow vs. Broad `rebalance_cap_usd` scope under the new matrix.
3. Impact of correlation filter (with vs without 0.7 threshold).
4. Long-only vs. Long/Short versions of the matrix.
5. Multiple market regimes (bull, bear, sideways, high-vol).

**Guiding principle**: Only add complexity if backtests show a clear, persistent edge that justifies the increased fragility.

## Next Steps

- [ ] Finalize candidate universe list (10–20 pairs)
- [ ] Implement matrix as a reusable function (`select_opportunistic_pairs`)
- [ ] Wire into `HybridRebalancer` and/or `Phase6Runner`
- [ ] Run backtests on historical data
- [ ] Decide on narrow vs broad rebalance cap behavior

---

*This matrix is intentionally conservative. The priority is robustness and backtestability over maximum theoretical returns.*

---

## Final Pair Selection & Ranking (Post-Filter)

After the matrix filters are applied, the following logic is used to make the final selection from the qualified pool:

### Composite Scoring

Each eligible pair receives a score:

```python
score = (
    0.35 * normalized_volatility +           # Primary driver
    0.30 * sentiment_strength +              # Absolute value for long/short
    0.20 * inverse_correlation_score +       # Rewards diversification
    0.15 * rsi_quality                       # Centered RSI preferred
)
```

### Selection Rules

| Situation                        | Behavior |
|----------------------------------|----------|
| Idle cash available              | Select top 1–2 highest-scoring pairs |
| Considering rotation             | Compare new candidate score vs weakest current holding |
| No strong candidates             | Hold cash (respect rebalance cap + Let It Ride) |
| Tie between candidates           | Break by liquidity volume, then segment diversity |

### Constraints

- Maximum **1 new pair** added per rebalance cycle (conservative default)
- Maximum **2–3 pairs per segment** across the entire portfolio
- Skip any addition that would push portfolio-level correlation too high

---

## Volatility in This Matrix

**Volatility is treated primarily as an opportunity signal**, not just risk.

### Why it is weighted heavily (0.35)

- The original design goal was a **volatility-driven system** that can profit from larger price moves without requiring precise market timing.
- Higher volatility pairs tend to produce bigger swings. When combined with sentiment and correlation filters, these swings can be captured on both the long and short side.
- In backtesting, volatility has shown a positive relationship with profit potential in this style of system.

### Important caveats

- Volatility is **not** free upside. It increases both profit *and* drawdown potential.
- The matrix balances it with:
  - Correlation limits (to avoid clustered risk)
  - Sentiment gates (to avoid low-conviction volatile pairs)
  - RSI guardrails (to avoid extreme conditions)
- In practice, the system is looking for **"good volatility"** — volatile pairs with supportive sentiment and reasonable diversification — rather than the most volatile pair available.

This is why the 0.35 weight on volatility is balanced by the other factors rather than being used in isolation.
