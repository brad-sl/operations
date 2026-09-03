# Fib discount-zone entry shadow — 20260815

## Plain English

### Window `last_14d` (2026-08-01 → 2026-08-15)
- **Add-on (RSI+Fib AND):** inconclusive — too few trades; need longer tape or lower TF (not promote)
- **Fib as RSI replacement:** confirmed: FIB_ONLY is a poor RSI replacement on this tape (as hypothesized)

| Arm | Mean ret | Mean maxDD | Trades |
|-----|----------|------------|--------|
| BH | +5.82% | -2.94% | 5 |
| BASE_RSI | +5.82% | -2.94% | 5 |
| RSI_FIB_AND | +4.40% | -2.36% | 5 |
| FIB_ONLY | +4.40% | -2.36% | 5 |
| RSI_OR_FIB | +5.82% | -2.94% | 5 |

- vs BASE: Δret **-1.42 pp**, ΔDD **+0.58 pp**, class `inconclusive_sparse_N`

### Window `last_90d` (2026-05-17 → 2026-08-15)
- **Add-on (RSI+Fib AND):** weak_positive_add_on — slightly better ret + not worse DD; observe-only, no live
- **Fib as RSI replacement:** unexpected: FIB_ONLY ≥ BASE on this window — still not a live swap without long WF

| Arm | Mean ret | Mean maxDD | Trades |
|-----|----------|------------|--------|
| BH | -13.53% | -27.33% | 5 |
| BASE_RSI | -12.68% | -19.78% | 26 |
| RSI_FIB_AND | -7.74% | -14.23% | 15 |
| FIB_ONLY | -7.74% | -14.23% | 15 |
| RSI_OR_FIB | -12.68% | -19.78% | 26 |

- vs BASE: Δret **+4.94 pp**, ΔDD **+5.55 pp**, class `EDGE_VS_BAGS_ONLY`

### Window `long_tape` (2021-01-01 → 2026-08-15)
- **Add-on (RSI+Fib AND):** no_go_add_on — Fib AND does not beat RSI-only BASE on this tape
- **Fib as RSI replacement:** confirmed: FIB_ONLY is a poor RSI replacement on this tape (as hypothesized)

| Arm | Mean ret | Mean maxDD | Trades |
|-----|----------|------------|--------|
| BH | +48.25% | -86.31% | 5 |
| BASE_RSI | -89.01% | -97.55% | 744 |
| RSI_FIB_AND | -96.98% | -98.67% | 504 |
| FIB_ONLY | -97.12% | -98.74% | 508 |
| RSI_OR_FIB | -90.06% | -97.60% | 747 |

- vs BASE: Δret **-7.98 pp**, ΔDD **-1.12 pp**, class `unstable_or_no_edge`

## Design (frozen knobs)

- Swing lookback: **20d** prior high/low; discount fib_ret ∈ **[0.5, 0.786]**
- Regime allow: BTC 30d bull (≥15%) or flat (|r|<8%); bear/transition park
- RSI caps: flat/transition path **≤55.0**, bull **≤70.0**
- Exit: SL **3%**, RSI≥80.0, max hold 21d
- Arms: BH · BASE_RSI · RSI_FIB_AND · FIB_ONLY · RSI_OR_FIB
- Data: Coinbase public daily candles. Fee 5 bps/side. Equal-weight pair mean.

## Go / no-go rules

- Promote path only if long-tape add-on beats BASE on growth **and** DD, N≥15, then shadow — never auto-live.
- FIB_ONLY beating BASE once does **not** authorize RSI removal.
- Sparse 14d windows → inconclusive, not a winner.

JSON: `FIB_DISCOUNT_ENTRY_SHADOW_20260815.json`
