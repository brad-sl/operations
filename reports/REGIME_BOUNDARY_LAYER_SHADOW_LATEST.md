# Regime boundary layer shadow

**As of:** 2026-08-20T18:14:36.521185+00:00
**Mode:** shadow only — **no live orders**

## Layer

| Field | Value |
|-------|-------|
| Coarse regime | `transition` |
| Layer | `soft_up` |
| Label | Soft-up — just above flat (shadow: Flat-B-like) |
| BTC 30d % | 8.973 |
| Shadow stance | `flat_b_tight` |

## Live vs shadow

| | Live REGIME-CASH | Shadow cream gates |
|--|------------------|--------------------|
| Mode | `usdc_park` cap $0.0 | `flat_b_tight` cap $50.0 |
| Would-buy count | **0** | **0** |
| Pairs | — | — |

## Book

- Util: 0.1405245478729864
- Cash: $2106.963873576126
- Held: LINK-USD
- Blocked: UNI-USD

## Shadow rows (basket)

| Pair | Would buy | RSI | Sent | Reasons |
|------|-----------|-----|------|---------|
| BTC-USD | no | 64.48 | 0.1299 | rsi 64.5 > max 55.0; sentiment 0.130 < min 0.38 |
| ETH-USD | no | 66.61 | 0.0045 | rsi 66.6 > max 55.0; sentiment 0.004 < min 0.38 |
| SOL-USD | no | 57.44 | 0.0204 | rsi 57.4 > max 55.0; sentiment 0.020 < min 0.38 |
| XRP-USD | no | 70.87 | -0.0222 | rsi 70.9 > max 55.0; sentiment -0.022 < min 0.38 |
| DOGE-USD | no | 77.9 | 0.008333333333333323 | rsi 77.9 > max 55.0; sentiment 0.008 < min 0.38 |
| RAVE-USD | no | 59.24 | None | rsi 59.2 > max 55.0; sentiment_missing |
| AVAX-USD | no | 77.3 | None | rsi 77.3 > max 55.0; sentiment_missing |
| LINK-USD | no | 62.5 | 0.1148 | rsi 62.5 > max 55.0; sentiment 0.115 < min 0.28 |
| UNI-USD | no | 64.15 | 0.0532 | buy_blocked_cooldown; rsi 64.2 > max 55.0; sentiment 0.053 < min 0.38 |
| ARB-USD | no | 63.25 | 0.06818181818181818 | rsi 63.2 > max 55.0; sentiment 0.068 < min 0.38 |
| ICP-USD | no | 55.94 | None | rsi 55.9 > max 55.0; sentiment_missing |

## Next

- Accumulate shadow ticks (jsonl) before any climb promote.
- Promote only with Brad go + expectancy vs park — not this file alone.

Design: `reports/REGIME_BOUNDARY_LAYERS_DESIGN_20260820.md`
