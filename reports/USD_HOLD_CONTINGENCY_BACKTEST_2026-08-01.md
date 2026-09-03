# USD hold contingency backtest (refined)
**As of:** 2026-08-01
**Status:** OFFLINE RESEARCH — not live
**JSON:** `data/state/usd_hold_contingency_backtest_latest.json`
**Fees:** 0.20% RT | **Initial:** $10,000

## Plain English
18m (2025-01-30→2026-08-01): USDC0 0.0%, USDC4% 6.065%, PAXG BH 44.768% (DD -28.067%), BTC BH -40.065%, static 20% PAXG 8.947% (DD -9.297%), static 25% 11.184% (DD -11.164%), static 50% 22.373% (DD -18.653%). Best doc timed: doc_s7_no12m_w50_bullOnly ret 8.746% hedged 48.09% days. Go/no-go: shadow_static_ballast_first.

**Go/no-go:** `shadow_static_ballast_first`

## Optimum returns (~18m primary)

| Strategy | Return% | MaxDD% | Sharpe | Notes |
|---|---:|---:|---:|---|
| **PAXG 100% BH** | 44.768 | -28.067 | 1.076 | Max return |
| Static 50% PAXG | 22.373 | -18.653 | 0.927 | |
| Static 25% PAXG | 11.184 | -11.164 | 0.832 | |
| **Static 20% PAXG** | 8.947 | -9.297 | 0.81 | Recommended ballast |
| USDC 4% APY | 6.065 | 0.0 | n/a | Yield floor |
| USDC 0% | 0.0 | 0 | 0 | Pure park |
| BTC 100% BH | -40.065 | -52.972 | -0.563 | Failed USD store |
| ETH 100% BH | -43.248 | -67.553 | -0.177 | |
| SOL 100% BH | -69.851 | -74.869 | -0.646 | |
| TRX 100% BH | 30.041 | -26.479 | 0.706 | Best major crypto BH |

## Timed contingency (BTC → PAXG)

Exiting on flat/re-entry **layer** is too twitchy. Serious arms exit on **bull / 30d thaw** only.

### Doc arms (18m)

| Arm | Ret% | DD% | %days hedged | Entries |
|---|---:|---:|---:|---:|
| `doc_s7_no12m_w50_bullOnly` | 8.746 | -12.579 | 48.09 | 3 |
| `doc_s14_no12m_w100_bullOnly` | 5.559 | -22.136 | 36.43 | 2 |
| `bear_s14_w100_thaw15` | 5.559 | -22.136 | 36.43 | 2 |
| `doc_s14_no12m_w50_bullOnly` | 2.975 | -12.456 | 36.43 | 2 |
| `bear_s14_w50_thaw15` | 2.975 | -12.456 | 36.43 | 2 |
| `doc_s14_no12m_w20_bullOnly` | 1.237 | -5.4 | 36.43 | 2 |
| `doc_s14_12m25_w20_exitL` | -0.409 | -2.44 | 6.56 | 2 |
| `doc_s14_12m25_w50_exitL` | -1.039 | -5.991 | 6.56 | 2 |
| `doc_s14_12m25_w100_exitL` | -2.134 | -11.638 | 6.56 | 2 |
| `doc_s14_12m25_w20_bullOnly` | -2.736 | -4.465 | 21.68 | 2 |
| `doc_s14_12m35_w50_bullOnly` | -3.109 | -3.901 | 8.56 | 1 |
| `doc_s21_12m25_w50_bullOnly` | -6.049 | -9.707 | 19.13 | 2 |
| `doc_s14_12m25_w50_bullOnly` | -6.77 | -10.834 | 21.68 | 2 |
| `doc_s14_12m25_w50_trail12` | -6.97 | -11.025 | 14.75 | 2 |
| `bear_s30_w50_thaw15` | -7.014 | -9.466 | 15.85 | 2 |
| `doc_s14_12m25_w100_bullOnly` | -13.306 | -20.632 | 21.68 | 2 |

### Best meaningful timed (≥10% days hedged) — 18m

| Ret% | DD% | Calmar | Hedged% | Name |
|---:|---:|---:|---:|---|
| 17.324 | -22.17 | 0.781 | 48.09 | `g_s7_12moff_w100_thNone_trNone` |
| 17.324 | -22.17 | 0.781 | 48.09 | `g_s7_12moff_w100_th15.0_trNone` |
| 17.324 | -22.17 | 0.781 | 48.09 | `g_s7_12moff_w100_thNone_trNone` |
| 17.324 | -22.17 | 0.781 | 48.09 | `g_s7_12moff_w100_th15.0_trNone` |
| 17.324 | -22.17 | 0.781 | 48.09 | `g_s7_12moff_w100_thNone_trNone` |
| 17.324 | -22.17 | 0.781 | 48.09 | `g_s7_12moff_w100_th15.0_trNone` |
| 15.993 | -22.17 | 0.721 | 47.54 | `g_s7_12m-15_w100_thNone_trNone` |
| 15.993 | -22.17 | 0.721 | 47.54 | `g_s7_12m-15_w100_th15.0_trNone` |

## Viable entry/exit policy

### A) Recommended first (simple)

1. Default park: **USDC**.
2. While contingency armed: **20% PAXG / 80% USDC** static ballast.
3. No BTC-timed entry required for ballast.
4. Reduce PAXG → USDC when crypto bull / layered re-entry turns on.
5. Ceiling **20%** unless separate decision to size up.

Proxy 18m: static 20% ≈ **8.947%** ret, **-9.297%** DD (vs PAXG100 **44.768%** / **-28.067%** DD, USDC0 **0%**).

### B) Optional timed overlay

| Leg | Rule |
|-----|------|
| Entry | BTC bear streak ≥ **14d** AND optional BTC 12m ≤ **−25%** AND park/bear |
| Size | Raise PAXG 20% → up to **50%** equity |
| Exit | BTC **bull** (30d≥+15%) OR BTC 30d ≥ **+10%** |
| Do not | Exit on `flat_b` / breakout layer alone |
| Trail | Optional PAXG −12% from local peak while oversized |

Best doc-like arm: `doc_s7_no12m_w50_bullOnly` → ret 8.746%, DD -12.579%, hedged 48.09% days.

### C) Do not

- Use BTC/ETH/SOL as USD store (18m BTC **-40.065%**).
- Expect timed rules to beat 100% PAXG in a one-way gold uptrend.
- Go live without PAXG venue + SL + dust path + shadow.

## 12m check

| Strategy | Ret% | DD% |
|---|---:|---:|
| bh_PAXG | 20.211 | -28.067 |
| static_20paxg | 4.039 | -8.18 |
| static_25paxg | 5.049 | -9.941 |
| static_50paxg | 10.1 | -17.457 |
| usdc_0 | 0.0 | 0.0 |
| usdc_4apy | 4.0 | 0.0 |
| bh_BTC | -44.602 | -52.972 |
| bh_TRX | 1.29 | -26.479 |

### Doc arms 12m

| Arm | Ret% | DD% | Hedged% |
|---|---:|---:|---:|
| `doc_s14_no12m_w100_bullOnly` | 5.559 | -22.136 | 54.64 |
| `bear_s14_w100_thaw15` | 5.559 | -22.136 | 54.64 |
| `doc_s7_no12m_w50_bullOnly` | 4.509 | -12.579 | 58.47 |
| `doc_s14_no12m_w50_bullOnly` | 2.975 | -12.456 | 54.64 |
| `bear_s14_w50_thaw15` | 2.975 | -12.456 | 54.64 |
| `doc_s14_no12m_w20_bullOnly` | 1.237 | -5.4 | 54.64 |
| `doc_s14_12m25_w20_exitL` | -0.409 | -2.44 | 9.84 |
| `doc_s14_12m25_w50_exitL` | -1.039 | -5.991 | 9.84 |
| `doc_s14_12m25_w100_exitL` | -2.134 | -11.638 | 9.84 |
| `doc_s14_12m25_w20_bullOnly` | -2.736 | -4.465 | 32.51 |

## Method

- Binance Vision 1d USDT closes (USDT≈USD).
- BTC signals from `bull_reentry_layered` frozen knobs.
- Timed sleeve: cash ↔ PAXG only.
- Meaningful filter: ≥10% days hedged (avoids near-zero-trade score gaming).

## Rationale

- PAXG buy&hold strongly beat cash on 18m — gold trend dominated.
- Timed BTC-bear rules under-captured gold upside vs always-on PAXG this window.
- Optimum operable contingency = 20–25% static PAXG ballast + USDC rest.
- If using timed overlay: exit on bull/30d thaw only — not flat_b layer (whipsaw).