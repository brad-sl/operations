# Exit threshold × regime study — 2026-08-06

## Plain English (read first)

**Recommendation enum:** `regime_dependent`
- Usable legs: **76** (matched rounds 109) · lookback 120d
- Stop baseline: **-3%** · fee haircut on CF: 0.1% round-trip
- TP grid: [0.04, 0.05, 0.06, 0.08, 0.1, 0.12] · RSI grid: [60.0, 65.0, 68.0, 70.0, 75.0, 80.0]
- Skipped: {'no_ohlcv': 31, 'no_price': 2}

### What we asked
1. Best **take-profit** % vs riding to stop — by regime
2. Best **RSI overbought exit** vs riding to stop — by regime
3. Whether **one setup** works across Bull / Bear / Flat / Transition (we do **not** assume yes)

### Winners by regime (path sim vs SL-only)

| Regime | N | SL mean r | Best TP | Δ sum r | Best RSI | Δ sum r | Call |
|--------|--:|----------:|---------|--------:|----------|--------:|------|
| all | 76 | 0.012283 | tp_05 | -0.539362 | rsi_65 | 0.882859 | `prefer_rsi_rsi_65` |
| bear | 21 | 0.088116 | tp_12 | -2.051444 | rsi_60 | 0.0 | `prefer_sl_ride` |
| bull | 21 | -0.002058 | tp_06 | 0.582381 | rsi_65 | 0.152198 | `prefer_tp_tp_06` |
| flat | 34 | -0.025697 | tp_05 | 1.259701 | rsi_60 | 0.730661 | `prefer_tp_tp_05` |

### How to read the call
- `prefer_tp_*` / `prefer_rsi_*` — meaningful edge vs SL-only on that regime slice
- `prefer_sl_ride` — early exits hurt (supports prior “ride it out”)
- `no_clear_edge_vs_sl` — not enough lift after fees / thin fire rate
- `inconclusive_thin_n` — do not tune live knobs from this cell

### Policy detail (all regimes pooled)

| Policy | N | sum r | mean r | WR | Δsum vs SL | exit mix |
|--------|--:|------:|-------:|---:|-----------:|----------|
| sl_only | 76 | 0.933527 | 0.012283 | 0.1711 | None | {'sl': 60, 'path_end': 16} |
| rsi_60 | 76 | 1.776372 | 0.023373 | 0.2632 | 0.842845 | {'sl': 54, 'path_end': 7, 'rsi': 15} |
| rsi_65 | 76 | 1.816386 | 0.0239 | 0.2632 | 0.882859 | {'sl': 54, 'path_end': 7, 'rsi': 15} |
| rsi_68 | 76 | 1.085725 | 0.014286 | 0.1974 | 0.152198 | {'sl': 57, 'path_end': 12, 'rsi': 7} |
| rsi_70 | 76 | 0.939006 | 0.012355 | 0.1974 | 0.005479 | {'sl': 57, 'path_end': 13, 'rsi': 6} |
| rsi_75 | 76 | 0.865563 | 0.011389 | 0.1842 | -0.067964 | {'sl': 59, 'path_end': 13, 'rsi': 4} |
| rsi_80 | 76 | 0.865563 | 0.011389 | 0.1842 | -0.067964 | {'sl': 59, 'path_end': 13, 'rsi': 4} |
| tp06_rsi68 | 76 | 0.115262 | 0.001517 | 0.4079 | -0.818265 | {'sl': 44, 'path_end': 2, 'tp': 24, 'rsi': 6} |
| tp_04 | 76 | 0.343765 | 0.004523 | 0.5132 | -0.589762 | {'tp': 38, 'path_end': 1, 'sl': 37} |
| tp_05 | 76 | 0.394165 | 0.005186 | 0.4605 | -0.539362 | {'sl': 41, 'path_end': 2, 'tp': 33} |
| tp_06 | 76 | 0.274165 | 0.003607 | 0.3947 | -0.659362 | {'sl': 46, 'path_end': 2, 'tp': 28} |
| tp_08 | 76 | -0.045835 | -0.000603 | 0.2895 | -0.979362 | {'sl': 54, 'path_end': 2, 'tp': 20} |
| tp_10 | 76 | -0.100217 | -0.001319 | 0.2632 | -1.033744 | {'sl': 56, 'path_end': 5, 'tp': 15} |
| tp_12 | 76 | -0.665463 | -0.008756 | 0.1842 | -1.59899 | {'sl': 60, 'path_end': 7, 'tp': 9} |

### Per-regime policy snapshots

#### bear — `prefer_sl_ride`
- N=21 · SL sum_r=1.850444 mean=0.088116 · best_tp=tp_12 best_rsi=rsi_60 overall=sl_only
  - sl_only: sum_r=1.850444 Δ=None mix={'path_end': 3, 'sl': 18}
  - rsi_60: sum_r=1.850444 Δ=0.0 mix={'path_end': 3, 'sl': 18}
  - rsi_65: sum_r=1.850444 Δ=0.0 mix={'path_end': 3, 'sl': 18}
  - rsi_68: sum_r=1.850444 Δ=0.0 mix={'path_end': 3, 'sl': 18}
  - rsi_70: sum_r=1.850444 Δ=0.0 mix={'path_end': 3, 'sl': 18}

#### bull — `prefer_tp_tp_06`
- N=21 · SL sum_r=-0.043216 mean=-0.002058 · best_tp=tp_06 best_rsi=rsi_65 overall=tp_06
  - tp_06: sum_r=0.539165 Δ=0.582381 mix={'sl': 7, 'path_end': 2, 'tp': 12}
  - tp_04: sum_r=0.438765 Δ=0.481981 mix={'tp': 15, 'path_end': 1, 'sl': 5}
  - tp_05: sum_r=0.419165 Δ=0.462381 mix={'sl': 7, 'path_end': 2, 'tp': 12}
  - tp06_rsi68: sum_r=0.380262 Δ=0.423478 mix={'sl': 5, 'path_end': 2, 'tp': 8, 'rsi': 6}
  - tp_08: sum_r=0.339165 Δ=0.382381 mix={'sl': 11, 'path_end': 2, 'tp': 8}

#### flat — `prefer_tp_tp_05`
- N=34 · SL sum_r=-0.873701 mean=-0.025697 · best_tp=tp_05 best_rsi=rsi_60 overall=tp_05
  - tp_05: sum_r=0.386 Δ=1.259701 mix={'sl': 16, 'tp': 18}
  - tp_04: sum_r=0.346 Δ=1.219701 mix={'tp': 20, 'sl': 14}
  - tp_06: sum_r=0.116 Δ=0.989701 mix={'sl': 21, 'tp': 13}
  - tp06_rsi68: sum_r=0.116 Δ=0.989701 mix={'sl': 21, 'tp': 13}
  - tp_08: sum_r=-0.064 Δ=0.809701 mix={'sl': 25, 'tp': 9}

### Slice: ledger reason = stop-loss only
Closer to “vs riding to SL” on legs that actually stopped.

- **all**: N=47 SL_sum=-0.004582 best=`rsi_60`
- **bear**: N=13 SL_sum=0.869982 best=`sl_only`
- **bull**: N=7 SL_sum=-0.163466 best=`tp_06`
- **flat**: N=27 SL_sum=-0.711098 best=`tp_05`

## Go / no-go (ops)

| Action | Gate |
|--------|------|
| Live take-profit | Only if a regime call is `prefer_tp_*` with N≥8 that regime **and** Brad OK; still shadow-first |
| Auto RSI hard-exit | Only if `prefer_rsi_*` with N gate **and** operator_approve flip explicit |
| Single global threshold | **No** unless enum is `uniform_*` |
| Default while thin/unclear | Keep SL live; TP shadow; hard-exit operator loop |

## Notes
- Daily OHLCV: TP touch optimistic; same-day SL+TP → SL wins.
- RSI exit at daily close when RSI>=threshold (Wilder 14).
- Baseline for deltas is simulated SL-only on the same path, not mixed rotation exits.
- realized_r kept for audit; policy ranking uses path engines.
- Prior sim 'ride it out' is the null; overturn only with meaningful delta + N gates.
- No live take_profit or operator_approve change from this report alone.
