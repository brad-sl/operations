# Basket swap shadow counterfactual
As of `2026-09-03T18:30:25.521702+00:00`

Real Coinbase hourly candles. Equal-notional ADD vs REMOVE. **No live promote / no orders.**

## Decision gate (baseline)

**modify_selector** — Baseline 7d: mean excess -0.05% hit=41% on N=27. Selection mechanism underperforms stay-on-remove — prefer parallel arms / tighten pump brakes before any live promote.

## Aggregate by arm

### `anti_pump`
- 1d: N=27 mean excess **-0.26%** (add +1.12 / rem +1.38) hit 33%
- 3d: N=25 mean excess **+4.18%** (add +6.72 / rem +2.54) hit 52%
- 7d: N=23 mean excess **+11.74%** (add +10.71 / rem -1.03) hit 52%
- 14d: N=12 mean excess **+31.92%** (add +26.96 / rem -4.96) hit 75%
- paper sleeve: N=28 ADD $3132.06 vs REM $2737.39 Δ $+394.67

### `baseline_hybrid`
- 1d: N=38 mean excess **-0.29%** (add -0.29 / rem +0.00) hit 42%
- 3d: N=35 mean excess **+11.45%** (add +12.13 / rem +0.67) hit 43%
- 7d: N=27 mean excess **-0.05%** (add +2.36 / rem +2.41) hit 41%
- 14d: N=14 mean excess **-0.97%** (add +18.93 / rem +19.90) hit 50%
- paper sleeve: N=39 ADD $4458.02 vs REM $4390.15 Δ $+67.87

### `dual_agree`
- 1d: N=12 mean excess **-1.81%** (add -2.65 / rem -0.84) hit 25%
- 3d: N=10 mean excess **+1.62%** (add +1.62 / rem -0.00) hit 50%
- 7d: N=10 mean excess **+11.23%** (add +9.03 / rem -2.20) hit 60%
- 14d: N=5 mean excess **+33.34%** (add +27.51 / rem -5.84) hit 60%
- paper sleeve: N=12 ADD $1301.50 vs REM $1138.31 Δ $+163.19

### `rel_btc_stable`
- 1d: N=35 mean excess **-0.18%** (add +1.86 / rem +2.05) hit 43%
- 3d: N=31 mean excess **+0.55%** (add +7.14 / rem +6.58) hit 55%
- 7d: N=25 mean excess **+6.44%** (add +25.29 / rem +18.86) hit 48%
- 14d: N=17 mean excess **+2.04%** (add +32.23 / rem +30.18) hit 53%
- paper sleeve: N=36 ADD $4390.39 vs REM $4236.71 Δ $+153.67

### `risk_adj_mom`
- 1d: N=29 mean excess **-0.17%** (add +0.26 / rem +0.43) hit 45%
- 3d: N=27 mean excess **+2.62%** (add +4.26 / rem +1.64) hit 52%
- 7d: N=24 mean excess **+14.59%** (add +14.54 / rem -0.05) hit 67%
- 14d: N=13 mean excess **+36.83%** (add +33.37 / rem -3.46) hit 85%
- paper sleeve: N=30 ADD $3534.60 vs REM $2941.51 Δ $+593.08

## Unique swaps (recent)

- `risk_adj_mom` 2026-09-01T18:30:26 ARB-USD→CRV-USD excess_to_now=None
- `dual_agree` 2026-09-01T18:30:47 ARB-USD→CRV-USD excess_to_now=None
- `baseline_hybrid` 2026-09-02T05:16:15 XRP-USD→FIL-USD excess_to_now=-7.08
- `anti_pump` 2026-09-02T06:30:10 UNI-USD→FIL-USD excess_to_now=1.54
- `rel_btc_stable` 2026-09-02T06:30:10 XRP-USD→ENA-USD excess_to_now=4.13
- `risk_adj_mom` 2026-09-02T06:30:10 UNI-USD→FIL-USD excess_to_now=1.54
- `dual_agree` 2026-09-02T06:30:28 UNI-USD→FIL-USD excess_to_now=1.54
- `baseline_hybrid` 2026-09-02T17:15:59 XRP-USD→ALGO-USD excess_to_now=None
- `anti_pump` 2026-09-02T18:30:48 ARB-USD→FIL-USD excess_to_now=None
- `rel_btc_stable` 2026-09-02T18:30:48 XRP-USD→FIL-USD excess_to_now=-7.99
- `risk_adj_mom` 2026-09-02T18:30:48 ARB-USD→FIL-USD excess_to_now=None
- `dual_agree` 2026-09-02T18:31:06 ARB-USD→FIL-USD excess_to_now=None
- `baseline_hybrid` 2026-09-03T05:15:53 ICP-USD→LIGHTER-USD excess_to_now=8.16
- `anti_pump` 2026-09-03T06:30:41 UNI-USD→LIGHTER-USD excess_to_now=-0.76
- `rel_btc_stable` 2026-09-03T06:30:41 XRP-USD→LIGHTER-USD excess_to_now=1.06
- `risk_adj_mom` 2026-09-03T06:30:41 UNI-USD→SEI-USD excess_to_now=-6.37
- `baseline_hybrid` 2026-09-03T17:16:19 ICP-USD→ADA-USD excess_to_now=None
- `anti_pump` 2026-09-03T18:30:05 ARB-USD→STX-USD excess_to_now=None
- `rel_btc_stable` 2026-09-03T18:30:05 SOL-USD→STX-USD excess_to_now=0.0
- `risk_adj_mom` 2026-09-03T18:30:05 ARB-USD→ADA-USD excess_to_now=None
