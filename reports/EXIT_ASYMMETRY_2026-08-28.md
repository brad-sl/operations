# Exit Asymmetry Report — 2026-08-28

**Window:** 30d · **Source:** `/home/brad/projects/crypto-trading-bot/trades/phase6_trades.jsonl`

## Totals
- Realized WR: **0.0909** (3/33)
- Sum realized PnL: **$-59.1165**
- Mean win / loss USD: $26.8329 / $-4.6538 · b≈5.7658

## By exit reason

| Reason | n | W | L | WR | Sum PnL |
|--------|---|---|---|----|---------|
| stop_loss_exchange | 13 | 0 | 13 | 0.0 | -136.146 |
| dust_sweep_after_sl | 8 | 0 | 8 | 0.0 | -1.7904 |
| dust_sweep_orphan | 5 | 0 | 5 | 0.0 | -0.5694 |
| lifecycle_dual_peak:failed_high_off=0.04 | 4 | 0 | 0 | None | 0.0 |
| preserve_disarm | 3 | 0 | 2 | 0.0 | -0.0021 |
| take_profit | 3 | 1 | 2 | 0.3333 | 75.6199 |
| rotation_exchange | 2 | 2 | 0 | 1.0 | 3.7715 |
| operator_trim_link_to_btc_30pct | 1 | 0 | 0 | None | 0.0 |
| operator_trim_link_30pct_to_cash | 1 | 0 | 0 | None | 0.0 |
| lifecycle_extension_partial:phase=exhaus | 1 | 0 | 0 | None | 0.0 |

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
