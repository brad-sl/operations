# Exit Asymmetry Report — 2026-08-16

**Window:** 30d · **Source:** `/home/brad/projects/crypto-trading-bot/trades/phase6_trades.jsonl`

## Totals
- Realized WR: **0.1667** (7/42)
- Sum realized PnL: **$-45.2606**
- Mean win / loss USD: $5.9293 / $-2.479 · b≈2.3918

## By exit reason

| Reason | n | W | L | WR | Sum PnL |
|--------|---|---|---|----|---------|
| stop_loss_exchange | 26 | 0 | 25 | 0.0 | -85.9986 |
| rotation_exchange | 7 | 7 | 0 | 1.0 | 41.5052 |
| dust_sweep_orphan | 5 | 0 | 5 | 0.0 | -0.5694 |
| preserve_disarm | 3 | 0 | 2 | 0.0 | -0.0021 |
| dust_sweep_after_sl | 3 | 0 | 3 | 0.0 | -0.1957 |
| unknown | 1 | 0 | 0 | None | 0.0 |

## Re-entry after stop_loss_exchange
- Within 24h: **0**
- Within 48h: **0**
- Within 72h: **1**

### Examples
- LINK-USD: sell 2026-08-01T16:07 → buy +59.89h (sell pnl=-35.582756)

## Diagnosis
- Primary: `exit_asymmetry_sl_dominated`
- Stop-loss exits dominate count and dollar drag; profit-taking surface thin/null. Re-entry windows show recycle risk after SL.

## North star
Better returns **and** less loss — fix exit stack / anti-rebuy before thaw.
