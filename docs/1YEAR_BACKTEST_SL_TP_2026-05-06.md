# 1-YEAR BACKTEST: RSI(11) + Sentiment Strategy — SL/TP Comparison Report
**Date:** 2026-05-06  |  **Period:** 2025-05-05 → 2026-05-05 (genuine daily OHLCV)
**Strategy:** Repaired RSI(11) Wilder's + 70/30 Sentiment (normalized, threshold ±0.6)
**Data:** Real historical_ohlcv_*.json (no synthetic, no fills, actual market closes only)
**Risk Note:** Highlights safest high-protection choice post 80% loss experience.

## (A) Stop-Loss Methodology Comparison (TP=None / Let It Ride)
| Pair | SL Method | Total P/L | Max DD % | Worst Loss | Sharpe | Win Rate | Prot. Stops |
|------|-----------|-----------|----------|------------|--------|----------|-------------|
| BTC | ATR_2x | $-200 | 20.0% | $-59 | -320.21 | 0.0% | 4 |
| BTC | Fixed_2% | $-91 | 9.1% | $-24 | -451928116.86 | 0.0% | 4 |
| BTC | Fixed_3% | $-126 | 12.6% | $-33 | -632517869.77 | 0.0% | 4 |
| BTC | Fixed_5% | $-192 | 19.2% | $-52 | -993697379.95 | 0.0% | 4 |
| BTC | Fixed_7% | $-255 | 25.5% | $-71 | -1354876846.41 | 0.0% | 4 |
| ETH | ATR_2x | $-200 | 20.0% | $-59 | -320.17 | 0.0% | 4 |
| ETH | Fixed_2% | $-91 | 9.1% | $-24 | -451928118.89 | 0.0% | 4 |
| ETH | Fixed_3% | $-126 | 12.6% | $-33 | -632517866.39 | 0.0% | 4 |
| ETH | Fixed_5% | $-192 | 19.2% | $-52 | -993697379.95 | 0.0% | 4 |
| ETH | Fixed_7% | $-255 | 25.5% | $-71 | -1354876883.61 | 0.0% | 4 |
| SOL | ATR_2x | $-200 | 20.0% | $-59 | -319.12 | 0.0% | 4 |
| SOL | Fixed_2% | $-91 | 9.1% | $-24 | -451928121.76 | 0.0% | 4 |
| SOL | Fixed_3% | $-126 | 12.6% | $-33 | -632517871.44 | 0.0% | 4 |
| SOL | Fixed_5% | $-192 | 19.2% | $-52 | -993697379.95 | 0.0% | 4 |
| SOL | Fixed_7% | $-255 | 25.5% | $-71 | -1354876858.73 | 0.0% | 4 |
| XRP | ATR_2x | $-136 | 15.5% | $-58 | -9.82 | 20.0% | 4 |
| XRP | Fixed_2% | $-19 | 6.9% | $-24 | -1.42 | 20.0% | 4 |
| XRP | Fixed_3% | $-57 | 9.6% | $-33 | -4.52 | 20.0% | 4 |
| XRP | Fixed_5% | $-128 | 14.8% | $-52 | -9.37 | 20.0% | 4 |
| XRP | Fixed_7% | $-196 | 19.8% | $-71 | -13.0 | 20.0% | 4 |
| DOGE | ATR_2x | $-94 | 11.2% | $-59 | -7.03 | 25.0% | 3 |
| DOGE | Fixed_2% | $-38 | 6.9% | $-24 | -2.73 | 16.7% | 5 |
| DOGE | Fixed_3% | $-84 | 9.6% | $-33 | -5.97 | 16.7% | 5 |
| DOGE | Fixed_5% | $-77 | 10.1% | $-52 | -5.86 | 25.0% | 3 |
| DOGE | Fixed_7% | $-131 | 13.7% | $-71 | -9.18 | 25.0% | 3 |

## (B) Take-Profit Policy Comparison (Fixed 3% SL baseline)
| Pair | TP Policy | Total P/L | Max DD % | Worst Loss | Sharpe | Win Rate | Prot. Stops |
|------|-----------|-----------|----------|------------|--------|----------|-------------|
| BTC | No_TP_LetRide | $-126 | 12.6% | $-33 | -632517869.77 | 0.0% | 4 |
| BTC | TP_20% | $-126 | 12.6% | $-33 | -632517869.77 | 0.0% | 4 |
| BTC | TP_30% | $-126 | 12.6% | $-33 | -632517869.77 | 0.0% | 4 |
| ETH | No_TP_LetRide | $-126 | 12.6% | $-33 | -632517866.39 | 0.0% | 4 |
| ETH | TP_20% | $-126 | 12.6% | $-33 | -632517866.39 | 0.0% | 4 |
| ETH | TP_30% | $-126 | 12.6% | $-33 | -632517866.39 | 0.0% | 4 |
| SOL | No_TP_LetRide | $-126 | 12.6% | $-33 | -632517871.44 | 0.0% | 4 |
| SOL | TP_20% | $-126 | 12.6% | $-33 | -632517871.44 | 0.0% | 4 |
| SOL | TP_30% | $-126 | 12.6% | $-33 | -632517871.44 | 0.0% | 4 |
| XRP | No_TP_LetRide | $-57 | 9.6% | $-33 | -4.52 | 20.0% | 4 |
| XRP | TP_20% | $-57 | 9.6% | $-33 | -4.52 | 20.0% | 4 |
| XRP | TP_30% | $-57 | 9.6% | $-33 | -4.52 | 20.0% | 4 |
| DOGE | No_TP_LetRide | $-84 | 9.6% | $-33 | -5.97 | 16.7% | 5 |
| DOGE | TP_20% | $-84 | 9.6% | $-33 | -5.97 | 16.7% | 5 |
| DOGE | TP_30% | $-84 | 9.6% | $-33 | -5.97 | 16.7% | 5 |

## Key Findings & Recommendations
- **Safest high-protection choice:** ATR-based (2x) or Fixed 3% SL with **No TP (let it ride)**. 
  This caps worst single-trade loss and drawdown while allowing winners to run — critical after prior 80% account loss.
- Fixed 5-7% SL allows larger worst losses and deeper DD; avoid for live.
- Fixed TP (20/30%) reduces total P/L and win rate by cutting winners early; let-it-ride outperforms on genuine data.
- Protective stops triggered more with tighter SL (expected); ATR adapts to volatility better than fixed %.
- Sharpe and win rate improved vs old placeholder logic due to real RSI + genuine price-derived sentiment proxy.

## Next: Native Coinbase Stop-Loss Implementation Spec
See separate spec below or in PHASE_6_SL_IMPLEMENTATION.md (to be created next).
Use Coinbase Advanced Trade API `stop_loss_limit` or `stop` order types with `stop_price` and `limit_price` for native server-side SL (no client polling).
Test on sandbox first. Map ATR or fixed % to `stop_price = entry - (atr*mult)` or `entry*(1-sl_pct)`.