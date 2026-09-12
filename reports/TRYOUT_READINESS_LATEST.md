# Tryout readiness — 2026-09-11T18:45:00.830537-07:00

**can_buy_before_next_rebalance:** `False`

> Sleeve membership open but no eng-cleared door (AVAX-USD, ETH-USD, XRP-USD). Free/tee is not a green light.

## Book
- Cash: `$200.00589129516365` · tryout cap `$75.0`
- Seats today: 0/2
- Eligible: AVAX-USD, ETH-USD, XRP-USD
- Regime: flat · equity_health: unknown
- Runner PID: 654873

## Floors (SSOT)
- min_sentiment: 0.25
- min_sentiment_new_pair: 0.35
- quality_tryout_min_sentiment: 0.3
- **live_floor_used:** 0.35 (max of new-pair + tryout)
- max_rsi: 55.0

## Sensor
- mode: `x_reddit_bridge`
- broken: `False` · class: `aged_out_primary_plus_thin_bridge`
- detail: X age ~9.9h (15m HL) → bridge to reddit; eng low/zero expected mid-cycle. mode=x_reddit_bridge; reddit_nz=0; free_nz=0 (tee only, shadow). Not a stuck-zero bug; X→reddit clock working. Live floor 0.35.
- next X refresh PT: 20:50 · next rebalance PT: ~21:00

## Doors
| Pair | elig | force | allowed | eng | RSI | reasons |
|------|------|-------|---------|-----|-----|---------|
| AVAX-USD | True | True | False | 0.0 | 49.9 | sentiment 0.000 < min 0.35 |
| ETH-USD | True | False | False | 0.0388 | 41.51 | sentiment 0.039 < min 0.35 |
| XRP-USD | True | False | False | 0.0 | 53.79 | sentiment 0.000 < min 0.35 |

## Rules
- Free/tee never clears REGIME-CASH.
- No floor bypass without Brad GO.
