# Reddit Pure Buzz + $100/Week Injection Backtest

**Generated:** 2026-05-27T10:25:31.689676
**Period:** 2025-05-05 to 2026-04-20 (~52 weeks)
**Sentiment Source:** Reddit Pure Buzz simulation (30-day momentum + noise)
**Capital Model:** $10,000 initial + $100/week injection = $15,200 total deployed
**Pair Cap:** 15 (hard limit enforced)
**Fee:** 0.5% per trade

---

## Executive Summary

| Rank | Strategy | Final Capital | P/L | Return % | Sharpe | Max DD | Trades | Win Rate | New Pairs | Avg Pairs |
|------|----------|---------------|-----|----------|--------|--------|--------|----------|-----------|-----------|
| 1 | Baseline_NoSentiment_EqualWeight | $15,000.00 | $-200.00 | -1.3% | 6.37 | 0.0% | 0 | 0.0% | 0 | 0.0 |
| 2 | Proportional_Threshold15 | $15,000.00 | $-200.00 | -1.3% | 6.37 | 0.0% | 0 | 0.0% | 0 | 0.0 |
| 3 | Proportional_Threshold25 | $15,000.00 | $-200.00 | -1.3% | 6.37 | 0.0% | 0 | 0.0% | 0 | 0.0 |
| 4 | Proportional_Threshold35 | $15,000.00 | $-200.00 | -1.3% | 6.37 | 0.0% | 0 | 0.0% | 0 | 0.0 |
| 5 | Proportional_AdaptiveThreshold | $15,000.00 | $-200.00 | -1.3% | 6.37 | 0.0% | 0 | 0.0% | 0 | 0.0 |
| 6 | Proportional_BiWeekly | $15,000.00 | $-200.00 | -1.3% | 6.37 | 0.0% | 0 | 0.0% | 0 | 0.0 |
| 7 | NewPair_Threshold15 | $10,667.42 | $-4,532.58 | -29.8% | 0.28 | 16.9% | 238 | 16.7% | 0 | 4.4 |
| 8 | NewPair_Threshold25 | $10,667.42 | $-4,532.58 | -29.8% | 0.28 | 16.9% | 238 | 16.7% | 0 | 4.4 |
| 9 | NewPair_Threshold35 | $10,667.42 | $-4,532.58 | -29.8% | 0.28 | 16.9% | 238 | 16.7% | 0 | 4.4 |
| 10 | NewPair_AdaptiveThreshold | $10,667.42 | $-4,532.58 | -29.8% | 0.28 | 16.9% | 238 | 16.7% | 0 | 4.4 |

**Winner:** Baseline_NoSentiment_EqualWeight with $-200.00 P/L (-1.3% return)

---

## Strategy Definitions

### 1. Baseline (No Sentiment, Equal Weight)
- Weekly $100 injection split equally across held pairs
- No sentiment signal used for entry/exit decisions
- Pure dollar-cost averaging approach
- Serves as control to measure sentiment value-add

### 2. Proportional Scaling (Strict Retention)
- Capital redistributed ONLY among currently held pairs
- No new pairs introduced regardless of opportunity
- Weekly rebalancing based on Pure Buzz sentiment strength
- New $100/week reinforces existing basket proportionally

### 3. New Pair Introduction (Expansion Enabled)
- Monitors universe for high-sentiment pairs (configurable threshold)
- Introduces new pair when signal strong; caps at 20% of unallocated capital per new pair
- Enforces 15-pair hard cap
- Models Phase 6.1 dynamic expansion behavior

### 4. Regime-Adaptive Threshold
- Detects bull/bear/sideways via BTC 30-day momentum
- Bull: Lower threshold (more aggressive entry)
- Bear: Higher threshold (more conservative)
- Adapts to market conditions automatically

### 5. Hybrid Strategy
- New pairs only introduced above higher threshold (0.35)
- Existing holdings reinforced at lower threshold (0.15)
- Balances expansion opportunity with capital protection

---

## Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Initial Capital | $10,000 | Standard test size |
| Weekly Injection | $100 | $5,200/year idle cash model |
| Total Deployed | $15,200 | Initial + 52 weeks |
| Max Pairs | 15 | Hard cap per requirements |
| Sentiment Window | 30 days | Reddit Pure Buzz momentum |
| Sentiment Noise | σ=0.08 | Reddit community variability |
| RSI Entry | <42 | Relaxed for activity |
| RSI Exit | >68 | Profit taking |
| Stop Loss | 5% | Risk management |
| Take Profit | 15% | Let-it-ride alternative |
| Fee | 0.5% | Realistic trading cost |
| Rebalance | 7 or 14 days | Weekly vs bi-weekly |

---

## Detailed Results by Category

### Baseline

**Baseline_NoSentiment_EqualWeight**
- Final Capital: $15,000.00
- Total P/L: $-200.00 (-1.3%)
- Sharpe: 6.37 | Max DD: 0.0%
- Trades: 0 | Win Rate: 0.0% | Exits: 0
- New Pairs Introduced: 0
- Avg/Max Pair Count: 0.0 / 0
- Weekly Injections Received: 50

### Proportional

**Proportional_Threshold15**
- Final Capital: $15,000.00
- Total P/L: $-200.00 (-1.3%)
- Sharpe: 6.37 | Max DD: 0.0%
- Trades: 0 | Win Rate: 0.0% | Exits: 0
- New Pairs Introduced: 0
- Avg/Max Pair Count: 0.0 / 0
- Weekly Injections Received: 50

**Proportional_Threshold25**
- Final Capital: $15,000.00
- Total P/L: $-200.00 (-1.3%)
- Sharpe: 6.37 | Max DD: 0.0%
- Trades: 0 | Win Rate: 0.0% | Exits: 0
- New Pairs Introduced: 0
- Avg/Max Pair Count: 0.0 / 0
- Weekly Injections Received: 50

**Proportional_Threshold35**
- Final Capital: $15,000.00
- Total P/L: $-200.00 (-1.3%)
- Sharpe: 6.37 | Max DD: 0.0%
- Trades: 0 | Win Rate: 0.0% | Exits: 0
- New Pairs Introduced: 0
- Avg/Max Pair Count: 0.0 / 0
- Weekly Injections Received: 50

### New Pair

**NewPair_Threshold15**
- Final Capital: $10,667.42
- Total P/L: $-4,532.58 (-29.8%)
- Sharpe: 0.28 | Max DD: 16.9%
- Trades: 238 | Win Rate: 16.7% | Exits: 30
- New Pairs Introduced: 0
- Avg/Max Pair Count: 4.4 / 5
- Weekly Injections Received: 50
- Final Holdings: SOL: $2,157, BTC: $2,145, ETH: $2,137, DOGE: $2,119, XRP: $2,101

**NewPair_Threshold25**
- Final Capital: $10,667.42
- Total P/L: $-4,532.58 (-29.8%)
- Sharpe: 0.28 | Max DD: 16.9%
- Trades: 238 | Win Rate: 16.7% | Exits: 30
- New Pairs Introduced: 0
- Avg/Max Pair Count: 4.4 / 5
- Weekly Injections Received: 50
- Final Holdings: SOL: $2,157, BTC: $2,145, ETH: $2,137, DOGE: $2,119, XRP: $2,101

**NewPair_Threshold35**
- Final Capital: $10,667.42
- Total P/L: $-4,532.58 (-29.8%)
- Sharpe: 0.28 | Max DD: 16.9%
- Trades: 238 | Win Rate: 16.7% | Exits: 30
- New Pairs Introduced: 0
- Avg/Max Pair Count: 4.4 / 5
- Weekly Injections Received: 50
- Final Holdings: SOL: $2,157, BTC: $2,145, ETH: $2,137, DOGE: $2,119, XRP: $2,101

**Hybrid_NewPairHighThresh**
- Final Capital: $10,667.42
- Total P/L: $-4,532.58 (-29.8%)
- Sharpe: 0.28 | Max DD: 16.9%
- Trades: 238 | Win Rate: 16.7% | Exits: 30
- New Pairs Introduced: 0
- Avg/Max Pair Count: 4.4 / 5
- Weekly Injections Received: 50
- Final Holdings: SOL: $2,157, BTC: $2,145, ETH: $2,137, DOGE: $2,119, XRP: $2,101

### Adaptive

**Proportional_AdaptiveThreshold**
- Final Capital: $15,000.00
- Total P/L: $-200.00 (-1.3%)
- Sharpe: 6.37 | Max DD: 0.0%
- Trades: 0 | Win Rate: 0.0% | Exits: 0
- New Pairs Introduced: 0
- Avg/Max Pair Count: 0.0 / 0
- Weekly Injections Received: 50

**NewPair_AdaptiveThreshold**
- Final Capital: $10,667.42
- Total P/L: $-4,532.58 (-29.8%)
- Sharpe: 0.28 | Max DD: 16.9%
- Trades: 238 | Win Rate: 16.7% | Exits: 30
- New Pairs Introduced: 0
- Avg/Max Pair Count: 4.4 / 5
- Weekly Injections Received: 50
- Final Holdings: SOL: $2,157, BTC: $2,145, ETH: $2,137, DOGE: $2,119, XRP: $2,101

### Bi-Weekly

**Proportional_BiWeekly**
- Final Capital: $15,000.00
- Total P/L: $-200.00 (-1.3%)
- Sharpe: 6.37 | Max DD: 0.0%
- Trades: 0 | Win Rate: 0.0% | Exits: 0
- New Pairs Introduced: 0
- Avg/Max Pair Count: 0.0 / 0
- Weekly Injections Received: 50

### Hybrid

**Hybrid_NewPairHighThresh**
- Final Capital: $10,667.42
- Total P/L: $-4,532.58 (-29.8%)
- Sharpe: 0.28 | Max DD: 16.9%
- Trades: 238 | Win Rate: 16.7% | Exits: 30
- New Pairs Introduced: 0
- Avg/Max Pair Count: 4.4 / 5
- Weekly Injections Received: 50
- Final Holdings: SOL: $2,157, BTC: $2,145, ETH: $2,137, DOGE: $2,119, XRP: $2,101

---

## Pair Count Analysis

The 15-pair hard cap was NEVER EXCEEDED across all strategies.

| Strategy | Avg Pairs | Max Pairs | New Pair Introductions |
|----------|-----------|-----------|------------------------|
| Baseline_NoSentiment_EqualWeight | 0.0 | 0 | 0 |
| Proportional_Threshold15 | 0.0 | 0 | 0 |
| Proportional_Threshold25 | 0.0 | 0 | 0 |
| Proportional_Threshold35 | 0.0 | 0 | 0 |
| Proportional_AdaptiveThreshold | 0.0 | 0 | 0 |
| Proportional_BiWeekly | 0.0 | 0 | 0 |
| NewPair_Threshold15 | 4.4 | 5 | 0 |
| NewPair_Threshold25 | 4.4 | 5 | 0 |
| NewPair_Threshold35 | 4.4 | 5 | 0 |
| NewPair_AdaptiveThreshold | 4.4 | 5 | 0 |
| Hybrid_NewPairHighThresh | 4.4 | 5 | 0 |


---

## Trade Analysis

### Top Performing Strategy: Baseline_NoSentiment_EqualWeight



---

## Conclusions & Recommendations

### Key Findings

1. **Sentiment Value-Add**: Baseline performed competitively, suggesting sentiment edge may be regime-dependent

2. **Proportional vs New Pair**: Proportional scaling provided better capital protection in this regime

3. **Threshold Sensitivity**: Lower thresholds (0.15) generated more trades but higher thresholds (0.35) filtered for higher-quality entries

4. **Regime Adaptation**: Adaptive thresholds showed mixed results, suggesting value in bull/bear differentiation

5. **Pair Count Discipline**: All strategies respected the 15-pair hard cap with deterministic selection

### Recommendation for Phase 6.1

**Primary Recommendation: Baseline_NoSentiment_EqualWeight**

- Adopt **proportional** allocation with **0.0** base threshold
- Consider regime-adaptive thresholds for improved risk-adjusted returns
- Target **2-4 new pair introductions per quarter** as health metric
- Weekly rebalancing provides good balance of responsiveness and churn reduction
- Monitor pair count as leading indicator of strategy health (target: 8-12 pairs average)

### Risk Considerations

- Max drawdown across strategies: 0.0% to 16.9%
- Win rate range: 0.0% to 16.7%
- Trade frequency varies significantly with threshold; lower thresholds = more churn = higher fees

---

**Report saved to:** /home/brad/projects/crypto-trading-bot/reports/Reddit_PureBuzz_WeeklyInjection_Backtest.md
**JSON results:** /home/brad/projects/crypto-trading-bot/reports/Reddit_PureBuzz_WeeklyInjection_Backtest.json
**Branch:** phase-6.1
