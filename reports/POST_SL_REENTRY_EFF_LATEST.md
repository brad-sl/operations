# Post-SL re-entry effectiveness (GAP-05)

**as_of:** 2026-09-03T22:42:22.119384+00:00
**enum:** `inconclusive`
**live_promote:** False

## Counts (non-dust SL core)
- SL episodes (core): **44** (dust excluded: 38)
- Re-entry episodes: **34**
- No rebuy in lookback: 10
- Second SL after rebuy: **29**
- Early rebuy (<72.0h): **16**

## Rates (of core SL)
- rebuy any: 0.7727
- rebuy@24h: 0.1136
- rebuy@48h: 0.1591
- rebuy@72h: 0.3636

## Rates (of re-entry episodes)
- second_sl_rate: **0.8529**
- early_rebuy_frac: **0.4706**

## $ PnL (ledger fields)
- sum SL exit (core): -286.5605
- sum SL on rebuy path: -252.6698
- sum second SL: -236.291
- recycle stack (1st+2nd SL): **-488.9608**
- _Ledger pnl fields only; not mark-to-market hold-cash CF_

## Enum reasons
- mixed early/second-SL pattern without clear less-loss proof
- recycle_stack_pnl_usd=-488.9608 with elevated second SL

## Policy note
- Config (read-only): hold_cash=True block_rebuy_hours=72.0
- This report does **not** shorten cooldown or touch live config.

