# Basket swap — Brad GO (2026-08-29)

## Decision (plain English)

- **Preferred paper arm:** `risk_adj_mom` (clear HC winner on current tape).
- **Keep collecting:** `dual_agree` (and supporting arms) for **30 more days**.
- **Revisit:** **2026-09-28 PT**.
- **Live basket swaps:** **NO** from this decision. Membership still needs an explicit promote of a *specific* swap.

## Why risk_adj_mom

| Metric | Value |
|--------|-------|
| 7d N | 20 |
| 7d mean excess | +20.3% |
| 7d hit | 80% |
| Sleeve Δ$ | +$441 |
| HC gates | all clear |

`anti_pump` is also HC but second. `dual_agree` looks strong (7d excess ~+18%, hit ~71%) but **N7=7** (need ≥12) — continue test.

## What changes operationally

1. Confidence board marks `preferred_arm=risk_adj_mom` from `data/state/basket_swap_brad_decision.json`.
2. Basket-swap CF cron **resumed** so dual_agree + CF keep ticking through the 30d window.
3. Operator attention / any future manual promote default bias: **risk_adj_mom** proposals first — still human promote, still L1≠fills.

## What does **not** change

- No auto membership writes
- No claim that ADD would pass RSI/sent/block (L2 still separate)
- dual_agree ≠ promote until Brad says so after revisit (or earlier explicit GO)

## Artifacts

- Decision JSON: `data/state/basket_swap_brad_decision.json`
- Board: `reports/BASKET_SWAP_CONFIDENCE_BOARD_LATEST.md`
- CF: `reports/BASKET_SWAP_SHADOW_CF_LATEST.md`
