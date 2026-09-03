# CR — ANALYST-20260902-003

**Title:** OPT pack refresh + re-entry stress (shadow)  
**Processed:** 2026-09-02T19:36:21.902789Z  
**Status:** processed_shadow  
**Live promote:** blocked (Brad GO required; not requested)

## Result (shadow / offline — no live writes)

**Call: HOLD park in transition. Cross-window prefers low-exposure rebalance over OPT 14d rotation winner for deploy talk.**

### Pipeline run
1. OHLCV extend → data_end **2026-09-02** (9/9 pairs)
2. Pack dates synced
3. `run_reentry_knob_stress.py` refreshed

### Cross-window scoreboard (top)
[
  {
    "id": "defensive_rebalance_14d",
    "best_count": 1,
    "positive_return_windows": 4,
    "windows": 6,
    "avg_return_pct": 1.44,
    "avg_sharpe": 3.235,
    "min_return_pct": -0.12,
    "max_return_pct": 3.72
  },
  {
    "id": "flat_option_b_rebalance_7d",
    "best_count": 1,
    "positive_return_windows": 4,
    "windows": 6,
    "avg_return_pct": 1.32,
    "avg_sharpe": 0.837,
    "min_return_pct": -0.31,
    "max_return_pct": 3.72
  },
  {
    "id": "transition_micro_rebalance_7d",
    "best_count": 0,
    "positive_return_windows": 4,
    "windows": 6,
    "avg_return_pct": 1.32,
    "avg_sharpe": 0.837,
    "min_return_pct": -0.31,
    "max_return_pct": 3.72
  }
]

### Winner stress (bear_window_rotation_14d vs baseline)
- Bull example: winner beats Sharpe (but small ret delta)
- Bear stress: winner does **not** beat baseline Sharpe
- Flat: both negative; winner worse ret (−5.16% vs −3.48%)
- Live-overlap style: treat as scenario context only

### Operator ladder (unchanged)
0. transition/PARK — no OPT winner  
1. parked USDC > weak rotation  
2. flat → option B rebalance small cap  
3. bull → shadow defensive_rotation_21d (not 14d OPT winner)  

### Artifacts
- `data/state/analyst_reentry_knob_stress_latest.json` (2026-09-02T19:32:56.240310+00:00)
- `data/state/analyst_winner_regime_stress_latest.json` (2026-09-02T19:32:56.240310+00:00)
- `data/state/ohlcv_extension_manifest.json`

### Live promote
**No.** Shadow context only.

