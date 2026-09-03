# Stoch → SL predictor — offline report

**Trial:** `ANALYST-STOCH-SL-PREDICTOR-20260803`  
**Generated:** 2026-08-03T17:52:52.495306+00:00  
**Window:** `2026-07-21T21:54:57.262723+00:00` → `2026-08-03T17:52:52.370356+00:00`  
**Recommendation:** **extend_collect**  
**Plain English:** Sample too small for utility call.  

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

- Buys in window: **9**
- With entry Stoch: **6** | RSI: **6**
- Ind sources: `{'indicators_at_trade': 6, 'missing': 3}`
- Base SL rate (entry-Stoch cohort): 7d **16.7%** | 14d **33.3%**

## Primary test — entry Stoch %K &lt; 30 vs ≥ 30 (7d SL)

- Rule: `stoch_k < 30.0 vs >=30.0`
- Low bucket: n=3 hits=1 rate=33.3% CI=[6.1%, 79.2%]
- High bucket: n=3 hits=0 rate=0.0% CI=[0.0%, 56.2%]
- Lift (low/high): **inf**

### Also

- Stoch&lt;20 @7d: low n=2 rate=0.0% | high n=4 rate=25.0% | lift=0.0
- Stoch&lt;30 @3d: low n=3 rate=0.0% | high n=3 rate=0.0% | lift=None
- Stoch&lt;30 @14d: low n=3 rate=33.3% | high n=3 rate=33.3% | lift=1.0
- RSI&lt;35 @7d (control): low n=2 rate=0.0% | high n=4 rate=25.0% | lift=0.0

## Additive test (RSI 40–60 only)

`{
  "rsi_band": [
    40.0,
    60.0
  ],
  "stoch_thr": 30.0,
  "horizon": "hit_sl_7d",
  "n_mid_rsi": 4,
  "low_stoch": {
    "n": 1,
    "sl_hits": 1,
    "sl_rate": 1.0,
    "wilson_lo": 0.20654329147389294,
    "wilson_hi": 1.0
  },
  "high_stoch": {
    "n": 3,
    "sl_hits": 0,
    "sl_rate": 0.0,
    "wilson_lo": 0.0,
    "wilson_hi": 0.5615060804490177
  },
  "lift": null,
  "note": "Additive test: Stoch split inside RSI-neutral band only"
}`

## Trailing vs leading

- Exit baseline: `{'n': 2, 'mean': 0.0, 'median': 0.0, 'pct_lt_thr': 1.0, 'threshold': 30.0, 'caveat': 'Exit Stoch is trailing — expected low after adverse move; not proof of entry utility.'}`
- Entry vs exit on SL hits: `{'sl_hits_with_entry_stoch': 2, 'entry_stoch_lt_thr': 1, 'entry_pct_lt_thr': 0.5, 'sl_hits_with_exit_stoch': 2, 'exit_stoch_lt_thr': 2, 'exit_pct_lt_thr': 1.0, 'threshold': 30.0, 'interpretation': 'If exit_pct >> entry_pct, Stoch is mostly trailing the loss path. If entry_pct elevated vs non-SL baseline, possible leading signal.'}`

## Caveats

- thin labeled buys with entry Stoch (n=6) — do not ship live knobs
- Need more buys with entry tags OR longer window after Stoch instrumentation.
- Allocator stays plain RSI; no live SL change.
- Multi-lot / partial exits: pair-level forward SL is coarse (may over-attribute).
- Buys that opened before Stoch instrumentation often lack true entry Stoch (history join helps only post-history).
- Small n → wide Wilson intervals; do not overfit thresholds.

## Decision gates

- Live SL change: **False**
- Allocator change: **False**
- Shadow SL-risk log: **False**

## Honest assessment

Stoch is more sensitive than RSI (more extremes, more disagreements). Sensitivity can mean **earlier stress labeling** and **stronger trailing confirmation** without being a clean **direction/entry filter**. This report scores *entry-time SL prediction only*.
