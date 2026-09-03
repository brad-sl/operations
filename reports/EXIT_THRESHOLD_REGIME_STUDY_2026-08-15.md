# Exit threshold × regime study — 2026-08-15

## Plain English (read first)

**Recommendation enum:** `regime_dependent`
- Usable legs: **77** (matched rounds 116) · lookback 120d
- Stop baseline: **-3%** · fee haircut on CF: 0.1% round-trip
- TP grid: [0.04, 0.05, 0.06, 0.08, 0.1, 0.12] · RSI grid: [60.0, 65.0, 68.0, 70.0, 75.0, 80.0]
- Skipped: {'no_ohlcv': 37, 'no_price': 2}

### What we asked
1. Best **take-profit** % vs riding to stop — by regime
2. Best **RSI overbought exit** vs riding to stop — by regime
3. Whether **one setup** works across Bull / Bear / Flat / Transition (we do **not** assume yes)

### Winners by regime (path sim vs SL-only)

| Regime | N | SL mean r | Best TP | Δ sum r | Best RSI | Δ sum r | Call |
|--------|--:|----------:|---------|--------:|----------|--------:|------|
| all | 77 | 0.012197 | tp_05 | -0.495982 | rsi_60 | 0.937253 | `prefer_rsi_rsi_60` |
| bear | 21 | 0.088116 | tp_12 | -2.051444 | rsi_60 | 0.0 | `prefer_sl_ride` |
| bull | 21 | -0.002058 | tp_06 | 0.582381 | rsi_65 | 0.152198 | `prefer_tp_tp_06` |
| flat | 35 | -0.024802 | tp_05 | 1.303081 | rsi_60 | 0.825069 | `prefer_tp_tp_05` |

### How to read the call
- `prefer_tp_*` / `prefer_rsi_*` — meaningful edge vs SL-only on that regime slice
- `prefer_sl_ride` — early exits hurt (supports prior “ride it out”)
- `no_clear_edge_vs_sl` — not enough lift after fees / thin fire rate
- `inconclusive_thin_n` — do not tune live knobs from this cell

### Policy detail (all regimes pooled)

| Policy | N | sum r | mean r | WR | Δsum vs SL | exit mix |
|--------|--:|------:|-------:|---:|-----------:|----------|
| sl_only | 77 | 0.939147 | 0.012197 | 0.1818 | None | {'sl': 60, 'path_end': 17} |
| rsi_60 | 77 | 1.8764 | 0.024369 | 0.2727 | 0.937253 | {'sl': 54, 'path_end': 7, 'rsi': 16} |
| rsi_65 | 77 | 1.822006 | 0.023662 | 0.2727 | 0.882859 | {'sl': 54, 'path_end': 8, 'rsi': 15} |
| rsi_68 | 77 | 1.091345 | 0.014173 | 0.2078 | 0.152198 | {'sl': 57, 'path_end': 13, 'rsi': 7} |
| rsi_70 | 77 | 0.944625 | 0.012268 | 0.2078 | 0.005478 | {'sl': 57, 'path_end': 14, 'rsi': 6} |
| rsi_75 | 77 | 0.871182 | 0.011314 | 0.1948 | -0.067965 | {'sl': 59, 'path_end': 14, 'rsi': 4} |
| rsi_80 | 77 | 0.871182 | 0.011314 | 0.1948 | -0.067965 | {'sl': 59, 'path_end': 14, 'rsi': 4} |
| tp06_rsi68 | 77 | 0.174262 | 0.002263 | 0.4156 | -0.764885 | {'sl': 44, 'path_end': 2, 'tp': 25, 'rsi': 6} |
| tp_04 | 77 | 0.382765 | 0.004971 | 0.5195 | -0.556382 | {'tp': 39, 'path_end': 1, 'sl': 37} |
| tp_05 | 77 | 0.443165 | 0.005755 | 0.4675 | -0.495982 | {'sl': 41, 'path_end': 2, 'tp': 34} |
| tp_06 | 77 | 0.333165 | 0.004327 | 0.4026 | -0.605982 | {'sl': 46, 'path_end': 2, 'tp': 29} |
| tp_08 | 77 | 0.033165 | 0.000431 | 0.2987 | -0.905982 | {'sl': 54, 'path_end': 2, 'tp': 21} |
| tp_10 | 77 | -0.001217 | -1.6e-05 | 0.2727 | -0.940364 | {'sl': 56, 'path_end': 5, 'tp': 16} |
| tp_12 | 77 | -0.546463 | -0.007097 | 0.1948 | -1.48561 | {'sl': 60, 'path_end': 7, 'tp': 10} |

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
- N=35 · SL sum_r=-0.868081 mean=-0.024802 · best_tp=tp_05 best_rsi=rsi_60 overall=tp_05
  - tp_05: sum_r=0.435 Δ=1.303081 mix={'sl': 16, 'tp': 19}
  - tp_04: sum_r=0.385 Δ=1.253081 mix={'tp': 21, 'sl': 14}
  - tp_06: sum_r=0.175 Δ=1.043081 mix={'sl': 21, 'tp': 14}
  - tp06_rsi68: sum_r=0.175 Δ=1.043081 mix={'sl': 21, 'tp': 14}
  - tp_08: sum_r=0.015 Δ=0.883081 mix={'sl': 25, 'tp': 10}

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
