# Trading Scenario Guide: Sentiment-Enhanced Proportional Allocation

**Version**: 1.0  
**Last Updated**: 2026-05-27  
**Status**: Active Baseline

---

## 1. Trading Scenario Overview

**Scenario Name**: Sentiment-Enhanced Proportional Allocation with Liquidity Awareness

**Description**:
A medium-frequency allocation strategy for an actively managed crypto portfolio consisting of a fixed set of high-liquidity trading pairs. The strategy seeks to improve risk-adjusted returns by layering time-decayed sentiment signals on top of inverse-volatility risk parity, while strongly preferring to scale existing holdings rather than introducing new pairs.

**Core Objectives**:
- Improve ROI on capital deployed to existing trading pairs
- Maintain proportional exposure aligned with current holdings
- Incorporate real-time sentiment with appropriate decay
- Respect liquidity and withdrawal reserve constraints

---

## 2. Core Hypothesis

By combining:
- Inverse volatility base weights
- Time-decayed X sentiment (15-minute half-life)
- Liquidity bias
- Holding proportional bias (sticky scaling)

…we can generate meaningfully better risk-adjusted returns than pure inverse-volatility allocation, while staying within the constraint of only scaling existing positions.

---

## 3. Initial Test Case Being Validated

**Test Case ID**: TC-001  
**Title**: ROI Improvement via Sentiment-Enhanced Proportional Scaling on Existing Pairs

**Description**:
A trading account actively manages a fixed basket of 5 trading pairs. The goal is to determine whether applying a sentiment-enhanced allocation method (X sentiment + liquidity + holding bias) to **extra USD** produces higher ROI than simply scaling positions proportionally or using inverse-volatility alone.

**Key Constraints**:
- Only scale existing holdings (no new pair injection)
- Daily rebalancing
- Respect withdrawal reserves
- Use real historical price/volume data

**Success Metric**:
Demonstrable improvement in portfolio ROI and/or risk-adjusted returns (Sharpe, max drawdown) versus baseline inverse-volatility allocation.

---

## 4. Backtest Methodology

**Data Period**: 2025-04-20 → 2026-04-20 (365 days available)  
**Test Window**: Last 120 trading days  
**Rebalancing Frequency**: Daily  
**Starting Capital**: $10,000  
**Pairs Tested**: BTC-USD, ETH-USD, SOL-USD, XRP-USD, DOGE-USD

**Components Applied**:
1. Inverse volatility base weights (20-day lookback)
2. Liquidity bias (volume-normalized)
3. Time-decayed X sentiment overlay (current cache, 15-min half-life)
4. Holding proportional bias (0.35 strength)

**Current Limitation**:
Sentiment scores are taken from the live cache (not date-specific historical sentiment). This provides a directional signal but understates the true power of the system.

---

## 5. Current Baseline Results (as of 2026-05-27)

| Metric                    | Result     | Notes |
|---------------------------|------------|-------|
| Final Portfolio Value     | $10,945.65 | Starting $10,000 |
| Total Return              | +9.46%     | Over ~120 days |
| Sharpe Ratio (annualized) | TBD        | Requires full metrics |
| Max Drawdown              | TBD        | Requires full metrics |

**Interpretation**:
The initial lightweight historical backtest shows positive returns while applying the full sentiment + enhanced allocation pipeline. This establishes a working baseline for incremental improvement.

---

## 6. Component Contribution Framework

To measure the value of each feature, we will run the following incremental tests:

| Layer | Test Name | Description | Expected Validation |
|-------|-----------|-------------|---------------------|
| 0     | Pure Inverse Vol | Baseline | Starting point |
| 1     | + Liquidity Bias | Add volume-based liquidity adjustment | Improved stability in volatile pairs |
| 2     | + Holding Proportional Bias | Add sticky scaling to existing holdings | Reduced churn, better alignment with user preference |
| 3     | + Time-Decayed X Sentiment | Add 15-min half-life X sentiment | Measurable ROI lift during sentiment regimes |
| 4     | + Reddit Sentiment | Add 60-min half-life Reddit sentiment | Further improvement or confirmation of marginal value |
| 5     | Full Pipeline | All components active | Best expected performance |

Each layer should be run against the same historical period with identical starting conditions.

---

## 7. Validation & Success Criteria

**Minimum Success Criteria**:
- Layer 3 (X Sentiment) shows ≥ 2–3% annualized improvement over Layer 0 in risk-adjusted terms.

**Strong Success Criteria**:
- Full pipeline (Layer 5) delivers ≥ 5–8% annualized improvement with equal or lower max drawdown.

**Documentation Requirement**:
Every new backtest run must record:
- Exact parameters used
- Start/end dates
- Final equity
- Key metrics (return, Sharpe, max DD)
- Qualitative observations

---

## 8. Next Steps & Ownership

- [ ] Expand backtest to full 365-day window with proper metrics
- [ ] Add no-sentiment baseline comparison
- [ ] Implement historical sentiment snapshotting for more accurate testing
- [ ] Add withdrawal reserve enforcement
- [ ] Create automated reporting for each test layer

---

**Document Owner**: Brad  
**Review Cadence**: After every major backtest iteration

This guide serves as the single source of truth for what we are testing and how we measure incremental progress.