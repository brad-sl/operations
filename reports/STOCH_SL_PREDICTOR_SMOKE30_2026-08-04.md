# Stoch → SL predictor — offline report

**Trial:** `STOCH-RSI-PARALLEL-20260721-observe`  
**Generated:** 2026-08-04T19:56:17.815633+00:00  
**Window:** `2026-07-11T00:00:00+00:00` → `2026-08-04T19:56:17.676063+00:00`  
**Recommendation:** **no_utility_drop**  
**Plain English:** No leading SL utility — entry low-Stoch did not predict more stops.  

## Hypothesis

Low Stoch %K **at buy/arm** predicts higher stop-loss rate within 3–14d, beyond plain RSI — i.e. leading risk signal, not only trailing label after the drop.

## Method

- Real fills: `trades/phase6_trades.jsonl`
- Entry indicators: `indicators_at_trade` else nearest `rsi_indicator_history.jsonl` (≤90m before / 10m after)
- Label: first `stop_loss*` on **same pair** after buy within horizon
- Controls: RSI&lt;35 split; RSI-neutral band Stoch split (additive test)
- Trailing check: exit Stoch on SL hits vs entry Stoch
- **Non-goals:** live SL %, allocator, Stoch param search

## Coverage

- Buys in window: **56**
- With entry Stoch: **32** | RSI: **43**
- Ind sources: `{'missing': 13, 'history_join': 14, 'indicators_at_trade': 29}`
- Base SL rate (entry-Stoch cohort): 7d **40.6%** | 14d **50.0%**

## Primary test — entry Stoch %K &lt; 30 vs ≥ 30 (7d SL)

- Rule: `stoch_k < 30.0 vs >=30.0`
- Low bucket: n=14 hits=5 rate=35.7% CI=[16.3%, 61.2%]
- High bucket: n=18 hits=8 rate=44.4% CI=[24.6%, 66.3%]
- Lift (low/high): **0.8035714285714286**

### Also

- Stoch&lt;20 @7d: low n=11 rate=36.4% | high n=21 rate=42.9% | lift=0.8484848484848485
- Stoch&lt;30 @3d: low n=14 rate=14.3% | high n=18 rate=44.4% | lift=0.32142857142857145
- Stoch&lt;30 @14d: low n=14 rate=35.7% | high n=18 rate=61.1% | lift=0.5844155844155844
- RSI&lt;35 @7d (control): low n=7 rate=57.1% | high n=36 rate=44.4% | lift=1.2857142857142858

## Additive test (RSI 40–60 only)

`{
  "rsi_band": [
    40.0,
    60.0
  ],
  "stoch_thr": 30.0,
  "horizon": "hit_sl_7d",
  "n_mid_rsi": 16,
  "low_stoch": {
    "n": 5,
    "sl_hits": 2,
    "sl_rate": 0.4,
    "wilson_lo": 0.11761823115925325,
    "wilson_hi": 0.769280067791163
  },
  "high_stoch": {
    "n": 11,
    "sl_hits": 3,
    "sl_rate": 0.2727272727272727,
    "wilson_lo": 0.09745880573921469,
    "wilson_hi": 0.5656502930102462
  },
  "lift": 1.4666666666666668,
  "note": "Additive test: Stoch split inside RSI-neutral band only"
}`

## Trailing vs leading

- Exit baseline: `{'n': 7, 'mean': 19.752857142857145, 'median': 0.0, 'pct_lt_thr': 0.5714285714285714, 'threshold': 30.0, 'caveat': 'Exit Stoch is trailing — expected low after adverse move; not proof of entry utility.'}`
- Entry vs exit on SL hits: `{'sl_hits_with_entry_stoch': 16, 'entry_stoch_lt_thr': 5, 'entry_pct_lt_thr': 0.3125, 'sl_hits_with_exit_stoch': 7, 'exit_stoch_lt_thr': 4, 'exit_pct_lt_thr': 0.5714285714285714, 'threshold': 30.0, 'interpretation': 'If exit_pct >> entry_pct, Stoch is mostly trailing the loss path. If entry_pct elevated vs non-SL baseline, possible leading signal.'}`

## Caveats

- Primary entry Stoch lift inverted (0.80x) — low Stoch cohort did not SL more
- RSI-neutral Stoch lift ignored: additive low-bucket n too small to override inverted primary
- Trailing exit Stoch can still look hot; that is not entry prediction utility.
- Keep Stoch on scorer narrative only; no SL threshold experiment.
- Multi-lot / partial exits: pair-level forward SL is coarse (may over-attribute).
- Buys that opened before Stoch instrumentation often lack true entry Stoch (history join helps only post-history).
- Small n → wide Wilson intervals; do not overfit thresholds.

## Decision gates

- Live SL change: **False**
- Allocator change: **False**
- Shadow SL-risk log: **False**

## Honest assessment

Stoch is more sensitive than RSI (more extremes, more disagreements). Sensitivity can mean **earlier stress labeling** and **stronger trailing confirmation** without being a clean **direction/entry filter**. This report scores *entry-time SL prediction only*.
