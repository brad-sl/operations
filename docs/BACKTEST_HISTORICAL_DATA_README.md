# Historical Data for Phase 6 Backtesting

## Purpose
Contains 365 days of synthetic historical OHLCV (Open, High, Low, Close, Volume) data for backtesting Phase 6 account initialization scenarios.

## Files Generated
- `backtest_historical_ohlcv_btc_2025-04-20_to_2026-04-20.json` — BTC-USD daily candles
- `backtest_historical_ohlcv_eth_2025-04-20_to_2026-04-20.json` — ETH-USD daily candles
- `backtest_historical_ohlcv_sol_2025-04-20_to_2026-04-20.json` — SOL-USD daily candles
- `backtest_historical_ohlcv_xrp_2025-04-20_to_2026-04-20.json` — XRP-USD daily candles
- `backtest_historical_ohlcv_doge_2025-04-20_to_2026-04-20.json` — DOGE-USD daily candles

## Data Format
Each file contains an array of candles:
```json
[
  {
    "timestamp": "2025-04-20T00:00:00Z",
    "open": 63450.50,
    "high": 64200.00,
    "low": 63100.00,
    "close": 63850.75,
    "volume": 28500000000
  },
  ...
]
```

## Generation Method
- **Data source:** Synthetic realistic data based on historical volatility patterns
- **Generation date:** 2026-04-20
- **Frequency:** Daily candles (1D)
- **Seed:** 42 (deterministic for reproducibility)

## Backtesting Usage
```python
from backtest_phase6_scenarios import load_historical_data, run_backtest

# Load data
data = load_historical_data()

# Run backtest across all 4 scenarios
results = run_backtest(data)

# Generate report
print(results)
```

## Notes
- Data is **synthetic** for testing purposes — not real Coinbase data
- Volatility and correlation patterns are realistic based on 2025-2026 market conditions
- For production backtesting, replace with real OHLCV data from Coinbase Historical API

## Future Improvements
- Pull real historical data from Coinbase API
- Integrate with Phase 5 actual trading logs for validation
- Add sentiment data overlay for signal-based backtesting
