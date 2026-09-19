# Polymarket influence backtest — ANALYST-POLYMARKET-INFLUENCE-EXT-20260919

**Proposal:** ANALYST-POLYMARKET-INFLUENCE-EXT-20260919
**Since:** 2026-09-02T22:00:00+00:00
**Outcome:** `inconclusive_sparse_N`
**Recommendation:** `continue_observe_only` (no live promote)

## Why re-run / window
Extend after parent RERUN-20260902 CLOSED extend_trial: sensor OK but crypto N incomplete. Edge SSOT = ex-stable joined sells. Relevance: crypto_joined>=15 OR (risk_on_n>=5 AND neutral_n>=5). Hard stop ~21d. No live promote.

## Plain English
Sensor OK. Joined crypto 10/20 (all_joined=20, stables_excluded=10) to bias≤24h. insufficient bucket coverage for lift claim. relevance_cleared=False. Live promote still blocked without Brad GO + promotion gates.

## Bias log
- Snapshots (window): 52 (all-log=216)
- Unique bias (3dp): 40
- Min/max/mean: 0.316 / 0.652 / 0.36715384615384616
- Stdev: 0.06003857241403057

## Relevance progress (extend gates)
- crypto_joined: 10 / 15
- risk_on_n: 0 / 5 · neutral_n: 2 / 5
- cleared: **False**
- stables_excluded: 10

## Buckets (crypto only — edge SSOT)
```json
{
  "risk_off": {
    "n": 8,
    "wr": 0.0,
    "mean_pnl": -0.496108625,
    "sum_pnl": -3.968869
  },
  "neutral": {
    "n": 2,
    "wr": 1.0,
    "mean_pnl": 2.2740050000000016,
    "sum_pnl": 4.548010000000003
  }
}
```

## Buckets (all joined including stables — noise reference)
```json
{
  "risk_off": {
    "n": 16,
    "wr": 0.0,
    "mean_pnl": -0.25204987500000003,
    "sum_pnl": -4.0327980000000005
  },
  "neutral": {
    "n": 4,
    "wr": 1.0,
    "mean_pnl": 1.147918250000001,
    "sum_pnl": 4.591673000000003
  }
}
```

## Preflight
```json
{
  "ok": true,
  "code": "sensor_ok",
  "plain_english": "All sensor preflight checks passed.",
  "checks": [
    {
      "name": "min_n",
      "pass": true,
      "got": 156,
      "need": 10
    },
    {
      "name": "not_stuck_at_neutral",
      "pass": true,
      "neutral": 0.5
    },
    {
      "name": "has_range",
      "pass": true,
      "unique_3dp": 32,
      "stdev": 0.3708262969436377,
      "need_unique": 3,
      "need_stdev": 0.01
    },
    {
      "name": "min_n",
      "pass": true,
      "got": 52,
      "need": 10
    },
    {
      "name": "not_stuck_at_neutral",
      "pass": true,
      "neutral": 0.5
    },
    {
      "name": "has_range",
      "pass": true,
      "unique_3dp": 40,
      "stdev": 0.06003857241403057,
      "need_unique": 3,
      "need_stdev": 0.01
    }
  ],
  "metrics": {
    "feature": "Polymarket event yes_p stamps",
    "n": 156,
    "unique_3dp": 32,
    "min": 0.0,
    "max": 1.0,
    "mean": 0.4601923076923077,
    "stdev": 0.3708262969436377,
    "all_equal": false,
    "sensor_ok_feature": "Polymarket risk_on_bias",
    "sensor_ok_n": 52,
    "sensor_ok_unique_3dp": 40,
    "sensor_ok_min": 0.316,
    "sensor_ok_max": 0.652,
    "sensor_ok_mean": 0.36715384615384616,
    "sensor_ok_stdev": 0.06003857241403057,
    "sensor_ok_all_equal": false,
    "n_events": 20,
    "n_joined": 20,
    "join_rate": 1.0
  },
  "live_promote_allowed": false,
  "score_allowed": true,
  "as_of": "2026-09-19T18:08:59.477714Z",
  "schema": "sensor_preflight_v1"
}
```

JSON: `/home/brad/projects/crypto-trading-bot/data/state/analyst_polymarket_influence_ext_20260919_latest.json`

