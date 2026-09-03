# Stoch → SL predictor — offline report

**Trial:** `ANALYST-STOCH-SL-PREDICTOR-20260803`  
**Generated:** 2026-09-03T16:00:24.907152+00:00  
**Window:** `2026-07-11T00:00:00+00:00` → `2026-09-03T16:00:24.323169+00:00`  
**Recommendation:** **no_utility_drop**  
**Plain English:** No material entry-time SL prediction utility.  

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

- Buys in window: **84**
- With entry Stoch: **59** | RSI: **70**
- Ind sources: `{'missing': 14, 'history_join': 15, 'indicators_at_trade': 55}`
- Base SL rate (entry-Stoch cohort): 7d **47.5%** | 14d **55.9%**

## Primary test — entry Stoch %K &lt; 30 vs ≥ 30 (7d SL)

- Rule: `stoch_k < 30.0 vs >=30.0`
- Low bucket: n=28 hits=13 rate=46.4% CI=[29.5%, 64.2%]
- High bucket: n=31 hits=15 rate=48.4% CI=[32.0%, 65.2%]
- Lift (low/high): **0.9595238095238096**

### Also

- Stoch&lt;20 @7d: low n=21 rate=52.4% | high n=38 rate=44.7% | lift=1.1708683473389356
- Stoch&lt;30 @3d: low n=28 rate=35.7% | high n=31 rate=38.7% | lift=0.9226190476190477
- Stoch&lt;30 @14d: low n=28 rate=53.6% | high n=31 rate=58.1% | lift=0.9226190476190476
- RSI&lt;35 @7d (control): low n=10 rate=50.0% | high n=60 rate=50.0% | lift=1.0

## Additive test (RSI 40–60 only)

`{
  "rsi_band": [
    40.0,
    60.0
  ],
  "stoch_thr": 30.0,
  "horizon": "hit_sl_7d",
  "n_mid_rsi": 32,
  "low_stoch": {
    "n": 13,
    "sl_hits": 6,
    "sl_rate": 0.46153846153846156,
    "wilson_lo": 0.23205754301488138,
    "wilson_hi": 0.7085656756816795
  },
  "high_stoch": {
    "n": 19,
    "sl_hits": 8,
    "sl_rate": 0.42105263157894735,
    "wilson_lo": 0.2314162039203038,
    "wilson_hi": 0.637244485348399
  },
  "lift": 1.0961538461538463,
  "note": "Additive test: Stoch split inside RSI-neutral band only"
}`

## Trailing vs leading

- Exit baseline: `{'n': 24, 'mean': 12.532916666666667, 'median': 0.0, 'pct_lt_thr': 0.875, 'threshold': 30.0, 'caveat': 'Exit Stoch is trailing — expected low after adverse move; not proof of entry utility.'}`
- Entry vs exit on SL hits: `{'sl_hits_with_entry_stoch': 33, 'entry_stoch_lt_thr': 15, 'entry_pct_lt_thr': 0.45454545454545453, 'sl_hits_with_exit_stoch': 24, 'exit_stoch_lt_thr': 21, 'exit_pct_lt_thr': 0.875, 'threshold': 30.0, 'interpretation': 'If exit_pct >> entry_pct, Stoch is mostly trailing the loss path. If entry_pct elevated vs non-SL baseline, possible leading signal.'}`

## Caveats

- Lift not material after entry-time framing
- Higher sensitivity ≠ reliable SL predictor ahead of the move.
- Keep Stoch on scorer narrative; do not gate entries or SL distance.
- Multi-lot / partial exits: pair-level forward SL is coarse (may over-attribute).
- Buys that opened before Stoch instrumentation often lack true entry Stoch (history join helps only post-history).
- Small n → wide Wilson intervals; do not overfit thresholds.

## Decision gates

- Live SL change: **False**
- Allocator change: **False**
- Shadow SL-risk log: **False**

## Honest assessment

Stoch is more sensitive than RSI (more extremes, more disagreements). Sensitivity can mean **earlier stress labeling** and **stronger trailing confirmation** without being a clean **direction/entry filter**. This report scores *entry-time SL prediction only*.
