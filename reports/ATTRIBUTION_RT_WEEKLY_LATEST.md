# Attribution RT weekly (PC-06)

**As of:** 2026-09-12T04:39:40.694155+00:00
**Window:** 2026-09-05T04:39:40.694155+00:00 → 2026-09-12T04:39:40.694155+00:00 (7d)
**Schema:** `attribution_rt_weekly_v1`

## Coverage

- Primary RTs (ex stable): **7**
- Full core stamp (entry RSI+sent, exit reason, pnl): **7**
- Stamp coverage: **1.0**
- Edge claim allowed: **False** — No edge claim: need n_rt_primary≥20 with solid stamps

## Banks

- Process tax (SL/dust): n=5 sum=$-4.0458
- Non-tax exits: n=2 sum=$8.1783
- Buckets: `{'tp_profit': 2, 'dust_sweep': 3, 'sl_exchange': 2}`

## RT table (primary)

| pair | sell_ts | bucket | tax | pnl | eRSI | eSent | xRSI | bag | core |
|------|---------|--------|-----|-----|------|-------|------|-----|------|
| LINK-USD | 2026-09-05T19:50:14 | tp_profit |  | 2.1991 | 39.0 | 0.4879 | 59.8 |  | Y |
| LINK-USD | 2026-09-05T19:51:20 | dust_sweep | Y | 0.0036 | 39.0 | 0.4879 | 59.8 |  | Y |
| LINK-USD | 2026-09-08T04:01:38 | tp_profit |  | 5.9792 | 39.35 | 0.354506 | 39.35 |  | Y |
| LINK-USD | 2026-09-09T04:07:00 | sl_exchange | Y | -1.4424 | 34.99 | 0.350941 | 30.81 |  | Y |
| LINK-USD | 2026-09-09T09:54:46 | dust_sweep | Y | -0.0249 | 34.99 | 0.350941 | 30.81 |  | Y |
| LINK-USD | 2026-09-09T16:07:20 | sl_exchange | Y | -2.5265 | 35.57 | 0.372352 | 28.81 |  | Y |
| LINK-USD | 2026-09-09T22:09:27 | dust_sweep | Y | -0.0556 | 35.57 | 0.372352 | 28.81 |  | Y |

## Rules

- OPT / month_path may cite **stamped set only**.
- No fake backfill of RSI/sent.
- Edge talk blocked when n < 20.

State: `data/state/attribution_rt_weekly_latest.json`
