# Jev select-few CF (measure-only)

**As of:** `2026-09-23T17:57:17.639326+00:00`
**Claim:** `N_INSUFFICIENT_no_edge_claim` (need n_closed≥20 for sample bar; still no live edge)

> Paper notional only. `would_order` always false. No knobs.

## Universe

- Source: `readiness_intersect_scoreboard` · parity_ok=`True`
- Selected: `['LINK-USD', 'ETH-USD']`
- Held included: `['LINK-USD']`

## Paper book

- Open seats: **0** · pairs `[]`
- Notional/seat: $25.0 · max_open=4
- Realized CF PnL: **$0.0** · n_closed=0
- Unrealized (approx longest mark): **$0.0**
- Opened this tick: `[]`

## Lab tick

- ok=2/2 · paper_buy_tags=0 · budget={'day': '2026-09-23', 'calls': 2}
- dry_run=False · model=`~typesafe/jev-latest`

```json
[
  {
    "pair": "LINK-USD",
    "ok": true,
    "paper_buy": false,
    "action": "hold",
    "should_trade": 0.31,
    "fakeout": 0.39,
    "lat_ms": 407
  },
  {
    "pair": "ETH-USD",
    "ok": true,
    "paper_buy": false,
    "action": "hold",
    "should_trade": 0.29,
    "fakeout": 0.34,
    "lat_ms": 235
  }
]
```

State: `data/state/jev_select_few_cf_latest.json` · Book: `data/state/jev_select_few_cf_book.json`
