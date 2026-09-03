# Exit Asymmetry Report — 2026-08-05

**Window:** 30d · **Source:** `/home/brad/projects/crypto-trading-bot/trades/phase6_trades.jsonl`

## Totals
- Realized WR: **0.0746** (5/67)
- Sum realized PnL: **$-100.138**
- Mean win / loss USD: $7.5467 / $-2.2237 · b≈3.3937

## By exit reason

| Reason | n | W | L | WR | Sum PnL |
|--------|---|---|---|----|---------|
| stop_loss_exchange | 56 | 0 | 55 | 0.0 | -137.3002 |
| unknown | 6 | 0 | 0 | None | 0.0 |
| rotation_exchange | 5 | 5 | 0 | 1.0 | 37.7337 |
| dust_sweep_orphan | 5 | 0 | 5 | 0.0 | -0.5694 |
| preserve_disarm | 3 | 0 | 2 | 0.0 | -0.0021 |

## Re-entry after stop_loss_exchange
- Within 24h: **2**
- Within 48h: **10**
- Within 72h: **20**

### Examples
- BTC-USD: sell 2026-07-06T22:37 → buy +3.68h (sell pnl=-1.370059)
- SOL-USD: sell 2026-07-07T16:01 → buy +71.98h (sell pnl=-0.152987)
- SOL-USD: sell 2026-07-08T04:01 → buy +59.98h (sell pnl=-0.011203)
- ADA-USD: sell 2026-07-10T04:01 → buy +24.0h (sell pnl=-0.268301)
- DOGE-USD: sell 2026-07-11T16:01 → buy +68.0h (sell pnl=-2.259025)
- DOGE-USD: sell 2026-07-12T04:00 → buy +56.01h (sell pnl=-0.308947)
- OP-USD: sell 2026-07-12T16:01 → buy +60.06h (sell pnl=-1.432734)
- ADA-USD: sell 2026-07-12T16:01 → buy +54.67h (sell pnl=-0.053566)
- DOGE-USD: sell 2026-07-12T16:01 → buy +44.0h (sell pnl=-0.006102)
- SOL-USD: sell 2026-07-12T16:01 → buy +60.05h (sell pnl=-0.102222)
- AVAX-USD: sell 2026-07-13T16:01 → buy +36.05h (sell pnl=-0.001153)
- SOL-USD: sell 2026-07-13T16:01 → buy +36.05h (sell pnl=-0.001488)

## Diagnosis
- Primary: `exit_asymmetry_sl_dominated`
- Stop-loss exits dominate count and dollar drag; profit-taking surface thin/null. Re-entry windows show recycle risk after SL.

## North star
Better returns **and** less loss — fix exit stack / anti-rebuy before thaw.
