# Combined indicator multi-pair ablation — 2026-08-03

**Trial:** TEST-COMBINED-INDICATOR-ABLATION-2026-08
**Pairs:** btc, eth, sol, link, avax
**Fee:** 5.0 bps/side · long-only 95% equity · real project OHLCV
**Window:** 2025-05-20 00:00:00+00:00 → 2026-07-30 00:00:00+00:00 (~437 bars/pair)

## Plain English (read first)

- **Recommendation:** `dig_further`
- Best score arm E0: less-loss vs multi-asset BH (Δret=25.4%, maxDD -17.6% vs -55.2%) but not shadow-ready (abs mean ret still -6.1%; N exploratory; best N≥15 arm E3 abs ret -10.0% (lost-less-than-alts only)).
- Enhancement path worth digging: relax confluence (MACD×+RSI<40) + ATR trail; kill 4-way AND stack; avoid MACD-only spam (E1).
- Idle-cash arms (N=0 full confluence) excluded from ranking — sitting out a drawdown is not a trading edge.
- Scope remains offline/shadow only — no live RSI+Stoch combo without Brad OK.
- Best enhancement arm: E0 (Relaxed OS: MACD× + RSI<40 + Stoch<30) N=12 mean_ret=-6.1%.
- Best original ablation: A6 N=13 mean_ret=-11.4%.
- **Best viable arm (N_sum≥15):** E3 — mean ret -10.0%, mean maxDD -23.6%, ret−|DD| -33.6%, ΔBH 21.5%
- Full A0 confluence still **not tradeable** if N≈0 — filter stack is the problem, not 'patience'.
- Enhancements that add **hard SL / ATR trail** and **relax entry confluence** are the only path to N>0.

## Buy-hold by pair (benchmark)

| Pair | BH ret | bars | start → end |
|------|--------|------|-------------|
| BTC | 7.6% | 437 | 2025-05-20 → 2026-07-30 |
| ETH | -11.9% | 437 | 2025-05-20 → 2026-07-30 |
| SOL | -43.8% | 437 | 2025-05-20 → 2026-07-30 |
| LINK | -46.1% | 437 | 2025-05-20 → 2026-07-30 |
| AVAX | -71.4% | 437 | 2025-05-20 → 2026-07-30 |

## Cross-pair arm leaderboard (equal-weight mean)

| Rank | Arm | NΣ | mean Ret | mean MaxDD | ret−|DD| | mean Exp% | mean WR | ΔBH ret | n≥5 pairs |
|------|-----|----|----------|------------|---------|-----------|---------|---------|-----------|
| 1 | E0 | 12 | -6.1% | -17.6% | -23.7% | 5.29% | 84% | 25.4% | 1/5 |
| 2 | E3 | 15 | -10.0% | -23.6% | -33.6% | 4.20% | 63% | 21.5% | 1/5 |
| 3 | E5 | 12 | -12.5% | -25.9% | -38.4% | -0.23% | 67% | 19.0% | 0/5 |
| 4 | A6 | 13 | -11.4% | -31.4% | -42.8% | 0.28% | 70% | 20.1% | 0/5 |
| 5 | E4 | 15 | -19.8% | -29.2% | -49.1% | -2.36% | 27% | 11.7% | 1/5 |
| 6 | E8 | 26 | -18.9% | -34.2% | -53.1% | 1.50% | 64% | 12.6% | 2/5 |
| 7 | E7 | 54 | -22.8% | -45.1% | -68.0% | 3.29% | 55% | 8.7% | 5/5 |
| 8 | E2 | 46 | -34.8% | -45.7% | -80.5% | 0.62% | 55% | -3.3% | 5/5 |
| 9 | E1 | 72 | -59.7% | -65.5% | -125.2% | -0.97% | 42% | -28.2% | 5/5 |
| — | BH | 5 | -31.5% | -55.2% | -86.7% | — | — | 0.0% | — |

## Per-pair detail (top arms + BH + A0 + best E)

| Pair | Arm | N | Ret | MaxDD | Exp% | WR | SL% | ΔBH |
|------|-----|---|-----|-------|------|----|----|-----|
| BTC | BH | 1 | 7.2% | -34.9% | 7.52% | 100% | 0% | 0.0% |
| BTC | A0 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | -7.2% |
| BTC | A5 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | -7.2% |
| BTC | A6 | 2 | -9.6% | -24.5% | 0.06% | 50% | 0% | -16.8% |
| BTC | E0 | 1 | 3.3% | -4.7% | 8.76% | 100% | 0% | -3.9% |
| BTC | E3 | 1 | 4.2% | -4.6% | 9.72% | 100% | 0% | -3.0% |
| BTC | E1 | 14 | -56.1% | -57.2% | -0.65% | 50% | 71% | -63.2% |
| BTC | E4 | 1 | -12.1% | -19.6% | -7.47% | 0% | 100% | -19.3% |
| BTC | E5 | 1 | -3.2% | -11.4% | 1.88% | 100% | 100% | -10.4% |
| BTC | E6 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | -7.2% |
| BTC | E8 | 4 | -11.5% | -22.9% | 0.96% | 75% | 75% | -18.7% |
| ETH | BH | 1 | -11.3% | -34.9% | -11.97% | 0% | 0% | 0.0% |
| ETH | A0 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 11.3% |
| ETH | A5 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 11.3% |
| ETH | A6 | 2 | -1.5% | -27.4% | 1.88% | 100% | 0% | 9.8% |
| ETH | E0 | 2 | 8.3% | -7.0% | 9.57% | 100% | 0% | 19.6% |
| ETH | E3 | 3 | 4.2% | -17.1% | 7.21% | 67% | 33% | 15.5% |
| ETH | E1 | 14 | -51.4% | -58.9% | 0.16% | 50% | 71% | -40.0% |
| ETH | E4 | 3 | -16.6% | -30.1% | -0.55% | 33% | 67% | -5.3% |
| ETH | E5 | 2 | 7.2% | -19.3% | 6.57% | 100% | 50% | 18.5% |
| ETH | E6 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 11.3% |
| ETH | E8 | 4 | -3.7% | -23.9% | 4.66% | 75% | 75% | 7.6% |
| SOL | BH | 1 | -41.7% | -54.4% | -43.92% | 0% | 0% | 0.0% |
| SOL | A0 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 41.7% |
| SOL | A5 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 41.7% |
| SOL | A6 | 3 | -3.2% | -26.0% | 4.16% | 100% | 0% | 38.4% |
| SOL | E0 | 2 | 7.5% | -4.7% | 9.16% | 100% | 0% | 49.2% |
| SOL | E3 | 2 | 13.7% | -4.6% | 12.28% | 100% | 0% | 55.3% |
| SOL | E1 | 13 | -48.2% | -53.1% | 0.16% | 54% | 77% | -6.6% |
| SOL | E4 | 2 | -4.1% | -19.6% | 3.68% | 50% | 50% | 37.5% |
| SOL | E5 | 2 | -5.3% | -15.0% | 2.44% | 100% | 100% | 36.3% |
| SOL | E6 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 41.7% |
| SOL | E8 | 4 | 14.3% | -12.5% | 9.03% | 100% | 50% | 56.0% |
| LINK | BH | 1 | -43.9% | -71.0% | -46.24% | 0% | 0% | 0.0% |
| LINK | A0 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 43.9% |
| LINK | A5 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 43.9% |
| LINK | A6 | 3 | -2.1% | -26.9% | 5.17% | 67% | 0% | 41.8% |
| LINK | E0 | 2 | 10.5% | -9.7% | 10.65% | 100% | 0% | 54.3% |
| LINK | E3 | 3 | -8.3% | -27.5% | 2.77% | 33% | 67% | 35.5% |
| LINK | E1 | 15 | -66.6% | -78.4% | -1.13% | 33% | 47% | -22.8% |
| LINK | E4 | 3 | -18.4% | -26.2% | -1.13% | 33% | 67% | 25.4% |
| LINK | E5 | 3 | -11.9% | -30.7% | -0.08% | 33% | 67% | 31.9% |
| LINK | E6 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 43.9% |
| LINK | E8 | 6 | -36.2% | -46.0% | -2.60% | 33% | 83% | 7.7% |
| AVAX | BH | 1 | -67.9% | -80.5% | -71.53% | 0% | 0% | 0.0% |
| AVAX | A0 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 67.9% |
| AVAX | A5 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 67.9% |
| AVAX | A6 | 3 | -40.5% | -52.1% | -9.87% | 33% | 0% | 27.4% |
| AVAX | E0 | 5 | -59.9% | -62.0% | -11.70% | 20% | 0% | 7.9% |
| AVAX | E3 | 6 | -64.0% | -64.0% | -10.99% | 17% | 100% | 3.9% |
| AVAX | E1 | 16 | -76.5% | -80.0% | -3.37% | 25% | 56% | -8.6% |
| AVAX | E4 | 6 | -48.0% | -50.7% | -6.29% | 17% | 83% | 19.9% |
| AVAX | E5 | 4 | -49.0% | -53.3% | -11.95% | 0% | 75% | 18.9% |
| AVAX | E6 | 0 | 0.0% | 0.0% | 0.00% | 0% | 0% | 67.9% |
| AVAX | E8 | 8 | -57.6% | -65.8% | -4.57% | 38% | 88% | 10.2% |

## Methodology findings (entry / exit / SL)

### What failed
- **A0 full confluence** (MACD× ∩ RSI&lt;30 ∩ Stoch&lt;20 ∩ BB lower): systematically **N≈0** across pairs — unusable.
- Drop-one ablations (A1–A3) usually still too strict on this ~15m daily window.
- Indicator-only exits without a hard stop leave left-tail open when a rare entry does fire.

### What helps (enhancement direction)
1. **Cut confluence:** MACD cross + single OS filter (RSI&lt;40) beats 4-way AND.
2. **Hard loss cap:** fixed −6% or ATR/chandelier trail beats pure any-oppose for less-loss.
3. **Trend pullback (E2)** needs enough dips in uptrends — check N before trusting.
4. **Mean-revert (A6/E7)** can trade more but often loses to BH in bull tapes — regime-aware gate required.
5. Prefer **ret − |maxDD|** score over raw return when crowning offline arms.

### Regime note
Entry regime = pair 30d return buckets (bull &gt;+5%, bear &lt;−5%, else flat). See trial JSON `regime_expectancy` per arm/pair. Thin N → inconclusive by regime.

## Decision bar
- `final_recommendation`: **dig_further**
- N&lt;15 per arm (global) → do not promote; dig or drop only.
- No live allocator / RSI+Stoch combo without explicit Brad OK.

Trades CSV: `/home/brad/projects/crypto-trading-bot/reports/COMBINED_INDICATOR_ABLATION_TRADES_2026-08-03.csv`

