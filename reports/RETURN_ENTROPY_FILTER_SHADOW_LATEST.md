# Return entropy filter shadow (offline dig)

- **ts:** 2026-08-31T02:56:27.275298+00:00
- **decision:** `shadow_only_no_promote`
- **plain:** No promote. Entropy filter is a concentration feature dig only. Judge on mean return, ΔBH, max DD, turnover — not win rate. Best non-BH arm on this tape: INVERSE_HIGH_H mean_ret=0.387 ΔBH=-0.464 class=ATTENTION_ONLY. Not a standard-opt candidate without long walk-forward + Brad go.
- **knobs:** `{"window": 30, "n_bins": 10, "structure_max": 0.35, "noise_min": 0.7, "edge_mode": "fixed", "fixed_lo": -0.08, "fixed_hi": 0.08, "fee_bps": 5.0, "slip_bps": 2.0, "max_hold_bars": 60}`

## Arm summary (mean across pairs)

| arm | mean ret | mean ΔBH | mean maxDD | N rt | WR (2nd) | edge class |
|-----|----------|----------|------------|------|----------|------------|
| BH | 0.851 | 0.000 | -0.876 | 5 | 60.00% | HIT_10_ABS |
| LOW_H_ONLY | 0.000 | -0.851 | 0.000 | 0 | — | unstable_or_no_edge |
| AVOID_HIGH_H | 0.148 | -0.703 | -0.248 | 74 | 56.76% | ATTENTION_ONLY |
| INVERSE_HIGH_H | 0.387 | -0.464 | -0.889 | 193 | 47.67% | ATTENTION_ONLY |

## Success metrics (what would count as a win)

See `reports/RETURN_ENTROPY_SUCCESS_METRICS.md`.

## Per pair BH

- **BTC-USD** bars=2093 2020-11-22→2026-08-15 BH=1.641 labels={'structure': 0, 'mid': 723, 'noise': 1340, 'insufficient': 30}
- **ETH-USD** bars=2093 2020-11-22→2026-08-15 BH=1.952 labels={'structure': 0, 'mid': 282, 'noise': 1781, 'insufficient': 30}
- **SOL-USD** bars=1886 2021-06-17→2026-08-15 BH=1.815 labels={'structure': 0, 'mid': 22, 'noise': 1834, 'insufficient': 30}
- **LINK-USD** bars=2093 2020-11-22→2026-08-15 BH=-0.255 labels={'structure': 0, 'mid': 23, 'noise': 2040, 'insufficient': 30}
- **AVAX-USD** bars=1781 2021-09-30→2026-08-15 BH=-0.896 labels={'structure': 0, 'mid': 49, 'noise': 1702, 'insufficient': 30}

## Honesty
- Real long daily OHLCV only.
- Pre-registered arms/cutoffs — no post-hoc fishing in this script.
- No live wiring / no auto-promote.
