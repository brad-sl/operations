# Return-entropy shadow — success metrics

**Status:** shadow / evaluate-only  
**Date:** 2026-08-30  
**Not:** a buy signal, seat rule, or promote candidate until gates below clear **and** Brad go.

## What we built

| Piece | Path | Role |
|-------|------|------|
| Core math + live board | `phase6/core/return_entropy_shadow.py` | H_norm, labels, basket board |
| CLI board | `scripts/phase6/run_return_entropy_shadow.py` | Manual / cron-able board |
| Isolation | `scripts/phase6/test_isolation_return_entropy_shadow.py` | Unit truth |
| Offline dig | `phase6/research/return_entropy_filter_shadow.py` | Arm bakeoff on real daily OHLCV |

**Definition (frozen):**

- Returns: simple close-to-close (live hourly board; dig uses daily).
- \(H_{\mathrm{raw}} = -\sum p_i \log_2 p_i\), \(H_{\mathrm{norm}} = H_{\mathrm{raw}} / \log_2 k\), \(k=\) `n_bins` (default 10).
- Window: 48h live board / 30d dig.
- **Bin edges: fixed absolute return grid** (hourly ±2.5%, daily dig ±8%).  
  Pitfall: adaptive ±kσ edges re-scale every window and often keep H high → structure never fires (seen on first dig).
- Labels: **structure** \(H_{\mathrm{norm}} < 0.35\), **noise** \(> 0.70\), else **mid**.
- Cutoffs are **pre-registered implementation knobs**, not laws of physics.

## What “success” means (honest)

Primary scoreboard — **not win rate**:

| # | Metric | Pass bar (shadow → consider longer dig) | Fail / drop |
|---|--------|------------------------------------------|-------------|
| 1 | **Mean absolute return** (equal-pair or BTC-anchor) after fees | ≥ ~**5%** on the tested horizon *or* clear less-loss with product fit | ≤ 0 on long tape |
| 2 | **Δ vs buy & hold** (same pair, same window) | mean ΔBH **≥ 0** and abs ret not a pure bag-beater story | ΔBH ≪ 0 while selling “edge” |
| 3 | **Max drawdown** | not materially worse than BH *without* a compensating abs-ret story | shreds equity vs BH |
| 4 | **Turnover / N round-trips** | enough trades for a read (**N ≥ ~15** aggregate); not churn theatre | N≈0 “cash is best” cosplay or hyper-churn after costs |
| 5 | **Cost realism** | fee+slip path still shows edge | edge dies at 5+2 bps |
| 6 | **Inverse control** (`INVERSE_HIGH_H`) | should be **worse** than low-H / avoid-high if thesis holds | inverse wins → thesis weak |
| 7 | **Walk-forward** (next gate, not first board) | fixed params, multi-fold / multi-year, no re-tune per fold | single short window winner only |
| 8 | **Regime split** | not only works in one toy regime | BTC wrecked + strategy wrecked → no standard opt |
| 9 | **Win rate** | **secondary only** — report, do not promote on WR | WR story without 1–8 |

### Edge class labels (from offline-strategy-honesty)

| Class | Meaning |
|-------|---------|
| `HIT_10/20_ABS` | Mean portfolio return ≥10%/20% |
| `HIT_10/20_EDGE_BH` | Mean ΔBH ≥10%/20% **and** mean ret ≥0 |
| `EDGE_VS_BAGS_ONLY` | Beats BH bags; may still lose money |
| `ATTENTION_ONLY` | Mild positive / interesting; **no** proven forward excess |
| `unstable_or_no_edge` | Long / mean ≤0 or control failure |

**Promote language requires:** long-tape fixed-param walk-forward **and** Brad go.  
OPT → shadow → Brad go. **No auto-promote.**

## What would make us keep it

1. Offline dig: `AVOID_HIGH_H` or `LOW_H_ONLY` beats BH on **mean ret + ΔBH** with tolerable DD and N_rt.
2. Inverse control underperforms (sanity).
3. Live board stays coherent (labels move; no constant all-structure or all-noise bug).
4. Later: fold into scout→evaluate soft filter **in shadow** beside RVOL — still not seat/buy.

## What would make us drop it

- Inverse wins or random vs BH.
- Edge is only WR cosplay.
- Only works on one short alt window while BTC long tape dies.
- Any pressure to wire `evaluate_buy_entry` before walk-forward + Brad go.

## Commands

```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. python3 scripts/phase6/test_isolation_return_entropy_shadow.py
PYTHONPATH=. python3 scripts/phase6/run_return_entropy_shadow.py --json
PYTHONPATH=. python3 phase6/research/return_entropy_filter_shadow.py
```

## Non-goals (this ship)

- No runner hook, no `evaluate_buy_entry` gate, no knobs in `runtime_knobs.py`.
- No Telegram cron until you ask.
- No claim that Shannon / Two Sigma “solved” entries.
