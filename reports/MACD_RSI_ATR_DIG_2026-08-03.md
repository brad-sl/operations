# MACD× + RSI + ATR trail focused dig — 2026-08-03

## Plain English (read first)

**Target:** find a solid 10–20% trading edge (absolute or clean vs BH with non-negative return).
**Universe:** BTC, ETH, SOL, LINK · real project daily OHLCV
**Window:** 2025-07-19 → 2026-07-30 (377 bars)
**Recommendation:** `dig_further_promote_candidate`

### Best candidate: **F1** — MACD× + RSI<40 + 2×ATR + MACD-death
- Mean return: **4.7%** | mean maxDD: **-12.5%**
- Mean edge vs BH: **+30.9%** | vs cash: **+4.7%**
- N trades: **9** | TW expectancy/trade: **7.70%** | WR: **75%**
- Pairs with abs ≥10% / ≥20%: **1** / **0** of 4
- Edge class: `HIT_20_EDGE_BH`

### Edge definition used
- **HIT_10/20_ABS:** mean portfolio return ≥10% / ≥20%
- **HIT_10/20_EDGE_BH:** mean edge vs BH ≥10%/20% **and** mean return ≥0
- **PARTIAL_PICKUPS_10:** ≥2 pairs with abs return ≥10% and mean return ≥0
- **EDGE_VS_BAGS_ONLY:** beats BH by ≥20pp on ≥2 pairs but may still lose money — **not** a 10–20% pickup edge

## Buy-hold by pair

| Pair | BH ret |
|------|--------|
| BTC | 7.4% |
| ETH | -12.0% |
| SOL | -43.9% |
| LINK | -56.4% |

## Arm leaderboard

| Arm | N | mean Ret | mean DD | ΔBH | Δcash | TW exp | ≥10% pairs | class |
|-----|---|----------|---------|-----|-------|--------|------------|-------|
| F1 | 9 | 4.7% | -12.5% | +30.9% | +4.7% | 7.70% | 1/4 | HIT_20_EDGE_BH |
| F2 | 9 | 4.7% | -12.5% | +30.9% | +4.7% | 7.70% | 1/4 | HIT_20_EDGE_BH |
| F9 | 9 | 4.7% | -12.5% | +30.9% | +4.7% | 7.70% | 1/4 | HIT_20_EDGE_BH |
| F0 | 9 | 3.4% | -13.5% | +29.7% | +3.4% | 7.13% | 1/4 | HIT_20_EDGE_BH |
| F3 | 1 | 2.3% | -1.1% | +28.5% | +2.3% | 14.83% | 0/4 | HIT_20_EDGE_BH |
| F5 | 9 | 1.4% | -13.1% | +27.6% | +1.4% | 6.13% | 0/4 | HIT_20_EDGE_BH |
| CASH | 0 | 0.0% | 0.0% | +26.2% | +0.0% | 0.00% | 0/4 | BENCH |
| F4 | 18 | -5.4% | -23.4% | +20.8% | -5.4% | 3.86% | 1/4 | EDGE_VS_BAGS_ONLY |
| F6 | 9 | -5.6% | -18.8% | +20.6% | -5.6% | 2.86% | 0/4 | EDGE_VS_BAGS_ONLY |
| F8 | 9 | -6.0% | -19.1% | +20.2% | -6.0% | 2.69% | 0/4 | EDGE_VS_BAGS_ONLY |
| BH | 4 | -26.2% | -46.7% | +0.0% | -26.2% | -22.36% | 0/4 | BENCH |
| F7 | 45 | -42.6% | -50.9% | -16.4% | -42.6% | 0.15% | 0/4 | NO_10_20_EDGE |

## Per-pair detail (core arms)

| Pair | Arm | N | Ret | DD | Exp% | WR | ΔBH |
|------|-----|---|-----|----|------|----|-----|
| BTC | BH | 1 | 7.4% | -31.6% | 13.10% | 100% | +0.0% |
| BTC | F0 | 1 | 4.2% | -4.6% | 9.72% | 100% | -3.2% |
| BTC | F1 | 1 | 4.2% | -4.6% | 9.72% | 100% | -3.2% |
| BTC | F2 | 1 | 4.2% | -4.6% | 9.72% | 100% | -3.2% |
| BTC | F3 | 0 | 0.0% | 0.0% | 0.00% | 0% | -7.4% |
| BTC | F4 | 4 | -9.3% | -20.0% | 2.93% | 75% | -16.7% |
| BTC | F5 | 1 | 3.3% | -4.7% | 8.76% | 100% | -4.1% |
| BTC | F6 | 1 | -3.2% | -11.4% | 1.88% | 100% | -10.7% |
| BTC | F7 | 11 | -41.5% | -43.5% | 0.40% | 55% | -49.0% |
| BTC | F9 | 1 | 4.2% | -4.6% | 9.72% | 100% | -3.2% |
| ETH | BH | 1 | -12.0% | -32.6% | -7.39% | 0% | +0.0% |
| ETH | F0 | 3 | 4.2% | -17.1% | 7.21% | 67% | +16.2% |
| ETH | F1 | 3 | 4.2% | -17.1% | 7.21% | 67% | +16.2% |
| ETH | F2 | 3 | 4.2% | -17.1% | 7.21% | 67% | +16.2% |
| ETH | F3 | 0 | 0.0% | 0.0% | 0.00% | 0% | +12.0% |
| ETH | F4 | 4 | 4.7% | -19.7% | 6.86% | 75% | +16.7% |
| ETH | F5 | 3 | 5.5% | -14.8% | 7.49% | 67% | +17.5% |
| ETH | F6 | 3 | -5.6% | -25.1% | 3.86% | 67% | +6.4% |
| ETH | F7 | 11 | -35.5% | -45.8% | 1.40% | 55% | -23.4% |
| ETH | F9 | 3 | 4.2% | -17.1% | 7.21% | 67% | +16.2% |
| SOL | BH | 1 | -43.9% | -52.1% | -41.01% | 0% | +0.0% |
| SOL | F0 | 2 | 13.7% | -4.6% | 12.28% | 100% | +57.6% |
| SOL | F1 | 2 | 13.7% | -4.6% | 12.28% | 100% | +57.6% |
| SOL | F2 | 2 | 13.7% | -4.6% | 12.28% | 100% | +57.6% |
| SOL | F3 | 1 | 9.1% | -4.4% | 14.83% | 100% | +53.0% |
| SOL | F4 | 4 | 17.0% | -10.7% | 9.54% | 100% | +60.9% |
| SOL | F5 | 2 | 8.8% | -4.7% | 9.81% | 100% | +52.7% |
| SOL | F6 | 2 | -5.3% | -15.0% | 2.44% | 100% | +38.6% |
| SOL | F7 | 10 | -25.5% | -35.9% | 2.42% | 60% | +18.4% |
| SOL | F9 | 2 | 13.7% | -4.6% | 12.28% | 100% | +57.6% |
| LINK | BH | 1 | -56.4% | -70.6% | -54.13% | 0% | +0.0% |
| LINK | F0 | 3 | -8.3% | -27.5% | 2.77% | 33% | +48.0% |
| LINK | F1 | 3 | -3.4% | -23.6% | 4.47% | 33% | +53.0% |
| LINK | F2 | 3 | -3.4% | -23.6% | 4.47% | 33% | +53.0% |
| LINK | F3 | 0 | 0.0% | 0.0% | 0.00% | 0% | +56.4% |
| LINK | F4 | 6 | -34.2% | -43.0% | -1.31% | 33% | +22.2% |
| LINK | F5 | 3 | -12.0% | -28.2% | 1.44% | 33% | +44.4% |
| LINK | F6 | 3 | -8.5% | -23.6% | 2.48% | 33% | +47.9% |
| LINK | F7 | 13 | -67.9% | -78.4% | -2.86% | 31% | -11.5% |
| LINK | F9 | 3 | -3.4% | -23.6% | 4.47% | 33% | +53.0% |

## Pattern assessment (standard optimization?)

### Recipe under test
1. **Entry:** MACD line crosses above signal (bar close), RSI(14) < threshold (base 40)
2. **Exit:** trail stop at peak − k×ATR(14); optional MACD cross-down emergency; optional +2R TP
3. **Filters:** no Stoch/BB; optional skip if 30d ret < −40% or 90d weak/ATH drawdown
4. **Sizing:** 95% equity, 5 bps/side, long-only

### What the tape says
- **BTC F2:** N=1 ret=4.2% exp=9.7% ΔBH=-3.2% exits={'tp_2r': 1}
- **ETH F2:** N=3 ret=4.2% exp=7.2% ΔBH=+16.2% exits={'tp_2r': 2, 'sl_atr_trail': 1}
- **SOL F2:** N=2 ret=13.7% exp=12.3% ΔBH=+57.6% exits={'tp_2r': 2}
- **LINK F2:** N=3 ret=-3.4% exp=4.5% ΔBH=+53.0% exits={'macd_death': 1, 'sl_atr_trail': 1, 'tp_2r': 1}

### Standard-opt verdict
- There is a **repeatable structure** (F1) worth treating as a **candidate optimization pattern**, but sample is still thin — not live-default yet.

**final_recommendation:** `dig_further_promote_candidate`

Trades: `/home/brad/projects/crypto-trading-bot/reports/MACD_RSI_ATR_DIG_TRADES_2026-08-03.csv`

