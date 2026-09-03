# H3 hard-exit counterfactual

_as_of 2026-08-25T21:42:23.319935+00:00_

## BOTTOM LINE

INCONCLUSIVE — only 1 legs with hard-exit trigger + path (need ≥15). Keep operator loop; do not flip H3.

- recommend_live_h3_auto: **False**
- status: `inconclusive`
- N triggered (primary): **1** (min 15)
- mean excess r (hard − ride, after fees): **5.39%**
- hit rate hard better: **100%**
- sum Δ$ (primary): **$9.53**
- winners hard would have cut worse: **0**

## Counts

- rounds matched: 128
- legs scored: 62
- hard triggered: 1
- SL legs: 35 (with prior hard: 1)
- no OHLCV: 21 · no hard hit: 16

## Method limits

- Pair sentiment history not reconstructed; H3 CF is RSI-primary. Live H3 also fires on sentiment_weak — not measured here.
- fee_rt=0.0024
- lookback_days=120

## By regime (triggered only)

- **flat**: n=1 mean_Δr=5.39% hit=100%

## Locked thresholds

```json
{
  "bull": {
    "overbought_rsi": 75.0,
    "max_sentiment_hold": -0.35
  },
  "flat": {
    "overbought_rsi": 65.0,
    "max_sentiment_hold": -0.15
  },
  "bear": {
    "overbought_rsi": 60.0,
    "max_sentiment_hold": 0.0
  },
  "transition": {
    "overbought_rsi": 68.0,
    "max_sentiment_hold": -0.2
  },
  "soft_down": {
    "overbought_rsi": 62.0,
    "max_sentiment_hold": -0.1
  },
  "unknown": {
    "overbought_rsi": 60.0,
    "max_sentiment_hold": 0.0
  }
}
```

## Top helps (hard better)

- ARB-USD stop_loss_exchange: Δr=5.39% hard@2026-07-10 RSI=66.4500780184568 regime=flat

## Top hurts (hard worse)

- ARB-USD stop_loss_exchange: Δr=5.39% hard@2026-07-10 RSI=66.4500780184568 regime=flat

---
No config flip. H3 stays operator_approve until Brad go after clear edge + N.
