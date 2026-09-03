# Polymarket influence backtest — ANALYST-20260627-024 (PREFLIGHT FAIL)

**Proposal:** ANALYST-20260627-024
**Since:** full log
**Outcome:** `sensor_degenerate`
**Recommendation:** `fix_sensor_or_data_pipeline` (no live promote)

## Plain English
Polymarket event yes_p stamps stuck at 0.5 (historical log). Overlay previously mis-parsed Gamma outcomePrices JSON strings — re-run after parse fix + live bias range check; do not score WR/ROI. Cannot measure WR/ROI lift vs bias until the meter produces a real range. Do not promote allocator influence from this study.

## Bias log
- Snapshots (window): 168 (all-log=168)
- Unique bias (3dp): 1
- Min/max/mean: 0.5 / 0.5 / 0.5
- Stdev: 0.0
- Window: 2026-06-27T22:24:03.979564+00:00 → 2026-09-02T18:25:05.865854+00:00

## Preflight
```json
{
  "ok": false,
  "code": "sensor_degenerate",
  "plain_english": "Polymarket event yes_p stamps stuck at 0.5 (historical log). Overlay previously mis-parsed Gamma outcomePrices JSON strings \u2014 re-run after parse fix + live bias range check; do not score WR/ROI.",
  "checks": [
    {
      "name": "min_n",
      "pass": true,
      "got": 477,
      "need": 10
    },
    {
      "name": "not_stuck_at_neutral",
      "pass": false,
      "neutral": 0.5
    }
  ],
  "metrics": {
    "feature": "Polymarket event yes_p stamps",
    "n": 477,
    "unique_3dp": 1,
    "min": 0.5,
    "max": 0.5,
    "mean": 0.5,
    "stdev": 0.0,
    "all_equal": true
  },
  "live_promote_allowed": false,
  "score_allowed": false,
  "as_of": "2026-09-02T22:00:29.068036Z",
  "schema": "sensor_preflight_v1"
}
```

## Next
1. Ensure intel/influence stamps post-fix leave 0.5 (parse + polarity sealed 2026-09-02).
2. Prefer bias at **entry** on decision_context when available.
3. Re-score with `--since` only; never promote from pre-fix stuck log.

JSON: `/home/brad/projects/crypto-trading-bot/data/state/analyst_polymarket_influence_backtest_latest.json`

