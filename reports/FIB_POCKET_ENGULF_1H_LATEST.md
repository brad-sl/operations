# Fib pocket + engulf 1h — LAB result

**TS:** 2026-09-15T07:09:51.387242+00:00
**RT cost:** 0.0164 (taker+slip)
**Live wire:** False

spec=v0_default pivot=5 pocket=gold engulf=strict trend=ema50_200 · BTC-USD: N=13 meanR_net=-1.553 WR=15% PF=0.0554410460269097 DD_R=-20.20 class=inconclusive_sparse_N $75_sum=-18.24 · ETH-USD: N=21 meanR_net=-0.929 WR=38% PF=0.2555823213335833 DD_R=-22.60 class=unstable_or_no_edge $75_sum=-17.62 · LAB only — no live path.

## Spec
```json
{
  "name": "v0_default",
  "pivot": 5,
  "pocket": "gold",
  "engulf": "strict",
  "trend": "ema50_200",
  "long_only": true,
  "min_impulse_atr": 1.5,
  "max_swing_age": 120,
  "touch_confirm_bars": 6,
  "min_stop_pct": 0.004,
  "max_stop_pct": 0.04,
  "atr_sl_buf": 0.15,
  "min_engulf_atr": 0.35,
  "time_stop_bars": 72,
  "rr": 2.0
}
```

## Per pair
### BTC-USD
- N=13 edge=`inconclusive_sparse_N`
- mean R gross/net: -0.120 / -1.553
- WR net=15.4% PF=0.0554410460269097 maxDD_R=-20.20
- exits tp/sl/time=3/8/2 med bars=22
- sum PnL on $75 tickets (net): $-18.24
- BH (from bar200): -19.07%

### ETH-USD
- N=21 edge=`unstable_or_no_edge`
- mean R gross/net: +0.429 / -0.929
- WR net=38.1% PF=0.2555823213335833 maxDD_R=-22.60
- exits tp/sl/time=10/11/0 med bars=18
- sum PnL on $75 tickets (net): $-17.62
- BH (from bar200): -24.82%

## Verdict
- **DROP** this family for live consideration.
- v0 BTC: gross mean R already **negative** (−0.12) before ~1.64% RT costs; net mean R **−1.55** (fee domination on tight stops).
- Pre-registered BTC grid: **every** N≥30 cell has **mean R net < 0** (best still ~−1.3 R/trade).
- Tag: `unstable_or_no_edge` (ETH) / sparse N (BTC v0). Not ATTENTION for promote.
- Lab measure only. No promote / no runner hook / no further same-session fib fishing.
- Prior daily fib discount family was also **drop** (2026-08-15).

Spec: `docs/plans/2026-09-14-fib-pocket-engulf-1h-spec.md`
