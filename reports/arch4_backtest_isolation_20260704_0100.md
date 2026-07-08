# ARCH-4 Full Isolation Backtest Report (P2-02)
Generated: 2026-07-04T01:00:52.113953
Data window: 2025-04-20T00:00:00Z to 2026-04-19T00:00:00Z
Pairs used: ['BTC-USD', 'ETH-USD', 'SOL-USD']
Initial capital: $5000.0
Rebalance freq (steps): 30 days approx

## ARCH-4 (evaluate_universe + RotationStrategy + TradePlan sim)
- Return: -21.54%
- Max Drawdown: 22.46%
- Trades: 33
- Final equity: $3922.82
- Avg exposure: 12.6%

## Legacy (allocation_engine rebalance / inverse-vol style)
- Return: -22.93% (computed)
- Max Drawdown: 26.19%
- Trades: 15

## Comparison
- ARCH-4 return vs Legacy: -21.54% vs -22.93%
- ARCH-4 trades: 33 | Legacy trades: 15

## Notes / Evidence
- Full isolation: evaluate_universe called with explicit sentiment/rsi (no load_sentiment_scores network)
- Allocator/RotationStrategy exercised with recent_prices for DD/tilt logic
- TradePlan executed in pure PortfolioSimulator (no OrderExecutor live paths)
- No live calls, no external API, only local JSON OHLCV + computation
- See generated JSON for raw data