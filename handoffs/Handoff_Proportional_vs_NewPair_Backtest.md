# Handoff Document: Proportional vs New Pair Capital Allocation Backtest

**Task ID:** t_2ac55a75  
**Goal:** Determine which method of deploying unallocated USD produces higher returns under controlled conditions.

## Objective

Run a clean, isolated backtest comparing two capital deployment methods:

1. **Proportional Scaling** — Spread new/unallocated USD across existing pairs according to current rebalanced weights.
2. **New Pair Introduction** — Use new/unallocated USD to add a new high-sentiment pair.

## Fixed Parameters (Must Stay Constant)

- **Sentiment Source**: Reddit Pure Buzz (post volume + velocity). This is the only signal that previously produced positive results.
- **Rebalancing**: Minimal or disabled (to match conditions of the successful earlier test).
- **Time Period**: Use the same 350-day window as the previous successful Pure Buzz test where possible.
- **Pairs Universe**: Same 5 pairs used in prior successful test.
- **Fees**: Use realistic trading fees.

## Variable Being Tested

Only the capital deployment method should change between the two runs.

## Success Metrics (Report All)

- Total Return (%)
- Sharpe Ratio
- Maximum Drawdown
- Number of Trades
- Win Rate
- Average Holding Period

## Deliverables

1. Full backtest code (committed to `phase-6.1` branch)
2. Final report saved to:
   `/home/brad/projects/crypto-trading-bot/reports/Capital_Allocation_Proportional_vs_NewPair_Backtest.md`
3. Clear conclusion stating which method performed better and by how much.

## Constraints

- Do **not** introduce dynamic weekly/monthly rebalancing in this run.
- Do **not** change the sentiment source.
- Focus strictly on isolating the allocation method.

## Success Criteria

A clear, data-backed answer to:  
**"When new USD becomes available, is it better to scale existing positions proportionally or introduce a new pair?"**