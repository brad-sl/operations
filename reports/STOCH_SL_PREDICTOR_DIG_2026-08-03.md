# Stoch → SL predictor — offline report

**Trial:** `ANALYST-STOCH-SL-PREDICTOR-20260803`  
**Generated:** 2026-08-03T17:52:52.707594+00:00  
**Window:** `2026-07-11T00:00:00+00:00` → `2026-08-03T17:52:52.576814+00:00`  
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

- Buys in window: **53**
- With entry Stoch: **29** | RSI: **40**
- Ind sources: `{'missing': 13, 'history_join': 14, 'indicators_at_trade': 26}`
- Base SL rate (entry-Stoch cohort): 7d **44.8%** | 14d **55.2%**

## Primary test — entry Stoch %K &lt; 30 vs ≥ 30 (7d SL)

- Rule: `stoch_k < 30.0 vs >=30.0`
- Low bucket: n=13 hits=5 rate=38.5% CI=[17.7%, 64.5%]
- High bucket: n=16 hits=8 rate=50.0% CI=[28.0%, 72.0%]
- Lift (low/high): **0.7692307692307693**

### Also

- Stoch&lt;20 @7d: low n=10 rate=40.0% | high n=19 rate=47.4% | lift=0.8444444444444446
- Stoch&lt;30 @3d: low n=13 rate=15.4% | high n=16 rate=50.0% | lift=0.3076923076923077
- Stoch&lt;30 @14d: low n=13 rate=38.5% | high n=16 rate=68.8% | lift=0.5594405594405595
- RSI&lt;35 @7d (control): low n=7 rate=57.1% | high n=33 rate=48.5% | lift=1.1785714285714284

## Additive test (RSI 40–60 only)

`{
  "rsi_band": [
    40.0,
    60.0
  ],
  "stoch_thr": 30.0,
  "horizon": "hit_sl_7d",
  "n_mid_rsi": 13,
  "low_stoch": {
    "n": 4,
    "sl_hits": 2,
    "sl_rate": 0.5,
    "wilson_lo": 0.15003570882017145,
    "wilson_hi": 0.8499642911798285
  },
  "high_stoch": {
    "n": 9,
    "sl_hits": 3,
    "sl_rate": 0.3333333333333333,
    "wilson_lo": 0.12058159868274292,
    "wilson_hi": 0.6458026525009103
  },
  "lift": 1.5,
  "note": "Additive test: Stoch split inside RSI-neutral band only"
}`

## Trailing vs leading

- Exit baseline: `{'n': 7, 'mean': 19.752857142857145, 'median': 0.0, 'pct_lt_thr': 0.5714285714285714, 'threshold': 30.0, 'caveat': 'Exit Stoch is trailing — expected low after adverse move; not proof of entry utility.'}`
- Entry vs exit on SL hits: `{'sl_hits_with_entry_stoch': 16, 'entry_stoch_lt_thr': 5, 'entry_pct_lt_thr': 0.3125, 'sl_hits_with_exit_stoch': 7, 'exit_stoch_lt_thr': 4, 'exit_pct_lt_thr': 0.5714285714285714, 'threshold': 30.0, 'interpretation': 'If exit_pct >> entry_pct, Stoch is mostly trailing the loss path. If entry_pct elevated vs non-SL baseline, possible leading signal.'}`

## Caveats

- Primary entry Stoch lift inverted (0.77x) — low Stoch cohort did not SL more
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
