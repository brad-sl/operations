# Handoff: Complete Dashboard Dataflow & State Aggregation (Phase 6)

**Task ID**: DASH-001  
**Priority**: High  
**Owner**: Sub-agent / Crypto Engineer  
**Status**: Ready for handoff  
**Date**: 2026-06-02

---

## Goal

Create a single, reliable source of truth for the Phase 6 live dashboard by defining exactly how multiple data sources must be aggregated into `phase6_live_state.json` (written by the runner) and consumed by `serve_dashboard.py`.

The dashboard must display **real, live trading data** (balances, positions with values, activity, trades, sentiment, performance) or honest empty states — never hardcoded or dummy values.

---

## Current Reality (Verified)

- Runner writes `data/state/phase6_live_state.json` every cycle
- Current cache is minimal: balances + `bought_indicators` / `sold_indicators` + `active_positions` + totals + timestamp
- Dashboard on 8503 reads the cache for `/api/balances` and `/api/positions`
- Other sections (`/api/trades`, `/api/performance`, `/api/sentiment`) still pull from separate sources or fall back to hardcoded states
- Full enriched position data (size, entry, current value, PnL) is **not yet** in the cache

---

## Complete Data Sources

| Source | Location | Owner | Frequency | Purpose |
|--------|----------|-------|-----------|---------|
| `phase6_live_state.json` | `data/state/` | Runner (`_write_dashboard_cache`) | Every cycle | Balances, enriched positions, activity indicators, totals |
| `trades/phase6_trades.jsonl` | `trades/` | TradeLedger | On every trade | Historical trades, closed PnL, win ratio |
| Sentiment cache | `data/state/*_sentiment_cache.json` | Sentiment gatherer | 2× per hour | Pair sentiment scores |
| Exchange (Coinbase) | Live API | `exchange_client.py` | On demand | Current prices, full holdings (via runner) |

---

## Required Cache Schema (Target)

The runner must eventually write a rich payload:

```json
{
  "balances": [...],
  "positions": [
    {
      "pair": "DOGE-USD",
      "amount": 1234.56,
      "entry_price": 0.184,
      "current_price": 0.187,
      "value_usd": 230.85,
      "unrealized_pnl_pct": 1.63,
      "side": "long"
    }
  ],
  "active_positions": 3,
  "bought_indicators": ["DOGE-USD", "XRP-USD"],
  "sold_indicators": [],
  "total_usd": 1247.33,
  "total_holdings_value": 997.74,
  "cash_usd": 249.59,
  "last_updated": "2026-06-02T23:05:12Z",
  "recent_activity": [
    {"type": "buy", "pair": "SOL-USD", "time": "..."}
  ]
}
```

---

## Data Mapping (UI → Source)

| UI Section              | Endpoint                  | Primary Source                  | Status     | Notes |
|-------------------------|---------------------------|----------------------------------|------------|-------|
| Total Portfolio Value   | `/api/balances`           | `phase6_live_state.json`        | ✅ Working | Needs `total_usd` |
| Active Positions table  | `/api/positions`          | `phase6_live_state.json`        | Partial    | Needs enriched position objects |
| Activity Indicators     | (in-page)                 | `bought_indicators` + `sold_indicators` | ✅ Working | New panel added |
| Recent Trades           | `/api/trades`             | TradeLedger                     | Needs work | Currently limited |
| Performance KPIs        | `/api/performance`        | TradeLedger + cache             | Needs work | Win ratio, periods |
| Sentiment               | `/api/sentiment`          | Sentiment cache files           | Needs work | Pull from existing files |
| Recent Rebalances       | (in-page)                 | Runner event log                | Needs work | Not yet populated |

---

## Must Do

1. Runner is the single source of truth for live state — expand `_write_dashboard_cache()` to include enriched positions and totals.
2. Dashboard must read **only** from cache for balances/positions (already implemented).
3. All other endpoints (`trades`, `performance`, `sentiment`) must return real data or honest empty states.
4. Test every endpoint with `curl` before and after changes.
5. When data is missing, show clear “No data yet” messaging.
6. Update `docs/MASTER_TASK_TRACKING.md` on completion.

---

## Must Not Do

1. Do not hardcode trading numbers, PnL, or trade history.
2. Do not call the exchange directly from `serve_dashboard.py`.
3. Do not show misleading “open position” messages when `active_positions === 0`.
4. Do not invent performance metrics.

---

## Success Criteria

- Dashboard shows real balances + enriched positions from the cache.
- All sections either display live data or clear “no data” states.
- No dummy/hardcoded trading values remain.
- Full dataflow is documented and reproducible.

---

## Deliverables

- Updated `phase6_runner.py` with richer cache writer
- Updated `serve_dashboard.py` with complete endpoints
- Verified `phase6_live_state.json` schema
- Completed entry in `docs/MASTER_TASK_TRACKING.md`

---

**Handoff ready. Begin by expanding the cache writer in the runner.**