# GAP-06 Perf API Soak

**as_of:** 2026-08-18T17:28:43.024504+00:00  
**base:** `http://127.0.0.1:8502`  
**enum:** `ship`  
**ok (ship):** True  

## Gates (frozen)

| Gate | Pass | Detail |
|------|------|--------|
| Honesty (no silent wrong 0) | True | cold_viol=[] |
| Cold < 8.0s | True | t=6.7082s http=200 |
| Warm p95 < 1.0s | True | p95=0.1047s mean=0.1017s |
| Concurrent honesty+200 | True | n=8 max=0.9633s |
| History numeric period | True | |

## Samples

```json
{
  "cold": {
    "status": "ok",
    "cache": "miss",
    "source": "portfolio_snapshots_db + positions (period_snapshots_db_adjusted)",
    "today": -0.06,
    "d7": -0.36,
    "d14": -1.38,
    "d30": -1.95,
    "equity_status": "ok"
  },
  "warm_last": {
    "status": "ok",
    "cache": "hit",
    "source": "portfolio_snapshots_db + positions (period_snapshots_db_adjusted)",
    "today": -0.06,
    "d7": -0.36,
    "d14": -1.38,
    "d30": -1.95,
    "equity_status": "ok"
  }
}
```

Full JSON: `/home/brad/projects/crypto-trading-bot/data/state/perf_api_soak_latest.json`
