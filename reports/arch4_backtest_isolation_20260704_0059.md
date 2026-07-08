# ARCH-4 Full Isolation Backtest Report (P2-02)
Generated: 2026-07-04T00:59:14.349051
Data window: 2025-04-20T00:00:00Z to 2026-04-19T00:00:00Z
Pairs used: ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'DOGE-USD', 'LINK-USD', 'AVAX-USD', 'ARB-USD']
Initial capital: $10000.0
Rebalance freq (steps): 7 days approx

## ARCH-4 (evaluate_universe + RotationStrategy + TradePlan sim)
- Return: -29.34%
- Max Drawdown: 29.9%
- Trades: 237
- Final equity: $7066.43
- Avg exposure: 37.0%

## Legacy (allocation_engine rebalance / inverse-vol style)
- Return: -35.10% (computed)
- Max Drawdown: 45.24%
- Trades: 229

## Comparison
- ARCH-4 return vs Legacy: -29.34% vs -35.10%
- ARCH-4 trades: 237 | Legacy trades: 229

## Notes / Evidence
- Full isolation: evaluate_universe called with explicit sentiment/rsi (no load_sentiment_scores network)
- Allocator/RotationStrategy exercised with recent_prices for DD/tilt logic
- TradePlan executed in pure PortfolioSimulator (no OrderExecutor live paths)
- No live calls, no external API, only local JSON OHLCV + computation
- See generated JSON for raw data