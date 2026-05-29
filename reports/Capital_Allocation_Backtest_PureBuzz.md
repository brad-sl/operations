# Capital Allocation Backtest — Pure Buzz Focus
**Generated:** 2026-05-26T15:17:35.329656
**Period:** 2025-05-05 → 2026-05-05 (genuine daily OHLCV)
**Starting Capital:** $10,000
**Strategy:** RSI(11) + Sentiment (70/30) with Fixed 3% SL / Let-It-Ride TP

## Allocation Variants Tested

1. **Equal_Weight** — Uniform capital split across all 5 pairs (baseline)
2. **Pure_Buzz** — Weights proportional to |sentiment| strength only
3. **Buzz_Threshold_0.3** — Only pairs with |sentiment| ≥ 0.3 receive allocation (pure buzz among qualifiers)
4. **Inverse_Vol** — Risk-parity style: lower volatility pairs get higher weight
5. **Hybrid_Buzz60_Vol40** — 60% Pure Buzz + 40% Inverse Vol blended allocation

## Latest Sentiment & Volatility Snapshot (used for allocation)

| Pair | Sentiment | |Sentiment| | Ann. Vol |
|------|-----------|-------------|----------|
| BTC | -0.268 | 0.268 | 0.33 |
| ETH | -0.268 | 0.268 | 0.33 |
| SOL | -0.268 | 0.268 | 0.33 |
| XRP | -0.282 | 0.282 | 0.32 |
| DOGE | -0.188 | 0.188 | 0.50 |

## Results Summary

| Variant | Final Capital | Total P/L | Max DD | Sharpe | Trades | Win Rate | Pairs Used |
|---------|---------------|-----------|--------|--------|--------|----------|------------|
| Equal_Weight | $8,962 | $-1038 | 9.6% | -20.81 | 23 | 8.7% | 5 |
| Pure_Buzz | $8,955 | $-1045 | 9.6% | -23.68 | 23 | 8.7% | 5 |
| Buzz_Threshold_0.3 | $8,962 | $-1038 | 9.6% | -20.81 | 23 | 8.7% | 5 |
| Inverse_Vol | $8,950 | $-1050 | 9.6% | -24.64 | 23 | 8.7% | 5 |
| Hybrid_Buzz60_Vol40 | $8,953 | $-1047 | 9.6% | -24.06 | 23 | 8.7% | 5 |

## Key Findings

- **Best P/L performer:** Equal_Weight (+$-1038)
- **Worst P/L performer:** Inverse_Vol (+$-1050)

- **Pure_Buzz vs Equal_Weight:** ΔP/L = $-7, ΔDD = +0.0%
  - Equal-weight baseline outperformed Pure Buzz on this period.

## Allocation Details (by variant)

### Equal_Weight
- BTC: $2,000 (20.0%)
- ETH: $2,000 (20.0%)
- SOL: $2,000 (20.0%)
- XRP: $2,000 (20.0%)
- DOGE: $2,000 (20.0%)

### Pure_Buzz
- XRP: $2,213 (22.1%)
- ETH: $2,105 (21.1%)
- BTC: $2,105 (21.1%)
- SOL: $2,104 (21.0%)
- DOGE: $1,472 (14.7%)

### Buzz_Threshold_0.3
- BTC: $2,000 (20.0%)
- ETH: $2,000 (20.0%)
- SOL: $2,000 (20.0%)
- XRP: $2,000 (20.0%)
- DOGE: $2,000 (20.0%)

### Inverse_Vol
- XRP: $2,175 (21.7%)
- BTC: $2,138 (21.4%)
- ETH: $2,138 (21.4%)
- SOL: $2,138 (21.4%)
- DOGE: $1,411 (14.1%)

### Hybrid_Buzz60_Vol40
- XRP: $2,198 (22.0%)
- BTC: $2,118 (21.2%)
- ETH: $2,118 (21.2%)
- SOL: $2,118 (21.2%)
- DOGE: $1,448 (14.5%)

## Recommendations

- Pure Buzz allocation shines when sentiment dispersion is high (some pairs strongly bullish/bearish).
- Thresholded Buzz reduces noise but risks concentration if few pairs qualify.
- Hybrid (Buzz + Vol) offers a pragmatic middle ground for live deployment.
- Inverse Vol alone may under-allocate to high-sentiment volatile names (memecoins).

**Next Steps:**
- Re-run with live CoinGecko sentiment fetch instead of price-proxy.
- Add dynamic rebalancing simulation (weekly/monthly).
- Backtest across multiple market regimes (bull/bear/sideways).
