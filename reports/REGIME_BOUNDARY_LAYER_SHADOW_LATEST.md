# Regime boundary layer shadow

**As of:** 2026-08-29T15:20:34.318792+00:00
**Mode:** shadow only — **no live orders**

## Layer

| Field | Value |
|-------|-------|
| Coarse regime | `bull` |
| Layer | `bull` |
| Label | Bull — full deploy posture |
| BTC 30d % | 20.357 |
| Shadow stance | `deploy` |

## Live vs shadow

| | Live REGIME-CASH | Shadow cream gates |
|--|------------------|--------------------|
| Mode | `deploy` cap $100.0 | `deploy` cap $150.0 |
| Would-buy count | **1** | **0** |
| Pairs | BTC-USD | — |

## Book

- Util: 0.06102967470806983
- Cash: $2154.846305021965
- Held: BTC-USD
- Blocked: ICP-USD

## Shadow rows (basket)

| Pair | Would buy | RSI | Sent | Reasons |
|------|-----------|-----|------|---------|
| BTC-USD | no | 68.42 | 0.1299 | rsi 68.4 > max 65.0; sentiment 0.130 < min 0.2 |
| ETH-USD | no | 64.85 | 0.0045 | sentiment 0.004 < min 0.3 |
| SOL-USD | no | 73.92 | 0.0204 | rsi 73.9 > max 65.0; sentiment 0.020 < min 0.3 |
| XRP-USD | no | 63.14 | -0.0222 | sentiment -0.022 < min 0.3 |
| DOGE-USD | no | 76.42 | 0.008333333333333323 | rsi 76.4 > max 65.0; sentiment 0.008 < min 0.3 |
| PENGU-USD | no | 78.34 | None | rsi 78.3 > max 65.0; sentiment_missing |
| AVAX-USD | no | 67.08 | None | rsi 67.1 > max 65.0; sentiment_missing |
| LINK-USD | no | 67.35 | 0.1148 | rsi 67.3 > max 65.0; sentiment 0.115 < min 0.3 |
| UNI-USD | no | 75.55 | 0.0532 | rsi 75.5 > max 65.0; sentiment 0.053 < min 0.3 |
| ARB-USD | no | 65.98 | 0.06818181818181818 | rsi 66.0 > max 65.0; sentiment 0.068 < min 0.3 |
| ICP-USD | no | 73.89 | None | buy_blocked_cooldown; rsi 73.9 > max 65.0; sentiment_missing |

## Next

- Accumulate shadow ticks (jsonl) before any climb promote.
- Promote only with Brad go + expectancy vs park — not this file alone.

Design: `reports/REGIME_BOUNDARY_LAYERS_DESIGN_20260820.md`
