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
  price REAL,
  pnl REAL,
  status TEXT
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

-- Core enriched positions VIEW (logic in SQL: amount * price)
CREATE VIEW IF NOT EXISTS v_enriched_positions AS
SELECT 
  h.currency || '-USD' AS pair,
  h.amount,
  p.price AS current_price,
  (h.amount * p.price) AS value_usd,
  0.0 AS entry_price,
  0.0 AS unrealized_pnl_pct,
  'long' AS side
FROM v_current_holdings h
JOIN v_latest_prices p ON (h.currency || '-USD') = p.pair
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
  datetime('now') AS last_updated
FROM latest;

"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite DB")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(DDL)
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