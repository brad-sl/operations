# Liquidation → redeploy study

**As of:** 2026-08-16T22:15:18.572998Z  
**Cut:** 2026-07-01T00:00:00+00:00  
**Verdict:** `unreliable_as_default`  
**Live partial redeploy:** NO-GO live partial redeploy as default — evidence lossy; shadow path only

## Plain English

When we free capital (rotation sell, large stop, liquidation-class sell), do follow-on buys into *other* pairs help the book — or mostly recycle into more stops?

## Ledger facts (this book)

| Metric | Value |
|--------|------:|
| BUY→SL within 72h (n) | 43 |
| BUY→SL sum PnL | -162.79 |
| of which <6h / <24h | 10 / 18 |
| Large free-cap events ≥$50 | 33 |
| …with other-pair BUY in 24h | 20 |
| Follow BUY notional (24h) | $5478.93 |
| Those buys → SL within 7d (count) | 35 |
| Sum SL PnL on those follow buys | **-241.83** |
| Rotation sells ≥$50 | 10 |
| Rotation → follow-buy SL PnL | -159.42 |
| Immediate 6h redeploy >$10 | 1 / 33 |
| Hyp 25% of rotation notional fees @ 0.006 RT | $4.97 on $828.31 |

## Interpretation

1. **Immediate hop is rare under current hold policy** — by design after liquidation disposition.  
2. When free capital *did* fund other-pair buys within 24h, **follow-on stops were net negative** on this tape.  
3. Early catch-the-wave sim (2026-06) was fee-sensitive; live path still has **Exit WR low** and SL-dominated realizes.  
4. Therefore: **document a gated partial-redeploy product path**, but **default remains hold / small flat-lab deploy** until shadow proves a slice is +EV after fees.

## Product path (see policy doc)

`docs/features/LIQUIDATION_ROTATION_REDEPLOY_POLICY.md`

Regenerate: `PYTHONPATH=. python -m phase6.research.run_liquidation_redeploy_study`

