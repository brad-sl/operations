# Exit Asymmetry Report — 2026-08-12

**Window:** 30d · **Source:** `/home/brad/projects/crypto-trading-bot/trades/phase6_trades.jsonl`

## Totals
- Realized WR: **0.1132** (6/53)
- Sum realized PnL: **$-60.6062**
- Mean win / loss USD: $6.5535 / $-2.1261 · b≈3.0824

## By exit reason

| Reason | n | W | L | WR | Sum PnL |
|--------|---|---|---|----|---------|
| stop_loss_exchange | 39 | 0 | 38 | 0.0 | -99.2179 |
| unknown | 6 | 0 | 0 | None | 0.0 |
| rotation_exchange | 6 | 6 | 0 | 1.0 | 39.3213 |
| dust_sweep_orphan | 5 | 0 | 5 | 0.0 | -0.5694 |
| preserve_disarm | 3 | 0 | 2 | 0.0 | -0.0021 |
| dust_sweep_after_sl | 2 | 0 | 2 | 0.0 | -0.1381 |

## Re-entry after stop_loss_exchange
- Within 24h: **1**
- Within 48h: **5**
- Within 72h: **8**

### Examples
- AVAX-USD: sell 2026-07-15T00:08 → buy +3.93h (sell pnl=-1.3e-05)
- ADA-USD: sell 2026-07-15T00:08 → buy +51.9h (sell pnl=-1.230533)
- ARB-USD: sell 2026-07-15T04:04 → buy +47.98h (sell pnl=-0.107727)
- ADA-USD: sell 2026-07-15T16:01 → buy +36.02h (sell pnl=-0.059515)
- ADA-USD: sell 2026-07-16T04:01 → buy +24.03h (sell pnl=-0.000935)
- XRP-USD: sell 2026-07-16T16:02 → buy +24.07h (sell pnl=-0.000584)
- OP-USD: sell 2026-07-17T04:03 → buy +71.96h (sell pnl=-3e-05)
- LINK-USD: sell 2026-08-01T16:07 → buy +59.89h (sell pnl=-35.582756)

## Diagnosis
- Primary: `exit_asymmetry_sl_dominated`
- Stop-loss exits dominate count and dollar drag; profit-taking surface thin/null. Re-entry windows show recycle risk after SL.

## North star
Better returns **and** less loss — fix exit stack / anti-rebuy before thaw.
