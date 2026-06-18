# Phase 6 Dashboard SQL View + DB Persistence Refactor Plan

**Date:** 2026-06-12
**Owner:** Scotty (crypto-orchestrator)
**Status:** Designed + Tasks/Handoffs created. Parallel track to RSI/Sentiment Refactor (per user request).
**Priority:** High (reduces logic duplication in runner/dashboard, makes data source of truth queryable, aligns with signal freshness work).

## Goal
Move the bulk of dashboard state computation (balances + enriched positions with value_usd, totals, etc.) out of Python in `phase6_runner.py:_write_dashboard_cache()` and `serve_dashboard.py` into a proper SQLite DB + SQL VIEWs. The dashboard (serve + HTML) becomes a thin surface layer over the views. Runner persists *facts* (holdings, prices, balances, RSI, sentiment snapshots). This supports the existing RSI/Sentiment reliability work by giving signals/dashboards a shared, queryable, fresh data layer.

This is explicitly queued alongside the remaining RSI/Sentiment Refactor tasks from `docs/RSI_SENTIMENT_RELIABILITY_PLAN.md`.

## Why Now (Tie to RSI/Sentiment)
- Current dashboard logic duplicates enrichment that RSI/Sentiment pipelines will also need (prices, holdings, computed values).
- RSI plan calls for canonical price_history + rsi_cache + decoupled refresh. Adding DB tables + views gives a single place for "latest facts + computed views".
- Removes Python math (amount * price, SUMs, normalization of LPM wrappers) from dashboard path — exactly as requested.
- Enables future queries, history, monitoring without re-parsing JSON.
- Existing `db/` SQLAlchemy models (Price, Trade, Signal, Pair) provide a foundation; we can extend or use lightweight sqlite3 for Phase 6 runtime (runner currently avoids heavy ORM).

## Designed Schema (SQLite, compatible with db/ models.py extension)

**DB Location:** `data/phase6.db` (new, or migrate into `phase6_monitor.db` / `db/` setup later). Use raw `sqlite3` for writes in runner (simple, no new deps). SQLAlchemy for any advanced queries or future migration.

### Base Fact Tables (written by runner / refresh scripts; "raw" data only)
```sql
CREATE TABLE IF NOT EXISTS account_balances (
  ts TEXT NOT NULL,
  currency TEXT NOT NULL,  -- USD, USDC
  balance REAL NOT NULL,
  available REAL,
  hold REAL,
  source TEXT DEFAULT 'live',
  PRIMARY KEY (ts, currency)
);

CREATE TABLE IF NOT EXISTS holdings (
  ts TEXT NOT NULL,
  currency TEXT NOT NULL,  -- ETH, XRP, etc. (no USD here)
  amount REAL NOT NULL,
  available REAL,
  hold REAL,
  source TEXT DEFAULT 'live',
  PRIMARY KEY (ts, currency)
);

CREATE TABLE IF NOT EXISTS prices (
  ts TEXT NOT NULL,
  pair TEXT NOT NULL,      -- ETH-USD, XRP-USD
  price REAL NOT NULL,
  source TEXT DEFAULT 'price_history',
  PRIMARY KEY (ts, pair)
);

CREATE TABLE IF NOT EXISTS rsi_values (
  ts TEXT NOT NULL,
  pair TEXT NOT NULL,
  value REAL NOT NULL,
  source TEXT DEFAULT 'refresh',
  PRIMARY KEY (ts, pair)
);

CREATE TABLE IF NOT EXISTS sentiment_scores (
  ts TEXT NOT NULL,
  pair TEXT NOT NULL,
  score REAL,
  posts INTEGER DEFAULT 0,
  source TEXT,  -- x, reddit, combined
  confidence REAL,
  status TEXT,  -- ok, insufficient_data, stale
  PRIMARY KEY (ts, pair)
);

-- Optional: reuse/extend for trades (aligns with TradeLedger + db/models Trade)
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  pair TEXT NOT NULL,
  side TEXT,  -- buy/sell
  amount REAL,
  price REAL,
  pnl REAL,
  status TEXT
);
```

### SQL Views (the "computed component" — logic lives here)
```sql
-- Latest facts (for consumers)
CREATE VIEW IF NOT EXISTS v_latest_balances AS
SELECT * FROM account_balances ab
WHERE ts = (SELECT MAX(ts) FROM account_balances WHERE currency=ab.currency);

CREATE VIEW IF NOT EXISTS v_current_holdings AS
SELECT * FROM holdings h
WHERE ts = (SELECT MAX(ts) FROM holdings WHERE currency=h.currency);

CREATE VIEW IF NOT EXISTS v_latest_prices AS
SELECT * FROM prices p
WHERE ts = (SELECT MAX(ts) FROM prices WHERE pair=p.pair);

-- Enriched positions (core logic moved to SQL: amount * price, value_usd)
CREATE VIEW IF NOT EXISTS v_enriched_positions AS
SELECT 
  h.currency || '-USD' AS pair,
  h.amount,
  p.price AS current_price,
  (h.amount * p.price) AS value_usd,
  0.0 AS entry_price,  -- TODO: join to trades or avg_entries table later
  0.0 AS unrealized_pnl_pct,
  'long' AS side
FROM v_current_holdings h
JOIN v_latest_prices p ON (h.currency || '-USD') = p.pair
WHERE h.amount > 0;

-- Full dashboard snapshot view (assembled shape close to current live_state.json)
-- Note: SQLite views are flat; serve layer does light assembly or we use JSON1 for nested.
CREATE VIEW IF NOT EXISTS v_phase6_dashboard AS
SELECT 
  (SELECT balance FROM v_latest_balances WHERE currency='USD') AS cash_usd,
  (SELECT balance FROM v_latest_balances WHERE currency='USDC') AS usdc,
  (SELECT SUM(value_usd) FROM v_enriched_positions) AS total_holdings_value,
  (SELECT cash_usd) + (SELECT COALESCE(usdc,0)) + (SELECT total_holdings_value) AS total_usd,
  (SELECT COUNT(*) FROM v_enriched_positions) AS active_positions,
  -- Positions as JSON array using JSON1 extension (available in modern SQLite)
  (SELECT json_group_array(
     json_object(
       'pair', pair,
       'amount', amount,
       'current_price', current_price,
       'value_usd', value_usd,
       'entry_price', entry_price,
       'unrealized_pnl_pct', unrealized_pnl_pct,
       'side', side
     )
   ) FROM v_enriched_positions) AS positions_json,
  (SELECT value FROM rsi_values ORDER BY ts DESC LIMIT 1) AS latest_rsi_example,  -- extend as needed
  datetime('now') AS last_updated
;
```

**Notes on Schema:**
- Timestamps as ISO TEXT for simplicity (sortable).
- No FKs initially (decoupled facts; easy to backfill).
- Extend `db/models.py` later for SQLAlchemy (add Phase6Holding, Phase6PriceSnapshot etc. inheriting from Base).
- For full state (bought_indicators, performance from TradeLedger, sl_tp_info), keep some Python assembly in serve or add supporting tables/views.
- Aligns with RSI plan: price_history + rsi can feed these tables from the refresh scripts.

## Work Breakdown (Tasks + Queue Placement)
This is added as a **parallel track** to the RSI/Sentiment Refactor in `docs/RSI_SENTIMENT_RELIABILITY_PLAN.md` (Phases 0-5). Dashboard DB layer will consume the canonical price/RSI/sentiment outputs from those pipelines.

**High-level Lanes (for Kanban / Delegation):**
1. Schema + Migration + Views (design already here).
2. Runner fact persistence (isolation test first, per user rule).
3. Serve layer refactor (query views, light assembly).
4. Isolation/E2E tests + verification (Code Isolation Testing mandatory).
5. Docs, MASTER update, ops integration, cutover (dual-write during transition).
6. Tie-in to RSI/Sentiment (store their outputs in DB tables; use views in reports/dashboards).

**Detailed Sub-Tasks (will be turned into Handoff Documents + Kanban cards):**
- DASH-SQL-001: Schema design (this doc) + initial CREATE scripts + Alembic stub or migration script.
- DASH-SQL-002: Runner: Add `persist_facts_to_db()` + call from _write_dashboard_cache and RSI refresh. Isolation test `test_isolation_dashboard_db_persist.py`.
- DASH-SQL-003: Update `serve_dashboard.py` endpoints to prefer DB views (fall back to JSON). Remove enrichment math.
- DASH-SQL-004: Code Isolation Tests + manual wrapper comparison (verify view produces same numbers as current patched live client + screenshot).
- DASH-SQL-005: Update phase6_dashboard.html/JS if shape changes (minimal expected). Add DB health to monitor.
- DASH-SQL-006: Integrate with RSI/Sentiment refresh scripts (write to rsi_values / sentiment_scores tables).
- DASH-SQL-007: Update MASTER, create handoffs, queue in DELEGATION_QUEUE, ops-engineer ticket.
- DASH-SQL-008: E2E: Run refresh + runner cycle → assert dashboard API returns real enriched data from views (no more bogus positions-USD).

**Kanban Process Followed:**
- Master list (this file + RSI plan) is primary durable record.
- Tight Handoff Documents created below (per template + user prefs: Objective, Scope, Success Criteria, Deliverables, Validation).
- Tasks tracked in session todo + will be fanned to kanban board / sub-agents (crypto-engineer profile preferred for impl).
- Code Isolation Testing + real data verification required before any "done".
- Parallel to RSI work: no blocking; shared price/rsi/sentiment tables benefit both.

## Risks & Mitigations
- Dual-write during transition (JSON + DB) → keep JSON for now; deprecate after 48h stable.
- Performance (frequent inserts) → batch or use WAL; views are read-only fast.
- Schema drift with RSI plan → coordinate table names (prices, rsi_values, sentiment_scores).
- Runner still writes some derived (bought_indicators from TradeLedger) → acceptable; core enrichment in SQL.

## Next (Immediate per "go ahead")
- This plan + Handoffs created.
- MASTER updated.
- First handoff (schema impl) ready for delegation.
- Proceed to implement per Kanban (isolation test before changes).

**References:**
- Current dashboard: phase6/core/phase6_runner.py (_write_dashboard_cache), serve_dashboard.py, phase6_dashboard.html
- RSI Plan: docs/RSI_SENTIMENT_RELIABILITY_PLAN.md (Phases 0-5, canonical caches, refresh scripts)
- Existing DB: db/models.py (Price, Trade, Signal), data/state/*.json, phase6_monitor.db (empty)
- Prior dashboard handoffs: handoffs/phase6/Handoff_Dashboard_Dataflow_Fix.md, Handoff_Dashboard_Data_Quality.md
- User prefs: MASTER as primary, tight handoffs, Code Isolation Tests, real data only.

---
**Status:** Design complete. Handoffs + MASTER update in progress. Ready for Kanban queuing + delegation alongside RSI/Sentiment. 
