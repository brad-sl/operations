# Sentiment Source + Allocation Strategy Isolation Backtest

**Generated:** 2026-05-26T23:38:01.858692Z
**Period:** 2025-05-05 to 2026-04-20

## Objective

Controlled backtest to isolate which variable caused the -31% performance drop:

- **Core Comparison:** Proportional scaling vs New Pair Introduction
- **Variables Tested:** Reddit Pure Buzz signal vs X (Twitter) sentiment signal
- **Goal:** Determine whether sentiment source or allocation strategy was the main driver

## Fixed Parameters (Consistent Across All Tests)

- RSI Period: 11
- RSI Entry Threshold: < 40
- Stop Loss: 3% fixed
- Take Profit: Let-it-ride (no TP)
- Initial Capital per Pair: $1000
- Pairs Tested: BTC, ETH, SOL, XRP, DOGE

## Sentiment Source Definitions

**Reddit Pure Buzz:**
- 30-day momentum window
- Slower moving, more sustained signals
- Lower noise floor
- Previously performed well in isolation

**X Sentiment:**
- 7-day momentum window
- Faster moving, more volatile signals
- Higher noise characteristic of social media

## Allocation Strategy Definitions

**Proportional Scaling:**
- Position size scaled by combined signal strength (RSI + sentiment)
- Signal strength determines allocation (10%-50% of capital)

**New Pair Introduction:**
- Binary entry: Full allocation (50% of capital) on signal trigger
- No position sizing based on signal strength

## Results Summary

| Configuration | Sentiment Source | Allocation | Total P&L (USD) | Avg P&L % | Total Trades | Win Rate |
|---------------|------------------|------------|-----------------|-----------|--------------|----------|
| reddit_pure_buzz_proportional | reddit_pure_buzz | proportional | $0.00 | 0.00% | 0 | 0.0% |
| reddit_pure_buzz_new_pair | reddit_pure_buzz | new_pair | $0.00 | 0.00% | 0 | 0.0% |
| x_sentiment_proportional | x_sentiment | proportional | $-26.79 | -0.54% | 3 | 0.0% |
| x_sentiment_new_pair | x_sentiment | new_pair | $-39.90 | -0.80% | 2 | 0.0% |

## Key Findings

**Best Configuration:** reddit_pure_buzz_proportional ($0.00)
**Worst Configuration:** x_sentiment_new_pair ($-39.90)

**Reddit Pure Buzz - Allocation Impact:** $0.00 (Proportional better)
**X Sentiment - Allocation Impact:** $13.11 (Proportional better)

## Per-Pair Breakdown

### reddit_pure_buzz_proportional

- BTC: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- ETH: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- SOL: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- XRP: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- DOGE: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%

### reddit_pure_buzz_new_pair

- BTC: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- ETH: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- SOL: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- XRP: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- DOGE: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%

### x_sentiment_proportional

- BTC: $-9.04 (-0.9%) | 1 trades | Win: 0.0% | Max DD: 0.9%
- ETH: $-9.07 (-0.9%) | 1 trades | Win: 0.0% | Max DD: 0.9%
- SOL: $-8.68 (-0.9%) | 1 trades | Win: 0.0% | Max DD: 0.9%
- XRP: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- DOGE: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%

### x_sentiment_new_pair

- BTC: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- ETH: $-19.95 (-2.0%) | 1 trades | Win: 0.0% | Max DD: 2.0%
- SOL: $-19.95 (-2.0%) | 1 trades | Win: 0.0% | Max DD: 2.0%
- XRP: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%
- DOGE: $0.00 (0.0%) | 0 trades | Win: 0.0% | Max DD: 0.0%

## Conclusion

This isolation test reveals the relative contribution of sentiment source vs allocation strategy to overall performance. The configuration with the highest P&L indicates the optimal combination for the tested period.

**Recommendation:** Deploy the best-performing configuration (sentiment source + allocation strategy) to Phase 6 live runner for validation.
