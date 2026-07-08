# ARCH-4 Full Isolation Backtest Report (P2-02)
Generated: 2026-07-04T00:57:57.316216
Data window: 2025-04-20T00:00:00Z to 2026-04-19T00:00:00Z
Pairs used: ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD']
Initial capital: $10000.0
Rebalance freq (steps): 7 days approx

## ARCH-4 (evaluate_universe + RotationStrategy + TradePlan sim)
- Return: -29.71%
- Max Drawdown: 31.63%
- Trades: 160
- Final equity: $7029.03
- Avg exposure: 16.6%

## Legacy (allocation_engine rebalance / inverse-vol style)
- Return: -29.06% (computed)
- Max Drawdown: 32.36%
- Trades: 7

## Comparison
- ARCH-4 return vs Legacy: -29.71% vs -29.06%
- ARCH-4 trades: 160 | Legacy trades: 7

## Notes / Evidence
- Full isolation: evaluate_universe called with explicit sentiment/rsi (no load_sentiment_scores network)
- Allocator/RotationStrategy exercised with recent_prices for DD/tilt logic
- TradePlan executed in pure PortfolioSimulator (no OrderExecutor live paths)
- No live calls, no external API, only local JSON OHLCV + computation
- See generated JSON for raw data