# Regime Flat Knobs — DIG layered re-entry — 2026-07-30

**Trial:** `ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL`  
**Master:** `ANALYST-REGIME-FLAT-KNOBS-20260730`  
**Spec:** `docs/research/BULL_REENTRY_LAYERED_SPEC.md`  
**Generated:** 2026-07-30T22:02:22.708231+00:00  
**Live config writes:** False

## Plain English

Keep flat option B rebalance (not rotation). ADD scoped shadow experiment: layered bull re-entry (bear veto + breakout + RSI 50–70 @ $75 rebalance; 30d≥15% size-up $200 only). Do NOT live-edit regime_cash_policy. Reject breakout @$200 and 5d+RSI full bull flip.

- **Dig recommendation enum:** `propose_scoped_experiment`
- **Shadow layered?** **True**
- **Live promote?** **False**

### Flat primary (prior report)

```json
{
  "recommendation": {
    "enum": "continue_observe_only",
    "go_shadow": false,
    "confidence": "medium-high",
    "primary_hypothesis_supported": true,
    "grid_promote_candidate": null,
    "reasons": [
      "Primary hyp SUPPORTED: rebalance under B envelope beats rotation on DD/Sharpe on flat + live_overlap (Path B real OHLCV)",
      "Scorecard flat winner remains usdc_hold (true APY) \u2014 risk styles do not beat cash on flat window",
      "Nearby cap/freq grid does not materially beat live-B rebalance_7d cap75; cap differentiation often weak at low Path B exposure",
      "RSI/sentiment grid NOT testable in Path B \u2014 leave live B gates (RSI\u226455, sent\u22650.25) unchanged",
      "Live detector is `transition` (not flat) \u2014 flat B knobs are latent until flat returns; no live apply regardless",
      "No live regime_cash_policy / knob_map writes in this trial"
    ],
    "plain_english": "Keep flat option B as-is (rebalance-style small cap, not rotation). Evidence: on real flat and live-overlap OHLCV, rotation under the same $75 envelope takes much more drawdown for little/no extra return. Nearby Path B cap grid does not clearly beat live B. Do not promote bull rotation knobs into flat. RSI/sent not proven in harness \u2014 leave gates. Live is not in flat right now anyway.",
    "path_b_gaps": [
      "ARCH-4 Path B does not apply live RSI/sentiment/lockout REGIME-CASH entry filters",
      "cap0 usdc_hold_proxy has no USDC APY (~0); scorecard usdc_hold uses ~3.5% APY",
      "live rebalance clock != day stride; basket/allocator differs from live book",
      "do not promote from Path B alone \u2014 gates + Brad required"
    ],
    "north_star": "better returns AND less loss \u2014 prefer lower DD over idle-cash FOMO"
  },
  "go_shadow": null,
  "primary_hypothesis_supported": null,
  "plain_english": ""
}
```

## Spec gates

- **PASS** `full_sample_layered_vs_current` — lay ret=1.919 dd=-1.572 cur ret=0.362 dd=-2.14
- **PASS** `bear_dd_not_much_worse` — lay dd=-1.021 cur dd=-1.218
- **PASS** `live_overlap_not_disaster` — lay ret=1.128 dd=-1.258 cur ret=1.523 dd=-1.582
- **PASS** `reject_breakout_cap200_full_sample` — brk200 full ret=-3.483 dd=-5.345

## Window snapshot (ret% / dd% / time-in%)

### `full_sample`

| Arm | Ret% | MaxDD% | Time-in% | Mean cap$ |
|-----|------|--------|----------|-----------|
| current | 0.362 | -2.14 | 65.88 | 58.24 |
| layered_boost | 1.919 | -1.572 | 21.41 | 24.88 |
| layered_pure | 1.366 | -1.572 | 17.18 | 12.88 |
| layered_brk200 | -3.285 | -5.207 | 17.18 | 34.35 |
| brk75 | 1.304 | -1.183 | 26.82 | 20.12 |
| brk200 | -3.483 | -5.345 | 26.82 | 53.65 |
| only3015 | 4.523 | -1.218 | 7.06 | 14.12 |
| flat_always | 6.953 | -1.847 | 100.0 | 75.0 |

### `live_overlap`

| Arm | Ret% | MaxDD% | Time-in% | Mean cap$ |
|-----|------|--------|----------|-----------|
| current | 1.523 | -1.582 | 67.65 | 87.5 |
| layered_boost | 1.128 | -1.258 | 37.25 | 64.71 |
| layered_pure | 0.575 | -0.329 | 19.61 | 14.71 |
| layered_brk200 | -0.097 | -0.972 | 19.61 | 39.22 |
| brk75 | 1.232 | -0.429 | 39.22 | 29.41 |
| brk200 | 1.648 | -1.278 | 39.22 | 78.43 |
| only3015 | 1.347 | -1.258 | 29.41 | 58.82 |
| flat_always | 0.06 | -2.006 | 100.0 | 75.0 |

### `flat_chop`

| Arm | Ret% | MaxDD% | Time-in% | Mean cap$ |
|-----|------|--------|----------|-----------|
| current | -1.166 | -1.659 | 71.11 | 53.33 |
| layered_boost | 0.319 | -0.328 | 15.56 | 11.67 |
| layered_pure | 0.319 | -0.328 | 15.56 | 11.67 |
| layered_brk200 | -0.574 | -1.221 | 15.56 | 31.11 |
| brk75 | 0.003 | -0.607 | 18.89 | 14.17 |
| brk200 | -1.416 | -2.041 | 18.89 | 37.78 |
| only3015 | 0.857 | 0.0 | 0.0 | 0.0 |
| flat_always | 0.589 | -1.12 | 100.0 | 75.0 |

### `bear_stress`

| Arm | Ret% | MaxDD% | Time-in% | Mean cap$ |
|-----|------|--------|----------|-----------|
| current | -0.346 | -1.218 | 63.93 | 47.95 |
| layered_boost | -0.402 | -1.021 | 13.11 | 9.84 |
| layered_pure | -0.402 | -1.021 | 13.11 | 9.84 |
| layered_brk200 | -2.032 | -2.89 | 13.11 | 26.23 |
| brk75 | 0.135 | -0.631 | 24.59 | 18.44 |
| brk200 | -0.611 | -1.859 | 24.59 | 49.18 |
| only3015 | 0.577 | 0.0 | 0.0 | 0.0 |
| flat_always | -0.242 | -1.511 | 100.0 | 75.0 |

### `recent`

| Arm | Ret% | MaxDD% | Time-in% | Mean cap$ |
|-----|------|--------|----------|-----------|
| current | 0.519 | -1.6 | 70.0 | 73.33 |
| layered_boost | 1.251 | -1.257 | 31.11 | 44.17 |
| layered_pure | 0.699 | -0.329 | 21.11 | 15.83 |
| layered_brk200 | -1.023 | -1.333 | 21.11 | 42.22 |
| brk75 | 0.544 | -0.873 | 36.11 | 27.08 |
| brk200 | -1.448 | -3.253 | 36.11 | 72.22 |
| only3015 | 2.105 | -1.249 | 16.67 | 33.33 |
| flat_always | 6.098 | -1.866 | 100.0 | 75.0 |

### `bull_ex`

| Arm | Ret% | MaxDD% | Time-in% | Mean cap$ |
|-----|------|--------|----------|-----------|
| current | 0.504 | -1.078 | 53.26 | 39.95 |
| layered_boost | 1.369 | -0.309 | 19.57 | 14.67 |
| layered_pure | 1.369 | -0.309 | 19.57 | 14.67 |
| layered_brk200 | 2.187 | -0.88 | 19.57 | 39.13 |
| brk75 | 0.917 | -0.637 | 27.17 | 20.38 |
| brk200 | 0.976 | -1.806 | 27.17 | 54.35 |
| only3015 | 0.876 | 0.0 | 0.0 | 0.0 |
| flat_always | 0.041 | -1.301 | 100.0 | 75.0 |

## Signal base rates

- Breakout share: **24.41%** of bars
- Bull label (30d/15) share: **6.42%**
- Stress JSON: `data/state/analyst_breakout_reentry_stress_latest.json`

## Must / must not

- **Must:** re-entry size $75 rebalance; pair RSI/sent gates remain; param_audit clean before any shadow activate
- **Must not:** live regime_cash_policy edit; breakout @$200 default; 5d+RSI bull flip

## Decide

```bash
cd /home/brad/projects/crypto-trading-bot
python3 phase6/research/trial_cycle.py decide ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL propose_scoped_experiment \
  --note 'flat B rebalance keep; layered shadow per REGIME_FLAT_KNOBS_DIG_LAYERED_2026-07-30.md'
```

_module:_ `phase6/research/bull_reentry_layered.py`
