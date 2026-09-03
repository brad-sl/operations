# Polymarket influence backtest — ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902 (PREFLIGHT FAIL)

**Proposal:** ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902
**Since:** 2026-09-02T22:00:00+00:00
**Outcome:** `sensor_thin`
**Recommendation:** `fix_sensor_or_data_pipeline` (no live promote)

## Why re-run / window
Re-run of 024: prior study used degenerate sensor (bias stuck 0.5 from Gamma outcomePrices JSON-string parse + polarity). Historical log not rewritten. This window is post-fix stamps only; sensor_ok required before scoreboard. No live promote.

## Plain English
Polymarket event yes_p stamps: only n=3 finite samples (need ≥10). Do not score edge — thin sensor. Cannot measure WR/ROI lift vs bias until the meter produces a real range. Do not promote allocator influence from this study.

## Bias log
- Snapshots (window): 1 (all-log=165)
- Unique bias (3dp): 1
- Min/max/mean: 0.359 / 0.359 / 0.359
- Stdev: 0.0
- Window: 2026-09-02T22:01:37.121410+00:00 → 2026-09-02T22:01:37.121410+00:00

## Preflight
```json
{
  "ok": false,
  "code": "sensor_thin",
  "plain_english": "Polymarket event yes_p stamps: only n=3 finite samples (need \u226510). Do not score edge \u2014 thin sensor.",
  "checks": [
    {
      "name": "min_n",
      "pass": false,
      "got": 3,
      "need": 10
    }
  ],
  "metrics": {
    "feature": "Polymarket event yes_p stamps",
    "n": 3,
    "unique_3dp": 3,
    "min": 0.01,
    "max": 0.54,
    "mean": 0.32666666666666666,
    "stdev": 0.2283759084394752,
    "all_equal": false
  },
  "live_promote_allowed": false,
  "score_allowed": false,
  "as_of": "2026-09-03T00:09:36.736727Z",
  "schema": "sensor_preflight_v1"
}
```

## Next
1. Ensure intel/influence stamps post-fix leave 0.5 (parse + polarity sealed 2026-09-02).
2. Prefer bias at **entry** on decision_context when available.
3. Re-score with `--since` only; never promote from pre-fix stuck log.

JSON: `/home/brad/projects/crypto-trading-bot/data/state/analyst_polymarket_influence_rerun_20260902_latest.json`

