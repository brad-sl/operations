# Tryout readiness — 2026-09-17T13:40:21.328650-07:00

**can_buy_before_next_rebalance:** `True`

> Tryout can seat before next rebalance: LINK-USD clear eng floor.

## Book
- Cash: `$200.00589129516365` · tryout cap `$75.0`
- Seats today: 0/2
- Eligible: ADA-USD, AVAX-USD, ETH-USD, LINK-USD, NEAR-USD, XRP-USD, ZEC-USD
- Regime: flat · equity_health: unknown
- Runner PID: 3452760

## Floors (SSOT)
- min_sentiment: 0.25
- min_sentiment_new_pair: 0.35
- quality_tryout_min_sentiment: 0.3
- **live_floor_used:** 0.3 (max of new-pair + tryout)
- max_rsi: 65.0

## Sensor
- mode: `x`
- broken: `False` · class: `eng_heat_present`
- detail: mode=x; eng above floor for 1/7 doors; floor=0.30.
- next X refresh PT: 21:00 · next rebalance PT: ~21:05

## Doors
| Pair | elig | force | allowed | eng | RSI | reasons |
|------|------|-------|---------|-----|-----|---------|
| ADA-USD | True | False | False | 0.0947 | 59.08 | sentiment 0.095 < min 0.3 |
| AVAX-USD | True | True | False | 0.036 | 58.05 | sentiment 0.036 < min 0.3 |
| ETH-USD | True | False | False | 0.0033 | 50.45 | sentiment 0.003 < min 0.3 |
| LINK-USD | True | False | True | 0.482 | 57.16 | entry_ok quality_tryout_v2 |
| NEAR-USD | True | False | False | 0.0015 | 56.17 | sentiment 0.002 < min 0.3 |
| XRP-USD | True | False | False | 0.0287 | 49.99 | sentiment 0.029 < min 0.3 |
| ZEC-USD | True | False | False | 0.0787 | 68.33 | sentiment 0.079 < min 0.3; rsi 68.3 > max_buy 65.0 |

## Rules
- Free/tee never clears REGIME-CASH.
- No floor bypass without Brad GO.
