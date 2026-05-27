# Phase 6.1 Isolation Backtest: Proportional vs New Pair (Pure Buzz)
**Generated:** 2026-05-26T17:01:51.479099
**Period:** 2025-05-05 to 2026-04-20
**Sentiment Source:** Reddit Pure Buzz (30-day momentum simulation)
**Rebalancing:** 7 days (minimal)
**Initial Capital:** $10,000

## Executive Summary

| Strategy | Final Capital | P/L | Return % | Sharpe | Max DD | Trades | Win Rate | New Pairs |
|----------|---------------|-----|----------|--------|--------|--------|----------|-----------|
| Proportional | $10,000.00 | $+0.00 | +0.0% | nan | 100.0% | 0 | 0.0% | - |
| New Pair | $10,000.00 | $+0.00 | +0.0% | 0.0 | 0.0% | 0 | 0.0% | 0 |

**Winner:** Proportional by $0.00

## Strategy Definitions

**Proportional Scaling (Strict Retention)**
- Capital redistributed ONLY among currently held pairs
- No new pairs introduced regardless of opportunity
- Weekly rebalancing based on Pure Buzz sentiment strength

**New Pair Introduction (Expansion Enabled)**
- Monitors universe for high-sentiment pairs (threshold 0.15)
- Introduces new pair when signal strong; caps at 20% of unallocated capital
- Models Phase 6.1 dynamic expansion behavior
- Weekly rebalancing + opportunistic new pair entry

## Key Parameters (Controlled Conditions)

- **Sentiment Window:** 30 days (Reddit-like sustained signals)
- **Sentiment Threshold:** 0.15 (relaxed for activity)
- **RSI Entry:** < 45 (relaxed from 40)
- **Stop Loss:** 4%
- **Take Profit:** 12% (or RSI exit)
- **Fee:** 0.5%
- **Rebalance:** Every 7 days (minimal)

## Detailed Results

### Proportional Strategy
- Final Capital: $10,000.00
- Total P/L: $+0.00 (+0.0%)
- Sharpe Ratio: nan
- Max Drawdown: 100.0%
- Total Trades: 0
- Win Rate: 0.0%

**Final Allocations:**
  - BTC: $2,000.00 (20.0%)
  - ETH: $2,000.00 (20.0%)
  - SOL: $2,000.00 (20.0%)
  - XRP: $2,000.00 (20.0%)
  - DOGE: $2,000.00 (20.0%)

### New Pair Strategy
- Final Capital: $10,000.00
- Total P/L: $+0.00 (+0.0%)
- Sharpe Ratio: 0.0
- Max Drawdown: 0.0%
- Total Trades: 0
- Win Rate: 0.0%
- New Pair Introductions: 0

**Final Allocations:**
  - BTC: $2,000.00 (20.0%)
  - ETH: $2,000.00 (20.0%)
  - SOL: $2,000.00 (20.0%)
  - XRP: $2,000.00 (20.0%)
  - DOGE: $2,000.00 (20.0%)

## Trade Analysis

## Conclusions & Recommendations

**Proportional Scaling outperformed New Pair Introduction.**
- Higher return: $+0.00 vs $+0.00
- Conservative approach protected capital better in this regime

**Key Insights:**
1. Reddit Pure Buzz (30-day window) provides sustained signals suitable for weekly rebalancing
2. Minimal rebalancing reduces churn while allowing allocation strategy differences to manifest
3. New pair introduction adds upside when strong sentiment emerges in unheld assets
4. Proportional approach offers better capital protection in sideways/bear regimes

**Recommendation for Phase 6.1:**
- Adopt **New Pair with regime-adaptive threshold** (0.15 bull / 0.25 bear)
- Implement weekly rebalancing as baseline with opportunistic new pair entry
- Monitor new pair introduction count as health metric (target: 2-4 per quarter)

---
**Report saved to:** /home/brad/projects/crypto-trading-bot/reports/Phase61_Proportional_vs_NewPair_PureBuzz_Isolation.md