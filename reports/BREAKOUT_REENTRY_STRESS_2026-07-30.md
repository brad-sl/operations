# Breakout re-entry stress — 2026-07-30

**Status:** offline research only — not promoted to live REGIME-CASH

## Method

- Real multi-pair OHLCV (btc/eth/sol/avax/link/doge/arb), equal-weight sleeve
- BTC drives timing (30d regime, breakout state, RSI-14)
- Policy sets **USD cap** on crypto sleeve; idle cash earns USDC APY 3.5%
- Sleeve rebalance fee proxy: 10 bps on notion traded
- **Gaps:** no per-pair RSI/sentiment gates, no SL path, no live fill slippage — Path B upper/mid bound

### Breakout definition

- **ON:** close makes new 30d high AND 14d return > 0
- **OFF:** close < 20d low OR 14d return < −5%

### RSI band

- Enter-quality band: **50 ≤ RSI(14) ≤ 70** (not ‘any RSI>50’)

## Pack A — breakout vs 30d/15 vs flat B

### Window `full_sample`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| flat_b_always | 6.953 | -1.847 | 100.0 | 75.0 | 425 | 0 |
| current_30d15_only | 4.523 | -1.218 | 7.06 | 14.12 | 30 | 2 |
| breakout_reentry_cap75 | 1.304 | -1.183 | 26.82 | 20.12 | 114 | 13 |
| breakout_reentry_cap200 | -3.483 | -5.345 | 26.82 | 53.65 | 114 | 13 |

### Window `bull_ex`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| breakout_reentry_cap200 | 0.976 | -1.806 | 27.17 | 54.35 | 25 | 2 |
| breakout_reentry_cap75 | 0.917 | -0.637 | 27.17 | 20.38 | 25 | 2 |
| current_30d15_only | 0.876 | 0.0 | 0.0 | 0.0 | 0 | 0 |
| flat_b_always | 0.041 | -1.301 | 100.0 | 75.0 | 92 | 0 |

### Window `bear_stress`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| current_30d15_only | 0.577 | 0.0 | 0.0 | 0.0 | 0 | 0 |
| breakout_reentry_cap75 | 0.135 | -0.631 | 24.59 | 18.44 | 15 | 2 |
| flat_b_always | -0.242 | -1.511 | 100.0 | 75.0 | 61 | 0 |
| breakout_reentry_cap200 | -0.611 | -1.859 | 24.59 | 49.18 | 15 | 2 |

### Window `flat_chop`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| current_30d15_only | 0.857 | 0.0 | 0.0 | 0.0 | 0 | 0 |
| flat_b_always | 0.589 | -1.12 | 100.0 | 75.0 | 90 | 0 |
| breakout_reentry_cap75 | 0.003 | -0.607 | 18.89 | 14.17 | 17 | 3 |
| breakout_reentry_cap200 | -1.416 | -2.041 | 18.89 | 37.78 | 17 | 3 |

### Window `recent`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| flat_b_always | 6.098 | -1.866 | 100.0 | 75.0 | 180 | 0 |
| current_30d15_only | 2.105 | -1.249 | 16.67 | 33.33 | 30 | 2 |
| breakout_reentry_cap75 | 0.544 | -0.873 | 36.11 | 27.08 | 65 | 7 |
| breakout_reentry_cap200 | -1.448 | -3.253 | 36.11 | 72.22 | 65 | 7 |

### Window `live_overlap`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| breakout_reentry_cap200 | 1.648 | -1.278 | 39.22 | 78.43 | 40 | 2 |
| current_30d15_only | 1.347 | -1.258 | 29.41 | 58.82 | 30 | 1 |
| breakout_reentry_cap75 | 1.232 | -0.429 | 39.22 | 29.41 | 40 | 2 |
| flat_b_always | 0.06 | -2.006 | 100.0 | 75.0 | 102 | 0 |

## Pack B — layered vs current REGIME-CASH

### Window `full_sample`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| layered_brk_rsi_bear_flatb_bullboost | 1.919 | -1.572 | 21.41 | 24.88 | 91 | 29 |
| layered_pure_brk_rsi_bear_flatb | 1.366 | -1.572 | 17.18 | 12.88 | 73 | 29 |
| current_policy_regime_cash | 0.362 | -2.14 | 65.88 | 58.24 | 280 | 66 |
| layered_brk_rsi_bear_bullcap | -3.285 | -5.207 | 17.18 | 34.35 | 73 | 29 |

### Window `bull_ex`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| layered_brk_rsi_bear_bullcap | 2.187 | -0.88 | 19.57 | 39.13 | 18 | 6 |
| layered_brk_rsi_bear_flatb_bullboost | 1.369 | -0.309 | 19.57 | 14.67 | 18 | 6 |
| layered_pure_brk_rsi_bear_flatb | 1.369 | -0.309 | 19.57 | 14.67 | 18 | 6 |
| current_policy_regime_cash | 0.504 | -1.078 | 53.26 | 39.95 | 49 | 16 |

### Window `bear_stress`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| current_policy_regime_cash | -0.346 | -1.218 | 63.93 | 47.95 | 39 | 12 |
| layered_brk_rsi_bear_flatb_bullboost | -0.402 | -1.021 | 13.11 | 9.84 | 8 | 10 |
| layered_pure_brk_rsi_bear_flatb | -0.402 | -1.021 | 13.11 | 9.84 | 8 | 10 |
| layered_brk_rsi_bear_bullcap | -2.032 | -2.89 | 13.11 | 26.23 | 8 | 10 |

### Window `flat_chop`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| layered_brk_rsi_bear_flatb_bullboost | 0.319 | -0.328 | 15.56 | 11.67 | 14 | 3 |
| layered_pure_brk_rsi_bear_flatb | 0.319 | -0.328 | 15.56 | 11.67 | 14 | 3 |
| layered_brk_rsi_bear_bullcap | -0.574 | -1.221 | 15.56 | 31.11 | 14 | 3 |
| current_policy_regime_cash | -1.166 | -1.659 | 71.11 | 53.33 | 64 | 16 |

### Window `recent`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| layered_brk_rsi_bear_flatb_bullboost | 1.251 | -1.257 | 31.11 | 44.17 | 56 | 11 |
| layered_pure_brk_rsi_bear_flatb | 0.699 | -0.329 | 21.11 | 15.83 | 38 | 11 |
| current_policy_regime_cash | 0.519 | -1.6 | 70.0 | 73.33 | 126 | 20 |
| layered_brk_rsi_bear_bullcap | -1.023 | -1.333 | 21.11 | 42.22 | 38 | 11 |

### Window `live_overlap`

| Policy | Ret% | MaxDD% | Time-in% | Mean cap$ | Deploy days | Cap changes |
|--------|------|--------|----------|-----------|-------------|-------------|
| current_policy_regime_cash | 1.523 | -1.582 | 67.65 | 87.5 | 69 | 6 |
| layered_brk_rsi_bear_flatb_bullboost | 1.128 | -1.258 | 37.25 | 64.71 | 38 | 6 |
| layered_pure_brk_rsi_bear_flatb | 0.575 | -0.329 | 19.61 | 14.71 | 20 | 7 |
| layered_brk_rsi_bear_bullcap | -0.097 | -0.972 | 19.61 | 39.22 | 20 | 7 |

## Go / no-go

- **NO-GO** `promote_breakout_over_30d15` — live_overlap breakout75 ret=1.232 dd=-0.429 vs 30/15 ret=1.347 dd=-1.258
- **NO-GO** `promote_flat_b_always` — flat_b always is baseline sleeve not a timing edge; live_overlap ret=0.06 dd=-2.006
- **NO-GO** `shadow_layered_vs_current` — live_overlap layer ret=1.128 dd=-1.258 vs cur ret=1.523 dd=-1.582; full_ok=True bear_ok=True
- **NO-GO** `shadow_pure_layered_no_bullboost` — pure ret=0.575 dd=-0.329 vs cur

## Plain-English takeaway

- Live overlap: 30d/15-only ret=1.347 vs breakout@$75 ret=1.232 vs flatB-always ret=0.06.
- Live overlap: current REGIME-CASH ret=1.523 dd=-1.582 vs layered ret=1.128 dd=-1.258.
- Full sample layered vs current: 1.919 / dd -1.572 vs 0.362 / dd -2.14.
- Caps are USD risk sleeves on an equal-weight basket — not full ARCH-4 rotation with pair RSI/sentiment; do not promote on this alone.

_Generated 2026-07-30T22:02:22.634280+00:00_
