#!/usr/bin/env python3
"""
Migration script for Phase 6 Dashboard SQL View refactor.
Creates fact tables and SQL VIEWs in data/phase6.db (or specified DB).

Usage:
  python scripts/phase6/migrate_dashboard_db.py
  python scripts/phase6/migrate_dashboard_db.py --db data/phase6.db

Idempotent. Aligns with RSI/Sentiment for shared tables (prices, rsi_values, sentiment_scores).

Per Handoff: handoffs/phase6/Handoff_Dashboard_SQL_Schema_and_Views.md
Plan: docs/PHASE6_DASHBOARD_SQL_VIEW_REFACTOR_PLAN.md
"""

import argparse
import sqlite3
import os
from pathlib import Path

DEFAULT_DB = "data/phase6.db"

DDL = """
-- Fact tables (raw data written by runner/refresh scripts)
CREATE TABLE IF NOT EXISTS account_balances (
  ts TEXT NOT NULL,
  currency TEXT NOT NULL,
  balance REAL NOT NULL,
  available REAL,
  hold REAL,
  source TEXT DEFAULT 'live',
  PRIMARY KEY (ts, currency)
);

CREATE TABLE IF NOT EXISTS holdings (
  ts TEXT NOT NULL,
  currency TEXT NOT NULL,
  amount REAL NOT NULL,
  available REAL,
  hold REAL,
  source TEXT DEFAULT 'live',
  PRIMARY KEY (ts, currency)
);

CREATE TABLE IF NOT EXISTS prices (
  ts TEXT NOT NULL,
  pair TEXT NOT NULL,
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
  source TEXT,
  confidence REAL,
  status TEXT,
  PRIMARY KEY (ts, pair)
);

-- Optional trades for alignment with TradeLedger
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  pair TEXT NOT NULL,
  side TEXT,
  amount REAL,
  price REAL,  -- entry or fill
  exit_price REAL,
  pnl REAL,
  pnl_pct REAL,
  status TEXT,
  source TEXT DEFAULT 'runner'
);

CREATE TABLE IF NOT EXISTS current_positions (
  ts TEXT NOT NULL,
  pair TEXT NOT NULL,
  amount REAL NOT NULL,
  entry_price REAL,
  current_price REAL,
  value_usd REAL,
  unrealized_pnl_pct REAL,
  side TEXT DEFAULT 'long',
  source TEXT DEFAULT 'live',
  PRIMARY KEY (ts, pair)
);

-- Metric tables for unblocked dashboard (recovery_attempts, sl_success_rate, replay_parity, brief_consumed)
CREATE TABLE IF NOT EXISTS recovery_metrics (
  ts TEXT NOT NULL,
  attempts INTEGER DEFAULT 0,
  successes INTEGER DEFAULT 0,
  rate REAL DEFAULT 0.0,
  cooldown_pairs TEXT,
  last_update TEXT,
  source TEXT DEFAULT 'runner',
  PRIMARY KEY (ts)
);

CREATE TABLE IF NOT EXISTS sl_metrics (
  ts TEXT NOT NULL,
  attach_attempts INTEGER DEFAULT 0,
  attach_success INTEGER DEFAULT 0,
  success_rate REAL DEFAULT 0.0,
  source TEXT DEFAULT 'runner',
  PRIMARY KEY (ts)
);

CREATE TABLE IF NOT EXISTS replay_parity (
  ts TEXT NOT NULL,
  match_rate REAL DEFAULT 0.0,
  actions_match BOOLEAN,
  brief_influence BOOLEAN,
  details_json TEXT,
  source TEXT DEFAULT 'runner',
  PRIMARY KEY (ts)
);

CREATE TABLE IF NOT EXISTS brief_metrics (
  ts TEXT NOT NULL,
  consumed BOOLEAN DEFAULT 0,
  summary TEXT,
  details_json TEXT,
  source TEXT DEFAULT 'runner',
  PRIMARY KEY (ts)
);

-- DASH-VIEWS-01 base tables for raw facts (proposals, rebalances, period snapshots)
-- Runner populates these with raw data only; views/aggregates computed in SQL
CREATE TABLE IF NOT EXISTS proposals (
  ts TEXT NOT NULL,
  pair TEXT NOT NULL,
  side TEXT,
  score REAL,
  source TEXT,
  details_json TEXT,
  PRIMARY KEY (ts, pair)
);

CREATE TABLE IF NOT EXISTS rebalances (
  ts TEXT NOT NULL,
  plan_json TEXT,
  executed_count INTEGER DEFAULT 0,
  source TEXT DEFAULT 'runner',
  PRIMARY KEY (ts)
);

CREATE TABLE IF NOT EXISTS period_snapshots (
  ts TEXT NOT NULL,
  period TEXT NOT NULL,
  pnl REAL,
  win_rate REAL,
  utilization REAL,
  active_positions INTEGER,
  total_usd REAL,
  source TEXT DEFAULT 'runner',
  PRIMARY KEY (ts, period)
);

-- Views for latest facts
CREATE VIEW IF NOT EXISTS v_latest_balances AS
SELECT * FROM account_balances ab
WHERE ts = (SELECT MAX(ts) FROM account_balances WHERE currency = ab.currency);

CREATE VIEW IF NOT EXISTS v_current_holdings AS
SELECT * FROM holdings h
WHERE ts = (SELECT MAX(ts) FROM holdings WHERE currency = h.currency);

CREATE VIEW IF NOT EXISTS v_latest_prices AS
SELECT * FROM prices p
WHERE ts = (SELECT MAX(ts) FROM prices WHERE pair = p.pair);

-- Latest metric views (for dashboard full operational metrics)
CREATE VIEW IF NOT EXISTS v_latest_recovery AS
SELECT * FROM recovery_metrics
WHERE ts = (SELECT MAX(ts) FROM recovery_metrics);

CREATE VIEW IF NOT EXISTS v_latest_sl AS
SELECT * FROM sl_metrics
WHERE ts = (SELECT MAX(ts) FROM sl_metrics);

CREATE VIEW IF NOT EXISTS v_latest_replay AS
SELECT * FROM replay_parity
WHERE ts = (SELECT MAX(ts) FROM replay_parity);

CREATE VIEW IF NOT EXISTS v_latest_brief AS
SELECT * FROM brief_metrics
WHERE ts = (SELECT MAX(ts) FROM brief_metrics);

-- Core enriched positions VIEW (logic in SQL: amount * price)
CREATE VIEW IF NOT EXISTS v_enriched_positions AS
SELECT 
  CASE WHEN h.currency LIKE '%-USD' THEN h.currency ELSE h.currency || '-USD' END AS pair,
  h.amount,
  COALESCE(p.price, 0.0) AS current_price,
  (h.amount * COALESCE(p.price, 0.0)) AS value_usd,
  COALESCE(cp.entry_price, 0.0) AS entry_price,
  CASE 
    WHEN COALESCE(cp.entry_price, 0) > 0 THEN ROUND( (COALESCE(p.price, 0) - cp.entry_price) / cp.entry_price , 4)
    ELSE 0.0 
  END AS unrealized_pnl_pct,
  'long' AS side
FROM v_current_holdings h
LEFT JOIN v_latest_prices p 
  ON (CASE WHEN h.currency LIKE '%-USD' THEN h.currency ELSE h.currency || '-USD' END) = p.pair
LEFT JOIN current_positions cp 
  ON (CASE WHEN h.currency LIKE '%-USD' THEN h.currency ELSE h.currency || '-USD' END) = cp.pair
  AND cp.ts = (SELECT MAX(ts) FROM current_positions WHERE pair = cp.pair)
WHERE h.amount > 0;

-- Dashboard snapshot VIEW (for serve layer)
-- Note: total_usd computed with subqueries to avoid alias reference issues in SQLite
CREATE VIEW IF NOT EXISTS v_phase6_dashboard AS
WITH latest AS (
  SELECT 
    (SELECT balance FROM v_latest_balances WHERE currency='USD') AS cash_usd,
    (SELECT balance FROM v_latest_balances WHERE currency='USDC') AS usdc,
    (SELECT SUM(value_usd) FROM v_enriched_positions) AS total_holdings_value,
    (SELECT COUNT(*) FROM v_enriched_positions) AS active_positions,
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
     ) FROM v_enriched_positions) AS positions_json
)
SELECT 
  cash_usd,
  usdc,
  total_holdings_value,
  COALESCE(cash_usd, 0) + COALESCE(usdc, 0) + COALESCE(total_holdings_value, 0) AS total_usd,
  active_positions,
  positions_json,
  (SELECT attempts FROM v_latest_recovery) AS recovery_attempts,
  (SELECT rate FROM v_latest_recovery) AS recovery_rate,
  (SELECT success_rate FROM v_latest_sl) AS sl_success_rate,
  (SELECT match_rate FROM v_latest_replay) AS replay_match_rate,
  (SELECT consumed FROM v_latest_brief) AS brief_consumed,
  datetime('now') AS last_updated
FROM latest;

-- DASH-VIEWS-02: Enhanced pre-calculated reporting metrics (period PnL, win_rate, utilization, sl_success_rate, proposal_acceptance, churn, rebalance_stats)
-- All computation in SQL; runner supplies raw facts only (see DASH-VIEWS-01).
-- v_phase6_dashboard already uses latest-per-currency via v_current_holdings / v_enriched_positions for clean snapshot.
CREATE VIEW IF NOT EXISTS v_dashboard_metrics AS
WITH base AS (
  SELECT 
    COALESCE((SELECT total_usd FROM v_phase6_dashboard), 0.0) AS total_usd,
    COALESCE((SELECT total_holdings_value FROM v_phase6_dashboard), 0.0) AS holdings_value,
    COALESCE((SELECT active_positions FROM v_phase6_dashboard), 0) AS active_positions,
    COALESCE((SELECT sl_success_rate FROM v_phase6_dashboard), 0.0) AS sl_success_rate,
    COALESCE((SELECT recovery_attempts FROM v_phase6_dashboard), 0) AS recovery_attempts,
    COALESCE((SELECT match_rate FROM v_latest_replay), 0.0) AS replay_match_rate,
    COALESCE((SELECT consumed FROM v_latest_brief), 0) AS brief_consumed
),
trade_agg AS (
  SELECT 
    COALESCE(SUM(COALESCE(pnl, 0)), 0.0) AS total_pnl,
    COALESCE(1.0 * SUM(CASE WHEN COALESCE(pnl,0) > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 0.0) AS win_rate,
    COUNT(*) AS trade_count
  FROM trades
),
rebal_agg AS (
  SELECT 
    COUNT(*) AS rebalance_count,
    COALESCE(SUM(COALESCE(executed_count, 0)), 0) AS total_executed
  FROM rebalances
),
prop_agg AS (
  SELECT 
    COUNT(*) AS proposal_count,
    COALESCE(SUM(COALESCE(accepted, 0)), 0) AS accepted_count
  FROM proposals
)
SELECT 
  -- Period PnL (stubs until period_snapshots or time-bucketed trades populated; can extend with period_snapshots join)
  0.0 AS today_pnl,
  0.0 AS h24_pnl,
  0.0 AS d7_pnl,
  0.0 AS d30_pnl,
  trade_agg.win_rate AS win_rate,
  CASE WHEN base.total_usd > 0 THEN ROUND(base.holdings_value / base.total_usd, 4) ELSE 0.0 END AS utilization,
  base.sl_success_rate AS sl_success_rate,
  CASE WHEN prop_agg.proposal_count > 0 THEN ROUND(1.0 * prop_agg.accepted_count / prop_agg.proposal_count, 4) ELSE 0.0 END AS proposal_acceptance,
  -- Fixed churn to use rebalance activity (lifetime trade_count / active was bogus ~60+); will be meaningful once rebalances persist in legacy path
  CASE WHEN base.active_positions > 0 THEN ROUND(1.0 * rebal_agg.rebalance_count / base.active_positions, 2) ELSE 0.0 END AS churn,
  rebal_agg.rebalance_count AS rebalance_count,
  json_object(
    'count', rebal_agg.rebalance_count,
    'executed', rebal_agg.total_executed,
    'recent', (SELECT json_group_array(json_object('ts', ts, 'executed', executed_count)) FROM (SELECT ts, executed_count FROM rebalances ORDER BY ts DESC LIMIT 5))
  ) AS rebalance_stats,
  base.recovery_attempts AS recovery_attempts,
  base.replay_match_rate AS replay_match_rate,
  base.brief_consumed AS brief_consumed,
  datetime('now') AS computed_at
FROM base, trade_agg, rebal_agg, prop_agg;

"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite DB")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    # Drop existing views to force recreate with full metrics (DASH-VIEWS-02)
    for v in ["v_phase6_dashboard", "v_dashboard_metrics", "v_latest_recovery", "v_latest_sl", "v_latest_replay", "v_latest_brief"]:
        conn.execute(f"DROP VIEW IF EXISTS {v}")
    conn.executescript(DDL)
    # Ensure accepted column for proposal_acceptance (P1) - tolerant for existing DB
    try:
        conn.execute("ALTER TABLE proposals ADD COLUMN accepted INTEGER DEFAULT 0")
    except Exception:
        pass  # column exists or other benign
    conn.commit()

    # Verify
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;").fetchall()
    views = conn.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name;").fetchall()
    conn.close()

    print(f"Migration complete for {db_path}")
    print("Tables:", [t[0] for t in tables])
    print("Views:", [v[0] for v in views])

if __name__ == "__main__":
    main()