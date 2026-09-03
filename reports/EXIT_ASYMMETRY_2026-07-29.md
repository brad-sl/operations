# Exit Asymmetry Report — 2026-07-29

**Window:** 30d · **Source:** `/home/brad/projects/crypto-trading-bot/trades/phase6_trades.jsonl`

## Totals
- Realized WR: **0.1148** (7/61)
- Sum realized PnL: **$-57.2105**
- Mean win / loss USD: $5.5177 / $-1.7747 · b≈3.1091

## By exit reason

| Reason | n | W | L | WR | Sum PnL |
|--------|---|---|---|----|---------|
| stop_loss_exchange | 54 | 0 | 53 | 0.0 | -93.5883 |
| rotation_exchange | 8 | 7 | 1 | 0.875 | 36.3778 |
| unknown | 6 | 0 | 0 | None | 0.0 |

## Re-entry after stop_loss_exchange
- Within 24h: **3**
- Within 48h: **11**
- Within 72h: **21**

### Examples
- UNI-USD: sell 2026-07-01T04:05 → buy +65.03h (sell pnl=-2.31897)
- BTC-USD: sell 2026-07-04T23:02 → buy +8.1h (sell pnl=-0.000567)
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

## Diagnosis
- Primary: `exit_asymmetry_sl_dominated`
- Stop-loss exits dominate count and dollar drag; profit-taking surface thin/null. Re-entry windows show recycle risk after SL.

## North star
Better returns **and** less loss — fix exit stack / anti-rebuy before thaw.
